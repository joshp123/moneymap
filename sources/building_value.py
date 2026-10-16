"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

National net building stocks, excluding land and civil engineering, in 2024 USD.
OECD Table 9B dwellings (N111N) plus non-residential buildings (N1121N) are
scaled to 2024 with their latest matched-year buildings/GDP ratio. Countries
without both assets use the constant ratio selected by reporter leave-one-out.
"""

from collections import Counter, defaultdict
import csv
import json
import math

import numpy as np
from openpyxl import load_workbook

from layers.grid import ROOT
from sources import land_value

RAW = ROOT / "data/raw/building-value"
BUILDING_ASSETS = {"N111N", "N1121N"}


def official_building_ratios():
    local_gdp = land_value.world_bank_series("gdp_lcu.json")
    assets = defaultdict(lambda: defaultdict(dict))
    with (RAW / "oecd-buildings.csv").open(newline="") as source:
        for row in csv.DictReader(source):
            if row["SECTOR"] != "S1" or row["INSTR_ASSET"] not in BUILDING_ASSETS:
                continue
            if row["OBS_VALUE"] and float(row["OBS_VALUE"]) > 0:
                assets[row["REF_AREA"]][int(row["TIME_PERIOD"])][row["INSTR_ASSET"]] = (
                    float(row["OBS_VALUE"]) * 10 ** int(row["UNIT_MULT"]))
    ratios = {}
    for country, by_year in assets.items():
        years = [year for year, values in by_year.items()
                 if values.keys() == BUILDING_ASSETS and year in local_gdp.get(country, {})]
        if years:
            year = max(years)
            ratios[country] = {"year": year,
                               "building_to_gdp": sum(by_year[year].values()) / local_gdp[country][year]}
    return ratios


def model_scores():
    """Compare four small log-ratio models on the same held-out reporters."""
    income = defaultdict(dict)
    for row in json.loads((RAW / "gdp-per-head-ppp.json").read_text())[1]:
        if row["value"]:
            income[row["countryiso3code"]][int(row["date"])] = row["value"]
    urban = land_value.world_bank_series("wb_EN.URB.MCTY.TL.ZS.json")
    reporters = official_building_ratios()
    countries = sorted(reporters)
    target = np.array([math.log(reporters[c]["building_to_gdp"]) for c in countries])
    log_income = [math.log(land_value.latest(income[c], 2024)[1]) for c in countries]
    city_share = [(land_value.latest(urban[c], 2024)[1] or 0.0) / 100 for c in countries]
    columns = {
        "constant": [np.ones(len(countries))],
        "big_city_share": [np.ones(len(countries)), city_share],
        "gdp_per_head": [np.ones(len(countries)), log_income],
        "gdp_per_head_and_big_city_share": [np.ones(len(countries)), log_income, city_share],
    }
    results = {}
    for name, values in columns.items():
        design = np.array(values).T
        errors = []
        for index in range(len(countries)):
            training = np.arange(len(countries)) != index
            coefficients = np.linalg.lstsq(design[training], target[training], rcond=None)[0]
            errors.append(float(design[index] @ coefficients - target[index]))
        rmse = float(np.sqrt(np.mean(np.square(errors))))
        results[name] = {"coefficients": np.linalg.lstsq(design, target, rcond=None)[0].tolist(),
                         "leave_one_out_log_rmse": rmse,
                         "leave_one_out_error_factor": math.exp(rmse),
                         "leave_one_out_median_absolute_log_ratio": float(np.median(np.abs(errors))),
                         "leave_one_out_log_errors": dict(zip(countries, errors))}
    return results


def taiwan_gdp():
    workbook = load_workbook(RAW / "dgbas-gdp-2024.xlsx", read_only=True, data_only=True)
    for row in workbook.active.iter_rows(values_only=True):
        if row[1] == 2024:
            total = row[4] * 1e6
            workbook.close()
            return total
    workbook.close()
    raise ValueError("DGBAS national accounts table has no 2024 GDP")


def national_totals(country_codes):
    """Use the land build's market GDP inputs without changing its targets."""
    land_records = land_value.national_totals(country_codes)
    reporters = official_building_ratios()
    scores = model_scores()
    model_ratio = math.exp(scores["constant"]["coefficients"][0])
    records = {}
    for country, land_record in land_records.items():
        gdp = land_record["gdp_usd"]
        gdp_year, gdp_source = land_record["gdp_year"], land_record["gdp_source"]
        if country == "TWN":
            gdp, gdp_year, gdp_source = taiwan_gdp(), 2024, "DGBAS National Accounts Yearbook, GDP at current US dollars"
        official = reporters.get(country)
        ratio = official["building_to_gdp"] if official else model_ratio
        records[country] = {
            "total_usd2024": gdp * ratio,
            "source": "oecd_all_sectors" if official else "constant_building_gdp_model",
            "source_year": official["year"] if official else None,
            "building_to_gdp": ratio,
            "gdp_usd": gdp,
            "gdp_year": gdp_year,
            "gdp_source": gdp_source,
            "gdp_conversion_reference": land_record["gdp_conversion_reference"],
        }
    return records


def national_summary(records):
    source_totals = defaultdict(float)
    for record in records.values():
        source_totals[record["source"]] += record["total_usd2024"]
    return {"country_count": len(records),
            "source_counts": dict(Counter(record["source"] for record in records.values())),
            "source_totals_usd2024": dict(source_totals),
            "world_total_usd2024": sum(source_totals.values()),
            "asset_definition": "Net dwellings N111N plus net buildings other than dwellings N1121N; no N1122 civil engineering",
            "selected_model": "constant",
            "model_scores": model_scores(),
            "reporter_years": {country: values["year"] for country, values in official_building_ratios().items()},
            "prior_year_gdp_countries": {country: record["gdp_year"] for country, record in records.items()
                                         if record["gdp_year"] < 2024},
            "gdp_conversion_proxy_countries": [country for country, record in records.items()
                                                if record["gdp_conversion_reference"]]}


write_country_table = land_value.write_country_table

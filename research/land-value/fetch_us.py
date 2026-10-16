"""Fetch and extract US land-value test data at state and county level.

Written by AI on 2026.10.16 by model claude fable 5.1 subagent.

Run from the repo root:
    devenv shell -- python -I research/land-value/fetch_us.py

Downloads land in data/experiments/land-value/raw/us (untrusted data, never
executed). Extracted CSVs land in data/experiments/land-value/us.

Sources
  1. FHFA Working Paper 19-01 land prices, version 4.0 (June 2024), one xlsx
     with county, ZIP, tract, CBSA, state and national tabs.
  2. Census ACS 2023 5-year tables B25082 (aggregate value of owner-occupied
     housing units) and B25001 (housing units), from the table-based summary
     file on the Census FTP. The data API now refuses keyless calls.
  3. Larson (2015), BEA WP2015-3, Table 3: land area and value by state, 2009.
     Wentland et al. (2023), BEA WP2023-4, Table 6: land value by census
     division and land type, 2006-2015 (the paper has no state table).
  4. USDA NASS Land Values 2026 Summary (land0726) and Farms and Land in
     Farms 2025 Summary (fnlo0226), CSV bundles from the USDA ESMIS library.
  5. Census 2024 county cartographic boundaries already in data/raw.
"""

import csv
import io
import re
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import fiona
import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data/experiments/land-value/raw/us"
OUT_DIR = REPO_ROOT / "data/experiments/land-value/us"
COUNTY_BOUNDARIES_ZIP = REPO_ROOT / "data/raw/research-gdp/county_500k.zip"

USER_AGENT = "Mozilla/5.0 (Macintosh) moneymap-research"

CENSUS_SUMMARY_FILE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF"
USDA_ESMIS = "https://usda.library.cornell.edu/sites/default/release-files"

DOWNLOADS = {
    "fhfa_land_prices_2024_june.xlsx": "https://www.fhfa.gov/document/land-prices_2024_20_june.xlsx",
    "fhfa_faqs_land_2020.pdf": "https://www.fhfa.gov/document/faqs-land-10-28-20.pdf",
    "acsdt5y2023-b25082.dat": f"{CENSUS_SUMMARY_FILE}/data/5YRData/acsdt5y2023-b25082.dat",
    "acsdt5y2023-b25001.dat": f"{CENSUS_SUMMARY_FILE}/data/5YRData/acsdt5y2023-b25001.dat",
    "Geos20235YR.txt": f"{CENSUS_SUMMARY_FILE}/documentation/Geos20235YR.txt",
    "bea_wp2015-3_larson_land_value.pdf": "https://www.bea.gov/sites/default/files/papers/WP2015-3.pdf",
    "bea_wp2023-4_wentland_land_value.pdf": "https://www.bea.gov/sites/default/files/papers/BEA-WP2023-4.pdf",
    "usda_nass_land_values_2026_summary_land0726.pdf": "https://release.nass.usda.gov/reports/land0726.pdf",
    "usda_nass_land_values_2026_land0726.zip": f"{USDA_ESMIS}/795999/land0726.zip",
    "usda_nass_land_values_2026_land0726.txt": f"{USDA_ESMIS}/795999/land0726.txt",
    "usda_nass_land_values_2025_summary_land0825.pdf": "https://release.nass.usda.gov/reports/land0825.pdf",
    "usda_nass_land_values_2025_land0825.zip": f"{USDA_ESMIS}/pn89d6567/2n49w148w/2227pp20f/land0825.zip",
    "usda_nass_farms_and_land_in_farms_2026_fnlo0226.pdf": "https://release.nass.usda.gov/reports/fnlo0226.pdf",
    "usda_nass_farms_and_land_in_farms_2026_fnlo0226.zip": f"{USDA_ESMIS}/795776/fnlo0226.zip",
    "usda_nass_farms_and_land_in_farms_2026_fnlo0226.txt": f"{USDA_ESMIS}/795776/fnlo0226.txt",
}

ZIP_EXTRACT_DIRS = {
    "usda_nass_land_values_2026_land0726.zip": "usda_land0726",
    "usda_nass_land_values_2025_land0825.zip": "usda_land0825",
    "usda_nass_farms_and_land_in_farms_2026_fnlo0226.zip": "usda_fnlo0226",
}

# PDF -> text conversions. The converter CLIs live in the AI nix profile, not
# in devenv, so the converted text is kept next to the PDF and only
# regenerated when missing. markit lays out Wentland's Table 6 cleanly;
# markitdown lays out Larson's Table 3 cleanly.
AI_TOOLS_BIN = Path.home() / ".local/state/nix/profiles/ai/bin"
PDF_TEXT_CONVERSIONS = {
    "bea_wp2015-3_larson_land_value.md.txt": ("markitdown", "bea_wp2015-3_larson_land_value.pdf"),
    "bea_wp2023-4_wentland_land_value.markit.md.txt": ("markit", "bea_wp2023-4_wentland_land_value.pdf"),
    "fhfa_faqs_land_2020.md.txt": ("markitdown", "fhfa_faqs_land_2020.pdf"),
}


def download_missing_files():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in DOWNLOADS.items():
        target = RAW_DIR / filename
        if target.exists() and target.stat().st_size > 0:
            continue
        print(f"downloading {filename}")
        subprocess.run(
            ["curl", "-sSfL", "-A", USER_AGENT, "-o", str(target), url],
            check=True,
        )
    for zip_name, extract_dir_name in ZIP_EXTRACT_DIRS.items():
        extract_dir = RAW_DIR / extract_dir_name
        if extract_dir.exists():
            continue
        extract_dir.mkdir()
        with zipfile.ZipFile(RAW_DIR / zip_name) as archive:
            archive.extractall(extract_dir, filter="data")


def convert_missing_pdf_text():
    for text_name, (tool, pdf_name) in PDF_TEXT_CONVERSIONS.items():
        target = RAW_DIR / text_name
        if target.exists() and target.stat().st_size > 0:
            continue
        tool_path = shutil.which(tool) or str(AI_TOOLS_BIN / tool)
        if not Path(tool_path).exists():
            sys.exit(f"{text_name} is missing and {tool} was not found; install it or restore the text file")
        pdf_path = RAW_DIR / pdf_name
        print(f"converting {pdf_name} with {tool}")
        if tool == "markit":
            subprocess.run([tool_path, "-q", "--no-images", str(pdf_path), "-o", str(target)], check=True)
        else:
            with open(target, "w") as handle:
                subprocess.run([tool_path, str(pdf_path)], check=True, stdout=handle)


def write_csv(path, fieldnames, rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} rows)")


# --- 1. FHFA land prices -------------------------------------------------

FHFA_COLUMN_NAMES = {
    "State": "state",
    "State Name": "state",
    "State Abbreviation": "state_abbreviation",
    "County": "county",
    "FIPS": "geoid",
    "State FIPS": "geoid",
    "Census Tract": "geoid",
    "Year": "year",
    "Land Value\n(1/4 Acre Lot, Standardized)": "land_value_quarter_acre_lot_standardized_usd",
    "Land Value\n(Per Acre, As-Is)": "land_value_per_acre_as_is_usd",
    "Land Share of Property Value": "land_share_of_property_value",
    "Lot Size": "lot_size_sqft",
    "Interior Square Feet": "interior_square_feet",
    "Property Value (Standardized)": "property_value_standardized_usd",
    "Property Value (As-is)": "property_value_as_is_usd",
}

FHFA_SHEETS = {
    # sheet title (stripped) -> (output file stem, GEOID width)
    "Cross-Section Counties": ("fhfa_county_cross_section_2012_2022", 5),
    "Panel Counties": ("fhfa_county_panel_2012_2022", 5),
    "Cross-Section Census Tracts": ("fhfa_tract_cross_section_2012_2022", 11),
    "Panel Census Tracts": ("fhfa_tract_panel_2012_2022", 11),
    "Cross-Section States": ("fhfa_state_cross_section_2012_2022", 2),
    "Panel States": ("fhfa_state_panel_2012_2022", 2),
}


def extract_fhfa():
    workbook = openpyxl.load_workbook(RAW_DIR / "fhfa_land_prices_2024_june.xlsx", read_only=True)
    sheets_by_title = {sheet.title.strip(): sheet for sheet in workbook.worksheets}
    county_cross_section_geoids = set()
    for title, (stem, geoid_width) in FHFA_SHEETS.items():
        rows_iter = sheets_by_title[title].iter_rows(values_only=True)
        next(rows_iter)  # "All Single-Family Parcels" banner
        header = next(rows_iter)
        fieldnames = [FHFA_COLUMN_NAMES[name] for name in header if name is not None]
        rows = []
        for raw_row in rows_iter:
            values = raw_row[: len(fieldnames)]
            if all(value is None for value in values):
                continue
            row = dict(zip(fieldnames, values))
            row["geoid"] = str(row["geoid"]).zfill(geoid_width)
            rows.append(row)
        write_csv(OUT_DIR / f"{stem}.csv", fieldnames, rows)
        if title == "Cross-Section Counties":
            county_cross_section_geoids = {row["geoid"] for row in rows if row["land_share_of_property_value"] is not None}
    return county_cross_section_geoids


# --- 2. Census ACS 2023 5-year county housing values ---------------------

ACS_NULL_CODES = {"", "-666666666", "-999999999", "-888888888", "-222222222", "-333333333", "-555555555", "*", "N"}


def read_acs_table(filename, columns):
    values_by_geoid = {}
    with open(RAW_DIR / filename, newline="") as handle:
        for record in csv.DictReader(handle, delimiter="|"):
            if not record["GEO_ID"].startswith("0500000US"):
                continue
            values_by_geoid[record["GEO_ID"][-5:]] = [
                None if record[column] in ACS_NULL_CODES else int(record[column]) for column in columns
            ]
    return values_by_geoid


def extract_acs():
    names_by_geoid = {}
    with open(RAW_DIR / "Geos20235YR.txt", encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle, delimiter="|"):
            if record["SUMLEVEL"] == "050":
                names_by_geoid[record["GEO_ID"][-5:]] = record["NAME"]
    aggregate_values = read_acs_table("acsdt5y2023-b25082.dat", ["B25082_E001", "B25082_M001"])
    housing_units = read_acs_table("acsdt5y2023-b25001.dat", ["B25001_E001", "B25001_M001"])
    rows = []
    for geoid in sorted(aggregate_values):
        aggregate_value, aggregate_moe = aggregate_values[geoid]
        units, units_moe = housing_units.get(geoid, (None, None))
        rows.append({
            "geoid": geoid,
            "name": names_by_geoid.get(geoid, ""),
            "aggregate_value_owner_occupied_housing_usd": aggregate_value,
            "aggregate_value_owner_occupied_housing_moe_usd": aggregate_moe,
            "housing_units": units,
            "housing_units_moe": units_moe,
        })
    fieldnames = list(rows[0])
    write_csv(OUT_DIR / "acs_2023_5yr_county_housing_value.csv", fieldnames, rows)
    national_total = sum(row["aggregate_value_owner_occupied_housing_usd"] or 0 for row in rows)
    print(f"  ACS county aggregate owner-occupied value, all counties incl. PR: ${national_total / 1e12:.2f} trn")
    return {row["geoid"] for row in rows if row["aggregate_value_owner_occupied_housing_usd"] is not None}


# --- 3a. Larson 2015 (BEA WP2015-3) Table 3 -----------------------------

LARSON_FIELDS = [
    "state", "year", "land_area_thousand_acres", "land_value_usd_billions",
    "federal_share_of_area", "federal_share_of_value",
    "developed_share_of_area", "developed_share_of_value",
    "agricultural_share_of_area", "agricultural_share_of_value",
]


def parse_number(token):
    token = token.replace(",", "").replace("$", "").strip()
    if token in {"", "*", "\\*", "(D)", "(X)", "(NA)"}:
        return None
    return float(token) if "." in token else int(token)


def parse_percent(token):
    return round(float(token.rstrip("%")) / 100, 4)


def extract_larson():
    text = (RAW_DIR / "bea_wp2015-3_larson_land_value.md.txt").read_text()
    start = text.index("Table 3: Land Quantities and Values in the Lower 48 States, 2009")
    end = text.index("Lower 48 Total", start)
    rows = []
    for line in text[start:end].splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|") if cell.strip()]
        if len(cells) != 9 or not cells[1].replace(",", "").isdigit():
            continue
        state = cells[0].replace("Dist. Of Columbia", "District of Columbia")
        rows.append(dict(zip(LARSON_FIELDS, [
            state, 2009, parse_number(cells[1]), parse_number(cells[2]),
            *[parse_percent(cell) for cell in cells[3:9]],
        ])))
    write_csv(OUT_DIR / "larson_2015_state_land_value_2009.csv", LARSON_FIELDS, rows)
    total_line = text[end:end + 200].splitlines()[0]
    reported_total_billions = parse_number(total_line.split()[4])
    summed_billions = sum(row["land_value_usd_billions"] for row in rows)
    print(f"  Larson 2009: {len(rows)} states+DC, sum of states ${summed_billions:,} bn, "
          f"paper's lower-48 total ${reported_total_billions:,} bn")


# --- 3b. Wentland et al. 2023 (BEA WP2023-4) Table 6 --------------------

WENTLAND_LAND_TYPES = ["Dense Urban", "Urban", "Suburban", "Rural", "Commercial", "Industrial", "Agricultural"]
WENTLAND_YEARS = list(range(2006, 2016))
WENTLAND_FIELDS = ["census_division", "land_type", "nlud_2010_thousand_acres", "year", "land_value_usd_billions"]


def extract_wentland():
    text = (RAW_DIR / "bea_wp2023-4_wentland_land_value.markit.md.txt").read_text()
    start = text.index("Table 6. Land Value Totals by Division")
    end = text.index("U.S. National Totals", start)
    data_lines = []
    for line in text[start:end].splitlines():
        line = line.replace("|", " ").strip()
        tokens = line.split()
        if len(tokens) < 12 or tokens[0] in {"NLUD", "Note:", "###"} or set(tokens[0]) == {"-"}:
            continue
        data_lines.append(tokens)
    if len(data_lines) % len(WENTLAND_LAND_TYPES) != 0:
        sys.exit(f"Wentland Table 6 parse found {len(data_lines)} rows, expected a multiple of 7")
    rows = []
    for block_start in range(0, len(data_lines), len(WENTLAND_LAND_TYPES)):
        block = data_lines[block_start:block_start + len(WENTLAND_LAND_TYPES)]
        rural_tokens = block[WENTLAND_LAND_TYPES.index("Rural")]
        division = " ".join(rural_tokens[:-12]).replace(" Rural", "")
        for land_type, tokens in zip(WENTLAND_LAND_TYPES, block):
            label = " ".join(tokens[:-11])
            if not label.endswith(land_type):
                sys.exit(f"Wentland Table 6 parse: expected {land_type!r}, got {label!r}")
            acres = parse_number(tokens[-11])
            for year, token in zip(WENTLAND_YEARS, tokens[-10:]):
                rows.append({
                    "census_division": division, "land_type": land_type,
                    "nlud_2010_thousand_acres": acres, "year": year,
                    "land_value_usd_billions": parse_number(token),
                })
    write_csv(OUT_DIR / "wentland_2023_division_land_value_2006_2015.csv", WENTLAND_FIELDS, rows)
    totals_line = text[end:end + 200].splitlines()[0].split()
    summed_2015 = sum(r["land_value_usd_billions"] or 0 for r in rows if r["year"] == 2015)
    print(f"  Wentland 2015 national total (paper): ${parse_number(totals_line[-1]):,} bn; "
          f"sum of division rows 2015: ${summed_2015:,} bn. Two Suburban 2015 cells are suppressed in the paper "
          f"and the paper's own total matches the sum without them.")


# --- 4. USDA NASS farmland values and land in farms ----------------------

USDA_FIELDS = [
    "state", "year", "farm_real_estate_value_per_acre_usd", "cropland_value_per_acre_usd",
    "pasture_value_per_acre_usd", "land_in_farms_acres", "land_in_farms_year",
    "usda_value_of_farmland_and_buildings_musd", "per_acre_values_exclude_reservation_land",
]


def read_nass_state_table(paths, state_rows_are_indented):
    """Return ({state: {year: value}}, footnoted_states) from NASS report CSV pages.

    NASS CSV rows look like: page,"d","  Alabama",v1,v2,... The 'h' row that
    names the first column carries the year headings. Region rows are not
    indented; state rows are indented by two spaces (land values tables) or
    flush left (farms table). Footnote markers such as ' 1/' are dropped from
    the name and the state is reported in footnoted_states.
    """
    values_by_state = defaultdict(dict)
    footnoted_states = set()
    for path in paths:
        years = None
        with open(path, newline="", encoding="latin-1") as handle:
            for record in csv.reader(handle):
                kind, label = record[1], record[2]
                if kind == "h" and label in {"Region and State", "State"}:
                    years = [int(cell) for cell in record[3:] if cell.isdigit()]
                if kind != "d" or not label.strip() or label.startswith("United States"):
                    continue
                if state_rows_are_indented != label.startswith("  "):
                    continue
                state, footnote_count = re.subn(r"\s+\d+/$", "", label.strip())
                if footnote_count:
                    footnoted_states.add(state)
                for year, cell in zip(years, record[3:]):
                    values_by_state[state][year] = parse_number(cell)
    return values_by_state, footnoted_states


def extract_usda():
    land_values_dir = RAW_DIR / "usda_land0726"
    # Footnote 1/ on the per-acre tables: "Excludes American Indian Reservation land" (AZ, NV, NM, UT).
    # Land in farms and USDA's own total value tables include that land, so per-acre x acres overstates
    # those four states. USDA's total value table is the authoritative state total.
    farm_real_estate, reservation_excluded_states = read_nass_state_table(
        [land_values_dir / "land_p08_t001.csv", land_values_dir / "land_p09_t010.csv"], True)
    cropland, _ = read_nass_state_table([land_values_dir / "land_p10_t002.csv", land_values_dir / "land_p11_t011.csv"], True)
    pasture, _ = read_nass_state_table([land_values_dir / "land_p14_t005.csv", land_values_dir / "land_p15_t012.csv"], True)
    total_value, _ = read_nass_state_table([land_values_dir / "land_p16_t009.csv", land_values_dir / "land_p17_t013.csv"], True)
    farms_table = RAW_DIR / "usda_fnlo0226/fnlo_p06_t003.csv"
    # fnlo table 3 has paired columns (farms 2024, farms 2025, land 2024, land 2025, size 2024, size 2025);
    # the header years repeat, so read the land-in-farms pair by position instead.
    land_in_farms = {}
    with open(farms_table, newline="", encoding="latin-1") as handle:
        for record in csv.reader(handle):
            if record[1] == "d" and record[2].strip() and not record[2].startswith("United States"):
                land_in_farms[record[2].strip()] = {2024: parse_number(record[5]) * 1000, 2025: parse_number(record[6]) * 1000}
    rows = []
    for state in sorted(farm_real_estate):
        for year in (2024, 2025, 2026):
            acres_year = min(year, 2025)
            rows.append({
                "state": state, "year": year,
                "farm_real_estate_value_per_acre_usd": farm_real_estate[state].get(year),
                "cropland_value_per_acre_usd": cropland[state].get(year),
                "pasture_value_per_acre_usd": pasture[state].get(year),
                "land_in_farms_acres": land_in_farms[state][acres_year],
                "land_in_farms_year": acres_year,
                "usda_value_of_farmland_and_buildings_musd": total_value[state].get(year),
                "per_acre_values_exclude_reservation_land": state in reservation_excluded_states,
            })
    write_csv(OUT_DIR / "usda_farmland_values_by_state.csv", USDA_FIELDS, rows)
    for year in (2025, 2026):
        year_rows = [r for r in rows if r["year"] == year]
        summed = sum(r["farm_real_estate_value_per_acre_usd"] * r["land_in_farms_acres"] for r in year_rows)
        summed_excluding_flagged = sum(r["farm_real_estate_value_per_acre_usd"] * r["land_in_farms_acres"]
                                       for r in year_rows if not r["per_acre_values_exclude_reservation_land"])
        usda_total = sum(r["usda_value_of_farmland_and_buildings_musd"] or 0 for r in year_rows)
        usda_total_excluding_flagged = sum(r["usda_value_of_farmland_and_buildings_musd"] or 0
                                           for r in year_rows if not r["per_acre_values_exclude_reservation_land"])
        print(f"  USDA {year}: per-acre x acres summed over 48 states = ${summed / 1e12:.3f} trn "
              f"(${summed_excluding_flagged / 1e12:.3f} trn without {sorted(reservation_excluded_states)})"
              + (f"; USDA's own state totals = ${usda_total / 1e6:.3f} trn "
                 f"(${usda_total_excluding_flagged / 1e6:.3f} trn without those states)" if usda_total else ""))


# --- 5. County boundaries -------------------------------------------------

def check_county_boundaries():
    with fiona.open(f"zip://{COUNTY_BOUNDARIES_ZIP}") as source:
        fields = list(source.schema["properties"])
        print(f"  county_500k.zip opens with fiona: {len(source)} features, CRS {source.crs}, id field GEOID (5-digit state+county), "
              f"fields {fields}")
        return {feature["properties"]["GEOID"] for feature in source}


def main():
    download_missing_files()
    convert_missing_pdf_text()
    print("FHFA")
    fhfa_counties = extract_fhfa()
    print("ACS")
    acs_counties = extract_acs()
    print("Larson 2015")
    extract_larson()
    print("Wentland 2023")
    extract_wentland()
    print("USDA")
    extract_usda()
    print("County boundaries")
    boundary_counties = check_county_boundaries()
    both = fhfa_counties & acs_counties
    print(f"Counties with FHFA cross-section land share: {len(fhfa_counties)}; with ACS aggregate value: {len(acs_counties)}; "
          f"both: {len(both)}; both and in boundary file: {len(both & boundary_counties)}")


if __name__ == "__main__":
    main()

# Written by AI on 2026.10.16 by model gpt-6.1-sol.
"""Official spatial GDP/GVA controls, in each source's nominal currency.

Only within-country shares are used. ``load_controls`` returns the controls and
their spatial country sums, excluding extra-regio values without a location.
``load_published_totals`` retains the published totals for comparison.
"""

from collections import defaultdict
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import urllib.parse
import urllib.request

import fiona
import numpy as np
from openpyxl import load_workbook
from rasterio.warp import transform
from shapely import get_coordinates, set_coordinates
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


BEA_SOURCE = "https://apps.bea.gov/regional/zip/CAGDP1.zip"
BEA_MAPPING_SOURCE = "https://www.bea.gov/system/files/methodologies/BEA-County-Personal-Income-Concepts-and-Methods.pdf"
ONS_SOURCE = "https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates"
ONS_LA_SOURCE = "https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductlocalauthorities"
ONS_REGIONS_SOURCE = "https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductallnutslevelregions"
ONS_REGIONS_DOWNLOAD = "https://www.ons.gov.uk/file?uri=%2Feconomy%2Fgrossdomesticproductgdp%2Fdatasets%2Fregionalgrossdomesticproductallnutslevelregions%2F1998to2024%2Fregionalgrossdomesticproductgdpbyallinternationalterritoriallevelitlregions.xlsx"
CBS_SOURCE = "https://opendata.cbs.nl/ODataApi/OData/85924NED"
EUROSTAT_SOURCE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10r_3gdp?unit=MIO_EUR&time=2023"
SCOTLAND_BOUNDARIES = "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip"
NI_BOUNDARIES = "https://www.nisra.gov.uk/files/nisra/publications/SOA2011_Esri_Shapefile_0.zip"

# BEA method appendix, pp. 92-93. All remaining BEA codes use Census GEOID.
US_COMBINED_COUNTIES = {
    "15901": ("15005", "15009"),
    "51901": ("51003", "51540"),
    "51903": ("51005", "51580"),
    "51907": ("51015", "51790", "51820"),
    "51911": ("51031", "51680"),
    "51913": ("51035", "51640"),
    "51918": ("51053", "51570", "51730"),
    "51919": ("51059", "51600", "51610"),
    "51921": ("51069", "51840"),
    "51923": ("51081", "51595"),
    "51929": ("51089", "51690"),
    "51931": ("51095", "51830"),
    "51933": ("51121", "51750"),
    "51939": ("51143", "51590"),
    "51941": ("51149", "51670"),
    "51942": ("51153", "51683", "51685"),
    "51944": ("51161", "51775"),
    "51945": ("51163", "51530", "51678"),
    "51947": ("51165", "51660"),
    "51949": ("51175", "51620"),
    "51951": ("51177", "51630"),
    "51953": ("51191", "51520"),
    "51955": ("51195", "51720"),
    "51958": ("51199", "51735"),
}
EU_COUNTRIES = dict(zip(
    "AT BE BG HR CY CZ DK EE FI FR DE EL HU IE IT LV LT LU MT PL PT RO SK SI ES SE AL ME MK RS TR".split(),
    "AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT POL PRT ROU SVK SVN ESP SWE ALB MNE MKD SRB TUR".split(),
))
FRENCH_OVERSEAS = {"FRY10": "GLP", "FRY20": "MTQ", "FRY30": "GUF", "FRY40": "REU", "FRY50": "MYT"}


@dataclass(frozen=True)
class Control:
    country: str
    code: str
    name: str
    geometry: dict
    value: float
    source: str
    parent_code: str = ""


def _download_if_missing(path, url):
    if not path.exists():
        with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)


def _read_boundaries(path, code_property):
    source = "zip://" + str(path.resolve()) if path.suffix == ".zip" else str(path)
    boundaries = {}
    with fiona.open(source) as features:
        for feature in features:
            geometry = shape(feature["geometry"])
            coordinates = get_coordinates(geometry)
            longitude, latitude = transform(features.crs, "EPSG:4326", coordinates[:, 0], coordinates[:, 1])
            boundaries[feature["properties"][code_property]] = mapping(set_coordinates(geometry, np.column_stack([longitude, latitude])))
    return boundaries


def _union(geometries):
    return mapping(unary_union([shape(geometry) for geometry in geometries]))


def _bea_values(directory):
    values = {}
    with (directory / "cagdp1/CAGDP1__ALL_AREAS_2001_2024.csv").open(encoding="latin-1", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("LineCode") != "3":
                continue
            try:
                value = float(row["2024"]) * 1000
            except ValueError:
                continue  # Retired Alaska and Connecticut codes have no 2024 value.
            values[row["GeoFIPS"].strip().strip('"')] = (row["GeoName"].rstrip("*"), value)
    return values


def load_us_controls(directory):
    directory = Path(directory)
    boundaries = _read_boundaries(directory / "county/cb_2024_us_county_500k.shp", "GEOID")
    controls = []
    used_counties = set()
    for code, (name, value) in sorted(_bea_values(directory).items()):
        if len(code) != 5 or code.endswith("000") or code.startswith("9"):
            continue
        counties = US_COMBINED_COUNTIES.get(code, (code,))
        missing = set(counties) - boundaries.keys()
        if missing:
            raise ValueError(f"BEA {code} has no Census boundary: {sorted(missing)}")
        geometry = boundaries[code] if len(counties) == 1 else _union(boundaries[county] for county in counties)
        controls.append(Control("USA", code, name, geometry, value, BEA_SOURCE, code[:2]))
        used_counties.update(counties)
    expected = {code for code in boundaries if code[:2] not in {"60", "66", "69", "72", "78"}}
    if used_counties != expected:
        raise ValueError(f"Census counties without BEA control: {sorted(expected - used_counties)}")
    return controls


def uk_small_area_rows(directory):
    """Return all four countries from the same ONS 2023 publication."""
    workbook = load_workbook(Path(directory) / "ons_small_area_gva_2023.xlsx", read_only=True, data_only=True)
    result = []
    for table_number, expected_count in [(1, 32844), (2, 1909), (3, 6976), (4, 890)]:
        rows = workbook[f"Table {table_number}"].iter_rows(values_only=True)
        next(rows)
        header = next(rows)
        year_column = header.index("2023")
        table_rows = [row for row in rows if row[0]]
        if len(table_rows) != expected_count:
            raise ValueError(f"ONS Table {table_number}: expected {expected_count} areas, got {len(table_rows)}")
        for row in table_rows:
            value = float(row[year_column]) * 1_000_000
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid ONS 2023 GVA: {row[0]} {value}")
            result.append({"code": row[0], "name": row[1], "lad": row[2], "lad_name": row[3], "value": value})
    workbook.close()
    return result


def load_uk_controls(directory):
    directory = Path(directory)
    boundaries = {}
    for path in sorted((directory / "lsoa").glob("p*.geojson")):
        for feature in json.loads(path.read_text())["features"]:
            boundaries[feature["properties"]["LSOA11CD"]] = feature["geometry"]
    for filename, url, key in [("scotland_dz2011.zip", SCOTLAND_BOUNDARIES, "DataZone"), ("ni_soa2011.zip", NI_BOUNDARIES, "SOA_CODE")]:
        path = directory / filename
        _download_if_missing(path, url)
        boundaries.update(_read_boundaries(path, key))
    rows = uk_small_area_rows(directory)
    missing = {row["code"] for row in rows} - boundaries.keys()
    if missing:
        raise ValueError(f"ONS small areas without boundary: {sorted(missing)}")
    return [Control("GBR", row["code"], row["name"], boundaries[row["code"]], row["value"], ONS_SOURCE, row["lad"]) for row in rows]


def _cbs_values(directory):
    path = Path(directory) / "cbs_gdp2023.json"
    query = urllib.parse.urlencode({"$filter": "Perioden eq '2023JJ00'"})
    _download_if_missing(path, CBS_SOURCE + "/TypedDataSet?" + query)
    dataset = json.loads(path.read_text())
    if "odata.nextLink" in dataset:
        raise ValueError("CBS 2023 response is incomplete")
    return {row["RegioS"].strip(): float(row["BbpMarktprijzen_1"]) * 1_000_000 for row in dataset["value"]}


def load_nl_controls(directory):
    directory = Path(directory)
    values = _cbs_values(directory)
    features = json.loads((directory / "coropplus_2024.geojson").read_text())["features"]
    controls = []
    for feature in features:
        properties = feature["properties"]
        code = properties["statcode"]
        source_code = code if code in values else "CR" + code[2:4]
        controls.append(Control("NLD", code, properties["statnaam"], feature["geometry"], values[source_code], CBS_SOURCE, "CR" + code[2:4]))
    if len(controls) != 52:
        raise ValueError(f"Expected 52 COROP-plus controls, got {len(controls)}")
    return controls


def _eurostat_values(directory):
    dataset = json.loads((Path(directory) / "nuts3_2023.json").read_text())
    if dataset["id"] != ["freq", "unit", "geo", "time"] or dataset["size"][0:2] != [1, 1] or dataset["size"][-1] != 1:
        raise ValueError("Eurostat response must contain annual MIO_EUR for 2023 only")
    if set(dataset["dimension"]["time"]["category"]["index"]) != {"2023"}:
        raise ValueError("Eurostat response must contain 2023 only")
    indexes = dataset["dimension"]["geo"]["category"]["index"]
    return {code: float(dataset["value"][str(index)]) * 1_000_000 for code, index in indexes.items() if str(index) in dataset["value"]}


def load_eu_controls(directory):
    directory = Path(directory)
    values = _eurostat_values(directory)
    boundaries_path = directory / "nuts3_2024_01m.geojson"
    _download_if_missing(boundaries_path, "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2024_4326_LEVL_3.geojson")
    features = json.loads(boundaries_path.read_text())["features"]
    controls = []
    for feature in features:
        properties = feature["properties"]
        country_code, code = properties["CNTR_CODE"], properties["NUTS_ID"]
        if country_code not in EU_COUNTRIES:
            continue
        if code not in values:
            raise ValueError(f"NUTS 2024 area has no 2023 GDP: {code}")
        country = FRENCH_OVERSEAS.get(code, EU_COUNTRIES[country_code])
        controls.append(Control(country, code, properties["NUTS_NAME"], feature["geometry"], values[code], EUROSTAT_SOURCE, code[:4]))
    return controls


def load_controls(directory):
    controls = load_us_controls(directory) + load_uk_controls(directory) + load_nl_controls(directory) + load_eu_controls(directory)
    country_totals = defaultdict(float)
    for control in controls:
        country_totals[control.country] += control.value
    return controls, dict(country_totals)


def load_published_totals(directory):
    """National totals; includes extra-regio GDP and French overseas departments."""
    totals = {EU_COUNTRIES[code]: value for code, value in _eurostat_values(directory).items() if code in EU_COUNTRIES}
    totals["USA"] = _bea_values(Path(directory))["00000"][1]
    totals["NLD"] = _cbs_values(directory)["NL01"]
    # ONS small-area publication provides spatial building blocks, not UK total.
    totals["GBR"] = math.fsum(row["value"] for row in uk_small_area_rows(directory))
    return totals


def _uk_gdp2024_total(directory):
    # Some 2024 local authorities are suppressed. Use the unaffected UK total.
    path = Path(directory) / "ons_regions_gdp_2024.xlsx"
    _download_if_missing(path, ONS_REGIONS_DOWNLOAD)
    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = workbook["Table 5"].iter_rows(values_only=True)
    next(rows)
    year_column = next(rows).index("2024")
    total = next(float(row[year_column]) * 1_000_000 for row in rows if row[0] == "UK" and row[1] == "UK")
    workbook.close()
    return total


def load_official_comparisons(directory, controls=None):
    """Named unit figures with the denominator from the same table and year."""
    directory = Path(directory)
    if controls is None:
        controls, _ = load_controls(directory)
    spatial_totals = defaultdict(float)
    lookup = {}
    for control in controls:
        spatial_totals[control.country] += control.value
        lookup[control.code] = control
    result = {}

    def add(name, control, year, unit, measure="GDP", country_total=None):
        result[name] = {"country": control.country, "code": control.code, "name": control.name,
                        "geometry": control.geometry, "value": control.value,
                        "country_total": spatial_totals[control.country] if country_total is None else country_total,
                        "year": year, "unit": unit, "measure": measure, "source": control.source}

    add("Manhattan", lookup["36061"], 2024, "current USD")
    for name, prefix in [("Groot-Amsterdam", "CP23"), ("Groot-Rijnmond", "CP29")]:
        children = [control for control in controls if control.country == "NLD" and control.code.startswith(prefix)]
        add(name, Control("NLD", prefix, name, _union(control.geometry for control in children), math.fsum(control.value for control in children), CBS_SOURCE), 2023, "current EUR")
    for name, code in [("Amsterdam municipality", "CP2311"), ("Haarlemmermeer en omgeving", "CP2323")]:
        add(name, lookup[code], 2023, "current EUR")
    workbook = load_workbook(directory / "ons_la_gdp_2024.xlsx", read_only=True, data_only=True)
    rows = workbook["Table 5"].iter_rows(values_only=True)
    next(rows)
    year_column = next(rows).index("2024")
    la_values = {row[1]: float(row[year_column]) * 1_000_000 for row in rows if len(row) > year_column and isinstance(row[1], str) and row[1].startswith(("E", "W", "S", "N")) and isinstance(row[year_column], (int, float))}
    workbook.close()
    uk_gdp2024_total = _uk_gdp2024_total(directory)
    for name, code in [("City of London", "E09000001"), ("Westminster", "E09000033")]:
        children = [control for control in controls if control.country == "GBR" and control.parent_code == code]
        control = Control("GBR", code, name, _union(child.geometry for child in children), math.fsum(child.value for child in children), ONS_SOURCE)
        add(name + " 2023 GVA", control, 2023, "current GBP", "GVA")
        key = name + " 2024 GDP"
        add(key, Control("GBR", code, name, control.geometry, la_values[code], ONS_LA_SOURCE), 2024, "current GBP", country_total=uk_gdp2024_total)
        result[key]["country_total_source"] = ONS_REGIONS_SOURCE
    return result

"""Parse official land-value tables for South Korea, British Columbia and Denmark into tidy CSVs.

Written by AI on 2026.10.16 by model claude fable 5.1 subagent.

Inputs are the files already downloaded with curl into
data/experiments/land-value/raw/{korea,bc,denmark}/ (see README.txt in each folder).
Outputs are written next to the inputs as tidy_*.csv. The script also checks how well
the region names in each value table join to the downloaded boundary GeoJSON files
and prints national totals and the largest region's share.

Run from the repo root:
    devenv shell -- python -I research/land-value/fetch_misc.py
"""

import csv
import json
import re
import sys
from pathlib import Path

import openpyxl
from shapely.geometry import shape
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data" / "experiments" / "land-value" / "raw"
KOREA_DIR = RAW_ROOT / "korea"
BC_DIR = RAW_ROOT / "bc"
DENMARK_DIR = RAW_ROOT / "denmark"


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} rows)")


def normalise_name(text):
    text = re.sub(r"\[.*?\]", "", text)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def strip_korean_suffix(normalised_name):
    return re.sub(r"(si|gun|gu)$", "", normalised_name)


def report_total_and_largest(label, rows, name_key, value_key):
    total = sum(row[value_key] for row in rows)
    largest = max(rows, key=lambda row: row[value_key])
    share = largest[value_key] / total if total else float("nan")
    print(f"{label}: total {total:,.0f}; largest {largest[name_key]} = {largest[value_key]:,.0f} ({share:.1%})")
    return total


# ---------------------------------------------------------------------------
# South Korea
# ---------------------------------------------------------------------------

# KOSIS 시도 names -> English names as used by geoBoundaries KOR ADM1 (shapeName).
KOREA_SIDO_ENGLISH = {
    "전국": "Korea (national total)",
    "서울특별시": "Seoul",
    "부산광역시": "Busan",
    "대구광역시": "Daegu",
    "인천광역시": "Incheon",
    "광주광역시": "Gwangju",
    "대전광역시": "Daejeon",
    "울산광역시": "Ulsan",
    "세종특별자치시": "Sejong",
    "경기도": "Gyeonggi",
    "강원특별자치도": "Gangwon",
    "강원도": "Gangwon",
    "충청북도": "North Chungcheong",
    "충청남도": "South Chungcheong",
    "전북특별자치도": "North Jeolla",
    "전라북도": "North Jeolla",
    "전라남도": "South Jeolla",
    "경상북도": "North Gyeongsang",
    "경상남도": "South Gyeongsang",
    "제주특별자치도": "Jeju",
}

HANGUL_INITIALS = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
HANGUL_VOWELS = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
# Final consonants: (romanisation before a consonant or at the end, romanisation when carried
# over to the next syllable's vowel, phonetic class used for assimilation).
HANGUL_FINALS = [
    None,
    ("k", "g", "k"), ("k", "kk", "k"), ("k", "ks", "k"), ("n", "n", "n"), ("n", "nj", "n"), ("n", "nh", "n"),
    ("t", "d", "t"), ("l", "r", "l"), ("k", "lg", "k"), ("m", "lm", "m"), ("l", "lb", "l"), ("l", "ls", "l"),
    ("l", "lt", "l"), ("p", "lp", "p"), ("l", "lh", "l"), ("m", "m", "m"), ("p", "b", "p"), ("p", "ps", "p"),
    ("t", "s", "t"), ("t", "ss", "t"), ("ng", "ng", "ng"), ("t", "j", "t"), ("t", "ch", "t"), ("k", "k", "k"),
    ("t", "t", "t"), ("p", "p", "p"), ("t", "h", "t"),
]
# Assimilation of a final consonant class followed by an initial consonant (Revised Romanization
# transcription rules, the cases that occur in Korean place names).
HANGUL_ASSIMILATION = {
    ("k", "n"): ("ng", "n"), ("k", "m"): ("ng", "m"), ("k", "r"): ("ng", "n"),
    ("t", "n"): ("n", "n"), ("t", "m"): ("n", "m"), ("t", "r"): ("n", "n"),
    ("p", "n"): ("m", "n"), ("p", "m"): ("m", "m"), ("p", "r"): ("m", "n"),
    ("ng", "r"): ("ng", "n"), ("m", "r"): ("m", "n"),
    ("n", "r"): ("l", "l"), ("l", "r"): ("l", "l"), ("l", "n"): ("l", "l"),
}


def romanise_korean(text):
    """Revised Romanization of a Korean place name, good enough to match geoBoundaries names."""
    syllables = []
    for char in text:
        code = ord(char) - 0xAC00
        if 0 <= code < 11172:
            syllables.append((code // 588, (code % 588) // 28, code % 28))
        else:
            syllables.append(char)
    out = []
    for index, syllable in enumerate(syllables):
        if isinstance(syllable, str):
            out.append(syllable)
            continue
        initial_index, vowel_index, final_index = syllable
        initial = HANGUL_INITIALS[initial_index]
        final = HANGUL_FINALS[final_index]
        next_syllable = syllables[index + 1] if index + 1 < len(syllables) else None
        next_is_hangul = isinstance(next_syllable, tuple)
        if final is None:
            out.append(initial + HANGUL_VOWELS[vowel_index])
            continue
        if next_is_hangul and HANGUL_INITIALS[next_syllable[0]] == "":
            out.append(initial + HANGUL_VOWELS[vowel_index] + final[1])
            # the carried-over consonant replaces the empty initial of the next syllable
            syllables[index + 1] = (11, next_syllable[1], next_syllable[2])
            continue
        final_text = final[0]
        if next_is_hangul:
            next_initial = HANGUL_INITIALS[next_syllable[0]]
            rule = HANGUL_ASSIMILATION.get((final[2], next_initial))
            if rule:
                final_text = rule[0]
                replacement_initial = rule[1]
                out.append(initial + HANGUL_VOWELS[vowel_index] + final_text)
                out.append(("__initial__", replacement_initial))
                continue
        out.append(initial + HANGUL_VOWELS[vowel_index] + final_text)
    # resolve replaced initials
    result = []
    pending_initial = None
    for piece in out:
        if isinstance(piece, tuple):
            pending_initial = piece[1]
            continue
        if pending_initial is not None:
            # strip the default initial of this syllable and use the assimilated one
            default_initial = re.match(r"^(kk|ch|tt|pp|jj|ss|[gndrmbsjktph]?)", piece).group(1)
            piece = pending_initial + piece[len(default_initial):]
            pending_initial = None
        result.append(piece)
    romanised = "".join(result)
    romanised = re.sub(r"(si|gu|gun)$", r"-\1", romanised)
    return romanised[:1].upper() + romanised[1:]


def parse_korea_sido():
    source = KOREA_DIR / "kosis_DT_104Y283_sido_land_assets_1995_2025_euckr.csv"
    with open(source, encoding="euc-kr", newline="") as handle:
        reader = list(csv.reader(handle))
    header = reader[0]
    years = []
    for column in header[1:]:
        match = re.search(r"Y(\d{4})", column)
        years.append((int(match.group(1)), "p)" in column))
    rows = []
    for record in reader[1:]:
        code, name = record[0].split(" ", 1)
        english = KOREA_SIDO_ENGLISH[name]
        for (year, provisional), value in zip(years, record[1:]):
            if value.strip() in ("-", ""):
                continue
            rows.append({
                "region_code_kosis": code,
                "region_name_korean": name,
                "region_name_english": english,
                "year": year,
                "provisional": "yes" if provisional else "no",
                "land_value_krw": round(float(value) * 1e9),
            })
    fieldnames = ["region_code_kosis", "region_name_korean", "region_name_english", "year", "provisional", "land_value_krw"]
    write_csv(KOREA_DIR / "tidy_korea_sido_land_assets_national_balance_sheet.csv", fieldnames, rows)

    adm1 = json.load(open(KOREA_DIR / "geoBoundaries-KOR-ADM1.geojson", encoding="utf-8"))
    adm1_names = {feature["properties"]["shapeName"] for feature in adm1["features"]}
    latest_year = max(year for year, _ in years)
    latest = [row for row in rows if row["year"] == latest_year and row["region_name_korean"] != "전국"]
    unmatched = sorted({row["region_name_english"] for row in latest} - adm1_names)
    print(f"Korea ADM1 join: {len(latest) - len(unmatched)}/{len(latest)} regions match geoBoundaries shapeName; unmatched {unmatched}")
    national = next(row for row in rows if row["year"] == latest_year and row["region_name_korean"] == "전국")
    summed = report_total_and_largest(f"Korea sido land assets {latest_year} (KRW)", latest, "region_name_english", "land_value_krw")
    print(f"  published national total {national['land_value_krw']:,.0f}; sum of regions differs by {summed - national['land_value_krw']:,.0f}")


def assign_adm2_to_adm1():
    """Province of each geoBoundaries ADM2 feature: the ADM1 polygon it overlaps most.

    The ADM1 (Natural Earth) and ADM2 (citypopulation.de) layers come from different
    sources and do not nest exactly, so point-in-polygon misplaces outer districts of
    the metropolitan cities; the largest overlap is robust.
    """
    adm1 = json.load(open(KOREA_DIR / "geoBoundaries-KOR-ADM1.geojson", encoding="utf-8"))
    adm2 = json.load(open(KOREA_DIR / "geoBoundaries-KOR-ADM2.geojson", encoding="utf-8"))
    adm1_shapes = [(feature["properties"]["shapeName"], shape(feature["geometry"]).buffer(0)) for feature in adm1["features"]]
    prepared = [(name, prep(geometry)) for name, geometry in adm1_shapes]
    assignments = []
    for feature in adm2["features"]:
        geometry = shape(feature["geometry"]).buffer(0)
        overlaps = {}
        for (name, adm1_geometry), (_, prepared_geometry) in zip(adm1_shapes, prepared):
            if prepared_geometry.intersects(geometry):
                overlaps[name] = adm1_geometry.intersection(geometry).area
        if overlaps:
            parent = max(overlaps, key=overlaps.get)
        else:
            point = geometry.representative_point()
            parent = min(adm1_shapes, key=lambda item: item[1].distance(point))[0]
        assignments.append({
            "parent": parent,
            "name": feature["properties"]["shapeName"],
            "shape_id": feature["properties"]["shapeID"],
            "overlaps": overlaps,
        })
    return assignments


# Units whose rule-based romanisation does not match the geoBoundaries spelling, or
# whose province changed after the 2020 boundary vintage (군위군 moved from North
# Gyeongsang to Daegu in 2023).
KOREA_UNIT_ROMANISATION_OVERRIDES = {
    "세종특별자치시": "Sejong-si",
}


def parse_korea_sigungu():
    source = KOREA_DIR / "kosis_DT_110013_FILE2025_01_land_by_ownership_type_sigungu_2025.xlsx"
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    year = int(sheet.title)
    rows = []
    current_sido = None
    for record in sheet.iter_rows(min_row=3, values_only=True):
        sido, district, area_m2, parcel_count, value_billion_krw = record[0], record[1], record[2], record[3], record[4]
        if sido:
            current_sido = sido
        if current_sido == "전국":
            continue
        if district == "소계":
            if current_sido != "세종특별자치시":
                continue
            # Sejong has no 시군구 below it; its subtotal row is the unit.
            district = current_sido
        parent_city = district.split(" ")[0] if " " in district else ""
        rows.append({
            "sido_name_korean": current_sido,
            "sido_name_english": KOREA_SIDO_ENGLISH[current_sido],
            "district_name_korean": district,
            "district_parent_city_korean": parent_city,
            "year": year,
            "area_m2": area_m2,
            "parcel_count": parcel_count,
            "assessed_land_value_krw": round(value_billion_krw * 1e9),
        })
    fieldnames = ["sido_name_korean", "sido_name_english", "district_name_korean", "district_parent_city_korean", "year", "area_m2", "parcel_count", "assessed_land_value_krw"]
    write_csv(KOREA_DIR / "tidy_korea_sigungu_assessed_land_value.csv", fieldnames, rows)
    summed = report_total_and_largest(f"Korea sigungu assessed land value {year} (KRW)", rows, "district_name_korean", "assessed_land_value_krw")
    national_row = next(sheet.iter_rows(min_row=3, max_row=3, values_only=True))
    national = round(national_row[4] * 1e9)
    print(f"  published national total {national:,.0f}; sum of districts differs by {summed - national:,.0f}")

    # Aggregate the non-autonomous 구 of large cities back to the city, which is the
    # geoBoundaries ADM2 unit, then match romanised names within each province.
    aggregated = {}
    for row in rows:
        unit_name = row["district_parent_city_korean"] or row["district_name_korean"]
        key = (row["sido_name_korean"], unit_name)
        entry = aggregated.setdefault(key, {
            "sido_name_korean": row["sido_name_korean"],
            "sido_name_english": row["sido_name_english"],
            "unit_name_korean": unit_name,
            "unit_name_romanised": KOREA_UNIT_ROMANISATION_OVERRIDES.get(unit_name) or romanise_korean(unit_name),
            "year": row["year"],
            "area_m2": 0.0,
            "parcel_count": 0,
            "assessed_land_value_krw": 0,
            "geoboundaries_adm2_shapeName": "",
            "geoboundaries_adm2_shapeID": "",
        })
        entry["area_m2"] += row["area_m2"]
        entry["parcel_count"] += row["parcel_count"]
        entry["assessed_land_value_krw"] += row["assessed_land_value_krw"]

    assignments = assign_adm2_to_adm1()
    features_by_key = {}
    for feature in assignments:
        for key in {normalise_name(feature["name"]), strip_korean_suffix(normalise_name(feature["name"]))}:
            features_by_key.setdefault(key, []).append(feature)
    used_shape_ids = set()

    def pick_feature(entry):
        province = entry["sido_name_english"]
        keys = [normalise_name(entry["unit_name_romanised"]), strip_korean_suffix(normalise_name(entry["unit_name_romanised"]))]
        candidates = {feature["shape_id"]: feature for key in keys for feature in features_by_key.get(key, [])}
        candidates = [feature for feature in candidates.values() if feature["shape_id"] not in used_shape_ids]
        if not candidates:
            return None
        same_province = [feature for feature in candidates if feature["parent"] == province]
        if same_province:
            return same_province[0]
        # Generic names (Dong-gu, Seo-gu, ...) whose ADM2 polygon overlaps the coarser
        # ADM1 polygon of a neighbouring province more than its own: take the candidate
        # that overlaps this province at all, most first.
        overlapping = [feature for feature in candidates if feature["overlaps"].get(province, 0) > 0]
        if overlapping:
            return max(overlapping, key=lambda feature: feature["overlaps"][province])
        # Province changed since the boundary vintage (e.g. 군위군 to Daegu in 2023):
        # accept a name that is unique across the whole country.
        if len(candidates) == 1:
            return candidates[0]
        return None

    matched = 0
    # Two passes: a generic name can only become nationally unique once the other
    # provinces' same-named districts have been matched.
    for _ in range(2):
        for entry in aggregated.values():
            if entry["geoboundaries_adm2_shapeID"]:
                continue
            feature = pick_feature(entry)
            if feature:
                entry["geoboundaries_adm2_shapeName"], entry["geoboundaries_adm2_shapeID"] = feature["name"], feature["shape_id"]
                used_shape_ids.add(feature["shape_id"])
                matched += 1
    unmatched_units = [f"{e['sido_name_english']}/{e['unit_name_korean']}({e['unit_name_romanised']})" for e in aggregated.values() if not e["geoboundaries_adm2_shapeID"]]
    unmatched_shapes = [f"{feature['parent']}/{feature['name']}" for feature in assignments if feature["shape_id"] not in used_shape_ids]
    print(f"Korea ADM2 join: {matched}/{len(aggregated)} value units matched to geoBoundaries ADM2 features")
    print(f"  unmatched value units: {unmatched_units}")
    print(f"  unmatched geoBoundaries features: {unmatched_shapes}")
    fieldnames = ["sido_name_korean", "sido_name_english", "unit_name_korean", "unit_name_romanised", "year", "area_m2", "parcel_count", "assessed_land_value_krw", "geoboundaries_adm2_shapeName", "geoboundaries_adm2_shapeID"]
    aggregated_rows = list(aggregated.values())
    for row in aggregated_rows:
        row["area_m2"] = round(row["area_m2"], 1)
    write_csv(KOREA_DIR / "tidy_korea_sigungu_assessed_land_value_geoboundaries_units.csv", fieldnames, aggregated_rows)


# ---------------------------------------------------------------------------
# British Columbia
# ---------------------------------------------------------------------------

def parse_money(text):
    text = text.strip().replace("$", "").replace(",", "")
    if text in ("", "-"):
        return 0
    return int(float(text))


def split_code_and_name(text):
    code, _, name = text.partition(" - ")
    return code.strip(), name.strip()


def bc_legal_name_key(name):
    """Comparable form of a BC municipality name.

    Drops "The Corporation of the", school-district suffixes such as "(SD61)" or
    "-SD47" that BC Assessment adds when a municipality spans school districts, and
    expands the abbreviation "Mun".
    """
    name = re.sub(r"\(SD\d+\)|-SD\d+", "", name, flags=re.I)
    name = re.sub(r"^(the )?corporation of (the )?", "", name.strip(), flags=re.I)
    name = re.sub(r"\bMun\b", "Municipality", name)
    return normalise_name(name)


def bc_proper_name_key(name):
    """The place name after the last " of " ("District of Tofino" -> "tofino")."""
    name = re.sub(r"\(SD\d+\)|-SD\d+", "", name, flags=re.I).strip()
    _, _, proper = name.rpartition(" of ")
    return normalise_name(proper or name)


def parse_bc():
    source = BC_DIR / "roll-totals-by-jurisdiction-and-property-class-2026-revised.csv"
    class_rows = []
    with open(source, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            area_code, area_name = split_code_and_name(record["Area"])
            jurisdiction_code, jurisdiction_name = split_code_and_name(record["Jurisdiction"])
            class_code, class_name = split_code_and_name(record["Property Class"])
            subclass_code, subclass_name = split_code_and_name(record["Property Subclass"])
            class_rows.append({
                "roll_year": int(record["Roll Year"]),
                "roll_version": record["Roll Version"],
                "area_code": area_code,
                "area_name": area_name,
                "jurisdiction_code": jurisdiction_code,
                "jurisdiction_name": jurisdiction_name,
                "property_class_code": class_code,
                "property_class": class_name,
                "property_subclass_code": subclass_code,
                "property_subclass": subclass_name,
                "occurrences": parse_money(record["Occurrences"]),
                "land_value_cad": parse_money(record["Actual - Land"]),
                "improvements_value_cad": parse_money(record["Actual - Impr"]),
                "total_value_cad": parse_money(record["Actual - Total"]),
                "net_taxable_general_land_cad": parse_money(record["Gen Net - Land"]),
                "net_taxable_general_improvements_cad": parse_money(record["Gen Net - Impr"]),
            })
    write_csv(BC_DIR / "tidy_bc_jurisdiction_property_class_land_improvements_2026.csv", list(class_rows[0].keys()), class_rows)

    source = BC_DIR / "roll-totals-by-jurisdiction-2026-revised.csv"
    jurisdiction_rows = []
    with open(source, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            area_code, area_name = split_code_and_name(record["Area"])
            jurisdiction_code, jurisdiction_name = split_code_and_name(record["Jurisdiction"])
            jurisdiction_rows.append({
                "roll_year": int(record["Roll Year"]),
                "roll_version": record["Roll Version"],
                "area_code": area_code,
                "area_name": area_name,
                "jurisdiction_code": jurisdiction_code,
                "jurisdiction_name": jurisdiction_name,
                "folios": parse_money(record["Folios"]),
                "land_value_cad": parse_money(record["Actual - Land"]),
                "improvements_value_cad": parse_money(record["Actual - Impr"]),
                "total_value_cad": parse_money(record["Actual - Total"]),
                "net_taxable_general_land_cad": parse_money(record["Gen Net - Land"]),
                "net_taxable_general_improvements_cad": parse_money(record["Gen Net - Impr"]),
                "municipality_boundary_LGL_ADMIN_AREA_ID": "",
                "municipality_boundary_ADMIN_AREA_NAME": "",
            })

    boundaries = json.load(open(BC_DIR / "bc_municipalities_ABMS_MUNICIPALITIES_SP_wgs84.geojson", encoding="utf-8"))
    by_name = {}
    by_proper_name = {}
    for feature in boundaries["features"]:
        properties = feature["properties"]
        identity = (properties["LGL_ADMIN_AREA_ID"], properties["ADMIN_AREA_NAME"])
        by_name[bc_legal_name_key(properties["ADMIN_AREA_NAME"])] = identity
        by_proper_name.setdefault(bc_proper_name_key(properties["ADMIN_AREA_NAME"]), []).append(identity)
    matched_ids = set()
    for row in jurisdiction_rows:
        key = bc_legal_name_key(row["jurisdiction_name"])
        hit = by_name.get(key) or by_name.get(key + "municipality")
        if hit is None:
            # Legal designation differs between the two sources ("District of Tofino"
            # vs "Corporation of the Village of Tofino"): accept a unique place name.
            proper_candidates = by_proper_name.get(bc_proper_name_key(row["jurisdiction_name"]), [])
            if len(proper_candidates) == 1:
                hit = proper_candidates[0]
        if hit:
            row["municipality_boundary_LGL_ADMIN_AREA_ID"], row["municipality_boundary_ADMIN_AREA_NAME"] = hit
            matched_ids.add(hit[0])
    write_csv(BC_DIR / "tidy_bc_jurisdiction_land_improvements_2026.csv", list(jurisdiction_rows[0].keys()), jurisdiction_rows)

    # One row per municipal boundary: several BC Assessment jurisdictions (split by
    # school district) can belong to one municipality.
    municipality_rows = {}
    for row in jurisdiction_rows:
        boundary_id = row["municipality_boundary_LGL_ADMIN_AREA_ID"]
        if boundary_id == "":
            continue
        entry = municipality_rows.setdefault(boundary_id, {
            "municipality_boundary_LGL_ADMIN_AREA_ID": boundary_id,
            "municipality_boundary_ADMIN_AREA_NAME": row["municipality_boundary_ADMIN_AREA_NAME"],
            "roll_year": row["roll_year"],
            "jurisdiction_codes": [],
            "folios": 0,
            "land_value_cad": 0,
            "improvements_value_cad": 0,
            "total_value_cad": 0,
        })
        entry["jurisdiction_codes"].append(row["jurisdiction_code"])
        for column in ("folios", "land_value_cad", "improvements_value_cad", "total_value_cad"):
            entry[column] += row[column]
    municipality_list = sorted(municipality_rows.values(), key=lambda row: row["municipality_boundary_ADMIN_AREA_NAME"])
    for row in municipality_list:
        row["jurisdiction_codes"] = "|".join(row["jurisdiction_codes"])
    write_csv(BC_DIR / "tidy_bc_municipality_land_improvements_2026.csv", list(municipality_list[0].keys()), municipality_list)

    unmatched_jurisdictions = [f"{r['jurisdiction_code']} {r['jurisdiction_name']}" for r in jurisdiction_rows if not r["municipality_boundary_LGL_ADMIN_AREA_ID"]]
    unmatched_boundaries = [f["properties"]["ADMIN_AREA_NAME"] for f in boundaries["features"] if f["properties"]["LGL_ADMIN_AREA_ID"] not in matched_ids]
    print(f"BC join: {len(matched_ids)}/{len(boundaries['features'])} municipal boundaries matched to a jurisdiction; {len(unmatched_jurisdictions)} jurisdictions without a municipal boundary (rural areas, Indigenous lands, etc.)")
    print(f"  unmatched boundaries: {unmatched_boundaries}")
    print(f"  unmatched jurisdictions: {unmatched_jurisdictions}")

    with open(BC_DIR / "roll-totals-by-province-2026-revised.csv", encoding="utf-8-sig", newline="") as handle:
        province = next(csv.DictReader(handle))
    province_land = parse_money(province["Actual - Land"])
    summed = report_total_and_largest("BC jurisdiction land value 2026 revised roll (CAD)", jurisdiction_rows, "jurisdiction_name", "land_value_cad")
    print(f"  published provincial land total {province_land:,.0f}; sum of jurisdictions differs by {summed - province_land:,.0f}")
    print(f"  provincial improvements {parse_money(province['Actual - Impr']):,.0f}; land share of total {province_land / parse_money(province['Actual - Total']):.1%}")


# ---------------------------------------------------------------------------
# Denmark
# ---------------------------------------------------------------------------

DENMARK_TAX_BASE_COLUMNS = {
    "3": "taxable_land_value_dkk",
    "2": "buildings_value_dkk",
    "1": "property_value_dkk",
    "4": "property_taxes_dkk",
}


def parse_denmark():
    english = DENMARK_DIR / "eskat_2023_2025.csv"
    danish = DENMARK_DIR / "eskat_2023_2025_da.csv"
    danish_names = {}
    with open(danish, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            code, _, name = record["OMRÅDE"].partition(" ")
            danish_names[code] = name
    table = {}
    with open(english, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            code, _, name = record["OMRÅDE"].partition(" ")
            tax_base_code = record["SKATGRL"].split(" ", 1)[0]
            year = int(record["TID"].split(" ")[0])
            value = record["INDHOLD"].strip()
            entry = table.setdefault((code, year), {
                "municipality_code": code,
                "municipality_name": danish_names[code],
                "municipality_name_english": name,
                "year": year,
            })
            column = DENMARK_TAX_BASE_COLUMNS[tax_base_code]
            if value in ("..", "...", "-", ""):
                entry[column] = ""
            elif column == "property_taxes_dkk":
                entry[column] = round(float(value) * 1e3)  # source unit DKK 1,000
            else:
                entry[column] = round(float(value) * 1e6)  # source unit DKK million
    rows = sorted(table.values(), key=lambda row: (row["year"], row["municipality_code"]))

    boundaries = json.load(open(DENMARK_DIR / "geoBoundaries-DNK-ADM2.geojson", encoding="utf-8"))
    boundary_names = {normalise_name(f["properties"]["shapeName"]): (f["properties"]["shapeName"], f["properties"]["shapeID"]) for f in boundaries["features"]}
    for row in rows:
        row["geoboundaries_adm2_shapeName"] = ""
        row["geoboundaries_adm2_shapeID"] = ""
        if row["municipality_code"] == "000":
            continue
        keys = [normalise_name(row["municipality_name"]), normalise_name(row["municipality_name_english"])]
        # "Nordfyns"/"Vesthimmerlands" (genitive) vs "Nordfyn"/"Vesthimmerland"
        keys += [key[:-1] for key in list(keys) if key.endswith("s")]
        hit = next((boundary_names[key] for key in keys if key in boundary_names), None)
        if hit:
            row["geoboundaries_adm2_shapeName"], row["geoboundaries_adm2_shapeID"] = hit
    fieldnames = ["municipality_code", "municipality_name", "municipality_name_english", "year", "taxable_land_value_dkk", "buildings_value_dkk", "property_value_dkk", "property_taxes_dkk", "geoboundaries_adm2_shapeName", "geoboundaries_adm2_shapeID"]
    write_csv(DENMARK_DIR / "tidy_denmark_kommune_taxable_land_value.csv", fieldnames, rows)

    latest_year = max(row["year"] for row in rows)
    latest = [row for row in rows if row["year"] == latest_year and row["municipality_code"] != "000"]
    unmatched = [row["municipality_name"] for row in latest if not row["geoboundaries_adm2_shapeID"]]
    print(f"Denmark ADM2 join: {len(latest) - len(unmatched)}/{len(latest)} municipalities match geoBoundaries shapeName by name; unmatched {unmatched}")
    national = next(row for row in rows if row["year"] == latest_year and row["municipality_code"] == "000")
    summed = report_total_and_largest(f"Denmark taxable land value {latest_year} (DKK)", latest, "municipality_name", "taxable_land_value_dkk")
    print(f"  published national total {national['taxable_land_value_dkk']:,.0f}; sum of municipalities differs by {summed - national['taxable_land_value_dkk']:,.0f}")


def main():
    parse_korea_sido()
    parse_korea_sigungu()
    parse_bc()
    parse_denmark()


if __name__ == "__main__":
    sys.exit(main())

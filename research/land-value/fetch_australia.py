"""Tidy official land-value totals by local government area for Australian states other than NSW.

Written by AI on 2026.10.16 by model claude fable 5.1 subagent.

Reads the downloaded sources under data/experiments/land-value/raw/australia/ (treated as
untrusted data: only parsed, never executed) and writes one tidy CSV per state and valuation
year into the same folder. Matches each council name to the ABS 2021 LGA boundaries
(lga_<state>.geojson) and lists names that did not match.

Run from the repo root:
    devenv shell -- python -I research/land-value/fetch_australia.py
"""

import csv
import html
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUSTRALIA_DIR = REPO_ROOT / "data" / "experiments" / "land-value" / "raw" / "australia"

TIDY_COLUMNS = [
    "state",
    "lga_name",
    "lga_code_2021",
    "valuation_date",
    "land_value_aud",
    "capital_improved_value_aud",
    "number_of_valuations",
    "source",
]

# Council renamed after the ABS 2021 boundaries were published, or spelt differently.
MANUAL_NAME_ALIASES = {
    "vic": {"merri-bek": "moreland"},
    "qld": {"blackall-tambo": "blackall tambo"},
}

ABS_NAME_SUFFIX_PATTERN = re.compile(r"\s*\((vic\.|qld|sa|wa|tas\.|nt|act)\)\s*$", re.IGNORECASE)
COUNCIL_WORDS_PATTERN = re.compile(
    r"\b(city council|shire council|regional council|aboriginal shire council|town council|council|city|shire|region)\b",
    re.IGNORECASE,
)


def normalise_lga_name(name: str) -> str:
    name = ABS_NAME_SUFFIX_PATTERN.sub("", name.strip())
    name = COUNCIL_WORDS_PATTERN.sub("", name)
    name = name.replace("'", "").replace("’", "")
    name = re.sub(r"\s+", " ", name).strip().lower()
    return name


def load_abs_lga_lookup(state: str) -> dict[str, tuple[str, str]]:
    """Map normalised ABS LGA name -> (lga_code_2021, lga_name_2021) for one state."""
    geojson = json.loads((AUSTRALIA_DIR / f"lga_{state}.geojson").read_text(encoding="utf-8"))
    lookup = {}
    for feature in geojson["features"]:
        properties = feature["properties"]
        lookup[normalise_lga_name(properties["lga_name_2021"])] = (
            properties["lga_code_2021"],
            properties["lga_name_2021"],
        )
    return lookup


def match_lga_code(state: str, printed_name: str, lookup: dict[str, tuple[str, str]]) -> str:
    key = normalise_lga_name(printed_name)
    key = MANUAL_NAME_ALIASES.get(state, {}).get(key, key)
    return lookup[key][0] if key in lookup else ""


def write_tidy_csv(path: Path, rows: list[dict], extra_columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIDY_COLUMNS + extra_columns)
        writer.writeheader()
        writer.writerows(rows)


def report(state_label: str, rows: list[dict], path: Path) -> None:
    total_land_value = sum(int(r["land_value_aud"]) for r in rows if r["land_value_aud"] != "")
    unmatched = [r["lga_name"] for r in rows if not r["lga_code_2021"]]
    print(f"{state_label}: {len(rows)} councils, total land value A${total_land_value:,} -> {path.relative_to(REPO_ROOT)}")
    print(f"  matched to ABS 2021 codes: {len(rows) - len(unmatched)}; unmatched: {unmatched or 'none'}")


# ---------------------------------------------------------------------------
# Victoria: Valuer-General Victoria revaluation outcome summary (sheet "Outcomes Summary <year>")
# Columns: A municipality; B-G assessments with buildings (Res, Com, Ind, Rural, Non-rateable
# leviable, Total); H-M assessments without buildings; N-S NAV; T-Y CIV; Z-AE SV.
# ---------------------------------------------------------------------------
VIC_SOURCES = {
    2025: ("vic/2025-outcome-summary.Outcomes-Summary-2025.csv", "2025-01-01",
           "https://www.land.vic.gov.au/__data/assets/excel_doc/0026/757016/2025-outcome-summary.xlsx"),
    2026: ("vic/2026-outcome-summary.Outcomes-Summary-2026.csv", "2026-01-01",
           "https://www.land.vic.gov.au/__data/assets/excel_doc/0037/775909/2026-outcome-summary.xlsx"),
}
VIC_SV_COLUMNS = {"site_value_residential_aud": 25, "site_value_commercial_aud": 26,
                  "site_value_industrial_aud": 27, "site_value_rural_aud": 28,
                  "site_value_non_rateable_leviable_aud": 29}


def tidy_victoria(year: int, lookup: dict) -> Path:
    relative_path, valuation_date, source_url = VIC_SOURCES[year]
    sheet_rows = list(csv.reader((AUSTRALIA_DIR / relative_path).open(encoding="utf-8")))
    assert sheet_rows[1][0] == "Municipality" and sheet_rows[0][25] == f"{year} SV", "unexpected sheet layout"
    rows = []
    for cells in sheet_rows[2:]:
        if not cells[0] or cells[0] == "Total":
            continue
        row = {
            "state": "VIC",
            "lga_name": cells[0],
            "lga_code_2021": match_lga_code("vic", cells[0], lookup),
            "valuation_date": valuation_date,
            "land_value_aud": cells[30],
            "capital_improved_value_aud": cells[24],
            "number_of_valuations": int(cells[6]) + int(cells[12]),
            "source": source_url,
            "net_annual_value_aud": cells[18],
        }
        for column_name, index in VIC_SV_COLUMNS.items():
            row[column_name] = cells[index]
        rows.append(row)
    sheet_total = next(cells for cells in sheet_rows if cells[0] == "Total")
    assert sum(int(r["land_value_aud"]) for r in rows) == int(sheet_total[30]), "SV does not add up to sheet total"
    path = AUSTRALIA_DIR / f"vic_land_value_by_lga_{year}.csv"
    write_tidy_csv(path, rows, ["net_annual_value_aud", *VIC_SV_COLUMNS])
    return path


# ---------------------------------------------------------------------------
# Queensland: Valuer-General 2026 annual valuation, LGA overview pages (HTML).
# "N properties revalued, with a total value of $X" plus a land-use table.
# ---------------------------------------------------------------------------
QLD_LAND_USE_LABELS = ["Single unit residential", "Rural residential", "Multi-unit residential",
                       "Commercial", "Industrial", "Primary production", "Other"]


def page_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def tidy_queensland(lookup: dict) -> Path:
    rows = []
    for page_path in sorted((AUSTRALIA_DIR / "qld" / "2026").glob("*-council.html")):
        text = page_text(page_path)
        title = re.search(r"([A-Za-z' -]+ (?:City|Shire|Regional) Council) - qld\.gov\.au", text)
        overview = re.search(r"Overview of 2026 land valuation ([\d,]+) properties revalued, with a total value of \$([\d,]+)", text)
        previous = re.search(r"since last revaluation issued in (\d{4})", text)
        if not (title and overview):
            raise ValueError(f"could not parse {page_path.name}")
        council_name = title.group(1).strip()
        row = {
            "state": "QLD",
            "lga_name": council_name,
            "lga_code_2021": match_lga_code("qld", council_name, lookup),
            "valuation_date": "2025-10-01",
            "land_value_aud": overview.group(2).replace(",", ""),
            "capital_improved_value_aud": "",
            "number_of_valuations": overview.group(1).replace(",", ""),
            "source": f"https://www.qld.gov.au/environment/land/title/valuation/2026-valuations/{page_path.stem}",
            "previous_valuation_year": previous.group(1) if previous else "",
        }
        for label in QLD_LAND_USE_LABELS:
            found = re.search(re.escape(label) + r" \$([\d,]+) ", text)
            row["land_value_" + re.sub(r"[^a-z]+", "_", label.lower()) + "_aud"] = found.group(1).replace(",", "") if found else ""
        lga_total = re.search(r"LGA total \$([\d,]+)", text)
        assert lga_total and lga_total.group(1) == overview.group(2), f"LGA total mismatch in {page_path.name}"
        rows.append(row)
    path = AUSTRALIA_DIR / "qld_land_value_by_lga_2026.csv"
    extra = ["previous_valuation_year"] + ["land_value_" + re.sub(r"[^a-z]+", "_", l.lower()) + "_aud" for l in QLD_LAND_USE_LABELS]
    write_tidy_csv(path, rows, extra)
    return path


# ---------------------------------------------------------------------------
# ACT: per-block unimproved values (ACT Revenue Office, data.act.gov.au rbu5-se5b), summed.
# The ACT is one ABS LGA ("Unincorporated ACT").
# ---------------------------------------------------------------------------
def tidy_act(lookup: dict) -> Path:
    source_csv = AUSTRALIA_DIR / "act" / "act_unimproved_values_rbu5-se5b.csv"
    totals = {}
    counts = {}
    with source_csv.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        uv_columns = [c for c in reader.fieldnames if c.lower().startswith("uv_")]
        for record in reader:
            for column in uv_columns:
                value = record[column].strip()
                if value:
                    totals[column] = totals.get(column, 0) + int(float(value))
                    counts[column] = counts.get(column, 0) + 1
    rows = []
    for column in sorted(uv_columns, key=lambda c: c.lower(), reverse=True):
        year = column.split("_")[1]
        rows.append({
            "state": "ACT",
            "lga_name": "Unincorporated ACT",
            "lga_code_2021": match_lga_code("act", "Unincorporated ACT", lookup),
            "valuation_date": f"{year}-01-01",
            "land_value_aud": totals[column],
            "capital_improved_value_aud": "",
            "number_of_valuations": counts[column],
            "source": "https://www.data.act.gov.au/dataset/Unimproved-value/rbu5-se5b (sum of per-block UV_" + year + ")",
        })
    path = AUSTRALIA_DIR / "act_land_value_by_lga.csv"
    write_tidy_csv(path, rows, [])
    return path


def main() -> None:
    vic_lookup = load_abs_lga_lookup("vic")
    for year in (2025, 2026):
        path = tidy_victoria(year, vic_lookup)
        report(f"VIC {year} (site value, 1 Jan {year})", list(csv.DictReader(path.open(encoding="utf-8"))), path)

    qld_path = tidy_queensland(load_abs_lga_lookup("qld"))
    report("QLD 2026 (15 LGAs revalued at 1 Oct 2025 only)", list(csv.DictReader(qld_path.open(encoding="utf-8"))), qld_path)

    act_path = tidy_act(load_abs_lga_lookup("act"))
    act_rows = list(csv.DictReader(act_path.open(encoding="utf-8")))
    for row in act_rows:
        report(f"ACT {row['valuation_date'][:4]} (unimproved value, all blocks)", [row], act_path)


if __name__ == "__main__":
    main()

"""Fetch and tidy Japan's official land values and boundaries.

Written by AI on 2026.10.16 by model claude fable 5.1 subagent.

Sources (all free, no login):
  1. MIC (総務省) 令和7年度 固定資産の価格等の概要調書, 土地 (fixed asset tax,
     summary of assessed land values, FY2025). Prefecture table 第2表 総括表
     and the municipality breakdown of the same table.
  2. MLIT 国土数値情報 N03 行政区域 2026 (administrative boundaries, CC BY 4.0).

Run from the repo root:
  devenv shell -- python -I research/land-value/fetch_japan.py

Downloaded files are untrusted data. This script only reads them with
openpyxl, zipfile and fiona; it never executes anything from the raw folder.
"""

import csv
import subprocess
import sys
import zipfile
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[2]
JAPAN_DIR = REPO_ROOT / "data/experiments/land-value/raw/japan"
SOUMU_DIR = JAPAN_DIR / "soumu_r07"
N03_DIR = JAPAN_DIR / "mlit_n03_2026"

SOUMU_BASE_URL = "https://www.soumu.go.jp/main_content/"
# 土地 national tables (001077088-99), 土地 prefecture tables (001077141-60,
# 001077261-66) and the municipality 土地 総括表 (001077119).
SOUMU_FILE_IDS = (
    list(range(1077088, 1077100))
    + list(range(1077141, 1077161))
    + list(range(1077261, 1077267))
    + [1077119]
)
PREFECTURE_SUMMARY_XLSX = SOUMU_DIR / "001077142.xlsx"
NATIONAL_SUMMARY_XLSX = SOUMU_DIR / "001077090.xlsx"
MUNICIPALITY_SUMMARY_XLSX = SOUMU_DIR / "001077119.xlsx"

N03_ZIP_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_GML.zip"
N03_ZIP = N03_DIR / "N03-20260101_GML.zip"

THOUSAND_YEN = 1000

# JIS X 0401 prefecture codes in official order. The prefecture sheet lists
# prefectures in this order with short names (青森 not 青森県).
PREFECTURES = [
    ("01", "北海道"), ("02", "青森県"), ("03", "岩手県"), ("04", "宮城県"),
    ("05", "秋田県"), ("06", "山形県"), ("07", "福島県"), ("08", "茨城県"),
    ("09", "栃木県"), ("10", "群馬県"), ("11", "埼玉県"), ("12", "千葉県"),
    ("13", "東京都"), ("14", "神奈川県"), ("15", "新潟県"), ("16", "富山県"),
    ("17", "石川県"), ("18", "福井県"), ("19", "山梨県"), ("20", "長野県"),
    ("21", "岐阜県"), ("22", "静岡県"), ("23", "愛知県"), ("24", "三重県"),
    ("25", "滋賀県"), ("26", "京都府"), ("27", "大阪府"), ("28", "兵庫県"),
    ("29", "奈良県"), ("30", "和歌山県"), ("31", "鳥取県"), ("32", "島根県"),
    ("33", "岡山県"), ("34", "広島県"), ("35", "山口県"), ("36", "徳島県"),
    ("37", "香川県"), ("38", "愛媛県"), ("39", "高知県"), ("40", "福岡県"),
    ("41", "佐賀県"), ("42", "長崎県"), ("43", "熊本県"), ("44", "大分県"),
    ("45", "宮崎県"), ("46", "鹿児島県"), ("47", "沖縄県"),
]
PREFECTURE_CODE_BY_FULL_NAME = {name: code for code, name in PREFECTURES}

# Column layout of every sheet in the prefecture 総括表 (after the name
# column). Verified against header rows 5-8 of the workbook.
# (land_category, land_subcategory); "計" marks a subtotal column in the sheet.
PREFECTURE_SHEET_COLUMNS = [
    ("田", "一般田"), ("田", "勧告遊休田"), ("田", "介在田・市街化区域田"),
    ("畑", "一般畑"), ("畑", "勧告遊休畑"), ("畑", "介在畑・市街化区域畑"),
    ("宅地", "小規模住宅用地"), ("宅地", "一般住宅用地"),
    ("宅地", "住宅用地以外の宅地"), ("宅地", "計"),
    ("鉱泉地", "計"), ("池沼", "計"),
    ("山林", "一般山林"), ("山林", "介在山林"),
    ("牧場", "計"), ("原野", "計"),
    ("雑種地", "ゴルフ場用地"), ("雑種地", "遊園地等の用地"),
    ("雑種地", "鉄軌道用地・単体利用"),
    ("雑種地", "鉄軌道用地・複合利用・小規模住宅用地"),
    ("雑種地", "鉄軌道用地・複合利用・一般住宅用地"),
    ("雑種地", "鉄軌道用地・複合利用・住宅用地以外"),
    ("雑種地", "鉄軌道用地・複合利用・計"),
    ("雑種地", "その他の雑種地"), ("雑種地", "計"),
    ("合計", "計"),
]
LAND_CATEGORY_ORDER = ["田", "畑", "宅地", "鉱泉地", "池沼", "山林", "牧場", "原野", "雑種地", "合計"]

# Sheet title -> output measure. Values in 千円 are converted to yen.
PREFECTURE_MEASURE_SHEETS = {
    "10-02(ア)評価総地積": ("area_m2", 1),
    "10-02(ｲ)決定価格_総額": ("assessed_value_yen", THOUSAND_YEN),
    "10-02(ｳ)課税標準額_総額": ("taxable_base_yen", THOUSAND_YEN),
    "10-02(ｴ)評価総筆数": ("parcels", 1),
}
PREFECTURE_FIRST_DATA_ROW = 8  # 0-based; row 55 is the national 合計
PREFECTURE_TOTAL_ROW = 55

MUNICIPALITY_BODY_CLASS = {1: "大都市", 2: "都市", 3: "町村"}


def download_if_missing(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    subprocess.run(
        ["curl", "-sSL", "-A", "Mozilla/5.0", "-o", str(destination), url],
        check=True,
    )


def load_rows(path: Path, sheet_title: str | None = None) -> list[tuple]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook[sheet_title] if sheet_title else workbook.worksheets[0]
    return list(worksheet.iter_rows(values_only=True))


def prefecture_full_name(short_name: str) -> str:
    matches = [name for _, name in PREFECTURES if name.startswith(short_name)]
    if len(matches) != 1:
        raise ValueError(f"cannot map prefecture name {short_name!r}: {matches}")
    return matches[0]


def read_prefecture_measure(sheet_title: str) -> dict[str, list[int]]:
    """Return {prefecture_full_name or '全国': [26 column values]}."""
    rows = load_rows(PREFECTURE_SUMMARY_XLSX, sheet_title)
    values_by_prefecture: dict[str, list[int]] = {}
    for row_index in range(PREFECTURE_FIRST_DATA_ROW, PREFECTURE_TOTAL_ROW + 1):
        row = rows[row_index]
        name = "全国" if row[0] == "合計" else prefecture_full_name(row[0])
        numbers = list(row[1 : 1 + len(PREFECTURE_SHEET_COLUMNS)])
        if any(not isinstance(value, int) for value in numbers):
            raise ValueError(f"{sheet_title} {name}: non-integer cell in {numbers}")
        values_by_prefecture[name] = numbers
    if len(values_by_prefecture) != 48:
        raise ValueError(f"{sheet_title}: expected 47 prefectures + 合計, got {len(values_by_prefecture)}")
    return values_by_prefecture


def check_prefecture_subtotals(name: str, values: list[int]) -> None:
    by_column = dict(zip(PREFECTURE_SHEET_COLUMNS, values))
    expected_residential_total = sum(
        by_column[("宅地", sub)] for sub in ("小規模住宅用地", "一般住宅用地", "住宅用地以外の宅地")
    )
    if by_column[("宅地", "計")] != expected_residential_total:
        raise ValueError(f"{name}: 宅地 計 mismatch")
    railway_mixed_total = sum(
        by_column[("雑種地", f"鉄軌道用地・複合利用・{sub}")]
        for sub in ("小規模住宅用地", "一般住宅用地", "住宅用地以外")
    )
    if by_column[("雑種地", "鉄軌道用地・複合利用・計")] != railway_mixed_total:
        raise ValueError(f"{name}: 鉄軌道用地 複合利用 計 mismatch")
    misc_total = (
        by_column[("雑種地", "ゴルフ場用地")]
        + by_column[("雑種地", "遊園地等の用地")]
        + by_column[("雑種地", "鉄軌道用地・単体利用")]
        + railway_mixed_total
        + by_column[("雑種地", "その他の雑種地")]
    )
    if by_column[("雑種地", "計")] != misc_total:
        raise ValueError(f"{name}: 雑種地 計 mismatch")


def category_totals(values: list[int]) -> dict[str, int]:
    """Sum subcategory columns into one value per 地目, plus 合計."""
    totals: dict[str, int] = {}
    for (category, subcategory), value in zip(PREFECTURE_SHEET_COLUMNS, values):
        if category == "合計":
            totals["合計"] = value
            continue
        if subcategory == "計" and category not in ("鉱泉地", "池沼", "牧場", "原野"):
            continue  # subtotal column; the subcategories are summed instead
        if subcategory.startswith("鉄軌道用地・複合利用・") and subcategory != "鉄軌道用地・複合利用・計":
            continue  # these three roll up into 鉄軌道用地・複合利用・計
        totals[category] = totals.get(category, 0) + value
    grand_total = sum(value for category, value in totals.items() if category != "合計")
    if grand_total != totals["合計"]:
        raise ValueError(f"合計 {totals['合計']} != sum of 地目 {grand_total}")
    return totals


def write_prefecture_csvs() -> dict[str, dict[str, int]]:
    measures = {
        measure: (read_prefecture_measure(sheet), unit_multiplier)
        for sheet, (measure, unit_multiplier) in PREFECTURE_MEASURE_SHEETS.items()
    }
    for measure, (by_prefecture, _) in measures.items():
        for name, values in by_prefecture.items():
            check_prefecture_subtotals(f"{measure} {name}", values)

    detail_rows = []
    summary_rows = []
    national_totals: dict[str, dict[str, int]] = {}
    for prefecture_code, full_name in PREFECTURES + [("", "全国")]:
        detail_by_measure = {
            measure: dict(zip(PREFECTURE_SHEET_COLUMNS, [v * unit for v in by_prefecture[full_name]]))
            for measure, (by_prefecture, unit) in measures.items()
        }
        totals_by_measure = {
            measure: category_totals([v * unit for v in by_prefecture[full_name]])
            for measure, (by_prefecture, unit) in measures.items()
        }
        if full_name == "全国":
            national_totals = totals_by_measure
            continue
        for category, subcategory in PREFECTURE_SHEET_COLUMNS:
            detail_rows.append({
                "prefecture_name_japanese": full_name,
                "prefecture_code": prefecture_code,
                "land_category": category,
                "land_subcategory": subcategory,
                **{measure: detail_by_measure[measure][(category, subcategory)] for measure in measures},
            })
        for category in LAND_CATEGORY_ORDER:
            summary_rows.append({
                "prefecture_name_japanese": full_name,
                "prefecture_code": prefecture_code,
                "land_category": category,
                **{measure: totals_by_measure[measure][category] for measure in measures},
            })

    for measure in measures:
        for category in LAND_CATEGORY_ORDER:
            prefecture_sum = sum(r[measure] for r in summary_rows if r["land_category"] == category)
            if prefecture_sum != national_totals[measure][category]:
                raise ValueError(f"{measure} {category}: prefectures sum {prefecture_sum} != national {national_totals[measure][category]}")

    measure_columns = ["parcels", "area_m2", "assessed_value_yen", "taxable_base_yen"]
    write_csv(JAPAN_DIR / "japan_prefecture_land_fy2025.csv", summary_rows,
              ["prefecture_name_japanese", "prefecture_code", "land_category"] + measure_columns)
    write_csv(JAPAN_DIR / "japan_prefecture_land_fy2025_detail.csv", detail_rows,
              ["prefecture_name_japanese", "prefecture_code", "land_category", "land_subcategory"] + measure_columns)
    return national_totals


def check_against_national_table(national_totals: dict[str, dict[str, int]]) -> None:
    """The national 総括表 (separate workbook) must agree with the prefecture 合計 row."""
    rows = load_rows(NATIONAL_SUMMARY_XLSX, "00-01-02全国計")
    total_row = next(r for r in rows if r[0] == "合計")
    numbers = [c for c in total_row if isinstance(c, int)]
    # layout: 地積 x3, 決定価格 x3, 課税標準額 総額, 課税標準額 x2, 筆数 x3, 平均価格
    area, assessed_thousand_yen, taxable_thousand_yen, parcels = numbers[0], numbers[3], numbers[6], numbers[9]
    expected = {
        "area_m2": area,
        "assessed_value_yen": assessed_thousand_yen * THOUSAND_YEN,
        "taxable_base_yen": taxable_thousand_yen * THOUSAND_YEN,
        "parcels": parcels,
    }
    for measure, value in expected.items():
        if national_totals[measure]["合計"] != value:
            raise ValueError(f"national 総括表 {measure} {value} != prefecture 合計 {national_totals[measure]['合計']}")


def jis_check_digit(five_digit_code: str) -> int:
    weighted_sum = sum(int(d) * w for d, w in zip(five_digit_code, (6, 5, 4, 3, 2)))
    remainder = 11 - weighted_sum % 11
    return {11: 1, 10: 0}.get(remainder, remainder)


def write_municipality_csv(national_totals: dict[str, dict[str, int]]) -> int:
    rows = load_rows(MUNICIPALITY_SUMMARY_XLSX)
    header = rows[2]
    expected_header_start = ("団体コード", "都道府県名", "市町村名", "表側", "団体区分（５）",
                             "地積・非課税地積（㎡）・（イ）", "地積・評価総地積（㎡）・（ロ）")
    if header[: len(expected_header_start)] != expected_header_start:
        raise ValueError(f"unexpected municipality header: {header}")
    if "決定価格・総額（千円）・（ホ）" != header[9] or "課税標準額・総額（千円）・（チ）" != header[12] or "筆数・評価総筆数（筆）・（ヲ）" != header[16]:
        raise ValueError(f"unexpected municipality value columns: {header}")

    output_rows = []
    body_codes = set()
    for row in rows[3:]:
        if row[0] is None:
            continue
        six_digit_code = f"{int(row[0]):06d}"
        five_digit_code = six_digit_code[:5]
        if jis_check_digit(five_digit_code) != int(six_digit_code[5]):
            raise ValueError(f"bad check digit in 団体コード {six_digit_code}")
        prefecture_code = PREFECTURE_CODE_BY_FULL_NAME[row[1]]
        if five_digit_code[:2] != prefecture_code:
            raise ValueError(f"{six_digit_code} does not match prefecture {row[1]}")
        body_codes.add(five_digit_code)
        if row[3] == "合計":
            category, subcategory = "合計", "計"
        else:
            category, subcategory = row[3].split("・", 1)
        numbers = row[5:20]
        if any(not isinstance(v, int) for v in numbers):
            raise ValueError(f"non-integer cell for {six_digit_code} {row[3]}: {numbers}")
        output_rows.append({
            "municipality_code": five_digit_code,
            "municipality_code_with_check_digit": six_digit_code,
            "prefecture_code": prefecture_code,
            "prefecture_name_japanese": row[1],
            "municipality_name_japanese": row[2],
            "body_class": MUNICIPALITY_BODY_CLASS[row[4]],
            "land_category": category,
            "land_subcategory": subcategory,
            "parcels": row[16],
            "area_m2": row[6],
            "area_nontaxable_m2": row[5],
            "assessed_value_yen": row[9] * THOUSAND_YEN,
            "taxable_base_yen": row[12] * THOUSAND_YEN,
        })

    for measure in ("parcels", "area_m2", "assessed_value_yen", "taxable_base_yen"):
        municipal_sum = sum(r[measure] for r in output_rows if r["land_category"] == "合計")
        if municipal_sum != national_totals[measure]["合計"]:
            raise ValueError(f"municipal {measure} sum {municipal_sum} != national {national_totals[measure]['合計']}")

    write_csv(JAPAN_DIR / "japan_municipality_land_fy2025.csv", output_rows, list(output_rows[0].keys()))
    return len(body_codes)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} rows)")


def extract_and_describe_n03() -> None:
    download_if_missing(N03_ZIP_URL, N03_ZIP)
    with zipfile.ZipFile(N03_ZIP) as archive:
        members = archive.namelist()
        geojson_members = [m for m in members if m.lower().endswith(".geojson")]
        if not geojson_members:
            raise ValueError(f"no GeoJSON in N03 zip; members: {members[:20]}")
        for member in geojson_members:
            target = N03_DIR / Path(member).name
            if not target.exists():
                print(f"extracting {member}")
                with archive.open(member) as source, target.open("wb") as sink:
                    while chunk := source.read(1 << 24):
                        sink.write(chunk)
        print("zip members:", members)

    import fiona

    for geojson_path in sorted(N03_DIR.glob("*.geojson")):
        with fiona.open(geojson_path) as layer:
            prefecture_names = set()
            municipality_codes = set()
            for feature in layer:
                prefecture_names.add(feature["properties"]["N03_001"])
                municipality_codes.add(feature["properties"]["N03_007"])
            print(f"{geojson_path.name}: crs={layer.crs} features={len(layer)} "
                  f"fields={list(layer.schema['properties'])} prefectures={len(prefecture_names)} "
                  f"distinct N03_007={len(municipality_codes)}")


def main() -> None:
    SOUMU_DIR.mkdir(parents=True, exist_ok=True)
    for file_id in SOUMU_FILE_IDS:
        extension = "docx" if file_id == 1077088 else "xlsx"
        download_if_missing(f"{SOUMU_BASE_URL}00{file_id}.{extension}", SOUMU_DIR / f"00{file_id}.{extension}")

    national_totals = write_prefecture_csvs()
    check_against_national_table(national_totals)
    body_count = write_municipality_csv(national_totals)

    assessed = national_totals["assessed_value_yen"]
    print(f"taxing bodies in municipality table: {body_count}")
    print(f"national land 決定価格 合計: {assessed['合計']:,} yen")
    print(f"宅地 決定価格: {assessed['宅地']:,} yen")
    print(f"田+畑 決定価格: {assessed['田'] + assessed['畑']:,} yen")
    print(f"national 評価総地積: {national_totals['area_m2']['合計']:,} m2")

    if "--skip-n03" not in sys.argv:
        extract_and_describe_n03()


if __name__ == "__main__":
    main()

"""Written by AI on 2026.10.16 by model claude fable 5.1.

Japan: official fixed-asset-tax assessed land values (決定価格, 1 January 2025; MIC 固定資産の価格等の概要調書)
by prefecture (47) and by municipality (1,719 taxing bodies), against fixed candidate weights.
Held out: no parameter was fitted on Japan.

Usage: devenv shell -- python -I research/land-value/holdout_japan.py
"""
import csv, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from landgrid import EXPERIMENTS
from holdout_units import load_units, run

RAW = EXPERIMENTS / 'raw/japan'
MAIN_ISLANDS_BBOX = (122.9, 24.0, 146.1, 45.7)   # drops only Minamitorishima (Ogasawara), negligible value


def main():
    pref_values, pref_farm = {}, collections.Counter()
    for row in csv.DictReader(open(RAW / 'japan_prefecture_land_fy2025.csv')):
        if row['land_category'] == '合計':
            pref_values[row['prefecture_code']] = float(row['assessed_value_yen'])
        if row['land_category'] in ('田', '畑'):
            pref_farm['farm'] += float(row['assessed_value_yen'])
    farm_share = pref_farm['farm'] / sum(pref_values.values())
    print(f'Japan: assessed land ¥{sum(pref_values.values())/1e12:,.0f} trn; paddy+field share {farm_share:.1%}')

    prefectures = load_units(RAW / 'mlit_n03_2026/N03-20260101_prefecture.geojson', 'N03_007', 'N03_001',
                             key_fn=lambda p: str(p['N03_007'])[:2])
    run('japan_prefectures', prefectures, pref_values, farm_share=farm_share, bbox=MAIN_ISLANDS_BBOX)

    muni_values, muni_pref, muni_names = {}, {}, {}
    for row in csv.DictReader(open(RAW / 'japan_municipality_land_fy2025.csv')):
        if row['land_category'] == '合計' and row['land_subcategory'] in ('', '合計', '総計', '計'):
            code = row['municipality_code']
            muni_values[code] = muni_values.get(code, 0.0) + float(row['assessed_value_yen'])
            muni_pref[code] = row['prefecture_code']; muni_names[code] = row['municipality_name_japanese']
    if not muni_values:   # subcategory label differs: take every 合計 row once per code
        seen = set()
        for row in csv.DictReader(open(RAW / 'japan_municipality_land_fy2025.csv')):
            if row['land_category'] == '合計' and row['municipality_code'] not in seen:
                seen.add(row['municipality_code'])
                muni_values[row['municipality_code']] = float(row['assessed_value_yen'])
                muni_pref[row['municipality_code']] = row['prefecture_code']; muni_names[row['municipality_code']] = row['municipality_name_japanese']
    print(f'{len(muni_values)} taxing bodies, total ¥{sum(muni_values.values())/1e12:,.0f} trn (should equal the prefecture total)')

    def body_code(props):
        code = str(props['N03_007'])
        if code in muni_values:
            return code
        for candidate in (code[:4] + '0', code[:3] + '00'):   # wards of designated cities and Tokyo's 23 wards
            if candidate in muni_values:
                return candidate
        return None
    municipalities = load_units(RAW / 'mlit_n03_2026/N03-20260101.geojson', 'N03_007', None, key_fn=body_code)
    for code in municipalities:
        municipalities[code] = (muni_names.get(code, code), municipalities[code][1])
    missing = [c for c in muni_values if c not in municipalities]
    print(f'{len(municipalities)} bodies with polygons; {len(missing)} without: {missing[:10]}')
    run('japan_municipalities', municipalities, muni_values, groups=muni_pref, farm_share=farm_share, bbox=MAIN_ISLANDS_BBOX)


if __name__ == '__main__':
    main()

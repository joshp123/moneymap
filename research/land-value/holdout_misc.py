"""Written by AI on 2026.10.16 by model claude fable 5.1.

Held-out tests on fixed candidate weights for:
  korea    17 regions (national balance sheet land assets, market value, year-end 2025, provisional) and
           about 228 districts (officially assessed land prices x area, 1 January 2025)
  bc       British Columbia municipalities (BC Assessment 2026 revised roll, actual land value)
  denmark  98 municipalities (Statistics Denmark ESKAT, taxable land value 2025 = 80% of assessed land value)

Usage: devenv shell -- python -I research/land-value/holdout_misc.py korea|bc|denmark
"""
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from landgrid import EXPERIMENTS
from holdout_units import load_units, run

RAW = EXPERIMENTS / 'raw'

def korea():
    rows = [r for r in csv.DictReader(open(RAW / 'korea/tidy_korea_sido_land_assets_national_balance_sheet.csv')) if r['year'] == '2025' and r['region_code_kosis'] != '00']
    regions = load_units(RAW / 'korea/geoBoundaries-KOR-ADM1.geojson', 'shapeName', 'shapeName')
    values = {}
    for r in rows:   # geoBoundaries uses the same English names as the tidy file (e.g. 'North Chungcheong')
        english = r['region_name_english']
        if english not in regions:
            print('unmatched region', english); continue
        values[english] = float(r['land_value_krw'])
    print(f'Korea regions: {len(values)} matched of {len(rows)}; land ₩{sum(values.values())/1e15:,.0f} quadrillion (national balance sheet, 2025p)')
    run('korea_regions', regions, values, bbox=(124.5, 33.0, 131.0, 38.7))

    districts = load_units(RAW / 'korea/geoBoundaries-KOR-ADM2.geojson', 'shapeID', 'shapeName')
    values, groups = {}, {}
    for r in csv.DictReader(open(RAW / 'korea/tidy_korea_sigungu_assessed_land_value_geoboundaries_units.csv')):
        if r['geoboundaries_adm2_shapeID'] and r['assessed_land_value_krw']:
            k = r['geoboundaries_adm2_shapeID']
            values[k] = values.get(k, 0.0) + float(r['assessed_land_value_krw'])
            groups[k] = r['sido_name_english']
    print(f'Korea districts: {len(values)} with polygons; assessed land ₩{sum(values.values())/1e15:,.0f} quadrillion (2025)')
    run('korea_districts', districts, values, groups=groups, bbox=(124.5, 33.0, 131.0, 38.7))


def bc():
    municipalities = load_units(RAW / 'bc/bc_municipalities_ABMS_MUNICIPALITIES_SP_wgs84.geojson', 'LGL_ADMIN_AREA_ID', 'ADMIN_AREA_NAME')
    values = {}
    for r in csv.DictReader(open(RAW / 'bc/tidy_bc_municipality_land_improvements_2026.csv')):
        if r['municipality_boundary_LGL_ADMIN_AREA_ID'] and r['land_value_cad']:
            values[r['municipality_boundary_LGL_ADMIN_AREA_ID']] = float(r['land_value_cad'])
    print(f'BC: {len(values)} municipalities; land C${sum(values.values())/1e12:.2f} trn (2026 revised roll)')
    run('bc_municipalities', municipalities, values, bbox=(-139.2, 48.2, -114.0, 60.1))


def denmark():
    kommuner = load_units(RAW / 'denmark/geoBoundaries-DNK-ADM2.geojson', 'shapeID', 'shapeName')
    values = {}
    for r in csv.DictReader(open(RAW / 'denmark/tidy_denmark_kommune_taxable_land_value.csv')):
        if r['year'] == '2025' and r['geoboundaries_adm2_shapeID'] and r['taxable_land_value_dkk']:
            values[r['geoboundaries_adm2_shapeID']] = float(r['taxable_land_value_dkk'])
    print(f'Denmark: {len(values)} municipalities; taxable land DKK {sum(values.values())/1e12:.2f} trn (2025)')
    run('denmark_municipalities', kommuner, values, bbox=(8.0, 54.5, 15.3, 57.8))


if __name__ == '__main__':
    {'korea': korea, 'bc': bc, 'denmark': denmark}[sys.argv[1]]()

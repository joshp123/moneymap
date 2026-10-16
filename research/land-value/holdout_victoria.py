"""Written by AI on 2026.10.16 by model claude fable 5.1.

Victoria, Australia: Valuer-General's 2026 general valuation outcome summary, total site value (land only) per
municipality, against fixed candidate weights. Same quantity as the NSW calibration data, different state: a true held-out test.

Usage: devenv shell -- python -I research/land-value/holdout_victoria.py
"""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from landgrid import EXPERIMENTS
from holdout_units import load_units, run

RAW = EXPERIMENTS / 'raw/australia'


def normalise(name):
    name = re.sub(r'\(.*?\)', '', name.upper())
    for token in ['CITY OF ', 'SHIRE OF ', 'RURAL CITY OF ', 'BOROUGH OF ', ' CITY', ' SHIRE', ' RURAL']:
        name = name.replace(token, '')
    return re.sub(r'[^A-Z]', '', name)


def main():
    rows = list(csv.reader(open(RAW / 'vic/2026-outcome-summary.Outcomes-Summary-2026.csv')))
    groups, headers = rows[0], rows[1]
    # the group label sits on the first column of each six-column block
    block_of = {}
    current = None
    for i, g in enumerate(groups):
        if g.strip():
            current = g.strip()
        block_of[i] = current
    sv_total_col = next(i for i, h in enumerate(headers) if h == 'Total' and block_of[i] and block_of[i].endswith('SV'))
    sv_rural_col = next(i for i, h in enumerate(headers) if h == 'Rural' and block_of[i] and block_of[i].endswith('SV'))
    values, rural = {}, 0.0
    for r in rows[2:]:
        if not r or not r[0].strip() or r[0].strip().lower().startswith('total'):
            continue
        values[r[0].strip()] = float(r[sv_total_col].replace(',', ''))
        rural += float(r[sv_rural_col].replace(',', '') or 0)
    total = sum(values.values())
    print(f'Victoria 2026: {len(values)} municipalities, site value A${total/1e9:,.0f}bn, rural share {rural/total:.1%}')

    boundaries = load_units(RAW / 'lga_vic.geojson', 'lga_code_2021', 'lga_name_2021')
    by_norm = {normalise(name): code for code, (name, _) in boundaries.items()}
    coded = {}
    for name, v in values.items():
        key = normalise(name)
        code = by_norm.get(key) or next((c for k, c in by_norm.items() if k.startswith(key) or key.startswith(k)), None)
        if code is None:
            print('unmatched', name); continue
        coded[code] = coded.get(code, 0.0) + v
    print(f'{len(coded)} matched to ABS boundaries')
    run('victoria_councils', boundaries, coded, farm_share=rural / total, bbox=(140.9, -39.3, 150.1, -33.9))


if __name__ == '__main__':
    main()

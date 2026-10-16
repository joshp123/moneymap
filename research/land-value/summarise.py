"""Written by AI on 2026.10.16 by model claude fable 5.1.

Collect the held-out scores written by holdout_*.py into one table (share of land value placed in the wrong unit).
Usage: devenv shell -- python -I research/land-value/summarise.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from landgrid import EXPERIMENTS

TESTS = [   # (file label, display name, held out?)
    ('nsw', 'NSW councils (128), calibration', False),
    ('japan_prefectures', 'Japan prefectures (47)', True),
    ('japan_municipalities', 'Japan municipalities (1,719)', True),
    ('nrw_municipalities', 'NRW municipalities (396)', True),
    ('us_states_larson2009', 'US states (49)', True),
    ('us_counties_residential_land', 'US counties, residential land (2,423)', True),
    ('korea_regions', 'Korea regions (17)', True),
    ('korea_districts', 'Korea districts (228)', True),
    ('bc_municipalities', 'British Columbia municipalities (160)', True),
    ('denmark_municipalities', 'Denmark municipalities (98)', True),
    ('victoria_councils', 'Victoria councils', True),
    ('queensland_councils', 'Queensland councils', True),
]
COLUMNS = [
    ('population', 'population'),
    ('population x access^0.25', 'pop × density^0.25'),
    ('GDP v3 (workplace)', 'GDP layer'),
    ('GDP Kummu (residence)', 'Kummu GDP'),
    ('1/2 population x access^0.25 + 1/2 GDP v3', '½ pop×density^0.25 + ½ GDP'),
    ('1/2 population + 1/2 GDP v3', '½ pop + ½ GDP'),
    ('built volume (all)', 'built volume'),
    ('population x access^0.35', 'pop × density^0.35'),
]


def main():
    rows, sums, counts = [], {c: 0.0 for c, _ in COLUMNS}, {c: 0 for c, _ in COLUMNS}
    for label, name, held_out in TESTS:
        path = EXPERIMENTS / f'{label}_scores.json'
        if not path.exists():
            continue
        scores = json.load(open(path))['scores']
        cells = []
        for key, _ in COLUMNS:
            if key in scores:
                v = scores[key]['misallocated_share']
                cells.append(f'{v:.1%}')
                if held_out:
                    sums[key] += v; counts[key] += 1
            else:
                cells.append('')
        rows.append((name, cells))
    header = '| Test | ' + ' | '.join(h for _, h in COLUMNS) + ' |'
    print(header)
    print('|' + '---|' * (len(COLUMNS) + 1))
    for name, cells in rows:
        print(f'| {name} | ' + ' | '.join(cells) + ' |')
    print('| **Mean over held-out tests** | ' + ' | '.join(f'**{sums[k]/counts[k]:.1%}**' if counts[k] else '' for k, _ in COLUMNS) + ' |')
    json.dump({'rows': rows, 'held_out_mean': {k: sums[k] / counts[k] for k, _ in COLUMNS if counts[k]}}, open(EXPERIMENTS / 'summary.json', 'w'), indent=1)


if __name__ == '__main__':
    main()

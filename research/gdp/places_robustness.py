"""Written by AI on 2026.10.16 by model claude opus 5.5.

Robustness for the places experiment: per-group win rates against production,
and place coverage per person by country (where no hold-out test exists).
"""
from collections import defaultdict
import json
import sys

import numpy as np

from places_eval import BUILD, OUTPUT, WEIGHTINGS, predict

PRODUCTION = '(a) 0.5 pop + 0.5 q [production]'
CANDIDATES = ['(d) 1/3 pop + 1/3 q + 1/3 places', '(f) 1/3 pop + 1/3 q + 1/3 workplace places']


def group_errors(data, weighting):
    keep, official, predicted, _ = predict(data, weighting)
    groups = np.asarray(data['group'])[keep]
    error, total = defaultdict(float), defaultdict(float)
    for g, o, p in zip(groups, official, predicted):
        error[g] += 0.5 * abs(p - o)
        total[g] += o
    return error, total


result = {}
for key in ('us', 'uk', 'eu', 'br'):
    data = json.loads((OUTPUT / f'{key}_sums.json').read_text())
    base, total = group_errors(data, WEIGHTINGS[PRODUCTION])
    informative = [g for g in base if base[g] > 0]
    for label in CANDIDATES:
        error, _ = group_errors(data, WEIGHTINGS[label])
        better = [g for g in informative if error[g] < base[g]]
        result[f'{key} {label}'] = dict(groups=len(informative), better=len(better),
                                        gdp_share_in_better_groups=sum(total[g] for g in better) / sum(total[g] for g in informative))
        print(f"{key}: {label}: better in {len(better)}/{len(informative)} groups, holding {result[f'{key} {label}']['gdp_share_in_better_groups']*100:.0f}% of GDP")

sums = dict(np.load(OUTPUT / 'unit_sums.npz'))
units = json.loads((BUILD / 'conservation.json').read_text())['units']
country = np.array([''] + [u['country'] for u in units])
coverage = {}
for code in sorted(set(country) - {''}):
    members = country == code
    pop = sums['pop'][members].sum()
    if pop > 2e7:
        coverage[code] = dict(population_m=pop / 1e6, places_per_1000=1000 * sums['places'][members].sum() / pop,
                              workplace_places_per_1000=1000 * sums['workplace_places'][members].sum() / pop)
result['coverage'] = coverage
print('\nPlaces per 1,000 people, countries over 20 million people (sorted by workplace places):')
for code, c in sorted(coverage.items(), key=lambda item: item[1]['workplace_places_per_1000']):
    print(f"  {code} pop {c['population_m']:.0f}m  places {c['places_per_1000']:.1f}  workplace {c['workplace_places_per_1000']:.2f}")
(OUTPUT / 'robustness.json').write_text(json.dumps(result, indent=2) + '\n')

"""Written by AI on 2026.10.16 by model claude opus 5.5.

What weighting (f) does where Overture coverage is thin: cell concentration in
China and India, and circles in central business districts outside the tests.
"""
import json

import numpy as np
import rasterio
from rasterio.windows import from_bounds

import places_eval
from places_eval import BUILD, OUTPUT, WEIGHTINGS, Layers, component_weights

A = WEIGHTINGS['(a) 0.5 pop + 0.5 q [production]']
F = WEIGHTINGS['(f) 1/3 pop + 1/3 q + 1/3 workplace places']
sums = dict(np.load(OUTPUT / 'unit_sums.npz'))
units = json.loads((BUILD / 'conservation.json').read_text())['units']
totals = np.array([0.] + [u['target'] for u in units])
totals[(sums['pop'] == 0) & (sums['q'] == 0)] = 0
country = np.array([''] + [u['country'] for u in units])


def cells(values, labels, weighting):
    weights = component_weights(weighting, sums)
    out = np.zeros(labels.shape)
    for component in weighting:
        factor = np.divide(totals * weights[component], sums[component], out=np.zeros_like(totals), where=sums[component] > 0)
        out += values[component] * factor[labels]
    return out


result = {}
with Layers() as layers, rasterio.open(BUILD / 'control-ids.tif') as labels_source:
    for code, bounds in [('CHN', (73.0, 18.0, 135.5, 54.0)), ('IND', (68.0, 6.0, 98.0, 37.5)), ('JPN', (122.0, 24.0, 146.0, 46.0))]:
        window = from_bounds(*bounds, layers.gdp.transform).round_offsets().round_lengths()
        labels = labels_source.read(1, window=window)
        labels[country[labels] != code] = 0
        values = layers.read(window)
        row = {}
        for name, weighting in (('a', A), ('f', F)):
            gdp = np.sort(cells(values, labels, weighting).ravel())[::-1]
            row[name] = dict(top100_share=gdp[:100].sum() / gdp.sum(), top1000_share=gdp[:1000].sum() / gdp.sum(), max_cell_bn=gdp[0] / 1e9)
        result[code] = row
        print(code, {k: {m: round(v, 3) for m, v in r.items()} for k, r in row.items()})
    places_eval.CIRCLES = [('Shanghai Lujiazui', 31.2397, 121.4998, 3), ('Beijing Guomao', 39.9087, 116.4605, 3),
                           ('Shenzhen Futian', 22.5410, 114.0560, 3), ('Mumbai Bandra Kurla', 19.0660, 72.8680, 3),
                           ('Lagos Victoria Island', 6.4281, 3.4219, 3), ('Tokyo Marunouchi', 35.6812, 139.7671, 3),
                           ('Tokyo Marunouchi', 35.6812, 139.7671, 10)]
    with rasterio.open(BUILD / 'gdp.tif') as built:
        circles = places_eval.circle_values(layers, units, sums, labels_source, built, {'a': A, 'f': F})
    for c in circles:
        print(f"{c['name']} {c['radius_km']} km: (a) {c['a']/1e9:.0f}bn  (f) {c['f']/1e9:.0f}bn  main unit {c['main_unit']['name']} "
              f"{c['main_unit']['target']/1e9:.0f}bn; inside: pop {c['main_unit'].get('pop_inside', 0)*100:.1f}% q {c['main_unit'].get('q_inside', 0)*100:.1f}% "
              f"workplace {c['main_unit'].get('workplace_places_inside', 0)*100:.1f}%")
    result['circles'] = circles
(OUTPUT / 'thin_coverage.json').write_text(json.dumps(result, indent=2, default=float) + '\n')

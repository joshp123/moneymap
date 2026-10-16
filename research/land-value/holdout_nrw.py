"""Written by AI on 2026.10.16 by model claude fable 5.1.

North Rhine-Westphalia: gridded official standard land values (see grid_nrw.py) against fixed candidate
weights, at three scales: 396 municipalities, 53 districts, and circles of 3 to 50 km around twelve places.
Held out: no parameter was fitted here.

Usage: devenv shell -- python -I research/land-value/holdout_nrw.py   (after grid_nrw.py)
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from landgrid import EXPERIMENTS, Region, unit_sums, candidate_weights, score, mix
from holdout_units import load_units, run
from grid_nrw import NRW_BBOX

RAW = EXPERIMENTS / 'raw/nrw'
CIRCLE_CENTRES = {   # name: (lon, lat)
    'Köln Dom': (6.9578, 50.9413), 'Düsseldorf Kö': (6.7793, 51.2254), 'Essen Hbf': (7.0147, 51.4514),
    'Dortmund centre': (7.4653, 51.5136), 'Münster Prinzipalmarkt': (7.6280, 51.9620), 'Bielefeld centre': (8.5325, 52.0302),
    'Aachen centre': (6.0839, 50.7753), 'Bonn centre': (7.0982, 50.7374),
    'Schmallenberg (Sauerland, rural)': (8.2863, 51.1548), 'Hellenthal (Eifel, rural)': (6.4318, 50.4877),
    'Südlohn (Münsterland farmland)': (6.8680, 51.9390), 'Höxter (rural east)': (9.3744, 51.7752),
}
RADII_KM = (3, 5, 10, 20, 30, 50)


def main():
    official = np.load(EXPERIMENTS / 'nrw_official_grid.npz')
    value = official['value']
    farm_share = float(official['value_agri'].sum() / value.sum())
    region = Region(*NRW_BBOX)
    assert value.shape == region.pop.shape, (value.shape, region.pop.shape)

    # ---- units: municipalities and districts, official value = gridded value summed inside ----
    municipalities = load_units(RAW / 'dvg/dvg1_gemeinden_4326.geojson', 'KN', 'GN')
    keys = sorted(municipalities)
    labels = region.rasterize_units((g, i + 1) for i, k in enumerate(keys) for g in municipalities[k][1])
    muni_values = dict(zip(keys, unit_sums(labels, value, len(keys))))
    district_of = {k: k[:5] for k in keys}
    print(f'NRW gridded official land value €{value.sum()/1e12:.2f} trn, farmland share {farm_share:.1%}; '
          f'{len(keys)} municipalities hold €{sum(muni_values.values())/1e12:.2f} trn of it')
    run('nrw_municipalities', municipalities, muni_values, groups=district_of, farm_share=farm_share, bbox=NRW_BBOX)

    # ---- circles ----
    weights = candidate_weights(region)
    candidates = {name: weights[name] for name in ('population', 'population x access^0.25', 'GDP v3 (workplace)', 'built volume (all)')}
    candidates['1/2 population x access^0.25 + 1/2 GDP v3'] = (
        0.5 * weights['population x access^0.25'] / weights['population x access^0.25'].sum() + 0.5 * weights['GDP v3 (workplace)'] / weights['GDP v3 (workplace)'].sum())
    candidates[f'population x access^0.25 + cropland {farm_share:.0%}'] = (
        (1 - farm_share) * weights['population x access^0.25'] / weights['population x access^0.25'].sum() + farm_share * weights['cropland (SPAM)'] / weights['cropland (SPAM)'].sum())
    rows = []
    official_total = value.sum()
    print('\nCircles: model ÷ official (both as shares of the NRW total)')
    header = f'{"place":34s}' + ''.join(f'{r:>7d}km' for r in RADII_KM)
    for name, field in candidates.items():
        print(f'\n[{name}]\n{header}')
        field_total = field.sum()
        for place, (lon, lat) in CIRCLE_CENTRES.items():
            ratios = []
            for r in RADII_KM:
                m = region.circle_mask(lon, lat, r)
                official_share = value[m].sum() / official_total
                model_share = field[m].sum() / field_total
                ratio = model_share / official_share if official_share > 0 else float('nan')
                ratios.append(ratio)
                rows.append({'candidate': name, 'place': place, 'radius_km': r, 'official_eur_bn': float(value[m].sum() / 1e9),
                             'official_share': float(official_share), 'model_share': float(model_share), 'ratio': float(ratio)})
            print(f'{place:34s}' + ''.join(f'{x:9.2f}' for x in ratios))
        # summary: median |log ratio| by radius
        print(f'{"median |log ratio| over places":34s}' + ''.join(
            f'{np.nanmedian([abs(np.log(x["ratio"])) for x in rows if x["candidate"] == name and x["radius_km"] == r]):9.3f}' for r in RADII_KM))
    json.dump({'farm_share': farm_share, 'circles': rows}, open(EXPERIMENTS / 'nrw_circles.json', 'w'), indent=1)
    print('\nOfficial value in the 10 km circles (€bn): ' + ', '.join(
        f'{x["place"]} {x["official_eur_bn"]:.0f}' for x in rows if x['candidate'] == 'population' and x['radius_km'] == 10))


if __name__ == '__main__':
    main()

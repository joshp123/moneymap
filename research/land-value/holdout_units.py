"""Written by AI on 2026.10.16 by model claude fable 5.1.

Generic held-out test: official land-only values per unit (council, municipality, prefecture, state)
against fixed candidate weights summed over the same units. Parameters are fixed in landgrid.py.

Usage:
  devenv shell -- python -I research/land-value/holdout_units.py --label japan_pref \
      --units path/to/units.geojson --id-field CODE --values path/to/values.csv --value-field land_value \
      [--name-field NAME] [--group-field PREF] [--farm-share 0.08] [--bbox W S E N]

values.csv must have a column named like --id-field (or --values-id-field) and the value column.
"""
import argparse, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I drops the script directory
import numpy as np
from shapely.geometry import shape
from landgrid import EXPERIMENTS, Region, unit_sums, candidate_weights, score, mix

URBAN_CANDIDATES = ['population', 'population x access^0.25', 'GDP v3 (workplace)', 'GDP Kummu (residence)',
                    'built volume (all)', 'built volume x access^0.25', 'non-residential q',
                    'built surface (all)', 'built surface x access^0.25']


def load_units(path, id_field, name_field=None, key_fn=None, where=None):
    """{key: (name, [shapely geometries])}. Multi-part units keep a list; no union is needed to rasterise."""
    import fiona
    units = {}
    with fiona.open(path) as source:
        for f in source:
            if f.geometry is None:
                continue
            props = dict(f.properties)
            if where and not where(props):
                continue
            key = key_fn(props) if key_fn else str(props[id_field]).strip()
            if key is None:
                continue
            name = str(props.get(name_field, key)) if name_field else key
            units.setdefault(key, (name, []))[1].append(shape(dict(f.geometry)))
    return units


def load_values(path, id_field, value_field, group_field=None):
    values, groups = {}, {}
    for row in csv.DictReader(open(path)):
        key = str(row[id_field]).strip()
        if not row.get(value_field):
            continue
        v = float(str(row[value_field]).replace(',', ''))
        values[key] = values.get(key, 0.0) + v
        if group_field:
            groups[key] = row[group_field]
    return values, groups


def run(label, units, values, groups=None, farm_share=None, bbox=None, tau_km=40.0, gamma=0.25, extra_mixes=None, print_worst=True):
    keys = [k for k in units if k in values and values[k] > 0]
    missing_geometry = [k for k in values if k not in units]
    if missing_geometry:
        print(f'{len(missing_geometry)} valued units without geometry (first: {missing_geometry[:5]})')
    geoms = [units[k][1] for k in keys]
    actual = np.array([values[k] for k in keys])
    if bbox is None:
        b = np.array([g.bounds for parts in geoms for g in parts])
        bbox = (b[:, 0].min() - 0.1, b[:, 1].min() - 0.1, b[:, 2].max() + 0.1, b[:, 3].max() + 0.1)
    print(f'{label}: {len(keys)} units, total {actual.sum():,.0f}; bbox {tuple(round(x, 2) for x in bbox)}')
    region = Region(*bbox)
    labels = region.rasterize_units((g, i + 1) for i, parts in enumerate(geoms) for g in parts)
    weights = candidate_weights(region, tau_km=tau_km, gamma=gamma)
    sums = {name: unit_sums(labels, field, len(keys)) for name, field in weights.items()}
    empty = int((np.array([sums['population'][i] + sums['area'][i] for i in range(len(keys))]) == 0).sum())
    if empty:
        print(f'{empty} units contain no cell centre (they score as zero prediction)')

    results = {}
    def report(name, predicted):
        s = score(predicted, actual)
        if groups:
            g = np.array([groups.get(k, '') for k in keys])
            pred_scaled = predicted / predicted.sum() * actual.sum()
            s['group_misallocated_share'] = float(sum(abs(pred_scaled[g == x].sum() - actual[g == x].sum()) for x in set(g)) / 2 / actual.sum())
        results[name] = s
        extra = f'   groups {s["group_misallocated_share"]:5.1%}' if groups else ''
        print(f'  {name:55s} wrong unit {s["misallocated_share"]:6.1%}{extra}   median |log ratio| {s["median_abs_log_ratio"]:.3f}')

    for name in URBAN_CANDIDATES:
        if name in sums:
            report(name, sums[name])
    report('3/4 population + 1/4 GDP v3', mix(sums, {'population': 0.75, 'GDP v3 (workplace)': 0.25}))
    report('1/2 population + 1/2 GDP v3', mix(sums, {'population': 0.5, 'GDP v3 (workplace)': 0.5}))
    report('1/2 population x access^0.25 + 1/2 GDP v3', mix(sums, {'population x access^0.25': 0.5, 'GDP v3 (workplace)': 0.5}))
    report('1/2 population + 1/2 built volume', mix(sums, {'population': 0.5, 'built volume (all)': 0.5}))
    print('  --- exponent sensitivity ---')
    for name in ('population x access^0.15', 'population x access^0.35', 'population x access^0.5'):
        report(name, sums[name])
    if farm_share is not None:
        print(f'  --- with farmland share {farm_share:.0%} ---')
        for urban in ['population', 'population x access^0.25', 'built volume (all)']:
            if 'cropland (SPAM)' in sums:
                report(f'{urban} + cropland', mix(sums, {urban: 1 - farm_share, 'cropland (SPAM)': farm_share}))
            report(f'{urban} + area', mix(sums, {urban: 1 - farm_share, 'area': farm_share}))
            if 'cropland (SPAM)' in sums:
                report(f'{urban} + half cropland half area', mix(sums, {urban: 1 - farm_share, 'cropland (SPAM)': farm_share / 2, 'area': farm_share / 2}))
    for name, coefficients in (extra_mixes or {}).items():
        report(name, mix(sums, coefficients))

    if print_worst:
        for name in ['population', 'population x access^0.25']:
            pred = sums[name] / sums[name].sum() * actual.sum()
            with np.errstate(divide='ignore'):
                ratio = np.log(np.where(pred > 0, pred, 1e-9) / actual)
            order = np.argsort(ratio)
            print(f'  {name}: under-predicted ' + ', '.join(f'{units[keys[i]][0]} ({np.exp(ratio[i]):.2f}x)' for i in order[:5])
                  + '; over-predicted ' + ', '.join(f'{units[keys[i]][0]} ({np.exp(ratio[i]):.2f}x)' for i in order[-5:]))

    EXPERIMENTS.mkdir(parents=True, exist_ok=True)
    per_unit = {k: {'name': units[k][0], 'actual': float(values[k]),
                    **{n: float(sums[n][i] / sums[n].sum() * actual.sum()) for n in ('population', 'population x access^0.25', 'built volume (all)', 'GDP v3 (workplace)')}}
                for i, k in enumerate(keys)}
    json.dump({'label': label, 'n_units': len(keys), 'total': float(actual.sum()), 'bbox': [float(x) for x in bbox],
               'scores': results, 'per_unit': per_unit}, open(EXPERIMENTS / f'{label}_scores.json', 'w'), indent=1)
    return results, sums, keys, actual


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', required=True)
    ap.add_argument('--units', required=True)
    ap.add_argument('--id-field', required=True)
    ap.add_argument('--name-field')
    ap.add_argument('--values', required=True)
    ap.add_argument('--values-id-field')
    ap.add_argument('--value-field', required=True)
    ap.add_argument('--group-field')
    ap.add_argument('--farm-share', type=float)
    ap.add_argument('--bbox', type=float, nargs=4)
    a = ap.parse_args()
    units = load_units(a.units, a.id_field, a.name_field)
    values, groups = load_values(a.values, a.values_id_field or a.id_field, a.value_field, a.group_field)
    run(a.label, units, values, groups or None, a.farm_share, tuple(a.bbox) if a.bbox else None)


if __name__ == '__main__':
    main()

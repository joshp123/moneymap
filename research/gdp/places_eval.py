"""Written by AI on 2026.10.16 by model claude opus 5.5.

Experiment: are Overture places per cell a better workplace proxy than GHSL q?

    nix shell nixpkgs#duckdb -c duckdb < sources/overture_places.sql
    nix shell nixpkgs#duckdb -c duckdb -c "COPY (FROM 'data/raw/overture/places_per_cell.parquet') TO '/tmp/moneymap-places/places_per_cell.csv' (HEADER)"
    devenv shell -- python research/gdp/places_eval.py sums us|uk|eu|br|units
    devenv shell -- python research/gdp/places_eval.py report

`sums` writes per-unit sums of population, q and place counts on the GHS-POP
grid to data/experiments/places/. `report` scores each weighting on the held-out
tests and recomputes the named circles from the production control totals.
Production code is imported, never changed.
"""
from collections import defaultdict
from contextlib import ExitStack
import glob
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
from affine import Affine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from layers.gdp.building_weight import building_weight_q as shifted_q  # noqa: E402
from layers.gdp.cell_ownership import PolygonIndex, sum_by_unit as grouped_sum  # noqa: E402
from layers.grid import (bounding_window, open_kummu_gdp_and_population as open_sources,  # noqa: E402
                         open_zipped_raster as open_zip_raster, read_window_zero_filled as clean_window, window_strips)
from sources.regional_gdp import REGIONAL_GDP_SOURCES as RAW, load_us_controls  # noqa: E402

# This experiment scored the second GDP build, before workplace places and jobs were added.
BUILD = ROOT / 'data/gdp-v2'
CIRCLES = [
    ('Midtown and Lower Manhattan', 40.73756, -73.99429, 6),
    ('Bank', 51.5133, -0.0886, 3), ('Canary Wharf', 51.5054, -0.0235, 3),
    ('Heathrow', 51.4700, -0.4543, 3), ('Zuidas', 52.3383, 4.8728, 3),
    ('Schiphol', 52.3105, 4.7683, 3), ('Maasvlakte', 51.9600, 4.0300, 5),
    ('Rotterdam', 51.93467, 4.55658, 50),
    ('Tokyo Marunouchi', 35.6812, 139.7671, 3), ('La Défense', 48.8920, 2.2380, 3),
]

import os
PLACES_CSV = Path(os.environ.get('PLACES_CSV', '/tmp/moneymap-places/places_per_cell.csv'))
OUTPUT = Path(os.environ.get('PLACES_OUTPUT', ROOT / 'data/experiments/places'))
PLACE_LAYERS = ('places', 'places_conf50', 'workplace_places', 'workplace_places_conf50')
LAYERS = ('pop', 'q') + PLACE_LAYERS
STRIP_ROWS = 240

WEIGHTINGS = {
    'population only': {'pop': 1},
    '(a) 0.5 pop + 0.5 q [production]': {'pop': .5, 'q': .5},
    '(b) 0.5 pop + 0.5 places': {'pop': .5, 'places': .5},
    '(c) places alone': {'places': 1},
    '(d) 1/3 pop + 1/3 q + 1/3 places': {'pop': 1/3, 'q': 1/3, 'places': 1/3},
    '(e) 0.5 pop + 0.5 workplace places': {'pop': .5, 'workplace_places': .5},
    '(f) 1/3 pop + 1/3 q + 1/3 workplace places': {'pop': 1/3, 'q': 1/3, 'workplace_places': 1/3},
}


class PlaceGrid:
    """Place counts per GHS-POP cell, sorted by row for window lookups."""

    def __init__(self, width, height, path=PLACES_CSV):
        data = np.loadtxt(path, delimiter=',', skiprows=1, dtype=np.int64, ndmin=2).reshape(-1, 2 + len(PLACE_LAYERS))
        inside = (data[:, 0] >= 0) & (data[:, 0] < width) & (data[:, 1] >= 0) & (data[:, 1] < height)
        self.outside_grid = data[~inside, 2:].sum(axis=0)
        data = data[inside]
        data = data[np.argsort(data[:, 1], kind='stable')]
        self.cols, self.rows, self.counts = data[:, 0], data[:, 1], data[:, 2:].astype('float64')
        self.totals = self.counts.sum(axis=0)

    def window(self, window):
        row0, col0 = int(window.row_off), int(window.col_off)
        height, width = int(window.height), int(window.width)
        low, high = np.searchsorted(self.rows, [row0, row0 + height])
        cols = self.cols[low:high]
        keep = (cols >= col0) & (cols < col0 + width)
        output = np.zeros((len(PLACE_LAYERS), height, width))
        output[:, self.rows[low:high][keep] - row0, cols[keep] - col0] = self.counts[low:high][keep].T
        return output


class Layers:
    """Population, shifted q and place counts for any GHS-POP window."""

    def __enter__(self):
        self.stack = ExitStack()
        self.gdp, self.population = open_sources()
        for source in (self.gdp, self.population):
            self.stack.enter_context(source)
        self.volume = self.stack.enter_context(open_zip_raster(RAW / 'nres_v_30ss.zip'))
        self.surface = self.stack.enter_context(open_zip_raster(RAW / 'nres_s_30ss.zip'))
        self.places = PlaceGrid(self.gdp.width, self.gdp.height)
        return self

    def __exit__(self, *exc):
        self.stack.close()

    def read(self, window):
        values = {'pop': clean_window(self.population, 1, window).astype('float64'),
                  'q': shifted_q(self.volume, self.surface, window, self.gdp)}
        values.update(zip(PLACE_LAYERS, self.places.window(window)))
        return values


def polygon_index(geometries):
    return PolygonIndex([SimpleNamespace(geometry=geometry) for geometry in geometries])


def cell_centre_sums(layers, geometries, bounds):
    """Sum every layer over polygons by cell centre, as production does."""
    index = polygon_index(geometries)
    sums = {name: np.zeros(len(geometries) + 1) for name in LAYERS}
    for window in window_strips(layers.gdp, bounds):
        labels = index.labels(window, layers.gdp.transform)
        for name, values in layers.read(window).items():
            sums[name] += grouped_sum(labels, values, len(geometries))
    return {name: values[1:] for name, values in sums.items()}


def area_share_sums(layers, geometries, bounds, sub=10):
    """Sum every layer over small polygons, splitting each cell into sub x sub parts."""
    grid = layers.gdp
    window = from_bounds(*bounds, grid.transform).round_offsets().round_lengths()
    values = layers.read(window)
    height, width = int(window.height), int(window.width)
    fine_transform = grid.window_transform(window) * Affine.scale(1 / sub)
    labels = rasterize([(geometry, i + 1) for i, geometry in enumerate(geometries)],
                       out_shape=(height * sub, width * sub), transform=fine_transform, fill=0, dtype='int32')
    cell = (np.arange(height * sub)[:, None] // sub) * width + (np.arange(width * sub)[None, :] // sub)
    pairs, counts = np.unique(cell.astype('int64').ravel() * (len(geometries) + 1) + labels.ravel(), return_counts=True)
    del labels, cell
    pair_cells, pair_labels = pairs // (len(geometries) + 1), pairs % (len(geometries) + 1)
    fractions = counts / (sub * sub)
    return {name: np.bincount(pair_labels, weights=layer.ravel()[pair_cells] * fractions,
                              minlength=len(geometries) + 1)[1:] for name, layer in values.items()}


def save(name, data):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clean = {key: value.tolist() if isinstance(value, np.ndarray) else value for key, value in data.items()}
    (OUTPUT / f'{name}_sums.json').write_text(json.dumps(clean) + '\n')
    print(name, 'units', len(data['ids']), flush=True)


def us_sums(layers):
    """State to county, with the same county controls and cell labels as production."""
    counties = load_us_controls(RAW)
    states = defaultdict(list)
    for county in counties:
        states[county.parent_code].append(county)
    result = defaultdict(list)
    for state, units in sorted(states.items()):
        index = PolygonIndex(units)
        bounds = (min(g.bounds[0] for g in index.geometries), min(g.bounds[1] for g in index.geometries),
                  max(g.bounds[2] for g in index.geometries), max(g.bounds[3] for g in index.geometries))
        sums = {name: np.zeros(len(units) + 1) for name in LAYERS}
        for window in window_strips(layers.gdp, bounds):
            labels = index.labels(window, layers.gdp.transform)
            for name, values in layers.read(window).items():
                sums[name] += grouped_sum(labels, values, len(units))
        result['ids'] += [unit.code for unit in units]
        result['names'] += [unit.name for unit in units]
        result['group'] += [state] * len(units)
        result['official'] += [unit.value for unit in units]
        for name in LAYERS:
            result[name] += sums[name][1:].tolist()
        print('US state', state, flush=True)
    save('us', dict(result, keep_single_unit_groups=True))


def uk_sums(layers):
    """England and Wales LSOAs by area share, aggregated to MSOAs within local authorities."""
    geometry = {}
    for path in sorted(glob.glob(str(RAW / 'lsoa/p*.geojson'))):
        for feature in json.loads(Path(path).read_text())['features']:
            geometry[feature['properties']['LSOA11CD']] = feature['geometry']
    gva = json.loads((RAW / 'uk_lsoa_gva.json').read_text())
    ids = [code for code in gva if code in geometry]
    sums = area_share_sums(layers, [geometry[code] for code in ids], (-6.0, 49.8, 2.0, 55.9))
    msoa = defaultdict(lambda: defaultdict(float))
    parent = {}
    for i, code in enumerate(ids):
        key = gva[code]['msoa']
        parent[key] = gva[code]['lad']
        msoa[key]['official'] += gva[code]['gva'] * 1e6
        for name in LAYERS:
            msoa[key][name] += sums[name][i]
    keys = sorted(msoa)
    data = {'ids': keys, 'names': keys, 'group': [parent[key] for key in keys]}
    for name in ('official',) + LAYERS:
        data[name] = [msoa[key][name] for key in keys]
    data['lsoas'] = len(ids)
    save('uk', data)


def eu_sums(layers):
    """NUTS3 within NUTS2, same regions and GDP as the earlier research."""
    previous = json.loads((RAW / 'eu_sums.json').read_text())
    features = {f['properties']['NUTS_ID']: f for f in json.loads((RAW / 'nuts3_2024_03m.geojson').read_text())['features']}
    ids = previous['ids']
    sums = cell_centre_sums(layers, [features[code]['geometry'] for code in ids], (-32.0, 27.0, 45.0, 72.0))
    save('eu', dict(ids=ids, names=[features[code]['properties']['NUTS_NAME'] for code in ids],
                    group=[code[:4] for code in ids], official=[v * 1e6 for v in previous['gdp2023_meur']], **sums))


def br_sums(layers):
    """Brazil municipality within state, IBGE 2023."""
    features = json.loads((RAW / 'br_mun.geojson').read_text())['features']
    ids = [str(f['properties']['codarea']) for f in features]
    gdp = {row['D1C']: float(row['V']) * 1000 for row in json.loads((RAW / 'br_pib_2023.json').read_text())[1:]
           if row['V'] not in ('-', '...', 'X')}
    sums = cell_centre_sums(layers, [f['geometry'] for f in features], (-74.5, -34.0, -28.5, 5.5))
    save('br', dict(ids=ids, names=ids, group=[code[:2] for code in ids],
                    official=[gdp.get(code, float('nan')) for code in ids], **sums))


def unit_sums(layers):
    """Per production control unit, over the whole globe, using the production cell labels."""
    conservation = json.loads((BUILD / 'conservation.json').read_text())
    count = len(conservation['units'])
    sums = {name: np.zeros(count + 1) for name in LAYERS}
    with rasterio.open(BUILD / 'control-ids.tif') as labels_source:
        for row in range(0, layers.gdp.height, STRIP_ROWS):
            window = Window(0, row, layers.gdp.width, min(STRIP_ROWS, layers.gdp.height - row))
            labels = labels_source.read(1, window=window)
            for name, values in layers.read(window).items():
                sums[name] += grouped_sum(labels, values, count)
            if row % 2400 == 0:
                print('global row', row, flush=True)
    np.savez(OUTPUT / 'unit_sums.npz', **sums)
    summary = {name: float(values.sum()) for name, values in sums.items()}
    summary['place_totals_in_grid'] = dict(zip(PLACE_LAYERS, layers.places.totals.tolist()))
    summary['place_totals_outside_grid'] = dict(zip(PLACE_LAYERS, layers.places.outside_grid.tolist()))
    summary['place_cells'] = int(len(layers.places.rows))
    (OUTPUT / 'unit_sums_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


# ---- Scoring -------------------------------------------------------------

def component_weights(weighting, sums):
    """Weights per group or unit, renormalised over components present (production rule)."""
    present = {name: sums[name] > 0 for name in weighting}
    total = sum(weight * present[name] for name, weight in weighting.items())
    return {name: np.divide(weight * present[name], total, out=np.zeros_like(total, dtype='float64'), where=total > 0)
            for name, weight in weighting.items()}


def predict(data, weighting):
    """Spread each group's official total over its units with the weighting."""
    official = np.asarray(data['official'], dtype='float64')
    group = np.asarray(data['group'])
    keep = np.isfinite(official) & (official > 0)
    groups, inverse = np.unique(group[keep], return_inverse=True)
    sizes = np.bincount(inverse)
    # Production's US check keeps Washington DC, a one-county group; the earlier
    # UK, EU and Brazil research dropped one-unit groups.
    if not data.get('keep_single_unit_groups'):
        keep[np.where(keep)[0][sizes[inverse] < 2]] = False
    groups, inverse = np.unique(group[keep], return_inverse=True)
    target = official[keep]
    group_total = np.bincount(inverse, weights=target)
    unit_values = {name: np.asarray(data[name], dtype='float64')[keep] for name in weighting}
    group_sums = {name: np.bincount(inverse, weights=values) for name, values in unit_values.items()}
    weights = component_weights(weighting, group_sums)
    share = sum(weights[name][inverse] * np.divide(unit_values[name], group_sums[name][inverse],
                                                   out=np.zeros_like(target), where=group_sums[name][inverse] > 0)
                for name in weighting)
    return keep, target, group_total[inverse] * share, len(groups)


def score(data, weighting):
    keep, official, predicted, groups = predict(data, weighting)
    ratio = np.maximum(predicted, 1e-12 * official) / official
    return dict(misallocated=float(0.5 * np.abs(predicted - official).sum() / official.sum()),
                median_abs_log=float(np.median(np.abs(np.log(ratio)))),
                units=int(keep.sum()), groups=groups, zero_predictions=int((predicted <= 0).sum()))


def unit_share(data, weighting, code, group_code):
    """A unit's predicted and official share of its group."""
    ids, group = np.asarray(data['ids']), np.asarray(data['group'])
    members = group == group_code
    i = int(np.where(ids == code)[0][0])
    sums = {name: np.asarray(data[name], dtype='float64')[members].sum() for name in weighting}
    weights = component_weights(weighting, {name: np.array([value]) for name, value in sums.items()})
    predicted = sum(float(weights[name][0]) * data[name][i] / sums[name] for name in weighting if sums[name] > 0)
    official = np.asarray(data['official'], dtype='float64')
    return predicted, data['official'][i] / official[members].sum()


def circle_values(layers, units, sums, labels_source, built, weightings):
    """Circle GDP per weighting, from production control totals and per-unit sums."""
    totals = np.array([0.] + [unit['target'] for unit in units])
    # Production puts units without population or q at their centroid cell. Keep
    # them there in every weighting, rather than spreading them by places too.
    totals[(sums['pop'] == 0) & (sums['q'] == 0)] = 0
    results = []
    for name, latitude, longitude, radius in CIRCLES:
        angular = radius / 6371.0088
        lat_span = math.degrees(angular)
        lon_span = math.degrees(math.asin(min(1, math.sin(angular) / math.cos(math.radians(latitude)))))
        window = bounding_window(layers.gdp, (longitude - lon_span, latitude - lat_span, longitude + lon_span, latitude + lat_span))
        rows = layers.gdp.transform.f + (np.arange(window.row_off, window.row_off + window.height) + .5) * layers.gdp.transform.e
        cols = layers.gdp.transform.c + (np.arange(window.col_off, window.col_off + window.width) + .5) * layers.gdp.transform.a
        lat, lon = np.radians(rows[:, None]), np.radians(cols[None, :])
        lat0, lon0 = np.radians([latitude, longitude])
        h = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2
        inside = 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(h, 0, 1))) <= radius
        labels = labels_source.read(1, window=window)
        values = layers.read(window)
        production = clean_window(built, 1, window).astype('float64')

        def allocate(weighting):
            weights = component_weights(weighting, sums)
            cells = np.zeros(labels.shape)
            for component in weighting:
                factor = np.divide(totals * weights[component], sums[component],
                                   out=np.zeros_like(totals), where=sums[component] > 0)
                cells += values[component] * factor[labels]
            return cells

        # Centroid fallbacks (units without any population or q cell) are taken from
        # the production raster and kept for every weighting.
        fallback = production - allocate(WEIGHTINGS['(a) 0.5 pop + 0.5 q [production]'])
        noise = np.abs(fallback) > np.maximum(1e3, 1e-6 * production)
        result = dict(name=name, radius_km=radius, production=float(production[inside].sum()),
                      fallback=float(fallback[inside].sum()), fallback_cells=int((noise & inside).sum()),
                      cells=int(inside.sum()))
        for label, weighting in weightings.items():
            result[label] = float((allocate(weighting) + fallback)[inside].sum())
        # Which share of the circle's main unit lies inside, by component.
        main = int(np.argmax(np.bincount(labels[inside], weights=production[inside], minlength=len(totals))))
        result['main_unit'] = dict(name=units[main - 1]['name'], country=units[main - 1]['country'], target=totals[main],
                                   **{f'{component}_inside': float(values[component][inside & (labels == main)].sum() / sums[component][main])
                                      for component in LAYERS if sums[component][main] > 0})
        results.append(result)
    return results


def report():
    tests = {'US county within state (BEA 2024)': 'us', 'UK MSOA within local authority (ONS 2023)': 'uk',
             'EU NUTS3 within NUTS2 (Eurostat 2023)': 'eu', 'Brazil municipality within state (IBGE 2023)': 'br'}
    data = {key: json.loads((OUTPUT / f'{key}_sums.json').read_text()) for key in tests.values() if (OUTPUT / f'{key}_sums.json').exists()}
    weightings = dict(WEIGHTINGS)
    for base in ('(b) 0.5 pop + 0.5 places', '(c) places alone', '(e) 0.5 pop + 0.5 workplace places'):
        weightings[base + ', confidence >= 0.5'] = {name + ('_conf50' if name.endswith('places') else ''): weight
                                                    for name, weight in WEIGHTINGS[base].items()}
    output = {'tests': {}, 'manhattan_share_of_new_york_state': {}}
    for title, key in tests.items():
        if key in data:
            output['tests'][title] = {label: score(data[key], weighting) for label, weighting in weightings.items()}
    if 'us' in data:
        for label, weighting in weightings.items():
            predicted, official = unit_share(data['us'], weighting, '36061', '36')
            output['manhattan_share_of_new_york_state'][label] = dict(predicted=predicted, official=official)
    if (OUTPUT / 'unit_sums.npz').exists():
        sums = dict(np.load(OUTPUT / 'unit_sums.npz'))
        units = json.loads((BUILD / 'conservation.json').read_text())['units']
        with Layers() as layers, rasterio.open(BUILD / 'control-ids.tif') as labels_source, rasterio.open(BUILD / 'gdp.tif') as built:
            output['circles'] = circle_values(layers, units, sums, labels_source, built, weightings)
    (OUTPUT / 'report.json').write_text(json.dumps(output, indent=2) + '\n')
    print_report(output)


def print_report(output):
    tests = list(output['tests'])
    labels = list(next(iter(output['tests'].values())))
    print('Misallocated share (median |log(predicted / official)|)\n')
    print('| Weighting | ' + ' | '.join(tests) + ' |')
    print('|---' * (len(tests) + 1) + '|')
    for label in labels:
        cells = [f"{output['tests'][t][label]['misallocated']*100:.2f}% ({output['tests'][t][label]['median_abs_log']:.3f})" for t in tests]
        print(f'| {label} | ' + ' | '.join(cells) + ' |')
    print('\nUnits/groups: ' + '; '.join(f"{t}: {next(iter(r.values()))['units']}/{next(iter(r.values()))['groups']}" for t, r in output['tests'].items()))
    circles = output.get('circles', [])
    wanted = ['Midtown and Lower Manhattan', 'Tokyo Marunouchi', 'Bank', 'Zuidas', 'Schiphol', 'La Défense']
    circles = sorted([c for c in circles if c['name'] in wanted], key=lambda c: wanted.index(c['name']))
    print('\nManhattan share of New York State, and circle GDP in billions of 2021 international dollars\n')
    print('| Weighting | Manhattan / NY State | ' + ' | '.join(f"{c['name']} {c['radius_km']} km" for c in circles) + ' |')
    print('|---' * (len(circles) + 2) + '|')
    for label in labels:
        share = output['manhattan_share_of_new_york_state'][label]['predicted']
        print(f'| {label} | {share*100:.1f}% | ' + ' | '.join(f"{c[label]/1e9:.0f}" for c in circles) + ' |')
    print('\nShare of each circle\'s main control unit inside the circle')
    for c in circles:
        m = c['main_unit']
        print(f"  {c['name']}: {m['name']} ({m['country']}, {m['target']/1e9:.0f}bn) " + ', '.join(f"{k[:-7]} {v*100:.1f}%" for k, v in m.items() if k.endswith('_inside')))
    official = next(iter(output['manhattan_share_of_new_york_state'].values()))['official']
    print(f'\nOfficial Manhattan share {official*100:.1f}%. Centroid fallback GDP per circle: '
          + '; '.join(f"{c['name']} {c['fallback']/1e9:.1f}bn" for c in output.get('circles', [])))


def main():
    if sys.argv[1] == 'report':
        return report()
    with Layers() as layers:
        print('places loaded', dict(zip(PLACE_LAYERS, layers.places.totals.tolist())), flush=True)
        {'us': us_sums, 'uk': uk_sums, 'eu': eu_sums, 'br': br_sums, 'units': unit_sums}[sys.argv[2]](layers)


if __name__ == '__main__':
    main()

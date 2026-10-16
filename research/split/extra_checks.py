"""Written by AI on 2026.10.17 by model claude fable 5.1.

Three checks run after the candidates were scored:

1. Tokyo's 23 wards: share of Japan's land value, official against current and recommended rules.
2. North Rhine-Westphalia circles: the official land-price grid against the current and
   recommended land rules at 3 to 50 km around twelve centres, both scaled to the state total.
3. Post-hoc sensitivity, not a frozen candidate: the regional income term Y with a 20 km
   kernel instead of 40 km, to see whether neighbouring cities (Düsseldorf and the Ruhr)
   separate better.

Writes data/experiments/split/extra_checks.json.

    devenv shell -- python -m research.split.extra_checks
"""
import json
import math

import numpy as np
from rasterio.windows import Window

from layers.grid import EARTH_RADIUS_KM, GRID_TRANSFORM, GRID_WIDTH, open_zipped_raster, GHS_POPULATION_ZIP
from layers.land_value import density as density_module
from layers.land_value.density import coarse_population, interpolate_density, neighbourhood_density
from research.split.extract_cells import COUNTRY_BOXES, SPLIT_DIRECTORY
from research.split.rules import Country, load_test, spatial_score, unit_sums
from research.split.score_candidates import LAND_CANDIDATES, circle_mask

EXPERIMENTS = SPLIT_DIRECTORY.parent / 'land-value'
CURRENT, RECOMMENDED = 'L0 current: ½ P·D^0.25 + ½ G', 'L1: ½ P·D^0.5·Y² + ½ G'
NRW_CENTRES = {
    'Köln Dom': (6.9578, 50.9413), 'Düsseldorf Kö': (6.7793, 51.2254), 'Essen Hbf': (7.0147, 51.4514),
    'Dortmund centre': (7.4653, 51.5136), 'Münster Prinzipalmarkt': (7.6280, 51.9620), 'Bielefeld centre': (8.5325, 52.0302),
    'Aachen centre': (6.0839, 50.7753), 'Bonn centre': (7.0982, 50.7374),
    'Schmallenberg (Sauerland, rural)': (8.2863, 51.1548), 'Hellenthal (Eifel, rural)': (6.4318, 50.4877),
    'Südlohn (Münsterland farmland)': (6.8680, 51.9390), 'Höxter (rural east)': (9.3744, 51.7752),
}
RADII_KM = (3, 5, 10, 20, 30, 50)


def tokyo(countries, results):
    test = load_test('japan_municipalities')
    japan = countries['JPN']
    position = test['keys'].index('13100')
    official = float(test['land_value'][position] / test['land_value'].sum())
    predicted = {}
    for rule in (CURRENT, RECOMMENDED):
        sums = unit_sums(test, japan.mix(LAND_CANDIDATES[rule]))
        predicted[rule] = float(sums[position] / sums.sum())
    results['tokyo_23_wards_share_of_japan_land'] = dict(official=official, **predicted)
    print(f"Tokyo 23 wards: official {official:.1%}, current {predicted[CURRENT]:.1%}, recommended {predicted[RECOMMENDED]:.1%}")


def nrw_circles(countries, results):
    official = np.load(EXPERIMENTS / 'nrw_official_grid.npz')
    value, transform = official['value'], official['transform']
    row_offset = round((transform[5] - GRID_TRANSFORM.f) / GRID_TRANSFORM.e)
    col_offset = round((transform[2] - GRID_TRANSFORM.c) / GRID_TRANSFORM.a)
    germany = countries['DEU']
    cells = np.load(SPLIT_DIRECTORY / 'cells_DEU.npz')
    rows, cols = cells['row'] - row_offset, cells['col'] - col_offset
    on_grid = (rows >= 0) & (rows < value.shape[0]) & (cols >= 0) & (cols < value.shape[1])
    official_cells = np.zeros(len(rows))
    official_cells[on_grid] = value[rows[on_grid], cols[on_grid]]
    official_total = official_cells.sum()
    out = {}
    for rule in (CURRENT, RECOMMENDED):
        weights = germany.mix(LAND_CANDIDATES[rule])
        model_total = weights[on_grid].sum()
        per_radius = {}
        for radius in RADII_KM:
            logs = {}
            for name, (longitude, latitude) in NRW_CENTRES.items():
                inside = circle_mask(germany, latitude, longitude, radius) & on_grid
                model_share = weights[inside].sum() / model_total
                official_share = official_cells[inside].sum() / official_total
                logs[name] = float(np.log(model_share / official_share))
            per_radius[radius] = dict(median_abs_log=float(np.median(np.abs(list(logs.values())))), log_ratio=logs)
        out[rule] = per_radius
        print(f'NRW circles, {rule}: ' + ', '.join(f"{r} km {per_radius[r]['median_abs_log']:.2f}" for r in RADII_KM))
        print('   3 km model ÷ official: ' + ', '.join(f"{name.split(' (')[0]} {math.exp(v):.2f}" for name, v in per_radius[3]['log_ratio'].items()))
    results['nrw_circles'] = out


def regional_income_with_kernel(kernel_km, gdp_coarse, population_coarse):
    density_module.DENSITY_DISTANCE_KM = kernel_km
    density_module.KERNEL_DISTANCE_KM = 8 * kernel_km
    return neighbourhood_density(gdp_coarse), neighbourhood_density(population_coarse)


def income_sensitivity(countries, results):
    import rasterio
    from layers.gdp.build import GDP_BUILD_DIRECTORY
    with open_zipped_raster(GHS_POPULATION_ZIP) as population, rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp:
        population_coarse, gdp_coarse = coarse_population(population), coarse_population(gdp)
    gdp_20, population_20 = regional_income_with_kernel(20.0, gdp_coarse, population_coarse)
    out = {}
    for code, country in countries.items():
        cells = np.load(SPLIT_DIRECTORY / f'cells_{code}.npz')
        keys = cells['row'].astype('int64') * GRID_WIDTH + cells['col']
        order = np.argsort(keys)
        y20 = np.ones(len(keys))
        for bounds in COUNTRY_BOXES[code]:
            from layers.grid import bounding_window
            window = bounding_window(type('G', (), dict(transform=GRID_TRANSFORM, width=GRID_WIDTH, height=21384))(), bounds)
            g = interpolate_density(gdp_20, window)
            p = interpolate_density(population_20, window)
            window_rows = np.arange(int(window.row_off), int(window.row_off + window.height))
            window_cols = np.arange(int(window.col_off), int(window.col_off + window.width))
            window_keys = (window_rows[:, None] * GRID_WIDTH + window_cols[None, :]).ravel()
            position = np.searchsorted(keys[order], window_keys)
            position = np.clip(position, 0, len(keys) - 1)
            found = keys[order][position] == window_keys
            ratio = np.where(p.ravel() > 0, g.ravel() / np.maximum(p.ravel(), 1e-9), np.nan)
            y20[order[position[found]]] = ratio[found]
        national = country.G.sum() / country.P.sum()
        y20 = np.where(np.isfinite(y20), y20 / national, 1.0)
        country.Y40 = country.Y
        country.Y = y20
        country._cache.clear()
    tests = [load_test(name) for name in ('us_counties', 'us_tracts', 'nyc_districts', 'victoria_councils', 'bc_municipalities',
                                          'nrw_municipalities', 'japan_municipalities', 'denmark_municipalities')]
    from research.split.score_candidates import held_out
    scores = {}
    for test in tests:
        country = countries[test['country']]
        mask = held_out(test)
        land = unit_sums(test, country.mix(LAND_CANDIDATES[RECOMMENDED]))
        scores[test['name']] = spatial_score(land[mask], test['land_value'][mask])
    scores['mean_wrong_area'] = float(np.mean([scores[t['name']]['wrong_area'] for t in tests]))
    out['L1 with 20 km income kernel'] = scores
    print('L1 with Y from a 20 km kernel: ' + ', '.join(f"{name} {s['wrong_area']:.1%}/{s['median_abs_log']:.2f}" for name, s in scores.items() if name != 'mean_wrong_area')
          + f"; mean {scores['mean_wrong_area']:.1%}")
    germany = countries['DEU']
    for label, latitude, longitude in (('Düsseldorf 10 km', 51.2277, 6.7735), ('Gelsenkirchen 10 km', 51.5177, 7.0857)):
        inside = circle_mask(germany, latitude, longitude, 10)
        out[label] = dict(Y40=float((germany.P * germany.Y40)[inside].sum() / germany.P[inside].sum()),
                          Y20=float((germany.P * germany.Y)[inside].sum() / germany.P[inside].sum()),
                          land_share_of_germany_L1_Y20=float(germany.mix(LAND_CANDIDATES[RECOMMENDED])[inside].sum()))
        print(f"{label}: regional income relative to Germany, 40 km kernel {out[label]['Y40']:.2f}, 20 km kernel {out[label]['Y20']:.2f}")
    results['income_kernel_sensitivity'] = out


def main():
    countries = {code: Country(code) for code in ('USA', 'DEU', 'JPN', 'DNK', 'AUS', 'CAN', 'NLD', 'GBR')}
    results = {}
    tokyo(countries, results)
    nrw_circles(countries, results)
    income_sensitivity(countries, results)
    (SPLIT_DIRECTORY / 'extra_checks.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()

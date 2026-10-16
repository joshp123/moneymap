"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Check the production GDP allocation against held-out counties and circle queries.
"""
import argparse
from collections import defaultdict
from contextlib import ExitStack
import json
import math
import time
import urllib.parse
import urllib.request

import numpy as np
import rasterio
from rasterio.windows import Window

from build_layers import (BUILD, RAW, PolygonIndex, allocation, grouped_sum,
                          open_zip_raster, shifted_q)
from build_tiles import clean_window, open_sources
from gdp_controls import load_us_controls, load_official_comparisons

CIRCLES = [
    ('Midtown and Lower Manhattan', 40.73756, -73.99429, 6),
    ('Bank', 51.5133, -0.0886, 3), ('Canary Wharf', 51.5054, -0.0235, 3),
    ('Heathrow', 51.4700, -0.4543, 3), ('Zuidas', 52.3383, 4.8728, 3),
    ('Schiphol', 52.3105, 4.7683, 3), ('Maasvlakte', 51.9600, 4.0300, 5),
    ('Rotterdam', 51.93467, 4.55658, 50),
    ('Tokyo Marunouchi', 35.6812, 139.7671, 3), ('La Défense', 48.8920, 2.2380, 3),
]


def bounding_window(grid, bounds):
    left, top = ~grid.transform * (bounds[0], bounds[3])
    right, bottom = ~grid.transform * (bounds[2], bounds[1])
    col0, row0 = max(0, math.floor(left)), max(0, math.floor(top))
    col1, row1 = min(grid.width, math.ceil(right)), min(grid.height, math.ceil(bottom))
    return Window(col0, row0, col1-col0, row1-row0)


def window_strips(grid, bounds):
    window = bounding_window(grid, bounds)
    last_row = int(window.row_off + window.height)
    for row in range(int(window.row_off), last_row, 120):
        yield Window(window.col_off, row, window.width, min(120, last_row-row))


def scores(predicted, official):
    return dict(misallocated_share=float(0.5 * np.abs(predicted-official).sum() / official.sum()),
                median_absolute_log_ratio=float(np.median(np.abs(np.log(predicted/official)))))


def holdout():
    counties = load_us_controls(RAW)
    states = defaultdict(list)
    for county in counties:
        states[county.parent_code].append(county)
    expected_all, predicted_all = [], defaultdict(list)
    coverage = []
    with ExitStack() as stack:
        gdp, population = open_sources()
        for source in (gdp, population): stack.enter_context(source)
        volume = stack.enter_context(open_zip_raster(RAW/'nres_v_30ss.zip'))
        surface = stack.enter_context(open_zip_raster(RAW/'nres_s_30ss.zip'))
        for state, units in sorted(states.items()):
            polygons = PolygonIndex(units)
            bounds = (min(g.bounds[0] for g in polygons.geometries),
                      min(g.bounds[1] for g in polygons.geometries),
                      max(g.bounds[2] for g in polygons.geometries),
                      max(g.bounds[3] for g in polygons.geometries))
            official = np.array([unit.value for unit in units])
            county_population, county_q, county_old = (np.zeros(len(units)+1) for _ in range(3))
            for window in window_strips(gdp, bounds):
                labels = polygons.labels(window, gdp.transform)
                pop = clean_window(population, 1, window)
                q = shifted_q(volume, surface, window, gdp)
                county_population += grouped_sum(labels, pop, len(units))
                county_q += grouped_sum(labels, q, len(units))
                county_old += grouped_sum(labels, clean_window(gdp, 8, window), len(units))
            total = np.array([0., official.sum()])
            pop_sums, q_sums = np.array([0., county_population[1:].sum()]), np.array([0., county_q[1:].sum()])
            predicted = {name: np.zeros(len(units)+1) for name in ('population_only', 'production_half_population')}
            for window in window_strips(gdp, bounds):
                labels = polygons.labels(window, gdp.transform)
                state_labels = (labels > 0).astype('uint8')
                pop = clean_window(population, 1, window)
                q = shifted_q(volume, surface, window, gdp)
                for name, weight in [('population_only', 1.), ('production_half_population', .5)]:
                    built = allocation(pop, q, state_labels, total, pop_sums, q_sums, population_weight=weight)
                    predicted[name] += grouped_sum(labels, built, len(units))
            expected_all.extend(official.tolist())
            for name, values in predicted.items():
                np.testing.assert_allclose(values[1:].sum(), official.sum(), rtol=8e-8)
                predicted_all[name].extend(values[1:].tolist())
            # Match the state controls for a fair comparison of within-state location.
            predicted_all['kummu_state_normalised'].extend((county_old[1:] * official.sum() / county_old[1:].sum()).tolist())
            predicted_all['kummu_country_normalised'].extend(county_old[1:].tolist())
            coverage.append(dict(state=state, counties=len(units), zero_population_counties=int((county_population[1:]==0).sum())))
            print(f'Hold-out state {state}: {len(units)} counties', flush=True)
    official = np.asarray(expected_all)
    predicted_all['kummu_country_normalised'] = np.asarray(predicted_all['kummu_country_normalised'])
    predicted_all['kummu_country_normalised'] *= official.sum() / predicted_all['kummu_country_normalised'].sum()
    return dict(counties=len(counties), states=len(states), official_2024_usd=float(official.sum()), includes_alaska='02' in states,
                includes_hawaii='15' in states, coverage=coverage,
                basis='State totals are summed BEA 2024 county GDP. Production allocation runs on raster cells; county scoring uses cell centres. Kummu is shown normalised both within states and across the country.',
                scores={name:scores(np.asarray(values), official) for name,values in predicted_all.items()})


def source_circle(source, band, latitude, longitude, radius):
    angular = radius / 6371.0088
    lat_span = math.degrees(angular)
    lon_span = math.degrees(math.asin(min(1, math.sin(angular) / math.cos(math.radians(latitude)))))
    window = bounding_window(source, (longitude-lon_span, latitude-lat_span, longitude+lon_span, latitude+lat_span))
    rows = source.transform.f + (np.arange(window.row_off, window.row_off+window.height) + .5) * source.transform.e
    columns = source.transform.c + (np.arange(window.col_off, window.col_off+window.width) + .5) * source.transform.a
    latitudes, longitudes = np.radians(rows[:,None]), np.radians(columns[None,:])
    centre_latitude, centre_longitude = np.radians([latitude, longitude])
    haversine = np.sin((latitudes-centre_latitude)/2)**2 + np.cos(centre_latitude)*np.cos(latitudes)*np.sin((longitudes-centre_longitude)/2)**2
    distance = 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))
    return float(clean_window(source, band, window)[distance <= radius].sum(dtype='float64'))


def query(origin, latitude, longitude, radius):
    url = origin.rstrip('/') + '/api/circle?' + urllib.parse.urlencode(dict(lat=latitude, long=longitude, distance_km=radius))
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=180) as response:
        result = json.load(response)
    return result, (time.perf_counter()-started)*1000


def named_places(origin):
    results = []
    with ExitStack() as stack:
        gdp, population = open_sources()
        stack.enter_context(gdp)
        stack.enter_context(population)
        built = stack.enter_context(rasterio.open(BUILD/'gdp.tif'))
        for name, latitude, longitude, radius in CIRCLES:
            actual, milliseconds = query(origin, latitude, longitude, radius)
            expected = source_circle(built, 1, latitude, longitude, radius)
            np.testing.assert_allclose(actual['gdp'], expected, rtol=1e-11, atol=.001)
            expected_population = source_circle(population, 1, latitude, longitude, radius)
            np.testing.assert_allclose(actual['population'], expected_population, rtol=1e-11, atol=.001)
            result = dict(name=name, latitude=latitude, longitude=longitude, radius_km=radius,
                          v1_gdp=source_circle(gdp, 8, latitude, longitude, radius),
                          v2_gdp=actual['gdp'], population=actual['population'],
                          gdp_per_head=actual['gdp_per_head'], milliseconds=milliseconds)
            results.append(result)
            print(json.dumps(result), flush=True)
    timings = []
    for name, latitude, longitude, radius in [('Rotterdam',51.93467,4.55658,50), ('Paris',48.8566,2.3522,100)]:
        runs = [query(origin, latitude, longitude, radius)[1] for _ in range(2)]
        timings.append(dict(name=name, radius_km=radius, milliseconds=runs))
    conservation = json.loads((BUILD/'conservation.json').read_text())
    references = load_official_comparisons(RAW)
    official = {}
    for name, reference in references.items():
        clean = {key:value for key,value in reference.items() if key != 'geometry'}
        country = conservation['countries'][reference['country']]
        clean['ppp_ratio'] = country['source'] / reference['country_total']
        clean['ppp_2021_international_dollars'] = reference['value'] * clean['ppp_ratio']
        official[name] = clean
    return dict(named_places=results, timings=timings, official_references=official)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8787')
    parser.add_argument('--holdout-only', action='store_true')
    parser.add_argument('--places-only', action='store_true')
    arguments = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD/'checks.json'
    report = json.loads(output.read_text()) if output.exists() else {}
    if not arguments.places_only:
        report['holdout'] = holdout()
        output.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report['holdout']['scores'], indent=2), flush=True)
    if not arguments.holdout_only:
        report.update(named_places(arguments.origin))
        output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()

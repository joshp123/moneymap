"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

Check the real Worker's circle API against the grids it should reproduce. For
each named circle, every total and every cumulative kilometre row must match a
direct sum over cell centres within that distance: GDP from the built GDP grid,
population from GHS-POP, land value from its built grid, and stops from the
per-cell Parquet counts. None of these reads a tile, so the check covers the
tiles, their upload and the Worker.

Start the preview first (node deploy/preview.mjs), or pass --origin for the
live Site. To see what a method change does, keep data/checks/circles.json
from before the change and pass it with --compare. Campus radii below the
API minimum use the corresponding cumulative row from a 3 km query.

    devenv shell -- python -m checks.circles
"""
import argparse
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request

import numpy as np
import rasterio

from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.grid import (EARTH_RADIUS_KM, ROOT, SparseCellCounts, bounding_window,
                         open_kummu_gdp_and_population, read_window_zero_filled)
from layers.transit_stops import EXPECTED_TOTALS as STOP_LAYERS, STOPS_PER_CELL

REPORT = ROOT / 'data/checks/circles.json'
LAND_VALUE_RASTER = ROOT / 'data/build/land_value/land_value.tif'
CIRCLES = [
    ('Midtown and Lower Manhattan', 40.73756, -73.99429, 6),
    ('Bank', 51.5133, -0.0886, 3), ('Canary Wharf', 51.5054, -0.0235, 3),
    ('Zuidas', 52.3383, 4.8728, 3), ('Schiphol', 52.3105, 4.7683, 3),
    ('Amsterdam', 52.3731, 4.8922, 5), ('Rotterdam', 51.93467, 4.55658, 50),
    ('La Défense', 48.8920, 2.2380, 3), ('Paris', 48.8566, 2.3522, 100),
    ('Tokyo Marunouchi', 35.6812, 139.7671, 3),
    ('Shanghai Lujiazui', 31.2397, 121.4998, 3), ('Beijing Guomao', 39.9087, 116.4605, 3),
    ('Mountain View', 37.3861, -122.0839, 10), ('Palo Alto', 37.4419, -122.1430, 10),
    ('SF Financial District', 37.7936, -122.3965, 3), ('San Jose', 37.3382, -121.8863, 10),
    ('San Francisco', 37.7749, -122.4194, 10), ('Cupertino', 37.3349, -122.0090, 5),
    ('Menlo Park', 37.4848, -122.1484, 5), ('Santa Clara', 37.3707, -121.9638, 5),
    ('Seattle South Lake Union', 47.6223, -122.3365, 3), ('Redmond', 47.6423, -122.1368, 5),
    ('Apple Park', 37.3349, -122.0090, 1), ('Meta, Menlo Park', 37.4848, -122.1484, 1),
    ('Googleplex', 37.4220, -122.0841, 2), ('Googleplex', 37.4220, -122.0841, 3),
    ('Nvidia, Santa Clara', 37.3707, -121.9638, 1), ('Nvidia, Santa Clara', 37.3707, -121.9638, 2),
    ('Microsoft, Redmond', 47.6423, -122.1368, 1), ('Microsoft, Redmond', 47.6423, -122.1368, 3),
    ('Amazon, South Lake Union', 47.6223, -122.3365, 2),
    ('Cologne cathedral', 50.9413, 6.9578, 3), ('Cologne cathedral', 50.9413, 6.9578, 10),
    ('Düsseldorf', 51.2254, 6.7793, 10), ('Gelsenkirchen', 51.5177, 7.0857, 10),
    ('Sydney', -33.8688, 151.2093, 10),
]
# Bus, tram and rail stops from Tom Forth's tool, for comparison only.
TOM_FORTH_STOPS = {'Amsterdam': [696, 345, 33], 'Rotterdam': [11622, 1036, 180]}
TIMED_CIRCLES = ['Rotterdam', 'Paris']


def query(origin, latitude, longitude, radius):
    url = origin.rstrip('/') + '/api/circle?' + urllib.parse.urlencode(dict(lat=latitude, long=longitude, distance_km=radius))
    # Cloudflare rejects Python's default User-Agent.
    request = urllib.request.Request(url, headers={'User-Agent': 'curl/8 moneymap circle check'})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    return result, (time.perf_counter() - started) * 1000


def cell_distances_km(grid, latitude, longitude, radius):
    """The window around the circle and the great-circle distance to each cell centre."""
    angular = radius / EARTH_RADIUS_KM
    latitude_span = math.degrees(angular)
    longitude_span = math.degrees(math.asin(min(1, math.sin(angular) / math.cos(math.radians(latitude)))))
    window = bounding_window(grid, (longitude - longitude_span, latitude - latitude_span,
                                    longitude + longitude_span, latitude + latitude_span))
    rows = grid.transform.f + (np.arange(window.row_off, window.row_off + window.height) + .5) * grid.transform.e
    columns = grid.transform.c + (np.arange(window.col_off, window.col_off + window.width) + .5) * grid.transform.a
    latitudes, longitudes = np.radians(rows[:, None]), np.radians(columns[None, :])
    centre_latitude, centre_longitude = np.radians([latitude, longitude])
    haversine = (np.sin((latitudes - centre_latitude) / 2) ** 2 +
                 np.cos(centre_latitude) * np.cos(latitudes) * np.sin((longitudes - centre_longitude) / 2) ** 2)
    return window, 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))


def expected_circle(planes, distances, radius):
    """Totals within each whole kilometre up to the radius, then within the radius."""
    rows = []
    for kilometre in [*range(1, math.floor(radius) + 1), radius]:
        inside = distances <= kilometre
        row = {name: float(plane[inside].sum(dtype='float64')) for name, plane in planes.items()}
        row.update({name: round(row[name]) for name in STOP_LAYERS})
        row['gdp_per_head'] = row['gdp'] / row['population'] if row['population'] > 0 else None
        rows.append(row)
    return rows[:-1], rows[-1]


def assert_matches(actual, expected, where):
    for name, value in expected.items():
        if name in STOP_LAYERS or value is None:
            assert actual[name] == value, f'{where} {name}: API {actual[name]}, grid {value}'
        else:
            np.testing.assert_allclose(actual[name], value, rtol=1e-11, atol=1e-3, err_msg=f'{where} {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--origin', default='http://127.0.0.1:8787')
    parser.add_argument('--compare', type=Path, help='Earlier circles.json to compare GDP, population and stops')
    parser.add_argument('--unchanged-gdp', action='store_true', help='Also require GDP to match --compare')
    arguments = parser.parse_args()
    baseline = {}
    if arguments.compare:
        baseline = {(circle['name'], circle['radius_km']): circle
                    for circle in json.loads(arguments.compare.read_text())['circles']}
    stops = SparseCellCounts(STOPS_PER_CELL, STOP_LAYERS)
    report = {'origin': arguments.origin, 'circles': [], 'timings': []}
    kummu_gdp, population = open_kummu_gdp_and_population()
    with kummu_gdp, population, rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp, \
            rasterio.open(LAND_VALUE_RASTER) as land_value:
        for name, latitude, longitude, radius in CIRCLES:
            query_radius = max(3, radius)
            result, milliseconds = query(arguments.origin, latitude, longitude, query_radius)
            window, distances = cell_distances_km(gdp, latitude, longitude, query_radius)
            planes = dict(gdp=read_window_zero_filled(gdp, 1, window),
                          land_value=read_window_zero_filled(land_value, 1, window),
                          population=read_window_zero_filled(population, 1, window),
                          **dict(zip(STOP_LAYERS, stops.window(window))))
            expected_rows, expected_total = expected_circle(planes, distances, query_radius)
            assert_matches(result, expected_total, name)
            assert len(result['cumulative']) == len(expected_rows), f'{name}: cumulative row count'
            for row, expected in zip(result['cumulative'], expected_rows):
                assert_matches(row, expected, f"{name} {row['distance_km']} km")
            if radius < query_radius:
                result = next(row for row in result['cumulative'] if row['distance_km'] == radius)
            circle = dict(name=name, latitude=latitude, longitude=longitude, radius_km=radius,
                          **{key: result[key] for key in ('gdp', 'land_value', 'population', 'gdp_per_head', *STOP_LAYERS)},
                          milliseconds=milliseconds)
            if (name, radius) in baseline:
                previous = baseline[(name, radius)]
                circle['previous_gdp'] = previous['gdp']
                circle['gdp_change'] = result['gdp'] - previous['gdp']
                unchanged_fields = ('population', *STOP_LAYERS, *(('gdp',) if arguments.unchanged_gdp else ()))
                for field in unchanged_fields:
                    if field in previous:
                        np.testing.assert_allclose(result[field], previous[field], rtol=1e-12, atol=1e-3,
                                                   err_msg=f'{name} changed {field}')
            if name in TOM_FORTH_STOPS:
                circle['tom_forth_stops'] = dict(zip(STOP_LAYERS, TOM_FORTH_STOPS[name]))
            report['circles'].append(circle)
            print(json.dumps(circle, ensure_ascii=False), flush=True)
    for name, latitude, longitude, radius in CIRCLES:
        if name in TIMED_CIRCLES:
            report['timings'].append(dict(name=name, radius_km=radius, milliseconds=[
                query(arguments.origin, latitude, longitude, radius)[1] for _ in range(2)]))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f"All {len(CIRCLES)} circles match the grids, including every cumulative row. Timings: {report['timings']}")


if __name__ == '__main__':
    main()

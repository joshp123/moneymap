"""Written by AI on 2026.10.16 by model gpt-6.1-sol.
Independent source-raster checks; no tile reads.
"""
import concurrent.futures
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from rasterio.windows import Window
from build_tiles import open_sources, clean_window, ROOT

CIRCLES = [
    ('Rotterdam', 51.93467, 4.55658, 50), ('Amsterdam', 52.3731, 4.8922, 5),
    ('Amsterdam', 52.3731, 4.8922, 3), ('London', 51.5074, -0.1278, 20),
    ('Lagos', 6.4550, 3.3841, 10), ('Tokyo', 35.6812, 139.7671, 30),
    ('Luxembourg', 49.6116, 6.1319, 25), ('Tromsø', 69.6492, 18.9553, 50),
    ('Paris', 48.8566, 2.3522, 100),
]


def get_json(url, timeout=180):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def tom_population(circle):
    name, latitude, longitude, radius = circle
    url = 'https://ringpopulationsapi.azurewebsites.net/api/globalringpopulations?' + urllib.parse.urlencode(
        {'latitude': latitude, 'longitude': longitude, 'distance_km': radius})
    try:
        return {'response': get_json(url)}
    except Exception as error:
        return {'error': str(error)}


def reference(gdp, population, latitude, longitude, radius):
    # Conservative square bound; inclusion itself uses great-circle distance.
    angular = radius / 6371.0088
    latitude_span = math.degrees(angular)
    longitude_span = math.degrees(math.asin(min(1, math.sin(angular) / math.cos(math.radians(latitude)))))
    left, top = ~gdp.transform * (longitude - longitude_span, latitude + latitude_span)
    right, bottom = ~gdp.transform * (longitude + longitude_span, latitude - latitude_span)
    col0, row0 = max(0, math.floor(left)), max(0, math.floor(top))
    col1, row1 = min(gdp.width, math.ceil(right)), min(gdp.height, math.ceil(bottom))
    longitudes = np.radians(gdp.transform.c + (np.arange(col0, col1) + .5) * gdp.transform.a)
    latitudes = np.radians(gdp.transform.f + (np.arange(row0, row1) + .5) * gdp.transform.e)
    latitude_radians, longitude_radians = np.radians([latitude, longitude])
    haversine = np.sin((latitudes[:, None] - latitude_radians) / 2)**2 + np.cos(latitude_radians) * np.cos(latitudes[:, None]) * np.sin((longitudes[None, :] - longitude_radians) / 2)**2
    distances = 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))
    window = Window(col0, row0, col1-col0, row1-row0)
    layers = [clean_window(gdp, 8, window), clean_window(population, 1, window)]
    cumulative = []
    for kilometre in range(1, radius+1):
        mask = distances <= kilometre
        totals = [float(layer[mask].sum(dtype=np.float64)) for layer in layers]
        cumulative.append({'distance_km': kilometre, 'gdp': totals[0], 'population': totals[1], 'gdp_per_head': totals[0]/totals[1] if totals[1] else None})
    return cumulative


def main():
    results = []
    gdp, population = open_sources()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool, gdp, population:
        tom_futures = [pool.submit(tom_population, circle) for circle in CIRCLES]
        for circle, tom in zip(CIRCLES, tom_futures):
            name, latitude, longitude, radius = circle
            expected = reference(gdp, population, latitude, longitude, radius)
            url = 'http://127.0.0.1:8787/api/circle?' + urllib.parse.urlencode({'lat':latitude, 'long':longitude, 'distance_km':radius})
            started = time.perf_counter()
            actual = get_json(url)
            elapsed = (time.perf_counter() - started) * 1000
            for observed, target in zip(actual['cumulative'], expected, strict=True):
                for key in ('gdp', 'population', 'gdp_per_head'):
                    np.testing.assert_allclose(observed[key], target[key], rtol=1e-10, atol=.001)
            for key in ('gdp', 'population', 'gdp_per_head'):
                np.testing.assert_allclose(actual[key], expected[-1][key], rtol=1e-10, atol=.001)
            result = {'name': name, 'lat': latitude, 'long': longitude, 'radius': radius,
                      'worker': {key: actual[key] for key in ('gdp','population','gdp_per_head')},
                      'reference': expected[-1], 'milliseconds': elapsed, 'tom': tom.result()}
            if 'response' in result['tom']:
                result['tom_population'] = next(row['people'] for row in result['tom']['response'] if row['distance'] == radius)
                result['population_difference'] = actual['population'] - result['tom_population']
                result['population_difference_percent'] = 100 * result['population_difference'] / result['tom_population'] if result['tom_population'] else None
            results.append(result)
            print(json.dumps({key: value for key, value in result.items() if key != 'tom'}), flush=True)
    (ROOT / 'data/circle-checks.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()

"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Compare US GDP circles through the real Worker with the v3 and v4 grids.
"""
import argparse
import json

import numpy as np
import rasterio

from build_tiles import ROOT
from check_gdp_layers import query, source_circle

BUILD = ROOT / 'data/gdp-v4'
CIRCLES = [
    ('Mountain View', 37.3861, -122.0839, 10),
    ('Palo Alto', 37.4419, -122.1430, 10),
    ('SF Financial District', 37.7936, -122.3965, 3),
    ('San Jose', 37.3382, -121.8863, 10),
    ('San Francisco', 37.7749, -122.4194, 10),
    ('Cupertino', 37.3349, -122.0090, 5),
    ('Menlo Park', 37.4848, -122.1484, 5),
    ('Santa Clara', 37.3707, -121.9638, 5),
    ('Midtown and Lower Manhattan', 40.73756, -73.99429, 6),
    ('Seattle South Lake Union', 47.6223, -122.3365, 3),
    ('Redmond', 47.6423, -122.1368, 5),
]
UNCHANGED_FIELDS = ('population', 'bus_stops', 'tram_stops', 'rail_stops')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8787')
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    baseline_path = BUILD / 'v3-api.json'
    if args.baseline:
        baseline = {}
        with rasterio.open(ROOT / 'data/gdp-v3/gdp.tif') as source:
            for name, latitude, longitude, radius in CIRCLES:
                result, milliseconds = query(args.origin, latitude, longitude, radius)
                np.testing.assert_allclose(result['gdp'], source_circle(source, 1, latitude, longitude, radius), rtol=1e-12)
                baseline[name] = result
                print(f'{name}: v3 GDP {result["gdp"]:.3f}, {milliseconds:.1f} ms', flush=True)
        baseline_path.write_text(json.dumps(baseline, indent=2) + '\n')
        print(f'Saved verified v3 preview API results for {len(baseline)} circles: {baseline_path}')
        return

    baseline = json.loads(baseline_path.read_text())
    report = {'circles': []}
    with rasterio.open(ROOT / 'data/gdp-v3/gdp.tif') as old, rasterio.open(BUILD / 'gdp.tif') as new:
        for name, latitude, longitude, radius in CIRCLES:
            result, milliseconds = query(args.origin, latitude, longitude, radius)
            expected = source_circle(new, 1, latitude, longitude, radius)
            expected_old = source_circle(old, 1, latitude, longitude, radius)
            np.testing.assert_allclose(result['gdp'], expected, rtol=1e-12)
            np.testing.assert_allclose(baseline[name]['gdp'], expected_old, rtol=1e-12)
            for field in UNCHANGED_FIELDS:
                np.testing.assert_equal(result[field], baseline[name][field])
            np.testing.assert_equal(len(result['cumulative']), len(baseline[name]['cumulative']))
            for row, old_row in zip(result['cumulative'], baseline[name]['cumulative']):
                np.testing.assert_equal(row['distance_km'], old_row['distance_km'])
                np.testing.assert_allclose(row['gdp'], source_circle(new, 1, latitude, longitude, row['distance_km']), rtol=1e-12)
                for field in UNCHANGED_FIELDS:
                    np.testing.assert_equal(row[field], old_row[field])
            circle = dict(name=name, latitude=latitude, longitude=longitude, radius_km=radius,
                          v3_gdp=baseline[name]['gdp'], v4_gdp=result['gdp'],
                          population=result['population'], gdp_per_head=result['gdp_per_head'],
                          milliseconds=milliseconds)
            report['circles'].append(circle)
            print(json.dumps(circle), flush=True)
    (BUILD / 'circles.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Verified {len(report["circles"])} circles, including cumulative GDP and unchanged population and stops.')


if __name__ == '__main__':
    main()

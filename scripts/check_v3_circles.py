"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Check the real preview API against source grids and per-cell transit counts.
"""
import argparse
import json

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from build_layers import BUILD
from build_tiles import ROOT, open_sources
from check_gdp_layers import query, source_circle
from overture_grid import OvertureGrid

CIRCLES = [
    ('Midtown and Lower Manhattan', 40.73756, -73.99429, 6),
    ('Tokyo Marunouchi', 35.6812, 139.7671, 3),
    ('Bank', 51.5133, -.0886, 3), ('Canary Wharf', 51.5054, -.0235, 3),
    ('Zuidas', 52.3383, 4.8728, 3), ('Schiphol', 52.3105, 4.7683, 3),
    ('La Défense', 48.8920, 2.2380, 3), ('Rotterdam', 51.93467, 4.55658, 50),
    ('Shanghai Lujiazui', 31.2397, 121.4998, 3), ('Beijing Guomao', 39.9087, 116.4605, 3),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8787')
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    baseline_path = BUILD/'v2-api.json'
    if args.baseline:
        baseline = {name: query(args.origin, lat, lon, radius)[0]
                    for name, lat, lon, radius in CIRCLES}
        baseline_path.write_text(json.dumps(baseline, indent=2)+'\n')
        print('Saved v2 preview API results for ten circles.')
        return
    baseline = json.loads(baseline_path.read_text())
    report = {'circles': [], 'stops': [], 'timings': []}
    gdp_source, population_source = open_sources()
    with gdp_source, population_source, rasterio.open(ROOT/'data/gdp-v2/gdp.tif') as old, rasterio.open(BUILD/'gdp.tif') as new:
        for name, lat, lon, radius in CIRCLES:
            result, milliseconds = query(args.origin, lat, lon, radius)
            expected = source_circle(new, 1, lat, lon, radius)
            expected_old = source_circle(old, 1, lat, lon, radius)
            np.testing.assert_allclose(result['gdp'], expected, rtol=1e-12)
            np.testing.assert_allclose(baseline[name]['gdp'], expected_old, rtol=1e-12)
            np.testing.assert_equal(result['population'], baseline[name]['population'])
            for row in result['cumulative']:
                np.testing.assert_allclose(row['gdp'], source_circle(new, 1, lat, lon, row['distance_km']), rtol=1e-12)
                for key in ('population',):
                    np.testing.assert_equal(row[key], baseline[name]['cumulative'][row['distance_km']-1][key])
            report['circles'].append(dict(name=name, radius_km=radius, v2_gdp=expected_old,
                                          v3_gdp=result['gdp'], population=result['population'], milliseconds=milliseconds))
        stop_names = ['bus_stops', 'tram_stops', 'rail_stops']
        stops = OvertureGrid(ROOT/'data/raw/overture/stops_per_cell.parquet', stop_names,
                              new.width, new.height)
        # A small in-memory raster uses the original per-cell counts, independently of tiles.
        from check_gdp_layers import bounding_window
        import math
        for name, lat, lon, radius, tom in [
            ('Amsterdam',52.3731,4.8922,5,[696,345,33]),
            ('Rotterdam',51.93467,4.55658,50,[11622,1036,180])]:
            angular = radius/6371.0088
            span = math.degrees(angular)
            lon_span = math.degrees(math.asin(math.sin(angular)/math.cos(math.radians(lat))))
            window = bounding_window(new,(lon-lon_span,lat-span,lon+lon_span,lat+span))
            result, milliseconds = query(args.origin,lat,lon,radius)
            for layer, values in zip(stop_names,stops.window(window)):
                with MemoryFile() as memory:
                    with memory.open(driver='GTiff',width=int(window.width),height=int(window.height),count=1,
                                     dtype='float32',transform=new.window_transform(window)) as source:
                        source.write(values.astype('float32'),1)
                        for row in result['cumulative']:
                            assert row[layer] == round(source_circle(source,1,lat,lon,row['distance_km']))
                        assert result[layer] == round(source_circle(source,1,lat,lon,radius))
            report['stops'].append(dict(name=name, ours={key:result[key] for key in stop_names},
                                        tom=dict(zip(stop_names,tom)), milliseconds=milliseconds))
    for name,lat,lon,radius in [('Rotterdam',51.93467,4.55658,50),('Paris',48.8566,2.3522,100)]:
        report['timings'].append(dict(name=name,radius_km=radius,
                                     milliseconds=[query(args.origin,lat,lon,radius)[1] for _ in range(2)]))
    (BUILD/'circles.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    main()

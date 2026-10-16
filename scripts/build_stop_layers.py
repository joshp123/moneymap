"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Build and read back the three independent transit-stop layers.
"""
import json
import time

import numpy as np

from build_layers import strips, write_tiles
from build_tiles import ROOT, TILE_SIZE, open_sources
from overture_grid import OvertureGrid


EXPECTED_TOTALS = {'bus_stops': 4167514, 'tram_stops': 51083, 'rail_stops': 138265}


def build():
    started = time.monotonic()
    for layer in EXPECTED_TOTALS:
        output = ROOT / 'data/layers' / layer
        if output.exists() and any(output.iterdir()):
            raise RuntimeError(f'{output} is not empty; move it aside before rebuilding')
    gdp, population = open_sources()
    with gdp, population:
        counts = OvertureGrid(ROOT / 'data/raw/overture/stops_per_cell.parquet',
                              EXPECTED_TOTALS, population.width, population.height)
        if counts.totals != EXPECTED_TOTALS:
            raise RuntimeError(f'Unexpected source stop totals: {counts.totals}')
        if any(counts.outside_totals.values()):
            raise RuntimeError(f'Stops outside the population grid: {counts.outside_totals}')
        tile_counts = dict.fromkeys(EXPECTED_TOTALS, 0)
        for window in strips(population):
            for layer, values in zip(EXPECTED_TOTALS, counts.window(window)):
                tile_counts[layer] += write_tiles(layer, values, int(window.row_off))
            if int(window.row_off) // TILE_SIZE % 20 == 0:
                print(f'Row {int(window.row_off) // TILE_SIZE}: {tile_counts}', flush=True)
    report = {'source_totals': counts.totals, 'outside_totals': counts.outside_totals, 'layers': {}}
    for layer, expected in EXPECTED_TOTALS.items():
        paths = list((ROOT / 'data/layers' / layer).glob('*/*.bin'))
        actual = sum(np.fromfile(path, dtype='<f4').sum(dtype='float64') for path in paths)
        if actual != expected:
            raise RuntimeError(f'{layer} tile total {actual} differs from source total {expected}')
        report['layers'][layer] = {'tile_count': len(paths), 'bytes': sum(path.stat().st_size for path in paths),
                                   'tile_total': float(actual)}
    report['seconds'] = time.monotonic() - started
    directory = ROOT / 'data/gdp-v3'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'stops.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    build()

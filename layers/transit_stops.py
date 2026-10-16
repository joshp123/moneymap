"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

Build the bus_stops, tram_stops and rail_stops layers from the per-cell stop
counts that sources/overture_stops.sql extracts, and read them back.

    devenv shell -- python -m layers.transit_stops
"""
import json
import time

from layers.grid import (BUILD_DIRECTORY, ROOT, TILE_SIZE, SparseCellCounts, layer_tile_paths,
                         layer_tile_total, require_empty_layer_directory, tile_row_strips, write_layer_tiles)

STOPS_PER_CELL = ROOT / 'data/raw/overture/stops_per_cell.parquet'
EXPECTED_TOTALS = {'bus_stops': 4167514, 'tram_stops': 51083, 'rail_stops': 138265}


def build():
    started = time.monotonic()
    for layer in EXPECTED_TOTALS:
        require_empty_layer_directory(layer)
    counts = SparseCellCounts(STOPS_PER_CELL, EXPECTED_TOTALS)
    if counts.totals != EXPECTED_TOTALS:
        raise RuntimeError(f'Unexpected source stop totals: {counts.totals}')
    if any(counts.outside_totals.values()):
        raise RuntimeError(f'Stops outside the population grid: {counts.outside_totals}')
    tile_counts = dict.fromkeys(EXPECTED_TOTALS, 0)
    for window in tile_row_strips():
        for layer, values in zip(EXPECTED_TOTALS, counts.window(window)):
            tile_counts[layer] += write_layer_tiles(layer, values, int(window.row_off))
        if int(window.row_off) // TILE_SIZE % 20 == 0:
            print(f'Row {int(window.row_off) // TILE_SIZE}: {tile_counts}', flush=True)
    report = {'source_totals': counts.totals, 'outside_totals': counts.outside_totals, 'layers': {}}
    for layer, expected in EXPECTED_TOTALS.items():
        paths = layer_tile_paths(layer)
        actual = layer_tile_total(layer)
        if actual != expected:
            raise RuntimeError(f'{layer} tile total {actual} differs from source total {expected}')
        report['layers'][layer] = {'tile_count': len(paths), 'bytes': sum(path.stat().st_size for path in paths),
                                   'tile_total': float(actual)}
    report['seconds'] = time.monotonic() - started
    BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (BUILD_DIRECTORY / 'transit-stops.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    build()

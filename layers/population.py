"""Written by AI on 2026.10.16 by model claude opus 5.5.

Build the population layer: GHS-POP 2025 residents per cell, unchanged.

    devenv shell -- python -m layers.population
"""
import json

import numpy as np

from layers.grid import (BUILD_DIRECTORY, TILE_SIZE, layer_tile_paths, layer_tile_total,
                         open_kummu_gdp_and_population, read_window_zero_filled,
                         require_empty_layer_directory, tile_row_strips, write_layer_tiles)


def build():
    require_empty_layer_directory('population')
    source_total = 0.0
    gdp, population = open_kummu_gdp_and_population()
    with gdp, population:
        for window in tile_row_strips():
            values = read_window_zero_filled(population, 1, window)
            source_total += values.sum(dtype='float64')
            write_layer_tiles('population', values, int(window.row_off))
    tile_total = layer_tile_total('population')
    np.testing.assert_allclose(tile_total, source_total, rtol=1e-12)
    tile_count = len(layer_tile_paths('population'))
    report = dict(source_population=source_total, tile_population=tile_total,
                  tiles=dict(count=tile_count, bytes=tile_count * TILE_SIZE * TILE_SIZE * 4))
    BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (BUILD_DIRECTORY / 'population.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    build()

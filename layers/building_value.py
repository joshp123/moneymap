"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Spread national building values using the held-out choice of spatial weights.
Buildings exclude civil-engineering structures. Country ownership is identical
to land and GDP; the existing layers are only read.

    devenv shell -- python -m layers.building_value
"""
import argparse
import json

import numpy as np
import rasterio
from rasterio.windows import Window

from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.gdp.building_weight import check_built_grid_alignment
from layers.grid import (BUILD_DIRECTORY, GHS_POPULATION_ZIP, ROOT, TILE_SIZE,
                         layer_tile_total, open_zipped_raster, raster_profile,
                         read_window_zero_filled, require_empty_layer_directory,
                         tile_row_strips, write_layer_tiles)
from layers.land_value.build import country_assignment
from sources.building_value import national_totals, national_summary, write_country_table

BUILDING_BUILD_DIRECTORY = BUILD_DIRECTORY / 'building_value'
TOTAL_BUILT_VOLUME_ZIP = ROOT / 'data/raw/research-gdp/built_v_30ss.zip'
WEIGHTS = {
    'volume': ('volume',),
    'population': ('population',),
    'population_gdp': ('population', 'gdp'),
    'population_gdp_volume': ('population', 'gdp', 'volume'),
}
SELECTED_WEIGHT = 'population_gdp_volume'


def shifted_building_volume(volume, window, grid):
    """POP column k receives 0.8 BUILT[k-1] + 0.2 BUILT[k], including edge cells."""
    start = max(0, int(window.col_off)-1)
    end = min(volume.width, int(window.col_off+window.width))
    values = volume.read(1, window=Window(start, window.row_off, end-start, window.height),
                         masked=True).filled(0).astype('float64')
    output = np.zeros((int(window.height), int(window.width)), dtype='float64')
    east_fraction = (volume.transform.c-grid.transform.c)/grid.transform.a
    for shift, fraction in ((1, east_fraction), (0, 1-east_fraction)):
        target_start = max(int(window.col_off), start+shift)
        target_end = min(int(window.col_off+window.width), end+shift)
        if target_end > target_start:
            output[:, target_start-int(window.col_off):target_end-int(window.col_off)] += (
                fraction * values[:, target_start-shift-start:target_end-shift-start])
    return output


def allocate(components, country_labels, country_totals, country_component_sums, weight):
    names = WEIGHTS[weight]
    values = np.zeros_like(components[names[0]], dtype='float64')
    for name in names:
        sums = country_component_sums[name]
        scale = np.divide(country_totals, len(names) * sums, out=np.zeros_like(country_totals),
                          where=sums > 0)
        values += components[name] * scale[country_labels]
    return values.astype('<f4')


def weight_components():
    """Use the already checked component sums for candidate scoring."""
    countries, country_of_unit = country_assignment()
    buildings = json.loads((BUILDING_BUILD_DIRECTORY / 'conservation.json').read_text())
    gdp = json.loads((GDP_BUILD_DIRECTORY / 'conservation.json').read_text())
    targets = np.array([0.] + [buildings['countries'][c]['total_usd2024'] for c in countries])
    sums = dict(volume=np.array([0.] + [buildings['countries'][c]['built_volume_m3'] for c in countries]),
                gdp=np.array([0.] + [gdp['countries'][c]['built'] for c in countries]),
                population=np.bincount(country_of_unit[1:],
                                       weights=[unit['population'] for unit in gdp['units']],
                                       minlength=len(targets)))
    output = dict(countries=countries, targets=targets.tolist(),
                  component_sums={name: values.tolist() for name, values in sums.items()})
    (BUILDING_BUILD_DIRECTORY / 'weight_components.json').write_text(json.dumps(output, indent=2)+'\n')
    return countries, country_of_unit, targets, sums


def build(weight):
    require_empty_layer_directory('building_value')
    BUILDING_BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    countries, country_of_unit = country_assignment()
    records = national_totals(countries)
    write_country_table(records, BUILDING_BUILD_DIRECTORY / 'country_totals.csv')
    targets = np.array([0.] + [records[country]['total_usd2024'] for country in countries])
    component_sums = {name: np.zeros_like(targets) for name in ('volume', 'population', 'gdp')}
    built_sums = np.zeros_like(targets)
    weight_path = BUILDING_BUILD_DIRECTORY / 'built_volume.tif'
    with open_zipped_raster(GHS_POPULATION_ZIP) as grid, \
            open_zipped_raster(TOTAL_BUILT_VOLUME_ZIP) as volume, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as ownership:
        check_built_grid_alignment(grid, volume, volume)
        with rasterio.open(weight_path, 'w', **raster_profile(grid, 'float64')) as weights:
            for window in tile_row_strips():
                labels = country_of_unit[ownership.read(1, window=window)]
                values = shifted_building_volume(volume, window, grid)
                weights.write(values, 1, window=window)
                components = dict(volume=values, population=read_window_zero_filled(grid, 1, window),
                                  gdp=read_window_zero_filled(gdp, 1, window))
                for name, cells in components.items():
                    component_sums[name] += np.bincount(labels.ravel(), weights=cells.ravel(), minlength=len(targets))
                if window.row_off % 2400 == 0:
                    print(f'Building volume: row {window.row_off}', flush=True)
        missing = [country for index, country in enumerate(countries, 1)
                   if targets[index] > 0 and any(component_sums[name][index] <= 0 for name in WEIGHTS[weight])]
        if missing:
            raise RuntimeError(f'Countries with building value but a missing weight component: {missing}')
        tile_count = 0
        with rasterio.open(weight_path) as weights, \
                rasterio.open(BUILDING_BUILD_DIRECTORY / 'building_value.tif', 'w',
                              **raster_profile(grid, 'float32')) as built:
            for window in tile_row_strips():
                labels = country_of_unit[ownership.read(1, window=window)]
                components = dict(volume=weights.read(1, window=window),
                                  population=read_window_zero_filled(grid, 1, window),
                                  gdp=read_window_zero_filled(gdp, 1, window))
                values = allocate(components, labels, targets, component_sums, weight)
                built.write(values, 1, window=window)
                built_sums += np.bincount(labels.ravel(), weights=values.ravel(), minlength=len(targets))
                tile_count += write_layer_tiles('building_value', values, int(window.row_off))
                if window.row_off % 2400 == 0:
                    print(f'Building tiles: row {window.row_off}', flush=True)
    np.testing.assert_allclose(built_sums, targets, rtol=8e-8, atol=.01)
    tile_total = layer_tile_total('building_value')
    np.testing.assert_allclose(tile_total, built_sums.sum(), rtol=1e-12, atol=.01)
    report = dict(**national_summary(records), weight=weight, built_total=float(built_sums.sum()), tile_total=tile_total,
                  max_country_relative_error=float(np.max(np.abs(built_sums[1:]/targets[1:]-1))),
                  tiles=dict(count=tile_count, bytes=tile_count*TILE_SIZE*TILE_SIZE*4),
                  countries={country: dict(**records[country], built=float(built_sums[index]),
                                           built_volume_m3=float(component_sums['volume'][index]),
                                           population=float(component_sums['population'][index]),
                                           gdp=float(component_sums['gdp'][index]))
                             for index, country in enumerate(countries, 1)})
    (BUILDING_BUILD_DIRECTORY / 'conservation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'countries'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weight', choices=WEIGHTS, default=SELECTED_WEIGHT)
    build(parser.parse_args().weight)

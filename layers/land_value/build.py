"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Build land value in 2024 US dollars, excluding buildings. Country totals come
from national balance sheets or the fixed big-city-share model. The within-
country rule mixes density-weighted population and production GDP equally.

    devenv shell -- python -m layers.land_value.build
"""
import json

import numpy as np
import rasterio

from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.grid import (BUILD_DIRECTORY, TILE_SIZE, layer_tile_total, open_zipped_raster,
                         GHS_POPULATION_ZIP, raster_profile, read_window_zero_filled,
                         require_empty_layer_directory, tile_row_strips, write_layer_tiles)
from layers.land_value.allocation import allocate
from layers.land_value.density import coarse_population, neighbourhood_density, weighted_population
from sources.land_value import national_summary, national_totals, write_country_table

LAND_BUILD_DIRECTORY = BUILD_DIRECTORY / 'land_value'


def country_assignment():
    """Map the existing GDP cell owners to their countries, without rasterising again."""
    report = json.loads((GDP_BUILD_DIRECTORY / 'conservation.json').read_text())
    countries = sorted(report['countries'])
    numbers = {code: number for number, code in enumerate(countries, 1)}
    country_of_unit = np.array([0] + [numbers[unit['country']] for unit in report['units']])
    return countries, country_of_unit


def build():
    require_empty_layer_directory('land_value')
    LAND_BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    countries, country_of_unit = country_assignment()
    records = national_totals(countries)
    write_country_table(records, LAND_BUILD_DIRECTORY / 'country_totals.csv')
    totals = np.array([0.] + [records[country]['total_usd2024'] for country in countries])
    population_sums, gdp_sums, built_sums = (np.zeros_like(totals) for _ in range(3))
    with open_zipped_raster(GHS_POPULATION_ZIP) as population, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as ownership:
        density = neighbourhood_density(coarse_population(population))
        np.savez_compressed(LAND_BUILD_DIRECTORY / 'density_5arcmin.npz', density=density)
        population_weight_path = LAND_BUILD_DIRECTORY / 'population_weight.tif'
        with rasterio.open(population_weight_path, 'w', **raster_profile(population, 'float64')) as weights:
            for window in tile_row_strips():
                labels = country_of_unit[ownership.read(1, window=window)]
                residents = read_window_zero_filled(population, 1, window)
                population_weight = weighted_population(residents, density, window)
                weights.write(population_weight, 1, window=window)
                production = read_window_zero_filled(gdp, 1, window)
                population_sums += np.bincount(labels.ravel(), weights=population_weight.ravel(), minlength=len(totals))
                gdp_sums += np.bincount(labels.ravel(), weights=production.ravel(), minlength=len(totals))
                if window.row_off % 2400 == 0:
                    print(f'Land country sums: row {window.row_off}', flush=True)
        if np.any((totals > 0) & (population_sums <= 0) & (gdp_sums <= 0)):
            raise RuntimeError('A country with land value has neither population nor GDP cells')
        tile_count = 0
        with rasterio.open(population_weight_path) as weights, \
                rasterio.open(LAND_BUILD_DIRECTORY / 'land_value.tif', 'w', **raster_profile(population, 'float32')) as built:
            for window in tile_row_strips():
                labels = country_of_unit[ownership.read(1, window=window)]
                values = allocate(weights.read(1, window=window), read_window_zero_filled(gdp, 1, window),
                                  labels, totals, population_sums, gdp_sums)
                built.write(values, 1, window=window)
                built_sums += np.bincount(labels.ravel(), weights=values.ravel(), minlength=len(totals))
                tile_count += write_layer_tiles('land_value', values, int(window.row_off))
                if window.row_off % 2400 == 0:
                    print(f'Land tiles: row {window.row_off}', flush=True)
    np.testing.assert_allclose(built_sums, totals, rtol=8e-8, atol=.01)
    tile_total = layer_tile_total('land_value')
    np.testing.assert_allclose(tile_total, built_sums.sum(), rtol=1e-12, atol=.01)
    report = dict(**national_summary(records), built_total=float(built_sums.sum()), tile_total=tile_total,
                  max_country_relative_error=float(np.max(np.abs(built_sums[1:]/totals[1:]-1))),
                  tiles=dict(count=tile_count, bytes=tile_count*TILE_SIZE*TILE_SIZE*4),
                  countries={country: dict(**records[country], built=float(built_sums[index]),
                                           population_weight=float(population_sums[index]), gdp=float(gdp_sums[index]))
                             for index, country in enumerate(countries, 1)})
    (LAND_BUILD_DIRECTORY / 'conservation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'countries'}, indent=2), flush=True)


if __name__ == '__main__':
    build()

"""Written by AI on 2026.10.17 by model gpt-6.1-sol.

Spread national building values by 70% population share and 30% production GDP
share. Buildings exclude civil-engineering structures. Country ownership and
national totals are identical to the previous building layer.

    devenv shell -- python -m layers.building_value
"""
import json

import numpy as np
import rasterio

from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.grid import (BUILD_DIRECTORY, GHS_POPULATION_ZIP, TILE_SIZE,
                         layer_tile_total, open_zipped_raster, raster_profile,
                         read_window_zero_filled, require_empty_layer_directory,
                         tile_row_strips, write_layer_tiles)
from layers.land_value.build import country_assignment
from sources.building_value import national_totals, national_summary, write_country_table

BUILDING_BUILD_DIRECTORY = BUILD_DIRECTORY / 'building_value'


def allocate(population, gdp, labels, totals, population_sums, gdp_sums):
    """Return float32 cell values; country arrays include unused country zero."""
    population_scale = np.divide(.7 * totals, population_sums, out=np.zeros_like(totals),
                                 where=population_sums > 0)
    gdp_scale = np.divide(.3 * totals, gdp_sums, out=np.zeros_like(totals), where=gdp_sums > 0)
    return (population * population_scale[labels] + gdp * gdp_scale[labels]).astype('<f4')


def build():
    require_empty_layer_directory('building_value')
    BUILDING_BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    countries, country_of_unit = country_assignment()
    records = national_totals(countries)
    write_country_table(records, BUILDING_BUILD_DIRECTORY / 'country_totals.csv')
    totals = np.array([0.] + [records[country]['total_usd2024'] for country in countries])
    population_sums, gdp_sums, built_sums = (np.zeros_like(totals) for _ in range(3))
    with open_zipped_raster(GHS_POPULATION_ZIP) as population, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as ownership:
        for window in tile_row_strips():
            labels = country_of_unit[ownership.read(1, window=window)]
            residents = read_window_zero_filled(population, 1, window)
            production = read_window_zero_filled(gdp, 1, window)
            population_sums += np.bincount(labels.ravel(), weights=residents.ravel(), minlength=len(totals))
            gdp_sums += np.bincount(labels.ravel(), weights=production.ravel(), minlength=len(totals))
            if window.row_off % 2400 == 0:
                print(f'Building country sums: row {window.row_off}', flush=True)
        missing = [country for index, country in enumerate(countries, 1)
                   if totals[index] > 0 and (population_sums[index] <= 0 or gdp_sums[index] <= 0)]
        if missing:
            raise RuntimeError(f'Countries with building value but missing population or GDP: {missing}')
        tile_count = 0
        with rasterio.open(BUILDING_BUILD_DIRECTORY / 'building_value.tif', 'w',
                           **raster_profile(population, 'float32')) as built:
            for window in tile_row_strips():
                labels = country_of_unit[ownership.read(1, window=window)]
                values = allocate(read_window_zero_filled(population, 1, window),
                                  read_window_zero_filled(gdp, 1, window), labels, totals,
                                  population_sums, gdp_sums)
                built.write(values, 1, window=window)
                built_sums += np.bincount(labels.ravel(), weights=values.ravel(), minlength=len(totals))
                tile_count += write_layer_tiles('building_value', values, int(window.row_off))
                if window.row_off % 2400 == 0:
                    print(f'Building tiles: row {window.row_off}', flush=True)
    np.testing.assert_allclose(built_sums, totals, rtol=8e-8, atol=.01)
    tile_total = layer_tile_total('building_value')
    np.testing.assert_allclose(tile_total, built_sums.sum(), rtol=1e-12, atol=.01)
    report = dict(**national_summary(records), weight='0.7 population share + 0.3 GDP share',
                  built_total=float(built_sums.sum()), tile_total=tile_total,
                  max_country_relative_error=float(np.max(np.abs(built_sums[1:]/totals[1:]-1))),
                  tiles=dict(count=tile_count, bytes=tile_count*TILE_SIZE*TILE_SIZE*4),
                  countries={country: dict(**records[country], built=float(built_sums[index]),
                                           population=float(population_sums[index]), gdp=float(gdp_sums[index]))
                             for index, country in enumerate(countries, 1)})
    (BUILDING_BUILD_DIRECTORY / 'conservation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'countries'}, indent=2), flush=True)


if __name__ == '__main__':
    build()

"""Written by AI on 2026.10.17 by model claude fable 5.1.

Pull every input the land/building split could use out of the built grids, one
row per populated cell, for the countries that have official valuations to test
against. Later scripts attach valuation-unit labels to these cells and score
candidate rules without touching the rasters again.

Per cell: grid row and column, residents (GHS-POP 2025), the site's GDP layer,
GHSL built volume (shifted onto the population grid as production does),
population density within about 40 km, GDP within the same 40 km kernel, and in
the US LODES all jobs and high-pay jobs.

Writes data/experiments/split/gdp_density_5arcmin.npz and cells_<ISO3>.npz.

    devenv shell -- python -m research.split.extract_cells
"""
import time

import numpy as np
import rasterio

from layers.building_value import BUILDING_BUILD_DIRECTORY
from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.grid import (GHS_POPULATION_ZIP, ROOT, SparseCellCounts, open_zipped_raster,
                         read_window_zero_filled, window_strips)
from layers.land_value.build import LAND_BUILD_DIRECTORY, country_assignment
from layers.land_value.density import coarse_population, interpolate_density, neighbourhood_density

SPLIT_DIRECTORY = ROOT / 'data/experiments/split'
JOBS_PER_CELL = ROOT / 'data/raw/lodes/jobs_per_cell.parquet'

# Bounding boxes (west, south, east, north). Cells are kept only where the GDP
# layer's ownership raster says they belong to the country, so boxes may overlap
# neighbours. The US box omits the Aleutian islands west of the dateline.
COUNTRY_BOXES = {
    'USA': [(-125.0, 24.3, -66.8, 49.6), (-160.5, 18.8, -154.6, 22.4), (-170.0, 51.0, -129.9, 71.6)],
    'DEU': [(5.8, 47.2, 15.1, 55.1)],
    'JPN': [(122.9, 24.0, 146.1, 45.7)],
    'DNK': [(8.0, 54.5, 15.3, 57.8)],
    'AUS': [(112.9, -43.8, 153.7, -10.5)],
    'CAN': [(-141.1, 41.6, -52.5, 83.2)],
    'NLD': [(3.3, 50.7, 7.3, 53.6)],
    'GBR': [(-8.7, 49.8, 1.8, 60.9)],
}


def gdp_neighbourhood_density(gdp):
    """GDP per km² under the same 40 km kernel as the land layer's population density."""
    path = SPLIT_DIRECTORY / 'gdp_density_5arcmin.npz'
    if path.exists():
        return np.load(path)['density']
    started = time.time()
    density = neighbourhood_density(coarse_population(gdp))
    np.savez_compressed(path, density=density)
    print(f'GDP neighbourhood density computed in {time.time() - started:.0f} s', flush=True)
    return density


def extract(country, country_index, country_of_unit, population, gdp, volume, ownership,
            population_density, gdp_density, jobs):
    columns = {name: [] for name in ('row', 'col', 'population', 'gdp', 'volume',
                                     'density', 'gdp_density', 'all_jobs', 'high_pay_jobs')}
    for bounds in COUNTRY_BOXES[country]:
        for window in window_strips(gdp, bounds):
            labels = country_of_unit[ownership.read(1, window=window)]
            residents = read_window_zero_filled(population, 1, window)
            production = read_window_zero_filled(gdp, 1, window)
            built = read_window_zero_filled(volume, 1, window)
            keep = (labels == country_index) & ((residents > 0) | (production > 0) | (built > 0))
            if not keep.any():
                continue
            rows, cols = np.nonzero(keep)
            columns['row'].append((rows + int(window.row_off)).astype('int32'))
            columns['col'].append((cols + int(window.col_off)).astype('int32'))
            columns['population'].append(residents[keep])
            columns['gdp'].append(production[keep])
            columns['volume'].append(built[keep])
            columns['density'].append(interpolate_density(population_density, window)[keep].astype('float32'))
            columns['gdp_density'].append(interpolate_density(gdp_density, window)[keep].astype('float32'))
            if jobs is not None:
                all_jobs, high_pay = jobs.window(window)
                columns['all_jobs'].append(all_jobs[keep].astype('float32'))
                columns['high_pay_jobs'].append(high_pay[keep].astype('float32'))
    arrays = {name: np.concatenate(values) for name, values in columns.items() if values}
    np.savez_compressed(SPLIT_DIRECTORY / f'cells_{country}.npz', **arrays)
    print(f"{country}: {len(arrays['row']):,} cells, residents {arrays['population'].sum(dtype='float64'):,.0f}, "
          f"GDP {arrays['gdp'].sum(dtype='float64') / 1e9:,.0f} bn", flush=True)


def main():
    SPLIT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    countries, country_of_unit = country_assignment()
    population_density = np.load(LAND_BUILD_DIRECTORY / 'density_5arcmin.npz')['density']
    jobs = SparseCellCounts(JOBS_PER_CELL, ['all_jobs', 'high_pay_jobs'])
    with open_zipped_raster(GHS_POPULATION_ZIP) as population, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif') as gdp, \
            rasterio.open(BUILDING_BUILD_DIRECTORY / 'built_volume.tif') as volume, \
            rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as ownership:
        gdp_density = gdp_neighbourhood_density(gdp)
        for country in COUNTRY_BOXES:
            started = time.time()
            extract(country, countries.index(country) + 1, country_of_unit, population, gdp, volume,
                    ownership, population_density, gdp_density, jobs if country == 'USA' else None)
            print(f'{country}: {time.time() - started:.0f} s', flush=True)


if __name__ == '__main__':
    main()

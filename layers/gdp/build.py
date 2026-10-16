"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

Build the GDP layer: Kummu's 2024 country totals, split between official
regional units by their official shares, then spread over cells by
layers/gdp/allocation.py.

Writes data/layers/gdp/ and, in data/build/gdp/, the control unit of every cell
(control-ids.tif), the GDP grid (gdp.tif) and conservation.json, which checks
every unit and country total and records each unit's weights.

    devenv shell -- python -m layers.gdp.build
"""
from collections import defaultdict
from contextlib import ExitStack
import json

import numpy as np
import rasterio

from layers.gdp.allocation import US_JOB_WEIGHT, Weights, allocate, uses_job_weight, uses_workplace_places
from layers.gdp.building_weight import (building_weight_q, check_built_grid_alignment,
                                        open_nonresidential_volume_and_surface)
from layers.gdp.cell_ownership import CellOwnership, sum_by_unit
from layers.grid import (BUILD_DIRECTORY, GRID_HEIGHT, GRID_WIDTH, KUMMU_GDP_2024_BAND, ROOT, TILE_SIZE,
                         SparseCellCounts, layer_tile_total, open_kummu_gdp_and_population, raster_profile,
                         read_window_zero_filled, require_empty_layer_directory, tile_row_strips, write_layer_tiles)
from sources.regional_gdp import load_kummu_reported_controls, load_official_controls

GDP_BUILD_DIRECTORY = BUILD_DIRECTORY / 'gdp'
WORKPLACE_PLACES = ROOT / 'data/raw/overture/places_per_cell.parquet'
WORKPLACE_JOBS = ROOT / 'data/raw/lodes/jobs_per_cell.parquet'


def cell_weights(population, volume, surface, grid, places, jobs, window):
    all_jobs, high_pay_jobs = jobs.window(window)
    return Weights(population=read_window_zero_filled(population, 1, window),
                   building_q=building_weight_q(volume, surface, window, grid),
                   workplace_places=places.window(window)[0],
                   all_jobs=all_jobs, high_pay_jobs=high_pay_jobs)


def weight_name(unit_sums, total, index, uses_jobs, uses_places, centroid):
    if not total:
        return 'no GDP'
    if centroid:
        return 'centroid cell'
    if uses_jobs:
        return US_JOB_WEIGHT
    if uses_places:
        return 'population, buildings and workplace places'
    if unit_sums.population[index] and unit_sums.building_q[index]:
        return 'population and buildings'
    return 'population' if unit_sums.population[index] else 'buildings'


def build():
    require_empty_layer_directory('gdp')
    GDP_BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    kummu_units = load_kummu_reported_controls()
    official_units, official_sums = load_official_controls()
    ownership = CellOwnership(kummu_units, official_units, set(official_sums))
    units, countries = ownership.units, ownership.countries
    unit_count = len(units)
    is_us_unit = np.array([False] + [unit.country == 'USA' for unit in units])
    country_totals = np.zeros(len(countries) + 1)
    kummu_unit_totals = np.zeros(len(kummu_units) + 1)
    unit_sums = Weights(*(np.zeros(unit_count + 1) for _ in range(5)))
    cell_counts = np.zeros(unit_count + 1)
    source_gdp = 0.0
    with ExitStack() as stack:
        gdp, population = open_kummu_gdp_and_population()
        stack.enter_context(gdp)
        stack.enter_context(population)
        volume, surface = stack.enter_context(open_nonresidential_volume_and_surface())
        offset = check_built_grid_alignment(gdp, volume, surface)
        places = SparseCellCounts(WORKPLACE_PLACES, ['workplace_places'])
        jobs = SparseCellCounts(WORKPLACE_JOBS, ['all_jobs', 'high_pay_jobs'])
        labels_file = GDP_BUILD_DIRECTORY / 'control-ids.tif'
        with rasterio.open(labels_file, 'w', **raster_profile(gdp, 'uint32')) as labels_output:
            for window in tile_row_strips():
                cells = cell_weights(population, volume, surface, gdp, places, jobs, window)
                kummu_gdp = read_window_zero_filled(gdp, KUMMU_GDP_2024_BAND, window)
                occupied = (cells.population > 0) | (kummu_gdp > 0) | (cells.building_q > 0)
                kummu_ids, country_ids, labels = ownership.assign(window, gdp.transform, occupied)
                labels_output.write(labels, 1, window=window)
                country_totals += sum_by_unit(country_ids, kummu_gdp, len(countries))
                kummu_unit_totals += sum_by_unit(kummu_ids, kummu_gdp, len(kummu_units))
                for name in ('population', 'building_q', 'workplace_places', 'all_jobs', 'high_pay_jobs'):
                    getattr(unit_sums, name)[:] += sum_by_unit(labels, getattr(cells, name), unit_count)
                cell_counts += np.bincount(labels.ravel(), minlength=unit_count + 1)
                source_gdp += kummu_gdp.sum(dtype='float64')
                if window.row_off % 2400 == 0: print(f'Control unit sums: row {window.row_off}', flush=True)
        # LODES covers the US only; the few jobs in cells owned by neighbouring countries carry no weight.
        jobs_outside_us_units = {name: float(jobs.totals[name] - getattr(unit_sums, name)[is_us_unit].sum())
                                 for name in ('all_jobs', 'high_pay_jobs')}
        unit_sums.all_jobs[~is_us_unit] = 0
        unit_sums.high_pay_jobs[~is_us_unit] = 0
        kummu_by_code = {unit.code: kummu_unit_totals[i + 1] for i, unit in enumerate(kummu_units)}
        country_number = {country: i + 1 for i, country in enumerate(countries)}
        totals = np.array([0] + [country_totals[country_number[unit.country]] * unit.value / official_sums[unit.country]
                                 if unit.country in official_sums else kummu_by_code[unit.code] for unit in units])
        totals[0] = 0
        uses_jobs = uses_job_weight(unit_sums, US_JOB_WEIGHT)
        # A unit with no weight in any cell, often too small to contain a cell centre, goes to its centroid cell.
        centroid_cells = defaultdict(list)
        uses_centroid = np.zeros(unit_count + 1, dtype=bool)
        for i, unit in enumerate(units, 1):
            if totals[i] and not (unit_sums.population[i] or unit_sums.building_q[i] or uses_jobs[i]):
                centroid = ownership.unit_index.geometries[i - 1].centroid
                row, col = gdp.index(centroid.x, centroid.y)
                row, col = np.clip(row, 0, GRID_HEIGHT - 1), np.clip(col, 0, GRID_WIDTH - 1)
                centroid_cells[(int(row) // TILE_SIZE) * TILE_SIZE].append((i, int(row), int(col)))
                uses_centroid[i] = True
        built_unit_totals = np.zeros_like(totals)
        built_gdp = 0.0
        tile_count = 0
        with rasterio.open(labels_file) as labels_source, rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif', 'w', **raster_profile(gdp, 'float32')) as built:
            for window in tile_row_strips():
                labels = labels_source.read(1, window=window)
                cells = cell_weights(population, volume, surface, gdp, places, jobs, window)
                values = allocate(cells, labels, totals, unit_sums)
                built_unit_totals += sum_by_unit(labels, values, unit_count)
                for unit_id, row, col in centroid_cells[int(window.row_off)]:
                    values[row - int(window.row_off), col] += np.float32(totals[unit_id])
                    built_unit_totals[unit_id] += float(np.float32(totals[unit_id]))
                built.write(values, 1, window=window)
                built_gdp += values.sum(dtype='float64')
                tile_count += write_layer_tiles('gdp', values, int(window.row_off))
                if window.row_off % 2400 == 0: print(f'GDP tiles: row {window.row_off}', flush=True)
    np.testing.assert_allclose(built_unit_totals, totals, rtol=8e-8, atol=0.01)
    built_countries = np.bincount(ownership.unit_country, weights=built_unit_totals, minlength=len(countries) + 1)
    np.testing.assert_allclose(built_countries[1:], country_totals[1:], rtol=8e-8, atol=0.01)
    np.testing.assert_allclose(country_totals.sum(), source_gdp, rtol=1e-12)
    tile_gdp = layer_tile_total('gdp')
    np.testing.assert_allclose(tile_gdp, built_gdp, rtol=1e-12, atol=0.01)
    uses_places = uses_workplace_places(unit_sums) & ~uses_jobs
    with_gdp = totals > 0
    report = dict(
        source_gdp=source_gdp, built_gdp=built_gdp, tile_gdp=tile_gdp,
        tiles=dict(count=tile_count, bytes=tile_count * TILE_SIZE * TILE_SIZE * 4),
        max_unit_relative_error=float(np.max(np.abs(built_unit_totals[with_gdp] / totals[with_gdp] - 1))),
        max_country_relative_error=float(np.max(np.abs(built_countries[1:][country_totals[1:] > 0] / country_totals[1:][country_totals[1:] > 0] - 1))),
        us_job_weight=US_JOB_WEIGHT, us_units=int(is_us_unit.sum()), us_units_using_jobs=int(uses_jobs.sum()),
        jobs_in_grid=jobs.totals, jobs_outside_us_units=jobs_outside_us_units,
        places_units=int(uses_places.sum()), places_gdp=float(totals[uses_places].sum()),
        places_gdp_share=float(totals[uses_places].sum() / totals.sum()),
        workplace_places_in_grid=places.totals['workplace_places'],
        workplace_places_without_unit=float(unit_sums.workplace_places[0]),
        built_grid_offset=offset, coastal_cells_assigned_nearest=ownership.coastal_cells_assigned_nearest,
        official_boundary_gap_cells=ownership.official_boundary_gap_cells, centroid_units=int(uses_centroid.sum()),
        countries={country: dict(source=country_totals[i + 1], built=built_countries[i + 1], official_sum=official_sums.get(country))
                   for i, country in enumerate(countries)},
        units=[dict(country=unit.country, code=unit.code, name=unit.name, source=unit.source,
                    official=unit.value, target=totals[i], built=built_unit_totals[i], cells=int(cell_counts[i]),
                    population=unit_sums.population[i], building_q=unit_sums.building_q[i],
                    workplace_places=unit_sums.workplace_places[i], all_jobs=unit_sums.all_jobs[i],
                    high_pay_jobs=unit_sums.high_pay_jobs[i],
                    weight=weight_name(unit_sums, totals[i], i, uses_jobs[i], uses_places[i], uses_centroid[i]))
               for i, unit in enumerate(units, 1)])
    (GDP_BUILD_DIRECTORY / 'conservation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('countries', 'units')}, indent=2), flush=True)


if __name__ == '__main__':
    build()

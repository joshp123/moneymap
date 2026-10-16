"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Replace only US GDP cells using the workplace-job weight chosen by the hold-out.
"""
from contextlib import ExitStack
import json

import numpy as np
import rasterio

from build_layers import (RAW, clean_window, grouped_sum, open_zip_raster,
                          raster_profile, shifted_q, strips, write_tiles)
from build_tiles import ROOT, TILE_SIZE, open_sources
from overture_grid import OvertureGrid
from us_jobs_allocation import allocate_us_jobs

BUILD = ROOT / 'data/gdp-v4'
PREVIOUS = ROOT / 'data/gdp-v3'


def build():
    output = ROOT / 'data/layers/gdp'
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Preserve existing data/layers/gdp under data/gdp-v3/tiles before rebuilding')
    previous = json.loads((PREVIOUS / 'conservation.json').read_text())
    holdout = json.loads((BUILD / 'holdouts.json').read_text())
    candidate = holdout['chosen_weight']
    units = previous['units']
    count = len(units)
    us_unit = np.array([False] + [unit['country'] == 'USA' for unit in units])
    totals = np.array([0.] + [unit['target'] for unit in units])
    population_sums = np.array([0.] + [unit['population'] for unit in units])
    q_sums = np.array([0.] + [unit['q'] for unit in units])
    workplace_sums = np.array([0.] + [unit['workplace_places'] for unit in units])
    all_jobs_sums = np.zeros(count + 1)
    high_pay_jobs_sums = np.zeros(count + 1)
    for unit in holdout['job_units']:
        all_jobs_sums[unit['control_id']] = unit['all_jobs']
        high_pay_jobs_sums[unit['control_id']] = unit['high_pay_jobs']
    actual_us = np.zeros(count + 1)
    total = previous_total = 0.
    tile_count = non_us_cells_checked = changed_us_cells = 0
    with ExitStack() as stack:
        source_gdp, population = open_sources()
        stack.enter_context(source_gdp)
        stack.enter_context(population)
        old = stack.enter_context(rasterio.open(PREVIOUS / 'gdp.tif'))
        labels_source = stack.enter_context(rasterio.open(PREVIOUS / 'control-ids.tif'))
        volume = stack.enter_context(open_zip_raster(RAW / 'nres_v_30ss.zip'))
        surface = stack.enter_context(open_zip_raster(RAW / 'nres_s_30ss.zip'))
        jobs = OvertureGrid(ROOT / 'data/raw/lodes/jobs_per_cell.parquet',
                            ['all_jobs', 'high_pay_jobs'], old.width, old.height)
        places = OvertureGrid(ROOT / 'data/raw/overture/places_per_cell.parquet',
                              ['workplace_places'], old.width, old.height)
        built = stack.enter_context(rasterio.open(BUILD / 'gdp.tif', 'w', **raster_profile(old, 'float32')))
        for window in strips(old):
            labels = labels_source.read(1, window=window)
            us_cells = us_unit[labels]
            values = old.read(1, window=window)
            previous_total += values.sum(dtype='float64')
            if us_cells.any():
                pop = clean_window(population, 1, window)
                q = shifted_q(volume, surface, window, old)
                all_jobs, high_pay_jobs = jobs.window(window)
                allocated = allocate_us_jobs(
                    pop, q, places.window(window)[0], all_jobs, high_pay_jobs,
                    labels, totals, population_sums, q_sums, workplace_sums,
                    all_jobs_sums, high_pay_jobs_sums, candidate=candidate)
                actual_us += grouped_sum(labels[us_cells], allocated[us_cells], count)
                changed_us_cells += int(np.count_nonzero(values[us_cells] != allocated[us_cells]))
                values[us_cells] = allocated[us_cells]
            # Compare the final plane against its source, not merely its sums.
            original = old.read(1, window=window)
            assert np.array_equal(values[~us_cells], original[~us_cells])
            non_us_cells_checked += int((~us_cells).sum())
            built.write(values, 1, window=window)
            total += values.sum(dtype='float64')
            tile_count += write_tiles('gdp', values, int(window.row_off))
            if window.row_off % 2400 == 0:
                print(f'US GDP replacement: row {window.row_off}', flush=True)
    actual = np.array([0.] + [unit['built'] for unit in units])
    actual[us_unit] = actual_us[us_unit]
    np.testing.assert_allclose(actual, totals, rtol=8e-8, atol=.01)
    countries = {country: dict(values) for country, values in previous['countries'].items()}
    countries['USA']['built'] = float(actual[us_unit].sum())
    for values in countries.values():
        np.testing.assert_allclose(values['built'], values['source'], rtol=8e-8, atol=.01)
    np.testing.assert_allclose(total, sum(value['built'] for value in countries.values()), rtol=1e-12, atol=.01)
    tile_total = sum(np.fromfile(path, dtype='<f4').sum(dtype='float64') for path in output.glob('*/*.bin'))
    np.testing.assert_allclose(tile_total, total, rtol=1e-12, atol=.01)
    for index, unit in enumerate(units, 1):
        unit['built'] = float(actual[index])
        if us_unit[index]:
            unit['all_jobs'] = float(all_jobs_sums[index])
            unit['high_pay_jobs'] = float(high_pay_jobs_sums[index])
    job_sums = high_pay_jobs_sums if candidate == 'high_pay_jobs' else all_jobs_sums
    if candidate == 'half_jobs':
        job_sums = all_jobs_sums + high_pay_jobs_sums
    for index, unit in enumerate(units, 1):
        if us_unit[index]:
            unit['allocation'] = candidate if job_sums[index] else 'v3'
            if candidate != 'v3' and job_sums[index]:
                unit['uses_places'] = False
    report = dict(
        chosen_weight=candidate, source_gdp=previous['source_gdp'], previous_built_gdp=previous_total,
        built_gdp=total, tile_gdp=tile_total,
        tiles=dict(count=tile_count, bytes=tile_count*TILE_SIZE*TILE_SIZE*4),
        non_us_cells_identical=non_us_cells_checked, changed_us_cells=changed_us_cells,
        us_units=int(us_unit.sum()), us_units_without_jobs=int(np.count_nonzero(us_unit & (job_sums == 0))),
        max_unit_relative_error=float(np.max(np.abs(actual[totals>0]/totals[totals>0]-1))),
        max_country_relative_error=max(abs(value['built']/value['source']-1) for value in countries.values() if value['source']),
        countries=countries, units=units)
    (BUILD / 'conservation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('countries','units')}, indent=2), flush=True)


if __name__ == '__main__':
    build()

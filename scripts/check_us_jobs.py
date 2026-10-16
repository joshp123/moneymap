"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Choose a fixed US workplace weighting using state GDP held out to BEA counties.
"""
import json
import numpy as np
import rasterio

from build_layers import grouped_sum, strips
from build_tiles import ROOT
from check_gdp_v3 import scores, sha256
from overture_grid import OvertureGrid
from us_jobs_allocation import CANDIDATES, allocate_us_jobs


BUILD = ROOT / 'data/gdp-v4'
JOBS = ROOT / 'data/raw/lodes/jobs_per_cell.parquet'
BASELINE = ROOT / 'data/gdp-v3/conservation.json'
LABELS = ROOT / 'data/gdp-v3/control-ids.tif'


def job_control_sums(unit_count):
    all_jobs_sums = np.zeros(unit_count + 1)
    high_pay_jobs_sums = np.zeros(unit_count + 1)
    with rasterio.open(LABELS) as source:
        jobs = OvertureGrid(JOBS, ('all_jobs', 'high_pay_jobs'), source.width, source.height)
        for window in strips(source):
            labels = source.read(1, window=window)
            all_jobs, high_pay_jobs = jobs.window(window)
            all_jobs_sums += grouped_sum(labels, all_jobs, unit_count)
            high_pay_jobs_sums += grouped_sum(labels, high_pay_jobs, unit_count)
    return all_jobs_sums, high_pay_jobs_sums, jobs


def main():
    baseline = json.loads(BASELINE.read_text())
    units = baseline['units']
    all_jobs_sums, high_pay_jobs_sums, jobs = job_control_sums(len(units))
    ids = np.array([i + 1 for i, unit in enumerate(units) if unit['country'] == 'USA'])
    us_units = [units[i - 1] for i in ids]
    official = np.array([unit['official'] for unit in us_units])
    states, group_ids = np.unique([unit['code'][:2] for unit in us_units], return_inverse=True)
    labels = group_ids + 1
    components = {name: np.array([unit[name] for unit in us_units])
                  for name in ('population', 'q', 'workplace_places')}
    components.update(all_jobs=all_jobs_sums[ids], high_pay_jobs=high_pay_jobs_sums[ids])
    sums = {name: np.bincount(labels, weights=value, minlength=len(states) + 1)
            for name, value in components.items()}
    totals = np.bincount(labels, weights=official, minlength=len(states) + 1)
    results = {}
    for candidate in CANDIDATES:
        predicted = allocate_us_jobs(
            components['population'], components['q'], components['workplace_places'],
            components['all_jobs'], components['high_pay_jobs'], labels, totals,
            sums['population'], sums['q'], sums['workplace_places'], sums['all_jobs'],
            sums['high_pay_jobs'], candidate=candidate)
        np.testing.assert_allclose(np.bincount(labels, weights=predicted), totals, rtol=8e-8, atol=.01)
        results[candidate] = scores(predicted, official)
    winner = min(CANDIDATES, key=lambda candidate: results[candidate]['misallocated_share'])
    report = dict(
        basis='Production allocation on per-county cell sums, grouped to states. '
              'Allocation is linear within each state; float32 rounding is applied to '
              'held-out county totals rather than individual cells. All 50 states and '
              'Washington DC are included; DC contributes no within-state error.',
        units=len(ids), groups=len(states), candidates=results, chosen_weight=winner,
        jobs_sha256=sha256(JOBS), controls_sha256=sha256(LABELS),
        input_totals=jobs.totals, outside_grid_totals=jobs.outside_totals,
        unassigned_jobs=dict(all_jobs=float(all_jobs_sums[0]), high_pay_jobs=float(high_pay_jobs_sums[0])),
        us_job_totals=dict(all_jobs=float(all_jobs_sums[ids].sum()), high_pay_jobs=float(high_pay_jobs_sums[ids].sum())),
        outside_us_control_totals=dict(all_jobs=float(all_jobs_sums.sum() - all_jobs_sums[ids].sum()),
                                       high_pay_jobs=float(high_pay_jobs_sums.sum() - high_pay_jobs_sums[ids].sum())),
        units_without_all_jobs=int(np.count_nonzero(all_jobs_sums[ids] == 0)),
        units_without_high_pay_jobs=int(np.count_nonzero(high_pay_jobs_sums[ids] == 0)),
        county_codes_without_all_jobs=[unit['code'] for unit, i in zip(us_units, ids) if all_jobs_sums[i] == 0],
        county_codes_without_high_pay_jobs=[unit['code'] for unit, i in zip(us_units, ids) if high_pay_jobs_sums[i] == 0],
        job_units=[dict(control_id=int(i), all_jobs=float(all_jobs_sums[i]),
                        high_pay_jobs=float(high_pay_jobs_sums[i])) for i in ids])
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'holdouts.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'job_units'}, indent=2), flush=True)


if __name__ == '__main__':
    main()

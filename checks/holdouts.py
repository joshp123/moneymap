"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

Score the production allocation against official GDP held out one level finer
than the units it allocates from. Each test gives every coarse group its
official total, spreads it with layers/gdp/allocation.py, and compares the
result with the official figures of the finer units inside it.

Workplace places: four tests, with and without the places term, on the
per-unit sums that research/gdp/places_eval.py computed.
US industries: state CAGDP2 industry shares spread by the production industry
weights, compared with the previous high-pay-job rule.
US jobs: the earlier four-candidate test of state GDP spread to counties, on
the per-county sums that the GDP build recorded. Also reports how many jobs
the cell-centre rule places in a different county from their census block.

Allocation is linear within each group, so per-unit sums give the same answer
as per-cell allocation; only float32 rounding moves from cells to units.

    devenv shell -- python -m checks.holdouts
"""
import hashlib
import json

import numpy as np
import pyarrow.parquet as parquet
import rasterio
from rasterio.windows import Window

from layers.gdp.allocation import JOB_WEIGHTS, US_JOB_WEIGHT, Weights, allocate, allocate_industries, uses_workplace_places
from layers.gdp.build import GDP_BUILD_DIRECTORY, WORKPLACE_PLACES
from layers.grid import ROOT
from sources.lodes_jobs import INDUSTRY_JOBS_PER_CELL, RELEASES, read_workplace_blocks
from sources.us_industry_gdp import INDUSTRIES, state_industry_shares
from sources.regional_gdp import US_COMBINED_COUNTIES

RESEARCH_SUMS = ROOT / 'data/experiments/places'
REPORT = ROOT / 'data/checks/holdouts.json'
PLACES_TESTS = {
    'us': ('US county within state, BEA 2024',
           'County cell centres; all 50 states and Washington DC.'),
    'uk': ('UK MSOA within local authority, ONS 2023',
           'England and Wales LSOAs, 10 by 10 cell area fractions, aggregated to MSOAs.'),
    'eu': ('EU NUTS3 within NUTS2, Eurostat 2023',
           'NUTS3 cell centres; GISCO NUTS 2024 3M boundaries, as in the research.'),
    'br': ('Brazil municipality within state, IBGE 2023',
           'Municipality cell centres; IBGE boundaries, as in the research.'),
}
JOB_WEIGHT_NAMES = {None: 'population_buildings_and_workplace_places', 'all_jobs': 'all_jobs',
                    'high_pay_jobs': 'high_pay_jobs', 'all_and_high_pay_jobs': 'half_all_jobs_half_high_pay_jobs'}


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def scores(predicted, official):
    return {
        'misallocated_share': float(.5 * np.abs(predicted - official).sum() / official.sum()),
        'median_absolute_log_ratio': float(np.median(np.abs(np.log(predicted / official)))),
    }


def group_sums(labels, units, group_count):
    return Weights(*(None if values is None else np.bincount(labels, weights=values, minlength=group_count + 1)
                     for values in (units.population, units.building_q, units.workplace_places,
                                    units.all_jobs, units.high_pay_jobs)))


def workplace_places_test(key, title, basis):
    path = RESEARCH_SUMS / f'{key}_sums.json'
    data = json.loads(path.read_text())
    official = np.asarray(data['official'], dtype='float64')
    groups = np.asarray(data['group'])
    keep = np.isfinite(official) & (official > 0)
    _, group_ids = np.unique(groups[keep], return_inverse=True)
    if not data.get('keep_single_unit_groups'):
        keep[np.where(keep)[0][np.bincount(group_ids)[group_ids] < 2]] = False
    group_names, group_ids = np.unique(groups[keep], return_inverse=True)
    labels = group_ids + 1
    official = official[keep]
    units = Weights(population=np.asarray(data['pop'], dtype='float64')[keep],
                    building_q=np.asarray(data['q'], dtype='float64')[keep],
                    workplace_places=np.asarray(data['workplace_places'], dtype='float64')[keep])
    sums = group_sums(labels, units, len(group_names))
    totals = np.bincount(labels, weights=official, minlength=len(group_names) + 1)
    predictions = {name: allocate(units, labels, totals, sums, use_workplace_places=use_places, job_weight=None)
                   for name, use_places in (('without_places', False), ('with_places', True))}
    for predicted in predictions.values():
        np.testing.assert_allclose(np.bincount(labels, weights=predicted), totals, rtol=8e-8, atol=.01)
        if np.any(predicted <= 0):
            raise RuntimeError(f'{key}: a held-out unit has zero predicted GDP')
    result = dict(name=title, basis=basis, units=len(official), groups=len(group_names),
                  groups_using_places=int(uses_workplace_places(sums).sum()), sums_sha256=sha256(path),
                  **{name: scores(predicted, official) for name, predicted in predictions.items()})
    result['both_measures_improve'] = all(result['with_places'][measure] < result['without_places'][measure]
                                          for measure in result['without_places'])
    return result


def workplace_places_tests():
    table = parquet.read_table(WORKPLACE_PLACES, columns=['workplace_places'])
    total = int(table['workplace_places'].to_numpy().sum(dtype='int64'))
    research = json.loads((RESEARCH_SUMS / 'unit_sums_summary.json').read_text())
    if total != research['place_totals_in_grid']['workplace_places']:
        raise RuntimeError('Current Parquet workplace count differs from the researched component sums')
    return dict(workplace_places=total, places_sha256=sha256(WORKPLACE_PLACES),
                tests={key: workplace_places_test(key, *description) for key, description in PLACES_TESTS.items()})


def us_jobs_test(units):
    counties = [unit for unit in units if unit['country'] == 'USA']
    official = np.array([unit['official'] for unit in counties])
    states, group_ids = np.unique([unit['code'][:2] for unit in counties], return_inverse=True)
    labels = group_ids + 1
    county_sums = Weights(*(np.array([unit[name] for unit in counties])
                            for name in ('population', 'building_q', 'workplace_places', 'all_jobs', 'high_pay_jobs')))
    sums = group_sums(labels, county_sums, len(states))
    totals = np.bincount(labels, weights=official, minlength=len(states) + 1)
    results = {}
    for job_weight in JOB_WEIGHTS:
        predicted = allocate(county_sums, labels, totals, sums, job_weight=job_weight)
        np.testing.assert_allclose(np.bincount(labels, weights=predicted), totals, rtol=8e-8, atol=.01)
        results[JOB_WEIGHT_NAMES[job_weight]] = scores(predicted, official)
    best = min(results, key=lambda name: results[name]['misallocated_share'])
    return dict(name='US county within state, BEA 2024', counties=len(counties), states=len(states),
                weights=results, best_weight=best, selected_pre_industry_weight=US_JOB_WEIGHT,
                counties_without_high_pay_jobs=[unit['code'] for unit in counties if not unit['high_pay_jobs']])


US_BENCHMARK_AREAS = {
    'Bay Area (9 counties)': ['06001', '06013', '06041', '06055', '06075', '06081', '06085', '06095', '06097'],
    'Seattle (King, Pierce, Snohomish)': ['53033', '53053', '53061'],
    'New York City (5 boroughs)': ['36005', '36047', '36061', '36081', '36085'],
}


def us_industry_test(units):
    counties = [unit for unit in units if unit['country'] == 'USA']
    control_ids = np.array([index for index, unit in enumerate(units, 1) if unit['country'] == 'USA'])
    official = np.array([unit['official'] for unit in counties])
    states, state_ids = np.unique([unit['code'][:2] for unit in counties], return_inverse=True)
    labels = state_ids + 1
    table = parquet.read_table(INDUSTRY_JOBS_PER_CELL,
                              columns=['grid_row', 'grid_col', 'high_pay_jobs', *[name + '_hp' for name in INDUSTRIES]])
    with rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as ownership:
        owners = control_ids_for_cells(ownership, table['grid_row'].to_numpy(), table['grid_col'].to_numpy())

    def county_sums(column):
        return np.bincount(owners, weights=table[column].to_numpy(), minlength=len(units) + 1)[control_ids]

    high_pay = county_sums('high_pay_jobs')
    industry_weights = np.column_stack([county_sums(name + '_hp') for name in INDUSTRIES])
    state_totals = np.bincount(labels, weights=official, minlength=len(states) + 1)
    state_high_pay = np.bincount(labels, weights=high_pay, minlength=len(states) + 1)
    state_industry_weights = np.zeros((len(states) + 1, len(INDUSTRIES)))
    np.add.at(state_industry_weights, labels, industry_weights)
    industry_targets = np.zeros_like(state_industry_weights)
    industry_targets[1:] = state_industry_shares(states) * state_totals[1:, None]
    zeros = np.zeros(len(counties))
    county_weights = Weights(population=zeros, building_q=zeros, workplace_places=zeros,
                             all_jobs=zeros, high_pay_jobs=high_pay)
    predictions = {
        'high_pay_jobs': allocate(county_weights, labels, state_totals,
                                  group_sums(labels, county_weights, len(states)), job_weight='high_pay_jobs'),
        'industry_high_pay_jobs': allocate_industries(labels, industry_weights, high_pay, industry_targets,
                                                     state_industry_weights, state_high_pay),
    }
    for predicted in predictions.values():
        np.testing.assert_allclose(np.bincount(labels, weights=predicted), state_totals, rtol=8e-8, atol=.01)
    county_positions = {unit['code']: index for index, unit in enumerate(counties)}
    report = dict(name='US county within state, BEA CAGDP2 2024 industry shares',
                  counties=len(counties), states=len(states),
                  production_weight='industry_high_pay_jobs',
                  overall={name: scores(predicted, official) for name, predicted in predictions.items()}, areas={})
    for area, codes in US_BENCHMARK_AREAS.items():
        positions = [county_positions[code] for code in codes]
        report['areas'][area] = {name: scores(predicted[positions], official[positions])
                                 for name, predicted in predictions.items()}
    report['industry_gdp_without_jobs'] = float(industry_targets[state_industry_weights <= 0].sum())
    return report


def control_ids_for_cells(dataset, rows, columns):
    output = np.zeros(len(rows), dtype='uint32')
    block_columns = (dataset.width + 255) // 256
    blocks = (rows // 256) * block_columns + columns // 256
    order = np.argsort(blocks)
    starts = np.r_[0, np.flatnonzero(np.diff(blocks[order])) + 1, len(order)]
    for start, end in zip(starts[:-1], starts[1:]):
        selected = order[start:end]
        row_start, column_start = int(rows[selected[0]] // 256 * 256), int(columns[selected[0]] // 256 * 256)
        window = Window(column_start, row_start, min(256, dataset.width - column_start), min(256, dataset.height - row_start))
        values = dataset.read(1, window=window)
        output[selected] = values[rows[selected] - row_start, columns[selected] - column_start]
    return output


def us_job_county_mapping(units):
    """Jobs whose cell is owned by a different county, or by no US county, than their census block."""
    unit_codes = np.array([''] + [unit['code'] if unit['country'] == 'USA' else '' for unit in units])
    combined = {county: code for code, counties in US_COMBINED_COUNTIES.items() for county in counties}
    totals = dict.fromkeys(['all_jobs', 'outside_us_units', 'different_county', 'different_state'], 0)
    with rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif') as control_ids:
        for release in json.loads(RELEASES.read_text()):
            blocks = read_workplace_blocks(release)
            owners = unit_codes[control_ids_for_cells(control_ids, blocks.grid_rows, blocks.grid_columns)]
            counties = np.array([combined.get(f'{county:05d}', f'{county:05d}') for county in blocks.county_codes])
            in_us_unit = owners != ''
            totals['all_jobs'] += int(blocks.all_jobs.sum())
            totals['outside_us_units'] += int(blocks.all_jobs[~in_us_unit].sum())
            totals['different_county'] += int(blocks.all_jobs[in_us_unit & (owners != counties)].sum())
            totals['different_state'] += int(blocks.all_jobs[in_us_unit & (owners.astype('<U2') != counties.astype('<U2'))].sum())
    return totals


def main():
    units = json.loads((GDP_BUILD_DIRECTORY / 'conservation.json').read_text())['units']
    report = dict(workplace_places=workplace_places_tests(), us_jobs=us_jobs_test(units),
                  us_industries=us_industry_test(units),
                  us_job_county_mapping=us_job_county_mapping(units))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()

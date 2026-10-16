"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

How each control unit's GDP is spread over its cells. The GDP build and the
hold-out checks call the same function, so the checks score the production rule.

Within each unit, in order of preference:
1. US counties: each BEA industry's GDP follows its high-pay-weighted jobs.
2. Units with at least 3.9 workplace places per 1,000 residents, and with both
   population and building weight: equal thirds of population, building
   weight q and workplace places.
3. Otherwise half population and half q; population alone without q; q alone
   without population. The build puts a unit with neither in its centroid cell.

The options exist to score the alternatives the method was chosen from.
"""
from dataclasses import dataclass

import numpy as np

WORKPLACE_PLACES_PER_THOUSAND_RESIDENTS_REQUIRED = 3.9
JOB_WEIGHTS = (None, 'all_jobs', 'high_pay_jobs', 'all_and_high_pay_jobs')
US_JOB_WEIGHT = 'high_pay_jobs'
US_INDUSTRY_WEIGHT = 'industry_high_pay_jobs'


@dataclass
class Weights:
    """One array per weight: either the cells of a window, or the sum for each unit."""
    population: np.ndarray
    building_q: np.ndarray
    workplace_places: np.ndarray | None = None
    all_jobs: np.ndarray | None = None
    high_pay_jobs: np.ndarray | None = None


def uses_workplace_places(unit_sums):
    return ((unit_sums.population > 0) & (unit_sums.building_q > 0) &
            (unit_sums.workplace_places * 1000 >= WORKPLACE_PLACES_PER_THOUSAND_RESIDENTS_REQUIRED * unit_sums.population))


def uses_job_weight(unit_sums, job_weight):
    if job_weight is None:
        return np.zeros(len(unit_sums.population), dtype=bool)
    if job_weight == 'all_and_high_pay_jobs':
        return (unit_sums.all_jobs > 0) | (unit_sums.high_pay_jobs > 0)
    return getattr(unit_sums, job_weight) > 0


def allocate(cells, labels, unit_totals, unit_sums, *, use_workplace_places=True, job_weight=US_JOB_WEIGHT):
    """Return float32 GDP per cell. labels gives each cell's unit; unit arrays start with unit 0, no unit."""
    if job_weight not in JOB_WEIGHTS:
        raise ValueError(f'Unknown job weight: {job_weight}')
    totals = unit_totals
    population_factor = np.divide(totals, unit_sums.population, out=np.zeros_like(totals), where=unit_sums.population > 0)
    building_factor = np.divide(totals, unit_sums.building_q, out=np.zeros_like(totals), where=unit_sums.building_q > 0)
    both = (unit_sums.population > 0) & (unit_sums.building_q > 0)
    population_factor[both] *= .5
    building_factor[both] *= .5
    if use_workplace_places:
        covered = uses_workplace_places(unit_sums)
        population_factor[covered] = totals[covered] / unit_sums.population[covered] / 3
        building_factor[covered] = totals[covered] / unit_sums.building_q[covered] / 3
        workplace_factor = np.divide(totals / 3, unit_sums.workplace_places, out=np.zeros_like(totals), where=covered)
        values = (cells.population * population_factor[labels] + cells.building_q * building_factor[labels] +
                  cells.workplace_places * workplace_factor[labels])
    else:
        values = cells.population * population_factor[labels] + cells.building_q * building_factor[labels]
    if job_weight is not None:
        all_jobs_factor = np.divide(totals, unit_sums.all_jobs, out=np.zeros_like(totals), where=unit_sums.all_jobs > 0)
        high_pay_factor = np.divide(totals, unit_sums.high_pay_jobs, out=np.zeros_like(totals), where=unit_sums.high_pay_jobs > 0)
        if job_weight == 'all_jobs':
            job_values = cells.all_jobs * all_jobs_factor[labels]
        elif job_weight == 'high_pay_jobs':
            job_values = cells.high_pay_jobs * high_pay_factor[labels]
        else:
            both_jobs = (unit_sums.all_jobs > 0) & (unit_sums.high_pay_jobs > 0)
            all_jobs_factor[both_jobs] *= .5
            high_pay_factor[both_jobs] *= .5
            job_values = cells.all_jobs * all_jobs_factor[labels] + cells.high_pay_jobs * high_pay_factor[labels]
        values = np.where(uses_job_weight(unit_sums, job_weight)[labels], job_values, values)
    return values.astype('<f4')


def allocate_industries(labels, industry_weights, high_pay_weights, industry_targets,
                        industry_sums, high_pay_sums):
    """Spread each industry's GDP by its jobs; jobless industries follow high-pay jobs.

    Rows of weights are cells in a build or counties in a state hold-out.
    Columns are the twenty BEA/LODES industries, in source order.
    """
    factors = np.divide(industry_targets, industry_sums, out=np.zeros_like(industry_targets),
                        where=industry_sums > 0)
    values = (industry_weights * factors[labels]).sum(axis=1)
    jobless_gdp = np.where(industry_sums > 0, 0., industry_targets).sum(axis=1)
    fallback_factor = np.divide(jobless_gdp, high_pay_sums, out=np.zeros_like(jobless_gdp),
                                where=high_pay_sums > 0)
    values += high_pay_weights * fallback_factor[labels]
    return values.astype('<f4')


class IndustryAllocation:
    """Precompute the sparse US allocation and apply it to each output strip."""

    def __init__(self, rows, columns, labels, industry_weights, high_pay_weights,
                 industry_targets, industry_sums, high_pay_sums):
        self.covered_units = (industry_targets.sum(axis=1) > 0) & (high_pay_sums > 0)
        covered_cells = self.covered_units[labels]
        self.rows, self.columns = rows[covered_cells], columns[covered_cells]
        self.values = allocate_industries(labels[covered_cells], industry_weights[covered_cells],
                                         high_pay_weights[covered_cells], industry_targets,
                                         industry_sums, high_pay_sums)
        self.jobless_industry_gdp = float(np.where(industry_sums > 0, 0., industry_targets).sum())

    def apply(self, values, labels, window):
        """Replace covered county cells, retaining the ordinary rule everywhere else."""
        values[self.covered_units[labels]] = 0
        start, end = np.searchsorted(self.rows, [window.row_off, window.row_off + window.height])
        values[self.rows[start:end] - int(window.row_off), self.columns[start:end]] = self.values[start:end]

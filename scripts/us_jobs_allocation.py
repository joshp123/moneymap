"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Allocate US GDP using the same fixed workplace-job candidates in build and check.
"""
import numpy as np

from build_layers import allocation


CANDIDATES = ('v3', 'all_jobs', 'high_pay_jobs', 'half_jobs')


def allocate_us_jobs(population, q, workplace_places, all_jobs, high_pay_jobs,
                     labels, totals, population_sums, q_sums, workplace_sums,
                     all_jobs_sums, high_pay_jobs_sums, *, candidate):
    """Use workplace shares, retaining the existing mix in controls without jobs."""
    if candidate not in CANDIDATES:
        raise ValueError(f'Unknown US GDP candidate: {candidate}')
    values = allocation(population, q, labels, totals, population_sums, q_sums,
                        workplace_places=workplace_places, workplace_sums=workplace_sums)
    if candidate == 'v3':
        return values
    all_jobs_factor = np.divide(totals, all_jobs_sums, out=np.zeros_like(totals),
                                where=all_jobs_sums > 0)
    high_pay_factor = np.divide(totals, high_pay_jobs_sums, out=np.zeros_like(totals),
                                where=high_pay_jobs_sums > 0)
    if candidate == 'all_jobs':
        covered = all_jobs_sums > 0
        job_values = all_jobs * all_jobs_factor[labels]
    elif candidate == 'high_pay_jobs':
        covered = high_pay_jobs_sums > 0
        job_values = high_pay_jobs * high_pay_factor[labels]
    else:
        covered = (all_jobs_sums > 0) | (high_pay_jobs_sums > 0)
        both = (all_jobs_sums > 0) & (high_pay_jobs_sums > 0)
        all_jobs_factor[both] *= .5
        high_pay_factor[both] *= .5
        job_values = (all_jobs * all_jobs_factor[labels] +
                      high_pay_jobs * high_pay_factor[labels])
    return np.where(covered[labels], job_values, values).astype('<f4')

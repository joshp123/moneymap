"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Land follows equal shares of density-weighted residents and production GDP.
The build and the held-out checks use this same allocation.
"""
import numpy as np


def allocate(population_weight, gdp, labels, totals, population_sums, gdp_sums):
    """Return float32 cell values; country arrays include unused country zero."""
    population_fraction = np.divide(totals, population_sums, out=np.zeros_like(totals),
                                    where=population_sums > 0)
    gdp_fraction = np.divide(totals, gdp_sums, out=np.zeros_like(totals), where=gdp_sums > 0)
    both = (population_sums > 0) & (gdp_sums > 0)
    population_fraction[both] *= .5
    gdp_fraction[both] *= .5
    return (population_weight * population_fraction[labels] + gdp * gdp_fraction[labels]).astype('<f4')

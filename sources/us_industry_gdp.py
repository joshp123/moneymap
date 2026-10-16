"""Written by AI on 2026.10.16 by model gpt-6.1-sol, from the experiment by model claude opus 5.5.

Read BEA CAGDP2 2024 GDP by industry for US states and counties and fill
suppressed ("(D)") cells.

Twenty leaf industries match the twenty LODES workplace-job groups used here:
nineteen private NAICS sectors and government. Suppressed leaves are first
solved exactly from BEA's published parent lines where only one term is
missing. Any remainder left inside a published parent is shared among its
suppressed leaves in proportion to "county jobs in that industry x state GDP
per job in that industry".
"""
import csv
import numpy as np

from layers.grid import ROOT

CAGDP2_SOURCE = "https://apps.bea.gov/regional/zip/CAGDP2.zip"
RAW_CAGDP2 = ROOT / "data/raw/research-gdp/cagdp2/CAGDP2__ALL_AREAS_2001_2024.csv"

YEAR = '2024'

# BEA line code -> leaf industry name. Order defines the industry index.
LEAF_LINES = {
    3: 'agriculture', 6: 'mining', 10: 'utilities', 11: 'construction',
    12: 'manufacturing', 34: 'wholesale', 35: 'retail', 36: 'transport',
    45: 'information', 51: 'finance', 56: 'real_estate', 60: 'professional',
    64: 'management', 65: 'administrative', 69: 'education', 70: 'health',
    76: 'arts', 79: 'accommodation_food', 82: 'other_services', 83: 'government',
}
LEAF_CODES = list(LEAF_LINES)
INDUSTRIES = list(LEAF_LINES.values())

# The BEA tree, parent line -> child lines. Every line is a sum of its children.
TREE = {
    1: [2, 83],
    2: [3, 6, 10, 11, 12, 34, 35, 36, 45, 50, 59, 68, 75, 82],
    50: [51, 56], 59: [60, 64, 65], 68: [69, 70], 75: [76, 79],
}
# Cross-cutting BEA aggregates, used only to solve single missing leaves exactly.
EXTRA_SUMS = {87: [3, 6], 88: [34, 35], 89: [10, 36], 90: [12, 45],
              91: [3, 6, 11, 12], 92: [10, 34, 35, 36, 45, 50, 59, 68, 75, 82]}


def leaves_of(line):
    if line in LEAF_LINES:
        return [line]
    return [leaf for child in TREE[line] for leaf in leaves_of(child)]


def read_cagdp2(path=RAW_CAGDP2):
    """Return {geofips: {line: value or None}} for 2024, in dollars."""
    areas = {}
    with open(path, encoding='latin-1', newline='') as source:
        rows = csv.reader(source)
        header = next(rows)
        year_column = header.index(YEAR)
        for row in rows:
            if len(row) <= year_column:
                continue
            fips = row[0].strip().strip('"').strip()
            if not fips.isdigit() or len(fips) != 5:
                continue
            line = int(row[4])
            raw = row[year_column].strip()
            value = None if raw in ('(D)', '(NA)', '(NM)', '(L)') else float(raw) * 1000.0
            areas.setdefault(fips, {})[line] = value
    return areas


def solve_exact(lines):
    """Fill missing lines from identities with exactly one missing term."""
    identities = [(parent, children) for parent, children in TREE.items()]
    identities += [(parent, children) for parent, children in EXTRA_SUMS.items()]
    changed = True
    while changed:
        changed = False
        for parent, children in identities:
            terms = [parent] + children
            missing = [term for term in terms if lines.get(term) is None]
            if len(missing) != 1:
                continue
            term = missing[0]
            if term == parent:
                lines[parent] = sum(lines[child] for child in children)
            else:
                lines[term] = lines[parent] - sum(lines[child] for child in children if child != term)
            changed = True
    return lines


def fill_area(lines, leaf_estimates):
    """Return 20 leaf values summing to line 1, and the suppressed-and-estimated GDP.

    leaf_estimates: array of 20 non-negative weights (county jobs x state GDP per job).
    """
    lines = solve_exact(dict(lines))
    suppressed = [index for index, code in enumerate(LEAF_CODES) if lines.get(code) is None]

    def fill(line):
        if line in LEAF_LINES:
            return
        children = TREE[line]
        known = [child for child in children if lines.get(child) is not None]
        unknown = [child for child in children if lines.get(child) is None]
        if unknown:
            residual = max(lines[line] - sum(lines[child] for child in known), 0.0)
            # A suppressed parent's weight counts its published leaves at their value.
            weights = np.array([sum(lines[leaf] if lines.get(leaf) is not None
                                    else leaf_estimates[LEAF_CODES.index(leaf)] for leaf in leaves_of(child))
                                for child in unknown])
            if weights.sum() <= 0:
                weights = np.ones(len(unknown))
            for child, weight in zip(unknown, weights):
                lines[child] = residual * weight / weights.sum()
        for child in children:
            fill(child)

    fill(1)
    leaves = np.array([max(lines[code], 0.0) for code in LEAF_CODES])
    # Clipped negatives from BEA rounding: rescale so leaves reproduce the total exactly.
    if leaves.sum() > 0:
        leaves *= lines[1] / leaves.sum()
    return leaves, float(leaves[suppressed].sum())


def suppression_summary(areas, county_codes):
    return dict(counties=len(county_codes), leaf_cells=len(county_codes)*len(INDUSTRIES),
                suppressed_leaf_cells=sum(areas[code].get(line) is None
                                          for code in county_codes for line in LEAF_CODES))


def state_industry_shares(state_codes, areas=None):
    """One row per state, twenty 2024 industry shares from CAGDP2."""
    areas = read_cagdp2() if areas is None else areas
    values = np.array([[areas[state + '000'][line] for line in LEAF_CODES]
                       for state in state_codes], dtype='float64')
    return values / values.sum(axis=1)[:, None]


def county_industry_gdp(county_codes, county_jobs, areas=None):
    """County x industry GDP, filling suppressed cells by the published BEA tree.

    County jobs are the unweighted twenty industry counts on production cells.
    Returns the GDP matrix and GDP supplied by the suppression rule, in dollars.
    """
    areas = read_cagdp2() if areas is None else areas
    states, state_ids = np.unique([code[:2] for code in county_codes], return_inverse=True)
    state_jobs = np.zeros((len(states), len(INDUSTRIES)))
    np.add.at(state_jobs, state_ids, county_jobs)
    state_gdp = np.array([[areas[state + '000'][line] for line in LEAF_CODES]
                          for state in states], dtype='float64')
    state_gdp_per_job = np.divide(state_gdp, state_jobs, out=np.zeros_like(state_gdp),
                                  where=state_jobs > 0)
    values = np.zeros_like(county_jobs, dtype='float64')
    estimated = 0.0
    for position, code in enumerate(county_codes):
        estimates = county_jobs[position] * state_gdp_per_job[state_ids[position]]
        values[position], suppressed_gdp = fill_area(areas[code], estimates)
        estimated += suppressed_gdp
    return values, estimated

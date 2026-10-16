"""Written by AI on 2026.10.17 by model claude fable 5.1.

Candidate rules for spreading a country's land value and building value over
its cells, and the scoring of their unit sums against official valuations.
Every rule returns each cell's share of the national total, so national totals
never change; only where the value sits within the country does.

Inputs per cell (see extract_cells.py): residents P, the site's GDP layer G,
GHSL built volume V, population density within about 40 km D, GDP within the
same 40 km kernel per resident within it Y (a regional income level), and in
the US LODES all jobs J.
"""
import json

import numpy as np

from layers.grid import ROOT
from research.split.extract_cells import SPLIT_DIRECTORY

LAND_TOTALS = json.loads((ROOT / 'data/build/land_value/conservation.json').read_text())['countries']
BUILDING_TOTALS = json.loads((ROOT / 'data/build/building_value/conservation.json').read_text())['countries']


def share(values):
    total = values.sum(dtype='float64')
    return values / total if total > 0 else values


class Country:
    def __init__(self, code):
        cells = np.load(SPLIT_DIRECTORY / f'cells_{code}.npz')
        self.code = code
        self.P = cells['population'].astype('float64')
        self.G = cells['gdp'].astype('float64')
        self.V = cells['volume'].astype('float64')
        self.D = cells['density'].astype('float64')
        gdp_density = cells['gdp_density'].astype('float64')
        # Regional GDP per head, relative to the national mean; neighbourhoods with
        # no residents keep the national level.
        national = self.G.sum() / self.P.sum()
        self.Y = np.where(self.D > 0, gdp_density / np.maximum(self.D, 1e-9) / national, 1.0)
        self.J = cells['all_jobs'].astype('float64') if 'all_jobs' in cells else None
        self.land_total = LAND_TOTALS[code]['total_usd2024']
        self.building_total = BUILDING_TOTALS[code]['total_usd2024']
        self._cache = {}

    def component(self, name, a=0.0, b=0.0):
        """National share of one weight. 'PDY' is P × D^a × Y^b."""
        key = (name, a, b)
        if key not in self._cache:
            if name == 'PDY':
                values = self.P * np.power(np.maximum(self.D, 1e-6), a) * np.power(np.maximum(self.Y, 1e-6), b)
            elif name == 'VDY':
                values = self.V * np.power(np.maximum(self.D, 1e-6), a) * np.power(np.maximum(self.Y, 1e-6), b)
            elif name == 'GDY':
                values = self.G * np.power(np.maximum(self.D, 1e-6), a) * np.power(np.maximum(self.Y, 1e-6), b)
            elif name == 'JDY':
                if self.J is None:
                    return None
                values = self.J * np.power(np.maximum(self.D, 1e-6), a) * np.power(np.maximum(self.Y, 1e-6), b)
            else:
                values = getattr(self, name)
            self._cache[key] = share(values)
        return self._cache[key]

    def mix(self, terms):
        """terms: list of (weight, component name, a, b). Weights are national shares."""
        output = np.zeros_like(self.P)
        for weight, name, a, b in terms:
            component = self.component(name, a, b)
            if component is None:
                return None
            output += weight * component
        return output


# Land rules: each is a list of (weight, component, density exponent a, income exponent b).
LAND_RULES = {
    'current: ½ P·D^0.25 + ½ G': [(.5, 'PDY', .25, 0), (.5, 'G', 0, 0)],
}
BUILDING_RULES = {
    'current: ⅓ P + ⅓ G + ⅓ V': [(1/3, 'P', 0, 0), (1/3, 'G', 0, 0), (1/3, 'V', 0, 0)],
    'P': [(1, 'P', 0, 0)],
}


def unit_sums(test, cell_values):
    return np.bincount(test['unit_index'], weights=cell_values[test['cell_index']] * test['weight'],
                       minlength=len(test['keys']))


def load_test(name):
    data = np.load(SPLIT_DIRECTORY / f'units_{name}.npz')
    meta = json.loads(str(data['meta']))
    test = dict(name=name, country=meta['country'], keys=meta['keys'], components=meta['components'],
                cell_index=data['cell_index'], unit_index=data['unit_index'], weight=data['weight'])
    for component in meta['components']:
        test[component] = data[f'actual_{component}']
    return test


def spatial_score(predicted, actual):
    """Wrong-area share and median absolute log ratio, after scaling to the official total."""
    scaled = predicted / predicted.sum() * actual.sum()
    with np.errstate(divide='ignore', invalid='ignore'):
        log_ratio = np.log(np.where(scaled > 0, scaled, np.nan) / actual)
    return dict(wrong_area=float(np.abs(scaled - actual).sum() / (2 * actual.sum())),
                median_abs_log=float(np.nanmedian(np.abs(log_ratio))))


def rank(values):
    return np.argsort(np.argsort(values))


def share_score(predicted_share, actual_share):
    """How well the land share of property value is ordered and spread."""
    keep = np.isfinite(predicted_share) & np.isfinite(actual_share)
    p, a = predicted_share[keep], actual_share[keep]
    return dict(spearman=float(np.corrcoef(rank(p), rank(a))[0, 1]), pearson=float(np.corrcoef(p, a)[0, 1]),
                predicted_p10=float(np.percentile(p, 10)), predicted_median=float(np.median(p)),
                predicted_p90=float(np.percentile(p, 90)),
                official_p10=float(np.percentile(a, 10)), official_median=float(np.median(a)),
                official_p90=float(np.percentile(a, 90)), n=int(keep.sum()))

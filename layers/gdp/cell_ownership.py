"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

Which control unit owns each grid cell.

A cell belongs to the unit whose polygon contains its centre. Kummu's reported
polygons decide the country, so every source dollar stays in its country:
occupied coastal cells outside every polygon go to the nearest Kummu unit.
Countries with official tables then use their finer official boundaries, which
also keep small coastal enclaves such as Melilla; cells that the official
boundaries miss go to the nearest official unit of the same country. Elsewhere
each cell keeps its Kummu unit exactly.
"""
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely import STRtree, box, points
from shapely.geometry import shape


class PolygonIndex:
    def __init__(self, controls):
        self.controls = controls
        self.geometries = [shape(control.geometry) for control in controls]
        self.tree = STRtree(self.geometries)

    def labels(self, window, transform):
        """1-based index of the polygon containing each cell centre; 0 for none."""
        local_transform = rasterio.windows.transform(window, transform)
        bounds = rasterio.windows.bounds(window, transform)
        candidates = sorted(self.tree.query(box(*bounds)).tolist())
        if not candidates:
            return np.zeros((int(window.height), int(window.width)), dtype='uint32')
        return rasterize([(self.geometries[i], i + 1) for i in candidates],
                         out_shape=(int(window.height), int(window.width)),
                         transform=local_transform, dtype='uint32')

    def fill_nearest(self, labels, required, window, transform):
        """Give unlabelled required cells the nearest polygon; return how many."""
        rows, columns = np.where((labels == 0) & required)
        for offset in range(0, len(rows), 20000):
            rr, cc = rows[offset:offset + 20000], columns[offset:offset + 20000]
            x = transform.c + (cc + window.col_off + 0.5) * transform.a
            y = transform.f + (rr + window.row_off + 0.5) * transform.e
            labels[rr, cc] = self.tree.nearest(points(x, y)) + 1
        return len(rows)


def sum_by_unit(labels, values, unit_count):
    """Sum cell values per unit id; index 0 holds cells without a unit."""
    return np.bincount(labels.ravel(), weights=values.ravel(), minlength=unit_count + 1)


class CellOwnership:
    def __init__(self, kummu_units, official_units, official_countries):
        self.kummu_units = kummu_units
        self.units = [unit for unit in kummu_units if unit.country not in official_countries] + official_units
        self.countries = sorted({unit.country for unit in kummu_units})
        country_number = {country: i + 1 for i, country in enumerate(self.countries)}
        self.kummu_unit_country = np.array([0] + [country_number[unit.country] for unit in kummu_units])
        self.unit_country = np.array([0] + [country_number[unit.country] for unit in self.units])
        self.unit_is_official = np.array([False] + [unit.country in official_countries for unit in self.units])
        self.kummu_index = PolygonIndex(kummu_units)
        self.unit_index = PolygonIndex(self.units)
        self.official_units_by_country = {
            country_number[country]: [i for i, unit in enumerate(self.units) if unit.country == country]
            for country in official_countries}
        self.nearest_official_unit = {
            country: PolygonIndex([self.units[i] for i in indices])
            for country, indices in self.official_units_by_country.items()}
        retained_unit_ids = {unit.code: i + 1 for i, unit in enumerate(self.units) if unit.country not in official_countries}
        self.kummu_unit_to_unit = np.array([0] + [retained_unit_ids.get(unit.code, 0) for unit in kummu_units], dtype='uint32')
        self.coastal_cells_assigned_nearest = 0
        self.official_boundary_gap_cells = 0

    def assign(self, window, transform, occupied):
        """Return Kummu unit ids, country ids and control unit ids for each cell; 0 is none."""
        kummu_ids = self.kummu_index.labels(window, transform)
        self.coastal_cells_assigned_nearest += self.kummu_index.fill_nearest(kummu_ids, occupied, window, transform)
        country_ids = self.kummu_unit_country[kummu_ids]
        unit_ids = self.unit_index.labels(window, transform)
        unit_ids[(~self.unit_is_official[unit_ids]) & (self.unit_country[unit_ids] != country_ids)] = 0
        for country, indices in self.official_units_by_country.items():
            rows, columns = np.where((country_ids == country) & ~self.unit_is_official[unit_ids])
            if not len(rows):
                continue
            x = transform.c + (columns + window.col_off + 0.5) * transform.a
            y = transform.f + (rows + window.row_off + 0.5) * transform.e
            nearest = self.nearest_official_unit[country].tree.nearest(points(x, y))
            unit_ids[rows, columns] = np.asarray(indices)[nearest] + 1
            self.official_boundary_gap_cells += len(rows)
        retained = (self.kummu_unit_to_unit[kummu_ids] > 0) & ~self.unit_is_official[unit_ids]
        unit_ids[retained] = self.kummu_unit_to_unit[kummu_ids[retained]]
        return kummu_ids, country_ids, unit_ids

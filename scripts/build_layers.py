"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Build GDP with official control totals and a fixed half population, half built-up weight.
"""
from collections import defaultdict
from contextlib import ExitStack
import json
from pathlib import Path
import zipfile

import fiona
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from shapely import STRtree, box, points
from shapely.geometry import shape

from build_tiles import ROOT, TILE_SIZE, open_sources, clean_window
from gdp_controls import Control, load_controls

RAW = ROOT / 'data/raw/research-gdp'
BUILD = ROOT / 'data/gdp-v2'


def open_zip_raster(path):
    with zipfile.ZipFile(path) as archive:
        name, = [name for name in archive.namelist() if name.endswith('.tif')]
    return rasterio.open(f'/vsizip/{path}/{name}')


def reported_controls():
    with fiona.open(RAW / 'polyg_adm1_gdp_perCapita_1990_2024.gpkg') as source:
        return [Control(f['properties']['iso3'], str(int(f['properties']['GID_nmbr'])),
                        f['properties']['Subnat'], dict(f['geometry']), 0, 'Kummu reported admin-1')
                for f in source]


class PolygonIndex:
    def __init__(self, controls):
        self.controls = controls
        self.geometries = [shape(control.geometry) for control in controls]
        self.tree = STRtree(self.geometries)

    def labels(self, window, transform):
        local_transform = rasterio.windows.transform(window, transform)
        bounds = rasterio.windows.bounds(window, transform)
        candidates = sorted(self.tree.query(box(*bounds)).tolist())
        if not candidates:
            return np.zeros((int(window.height), int(window.width)), dtype='uint32')
        return rasterize([(self.geometries[i], i + 1) for i in candidates],
                         out_shape=(int(window.height), int(window.width)),
                         transform=local_transform, dtype='uint32')

    def fill_nearest(self, labels, required, window, transform):
        rows, columns = np.where((labels == 0) & required)
        for offset in range(0, len(rows), 20000):
            rr, cc = rows[offset:offset + 20000], columns[offset:offset + 20000]
            x = transform.c + (cc + window.col_off + 0.5) * transform.a
            y = transform.f + (rr + window.row_off + 0.5) * transform.e
            labels[rr, cc] = self.tree.nearest(points(x, y)) + 1
        return len(rows)


def shifted_q(volume, surface, window, grid):
    """Compute q on BUILT cells, then conservatively shift it onto POP cells."""
    start = max(0, int(window.col_off) - 1)
    end = min(volume.width, int(window.col_off + window.width))
    source_window = Window(start, window.row_off, end - start, window.height)
    v = clean_window(volume, 1, source_window).astype('float64')
    s = clean_window(surface, 1, source_window).astype('float64')
    q = np.divide(v * v, s, out=np.zeros_like(v), where=s > 0)
    output = np.zeros((int(window.height), int(window.width)), dtype='float64')
    # The measured BUILT origin is 0.8 POP pixels to the east.
    east_fraction = (volume.transform.c - grid.transform.c) / grid.transform.a
    for shift, fraction in ((1, east_fraction), (0, 1 - east_fraction)):
        target_start = max(int(window.col_off), start + shift)
        target_end = min(int(window.col_off + window.width), end + shift)
        if target_end > target_start:
            output[:, target_start-int(window.col_off):target_end-int(window.col_off)] += fraction * q[:, target_start-shift-start:target_end-shift-start]
    return output


def check_alignment(gdp, volume, surface):
    assert volume.shape == surface.shape == (21384, 43201)
    assert volume.transform == surface.transform
    np.testing.assert_allclose([volume.transform.a, volume.transform.e, volume.transform.f],
                               [gdp.transform.a, gdp.transform.e, gdp.transform.f], rtol=0, atol=1e-9)
    offset = (volume.transform.c - gdp.transform.c) / gdp.transform.a
    np.testing.assert_allclose(offset, 0.8, atol=1e-7)
    return offset


def grouped_sum(labels, values, count):
    return np.bincount(labels.ravel(), weights=values.ravel(), minlength=count + 1)


def allocation(population, q, labels, totals, population_sums, q_sums, population_weight=0.5):
    """Shared production allocation, also used for the state-to-county hold-out."""
    pop_factor = np.divide(totals, population_sums, out=np.zeros_like(totals), where=population_sums > 0)
    q_factor = np.divide(totals, q_sums, out=np.zeros_like(totals), where=q_sums > 0)
    both = (population_sums > 0) & (q_sums > 0)
    pop_factor[both] *= population_weight
    q_factor[both] *= 1 - population_weight
    return (population * pop_factor[labels] + q * q_factor[labels]).astype('<f4')


def raster_profile(grid, dtype):
    return dict(driver='GTiff', width=grid.width, height=grid.height, count=1,
                crs=grid.crs, transform=grid.transform, dtype=dtype,
                tiled=True, blockxsize=256, blockysize=256, compress='deflate', BIGTIFF='IF_SAFER')


def strips(grid):
    for row in range(0, grid.height, TILE_SIZE):
        yield Window(0, row, grid.width, min(TILE_SIZE, grid.height-row))


def write_tiles(layer, values, row):
    count = 0
    for col in range(0, values.shape[1], TILE_SIZE):
        block = values[:, col:col+TILE_SIZE]
        if not np.any(block):
            continue
        tile = np.zeros((TILE_SIZE, TILE_SIZE), dtype='<f4')
        tile[:block.shape[0], :block.shape[1]] = block
        directory = ROOT / 'data/layers' / layer / str(row // TILE_SIZE)
        directory.mkdir(parents=True, exist_ok=True)
        tile.tofile(directory / f'{col // TILE_SIZE}.bin')
        count += 1
    return count


def build():
    output = ROOT / 'data/layers'
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Move existing data/layers aside before rebuilding')
    BUILD.mkdir(parents=True, exist_ok=True)
    base = reported_controls()
    official, official_sums = load_controls(RAW)
    official_countries = set(official_sums)
    controls = [control for control in base if control.country not in official_countries] + official
    countries = sorted({control.country for control in base})
    country_number = {country: i+1 for i, country in enumerate(countries)}
    base_countries = np.array([0] + [country_number[c.country] for c in base])
    unit_countries = np.array([0] + [country_number[c.country] for c in controls])
    unit_is_official = np.array([False] + [c.country in official_countries for c in controls])
    base_index, control_index = PolygonIndex(base), PolygonIndex(controls)
    country_indices = {country: ([i for i, c in enumerate(controls) if c.country == country]) for country in official_countries}
    nearest_official = {country: PolygonIndex([controls[i] for i in indices]) for country, indices in country_indices.items()}
    retained_ids = {control.code: i+1 for i, control in enumerate(controls) if control.country not in official_countries}
    base_to_control = np.array([0] + [retained_ids.get(control.code, 0) for control in base], dtype='uint32')
    country_totals = np.zeros(len(countries)+1)
    base_totals = np.zeros(len(base)+1)
    population_sums = np.zeros(len(controls)+1)
    q_sums = np.zeros(len(controls)+1)
    cell_counts = np.zeros(len(controls)+1)
    source_population = source_gdp = 0.0
    coast_cells = official_gap_cells = 0
    with ExitStack() as stack:
        gdp, population = open_sources()
        for source in (gdp, population): stack.enter_context(source)
        volume = stack.enter_context(open_zip_raster(RAW / 'nres_v_30ss.zip'))
        surface = stack.enter_context(open_zip_raster(RAW / 'nres_s_30ss.zip'))
        offset = check_alignment(gdp, volume, surface)
        labels_file = BUILD / 'control-ids.tif'
        with rasterio.open(labels_file, 'w', **raster_profile(gdp, 'uint32')) as labels_output:
            for window in strips(gdp):
                pop = clean_window(population, 1, window)
                old = clean_window(gdp, 8, window)
                q = shifted_q(volume, surface, window, gdp)
                base_labels = base_index.labels(window, gdp.transform)
                # Polygon coasts omit a few occupied grid centres. Keep every source dollar.
                coast_cells += base_index.fill_nearest(base_labels, (pop > 0) | (old > 0) | (q > 0), window, gdp.transform)
                country_labels = base_countries[base_labels]
                country_totals += grouped_sum(country_labels, old, len(countries))
                base_totals += grouped_sum(base_labels, old, len(base))
                labels = control_index.labels(window, gdp.transform)
                # Official boundaries are finer than Kummu's coast and country outlines.
                # Keep their cell centres, including small coastal enclaves such as Melilla.
                labels[(~unit_is_official[labels]) & (unit_countries[labels] != country_labels)] = 0
                # Fill coastline/border differences from the same country's official geography.
                for country, indices in country_indices.items():
                    required = (country_labels == country_number[country]) & ~unit_is_official[labels]
                    rows, columns = np.where(required)
                    if not len(rows): continue
                    x = gdp.transform.c + (columns + 0.5) * gdp.transform.a
                    y = gdp.transform.f + (rows + window.row_off + 0.5) * gdp.transform.e
                    nearest = nearest_official[country].tree.nearest(points(x, y))
                    labels[rows, columns] = np.asarray(indices)[nearest] + 1
                    official_gap_cells += len(rows)
                # Unchanged reported units keep exactly the source mask, including coastal cells.
                retained_mask = (base_to_control[base_labels] > 0) & ~unit_is_official[labels]
                labels[retained_mask] = base_to_control[base_labels[retained_mask]]
                labels_output.write(labels, 1, window=window)
                population_sums += grouped_sum(labels, pop, len(controls))
                q_sums += grouped_sum(labels, q, len(controls))
                cell_counts += np.bincount(labels.ravel(), minlength=len(controls)+1)
                source_population += pop.sum(dtype='float64')
                source_gdp += old.sum(dtype='float64')
                if window.row_off % 2400 == 0: print(f'Control sums: row {window.row_off}', flush=True)
        base_by_code = {c.code: base_totals[i+1] for i, c in enumerate(base)}
        totals = np.array([0] + [country_totals[country_number[c.country]] * c.value / official_sums[c.country]
                                  if c.country in official_countries else base_by_code[c.code] for c in controls])
        totals[0] = 0
        fallback_cells = defaultdict(list)
        for i, control in enumerate(controls, 1):
            if totals[i] and not (population_sums[i] or q_sums[i]):
                centroid = control_index.geometries[i-1].centroid
                row, col = gdp.index(centroid.x, centroid.y)
                row, col = np.clip(row, 0, gdp.height-1), np.clip(col, 0, gdp.width-1)
                fallback_cells[(int(row)//TILE_SIZE)*TILE_SIZE].append((i, int(row), int(col)))
        actual_totals = np.zeros_like(totals)
        tile_counts = defaultdict(int)
        built_totals = defaultdict(float)
        with rasterio.open(labels_file) as labels_source, rasterio.open(BUILD / 'gdp.tif', 'w', **raster_profile(gdp, 'float32')) as built:
            for window in strips(gdp):
                labels = labels_source.read(1, window=window)
                pop = clean_window(population, 1, window)
                q = shifted_q(volume, surface, window, gdp)
                new_gdp = allocation(pop, q, labels, totals, population_sums, q_sums)
                actual_totals += grouped_sum(labels, new_gdp, len(controls))
                for unit_id, row, col in fallback_cells[int(window.row_off)]:
                    new_gdp[row-int(window.row_off), col] += np.float32(totals[unit_id])
                    actual_totals[unit_id] += float(np.float32(totals[unit_id]))
                built.write(new_gdp, 1, window=window)
                for name, values in [('gdp', new_gdp), ('population', pop)]:
                    built_totals[name] += values.sum(dtype='float64')
                    tile_counts[name] += write_tiles(name, values, int(window.row_off))
                if window.row_off % 2400 == 0: print(f'Layer tiles: row {window.row_off}', flush=True)
    np.testing.assert_allclose(actual_totals, totals, rtol=8e-8, atol=0.01)
    actual_countries = np.bincount(unit_countries, weights=actual_totals, minlength=len(countries)+1)
    np.testing.assert_allclose(actual_countries[1:], country_totals[1:], rtol=8e-8, atol=0.01)
    np.testing.assert_allclose(country_totals.sum(), source_gdp, rtol=1e-12)
    tile_totals = {name: sum(np.fromfile(path, dtype='<f4').sum(dtype='float64') for path in (output/name).glob('*/*.bin')) for name in tile_counts}
    for name in tile_totals: np.testing.assert_allclose(tile_totals[name], built_totals[name], rtol=1e-12, atol=0.01)
    np.testing.assert_allclose(built_totals['population'], source_population, rtol=1e-12)
    report = dict(source_gdp=source_gdp, source_population=source_population, built_totals=dict(built_totals),
                  tile_totals=tile_totals, tiles={name:dict(count=count, bytes=count*TILE_SIZE*TILE_SIZE*4) for name,count in tile_counts.items()},
                  built_grid_offset=offset, coastal_cells_assigned_nearest=coast_cells,
                  official_boundary_gap_cells=official_gap_cells,
                  fallback_units=sum(len(v) for v in fallback_cells.values()),
                  countries={c:dict(source=country_totals[i+1], built=actual_countries[i+1], official_sum=official_sums.get(c)) for i,c in enumerate(countries)},
                  units=[dict(country=c.country, code=c.code, name=c.name, source=c.source,
                              official=c.value, target=totals[i+1], built=actual_totals[i+1], cells=int(cell_counts[i+1])) for i,c in enumerate(controls)])
    (BUILD/'conservation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key not in ('countries','units')}, indent=2), flush=True)


if __name__ == '__main__':
    build()

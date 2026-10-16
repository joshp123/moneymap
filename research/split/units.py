"""Written by AI on 2026.10.17 by model claude fable 5.1.

Attach official valuation units to the extracted cells. Every test becomes the
same shape: sparse (cell index, unit index, weight) triplets, the unit keys, and
the official land, building and property values where the source has them.

Most units are polygons rasterised onto the grid (weight 1). US census tracts
and ZIP codes have no boundaries in this repository, so each cell is shared
between the tracts whose 2020 census blocks (LODES crosswalk internal points)
fall in it, in proportion to block counts. That loses variation inside a 1 km
cell, which the site cannot resolve anyway.

Writes data/experiments/split/units_<test>.npz.

    devenv shell -- python -m research.split.units
"""
import csv
import gzip
import json
from pathlib import Path

import numpy as np
import openpyxl
import pyarrow as arrow
import pyarrow.csv as arrow_csv
from rasterio.features import rasterize
from rasterio.windows import from_bounds

from checks.building_value import british_columbia_units, victoria_units
from checks.land_value import EXPERIMENTS, denmark_units, japan_units, nrw_units, read_rows, read_units
from layers.grid import GRID_TRANSFORM, GRID_WIDTH, ROOT
from research.split.extract_cells import SPLIT_DIRECTORY
from sources.building_valuations import nyc_units
from sources.european_property_values import european_units

LODES_RAW = ROOT / 'data/raw/lodes'
FHFA_WORKBOOK = EXPERIMENTS / 'raw/us/fhfa_land_prices_2024_june.xlsx'
ACS_TRACT_VALUES = EXPERIMENTS / 'raw/us/acsdt5y2023-b25082.dat'


def cell_keys(country):
    cells = np.load(SPLIT_DIRECTORY / f'cells_{country}.npz')
    return cells['row'].astype('int64') * GRID_WIDTH + cells['col']


def save(test, country, keys, cell_index, unit_index, weight, actual, extra=None):
    arrays = dict(cell_index=cell_index.astype('int64'), unit_index=unit_index.astype('int32'),
                  weight=weight.astype('float64'),
                  **{f'actual_{name}': np.asarray(values, dtype='float64') for name, values in actual.items()},
                  **(extra or {}))
    meta = dict(test=test, country=country, keys=list(keys), components=sorted(actual))
    np.savez_compressed(SPLIT_DIRECTORY / f'units_{test}.npz', meta=json.dumps(meta), **arrays)
    covered = len(np.unique(unit_index))
    print(f'{test}: {len(keys)} units, {covered} with cells, {len(cell_index):,} cell links', flush=True)


def rasterised(test, country, units, values, bounds, components):
    """Polygon units onto the grid. values: key -> {component: value}."""
    keys = [key for key in units if key in values and all(values[key].get(c, 0) > 0 for c in components)]
    window = from_bounds(*bounds, GRID_TRANSFORM).round_offsets().round_lengths()
    shapes = [(geometry, index + 1) for index, key in enumerate(keys) for geometry in units[key]]
    labels = rasterize(shapes, out_shape=(int(window.height), int(window.width)),
                       transform=rasterio_window_transform(window), fill=0, dtype='int32')
    cells = np.load(SPLIT_DIRECTORY / f'cells_{country}.npz')
    rows, cols = cells['row'] - int(window.row_off), cells['col'] - int(window.col_off)
    inside = (rows >= 0) & (rows < labels.shape[0]) & (cols >= 0) & (cols < labels.shape[1])
    cell_index = np.nonzero(inside)[0]
    unit_index = labels[rows[inside], cols[inside]]
    keep = unit_index > 0
    actual = {c: [values[key][c] for key in keys] for c in components}
    save(test, country, keys, cell_index[keep], unit_index[keep] - 1, np.ones(keep.sum()), actual)


def rasterio_window_transform(window):
    from rasterio.windows import transform
    return transform(window, GRID_TRANSFORM)


def fhfa_shares(path):
    return {row['geoid']: float(row['land_share_of_property_value'])
            for row in read_rows(path) if row['land_share_of_property_value']}


def us_counties():
    shares = fhfa_shares(EXPERIMENTS / 'us/fhfa_county_cross_section_2012_2022.csv')
    values = {}
    for row in read_rows(EXPERIMENTS / 'us/acs_2023_5yr_county_housing_value.csv'):
        code = row['geoid']
        if code in shares and row['aggregate_value_owner_occupied_housing_usd']:
            total = float(row['aggregate_value_owner_occupied_housing_usd'])
            values[code] = dict(land_value=shares[code] * total, building_value=(1 - shares[code]) * total,
                                property_value=total, fhfa_land_share=shares[code])
    units = read_units(f'zip://{ROOT}/data/raw/research-gdp/county_500k.zip',
                       lambda p: str(p['GEOID']) if str(p['GEOID']) in values else None)
    rasterised('us_counties', 'USA', units, values, (-179.5, 18.8, -66.8, 71.6),
               ('land_value', 'building_value', 'property_value', 'fhfa_land_share'))


def acs_tract_values():
    values = {}
    with ACS_TRACT_VALUES.open() as source:
        for line in source:
            if line.startswith('1400000US'):
                fields = line.rstrip('\n').split('|')
                if fields[1] not in ('', 'null'):
                    values[fields[0][9:]] = float(fields[1])
    return values


def read_crosswalk_blocks():
    """2020 census blocks: tract, ZCTA and the grid cell holding the internal point."""
    tables = []
    for path in sorted(LODES_RAW.glob('*_xwalk.csv.gz')):
        with gzip.open(path, 'rb') as source:
            tables.append(arrow_csv.read_csv(source, convert_options=arrow_csv.ConvertOptions(
                include_columns=['trct', 'zcta', 'blklatdd', 'blklondd'],
                column_types={'trct': arrow.string(), 'zcta': arrow.string(),
                              'blklatdd': arrow.float64(), 'blklondd': arrow.float64()})))
    table = arrow.concat_tables(tables)
    longitude, latitude = table['blklondd'].to_numpy(zero_copy_only=False), table['blklatdd'].to_numpy(zero_copy_only=False)
    valid = np.isfinite(longitude) & np.isfinite(latitude)
    cols = np.floor((longitude[valid] - GRID_TRANSFORM.c) / GRID_TRANSFORM.a).astype('int64')
    rows = np.floor((latitude[valid] - GRID_TRANSFORM.f) / GRID_TRANSFORM.e).astype('int64')
    return (np.array(table['trct'].to_pylist(), dtype=object)[valid],
            np.array(table['zcta'].to_pylist(), dtype=object)[valid], rows * GRID_WIDTH + cols)


def block_apportioned(test, block_unit, block_cell_key, values, components, extra_keys=()):
    """Share each cell among the units whose blocks it holds, by block count."""
    keys_sorted_cells = cell_keys('USA')
    order = np.argsort(keys_sorted_cells)
    sorted_keys = keys_sorted_cells[order]
    position = np.searchsorted(sorted_keys, block_cell_key)
    position = np.clip(position, 0, len(sorted_keys) - 1)
    found = sorted_keys[position] == block_cell_key
    has_value = np.array([unit in values for unit in block_unit])
    keep = found & has_value
    cell_index = order[position[keep]]
    unit_codes = block_unit[keep]
    keys, unit_index = np.unique(unit_codes, return_inverse=True)
    pair_keys = cell_index.astype('int64') * len(keys) + unit_index
    unique_pairs, pair_counts = np.unique(pair_keys, return_counts=True)
    pair_cell = unique_pairs // len(keys)
    pair_unit = unique_pairs % len(keys)
    # Blocks per cell counts every block in the cell with a valued unit, so weights within a cell sum to one.
    blocks_per_cell = np.bincount(pair_cell, weights=pair_counts, minlength=len(keys_sorted_cells))
    weight = pair_counts / blocks_per_cell[pair_cell]
    actual = {c: [values[key][c] for key in keys] for c in components}
    extra = {name: np.array([values[key][name] for key in keys]) for name in extra_keys}
    save(test, 'USA', list(keys), pair_cell, pair_unit, weight, actual, extra)


def us_tracts(block_tract, block_cell_key):
    shares = fhfa_shares(EXPERIMENTS / 'us/fhfa_tract_cross_section_2012_2022.csv')
    acs = acs_tract_values()
    values = {code: dict(land_value=share * acs[code], building_value=(1 - share) * acs[code],
                         property_value=acs[code], fhfa_land_share=share)
              for code, share in shares.items() if acs.get(code, 0) > 0}
    print(f'tracts: {len(shares)} FHFA, {len(values)} also in ACS 2023 with the same 2020 tract id', flush=True)
    block_apportioned('us_tracts', block_tract, block_cell_key, values,
                      ('land_value', 'building_value', 'property_value', 'fhfa_land_share'))


def us_zips(block_zcta, block_cell_key):
    """FHFA ZIP land shares; ZIP codes are matched to 2020 ZCTAs by code."""
    sheet = openpyxl.load_workbook(FHFA_WORKBOOK, read_only=True)['Cross-Section ZIP Codes']
    rows = sheet.iter_rows(values_only=True)
    next(rows)  # sheet title row
    header = [str(cell).strip().lower() if cell is not None else '' for cell in next(rows)]
    zip_column = next(i for i, name in enumerate(header) if 'zip' in name)
    share_column = next(i for i, name in enumerate(header) if 'share' in name)
    values = {}
    for row in rows:
        if row[zip_column] is None or row[share_column] is None:
            continue
        try:
            share = float(row[share_column])
        except (TypeError, ValueError):
            continue
        code = str(row[zip_column]).strip().split('.')[0].zfill(5)
        values[code] = dict(fhfa_land_share=share)
    print(f'ZIP codes: {len(values)} with FHFA land shares; columns {header[zip_column]!r}, {header[share_column]!r}', flush=True)
    block_apportioned('us_zips', block_zcta, block_cell_key, values, ('fhfa_land_share',))


def main():
    us_counties()
    block_tract, block_zcta, block_cell_key = read_crosswalk_blocks()
    us_tracts(block_tract, block_cell_key)
    us_zips(block_zcta, block_cell_key)
    nyc = nyc_units()
    rasterised('nyc_districts', 'USA', nyc['units'], nyc['values'], nyc['bounds'],
               ('land_value', 'building_value', 'property_value'))
    victoria = victoria_units()
    rasterised('victoria_councils', 'AUS', victoria['units'], victoria['values'], victoria['bounds'],
               ('land_value', 'building_value', 'property_value'))
    bc = british_columbia_units()
    rasterised('bc_municipalities', 'CAN', bc['units'], bc['values'], bc['bounds'],
               ('land_value', 'building_value', 'property_value'))
    for loader, country in ((nrw_units, 'DEU'), (japan_units, 'JPN'), (denmark_units, 'DNK')):
        label, units, values, bounds = loader()
        rasterised(label, country, units, {key: dict(land_value=value) for key, value in values.items()},
                   bounds, ('land_value',))
    amsterdam = european_units()
    rasterised('amsterdam_homes', 'NLD', amsterdam['units'], amsterdam['values'], amsterdam['bounds'],
               ('property_value',))


if __name__ == '__main__':
    main()

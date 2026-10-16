"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Download the latest LODES workplace counts and place block points on the GDP grid.
"""
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import re
import time
import urllib.request

import numpy as np
import pyarrow as arrow
import pyarrow.csv as arrow_csv
import pyarrow.parquet as parquet
import rasterio
from rasterio.windows import Window

from build_tiles import ROOT
from gdp_controls import US_COMBINED_COUNTIES

BASE = 'https://lehd.ces.census.gov/data/lodes/LODES8/'
RAW = ROOT / 'data/raw/lodes'
STATES = 'ak al ar az ca co ct dc de fl ga hi ia id il in ks ky la ma md me mi mn mo ms mt nc nd ne nh nj nm nv ny oh ok or pa ri sc sd tn tx ut va vt wa wi wv wy'.split()


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'moneymap data build'}), timeout=180)


def download(path, url):
    if path.exists():
        return
    partial = path.with_suffix(path.suffix + '.part')
    for attempt in range(4):
        try:
            with request(url) as source, partial.open('wb') as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
            partial.replace(path)
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def download_state(state):
    with request(BASE + state + '/wac/') as source:
        index = source.read().decode()
    years = sorted(set(re.findall(state + r'_wac_S000_JT00_(\d{4})\.csv\.gz', index)))
    if not years:
        raise ValueError(f'{state}: no S000_JT00 WAC release')
    year = int(years[-1])
    filename = f'{state}_wac_S000_JT00_{year}.csv.gz'
    download(RAW / filename, BASE + state + '/wac/' + filename)
    download(RAW / f'{state}_xwalk.csv.gz', BASE + state + f'/{state}_xwalk.csv.gz')
    print(f'{state}: {year} downloaded', flush=True)
    return {'state': state, 'year': year, 'wac': filename, 'xwalk': f'{state}_xwalk.csv.gz'}


def read_columns(path, columns, types):
    with gzip.open(path, 'rb') as source:
        return arrow_csv.read_csv(source, convert_options=arrow_csv.ConvertOptions(
            include_columns=columns, column_types=types))


def control_ids_for_cells(dataset, rows, columns):
    output = np.zeros(len(rows), dtype='uint32')
    block_columns = (dataset.width + 255) // 256
    blocks = (rows // 256) * block_columns + columns // 256
    order = np.argsort(blocks)
    starts = np.r_[0, np.flatnonzero(np.diff(blocks[order])) + 1, len(order)]
    for start, end in zip(starts[:-1], starts[1:]):
        selected = order[start:end]
        row_start, column_start = int(rows[selected[0]] // 256 * 256), int(columns[selected[0]] // 256 * 256)
        window = Window(column_start, row_start, min(256, dataset.width-column_start), min(256, dataset.height-row_start))
        values = dataset.read(1, window=window)
        output[selected] = values[rows[selected]-row_start, columns[selected]-column_start]
    return output


def grid_state(release, grid, controls, unit_report):
    workplace = read_columns(RAW / release['wac'], ['w_geocode', 'C000', 'CE03'],
                            {'w_geocode': arrow.int64(), 'C000': arrow.int64(), 'CE03': arrow.int64()})
    crosswalk = read_columns(RAW / release['xwalk'], ['tabblk2020', 'cty', 'blklatdd', 'blklondd'],
                            {'tabblk2020': arrow.int64(), 'cty': arrow.int32(), 'blklatdd': arrow.float64(), 'blklondd': arrow.float64()})
    blocks = workplace['w_geocode'].to_numpy()
    crosswalk_blocks = crosswalk['tabblk2020'].to_numpy()
    order = np.argsort(crosswalk_blocks)
    positions = np.searchsorted(crosswalk_blocks[order], blocks)
    if np.any(positions == len(order)) or np.any(crosswalk_blocks[order[positions]] != blocks):
        raise ValueError(f"{release['state']}: workplace blocks absent from crosswalk")
    matched = order[positions]
    latitudes = crosswalk['blklatdd'].to_numpy()[matched]
    longitudes = crosswalk['blklondd'].to_numpy()[matched]
    county_codes = crosswalk['cty'].to_numpy()[matched]
    all_jobs = workplace['C000'].to_numpy()
    high_pay_jobs = workplace['CE03'].to_numpy()
    rows = np.floor((latitudes-grid.transform.f)/grid.transform.e).astype('int32')
    columns = np.floor((longitudes-grid.transform.c)/grid.transform.a).astype('int32')
    inside = (rows >= 0) & (rows < grid.height) & (columns >= 0) & (columns < grid.width)
    if not np.all(inside):
        raise ValueError(f"{release['state']}: workplace block points outside grid")
    cell_numbers, cell_positions = np.unique(rows.astype('int64')*grid.width+columns, return_inverse=True)
    cell_rows = (cell_numbers // grid.width).astype('int32')
    cell_columns = (cell_numbers % grid.width).astype('int32')
    cell_all_jobs = np.bincount(cell_positions, weights=all_jobs).astype('int64')
    cell_high_pay_jobs = np.bincount(cell_positions, weights=high_pay_jobs).astype('int64')
    labels = control_ids_for_cells(controls, cell_rows, cell_columns)
    block_labels = labels[cell_positions]
    unit_countries = np.array([''] + [unit['country'] for unit in unit_report])
    unit_codes = np.array([''] + [unit['code'] for unit in unit_report])
    us_cells = unit_countries[block_labels] == 'USA'
    true_county_jobs = {}
    for county in np.unique(county_codes):
        county_mask = county_codes == county
        true_county_jobs[f'{county:05d}'] = [int(all_jobs[county_mask].sum()), int(high_pay_jobs[county_mask].sum())]
    combined_codes = {county: combined for combined, counties in US_COMBINED_COUNTIES.items() for county in counties}
    expected_codes = np.array([combined_codes.get(f'{county:05d}', f'{county:05d}') for county in county_codes])
    mismatch = us_cells & (unit_codes[block_labels] != expected_codes)
    state_mismatch = us_cells & np.array([code[:2] != f'{county:05d}'[:2]
                                         for code, county in zip(unit_codes[block_labels], county_codes)])
    report = dict(release, blocks=len(blocks), cells=len(cell_numbers), all_jobs=int(all_jobs.sum()),
                  high_pay_jobs=int(high_pay_jobs.sum()), outside_us_mask_jobs=int(all_jobs[~us_cells].sum()),
                  outside_us_mask_high_pay_jobs=int(high_pay_jobs[~us_cells].sum()),
                  different_county_jobs=int(all_jobs[mismatch].sum()), different_state_jobs=int(all_jobs[state_mismatch].sum()),
                  true_county_jobs=true_county_jobs)
    print(f"{release['state']}: {len(blocks):,} blocks, {report['all_jobs']:,} jobs gridded", flush=True)
    return arrow.table({'grid_row': cell_rows, 'grid_col': cell_columns, 'all_jobs': cell_all_jobs,
                        'high_pay_jobs': cell_high_pay_jobs}), report


def build():
    RAW.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=12) as executor:
        releases = list(executor.map(download_state, STATES))
    (RAW / 'releases.json').write_text(json.dumps(releases, indent=2) + '\n')
    units = json.loads((ROOT / 'data/gdp-v3/conservation.json').read_text())['units']
    with rasterio.open(ROOT / 'data/gdp-v3/gdp.tif') as grid, rasterio.open(ROOT / 'data/gdp-v3/control-ids.tif') as controls:
        tables, reports = [], []
        for release in releases:
            table, report = grid_state(release, grid, controls, units)
            tables.append(table)
            reports.append(report)
        table = arrow.concat_tables(tables).group_by(['grid_row', 'grid_col']).aggregate([
            ('all_jobs', 'sum'), ('high_pay_jobs', 'sum')])
        table = table.rename_columns(['grid_row', 'grid_col', 'all_jobs', 'high_pay_jobs'])
        table = table.sort_by([('grid_row', 'ascending'), ('grid_col', 'ascending')])
        parquet.write_table(table, RAW / 'jobs_per_cell.parquet', compression='zstd')
    summary = {'source': BASE, 'states': reports, 'cells': len(table),
               'all_jobs': sum(row['all_jobs'] for row in reports),
               'high_pay_jobs': sum(row['high_pay_jobs'] for row in reports),
               'outside_us_mask_jobs': sum(row['outside_us_mask_jobs'] for row in reports),
               'different_county_jobs': sum(row['different_county_jobs'] for row in reports),
               'different_state_jobs': sum(row['different_state_jobs'] for row in reports)}
    assert int(table['all_jobs'].to_numpy().sum()) == summary['all_jobs']
    assert int(table['high_pay_jobs'].to_numpy().sum()) == summary['high_pay_jobs']
    (RAW / 'grid-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'states'}, indent=2), flush=True)


if __name__ == '__main__':
    build()

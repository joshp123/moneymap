"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

US workplace jobs per grid cell, from the US Census Bureau's LEHD
Origin-Destination Employment Statistics (LODES8). For each state and DC, the
latest S000_JT00 workplace file gives all jobs (C000) and high-pay jobs (CE03)
per 2020 census block; the crosswalk gives each block's internal point and
current county. Blocks are counted in the grid cell that contains their point.

Writes data/raw/lodes/releases.json, jobs_per_cell.parquet and
industry_jobs_per_cell.parquet. Existing releases.json pins rebuilds to the
downloaded vintage; remove it to discover the latest releases again.

    devenv shell -- python -m sources.lodes_jobs
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import gzip
import json
import re
import time
import urllib.request

import numpy as np
import pyarrow as arrow
import pyarrow.csv as arrow_csv
import pyarrow.parquet as parquet

from layers.grid import GRID_HEIGHT, GRID_TRANSFORM, GRID_WIDTH, ROOT
from sources.us_industry_gdp import INDUSTRIES

LODES = 'https://lehd.ces.census.gov/data/lodes/LODES8/'
RAW = ROOT / 'data/raw/lodes'
RELEASES = RAW / 'releases.json'
JOBS_PER_CELL = RAW / 'jobs_per_cell.parquet'
INDUSTRY_JOBS_PER_CELL = RAW / 'industry_jobs_per_cell.parquet'
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


def download_latest_state_release(state):
    with request(LODES + state + '/wac/') as source:
        index = source.read().decode()
    years = sorted(set(re.findall(state + r'_wac_S000_JT00_(\d{4})\.csv\.gz', index)))
    if not years:
        raise ValueError(f'{state}: no S000_JT00 WAC release')
    year = int(years[-1])
    filename = f'{state}_wac_S000_JT00_{year}.csv.gz'
    download(RAW / filename, LODES + state + '/wac/' + filename)
    download(RAW / f'{state}_xwalk.csv.gz', LODES + state + f'/{state}_xwalk.csv.gz')
    print(f'{state}: {year} downloaded', flush=True)
    return {'state': state, 'year': year, 'wac': filename, 'xwalk': f'{state}_xwalk.csv.gz'}


def read_columns(path, columns, types):
    with gzip.open(path, 'rb') as source:
        return arrow_csv.read_csv(source, convert_options=arrow_csv.ConvertOptions(
            include_columns=columns, column_types=types))


@dataclass
class WorkplaceBlocks:
    """One entry per census block with workplace jobs."""
    grid_rows: np.ndarray
    grid_columns: np.ndarray
    county_codes: np.ndarray
    all_jobs: np.ndarray
    high_pay_jobs: np.ndarray


def read_workplace_blocks(release):
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
    rows = np.floor((latitudes - GRID_TRANSFORM.f) / GRID_TRANSFORM.e).astype('int32')
    columns = np.floor((longitudes - GRID_TRANSFORM.c) / GRID_TRANSFORM.a).astype('int32')
    if not np.all((rows >= 0) & (rows < GRID_HEIGHT) & (columns >= 0) & (columns < GRID_WIDTH)):
        raise ValueError(f"{release['state']}: workplace block points outside grid")
    return WorkplaceBlocks(rows, columns, crosswalk['cty'].to_numpy()[matched],
                           workplace['C000'].to_numpy(), workplace['CE03'].to_numpy())


def jobs_per_cell(release):
    blocks = read_workplace_blocks(release)
    cell_numbers, cell_positions = np.unique(blocks.grid_rows.astype('int64') * GRID_WIDTH + blocks.grid_columns, return_inverse=True)
    table = arrow.table({'grid_row': (cell_numbers // GRID_WIDTH).astype('int32'),
                         'grid_col': (cell_numbers % GRID_WIDTH).astype('int32'),
                         'all_jobs': np.bincount(cell_positions, weights=blocks.all_jobs).astype('int64'),
                         'high_pay_jobs': np.bincount(cell_positions, weights=blocks.high_pay_jobs).astype('int64')})
    summary = dict(release, blocks=len(blocks.all_jobs), cells=len(cell_numbers),
                   all_jobs=int(blocks.all_jobs.sum()), high_pay_jobs=int(blocks.high_pay_jobs.sum()))
    print(f"{release['state']}: {summary['blocks']:,} blocks, {summary['all_jobs']:,} jobs gridded", flush=True)
    return table, summary


def build():
    RAW.mkdir(parents=True, exist_ok=True)
    if RELEASES.exists():
        releases = json.loads(RELEASES.read_text())
        for release in releases:
            state = release['state']
            download(RAW / release['wac'], LODES + state + '/wac/' + release['wac'])
            download(RAW / release['xwalk'], LODES + state + '/' + release['xwalk'])
    else:
        with ThreadPoolExecutor(max_workers=12) as executor:
            releases = list(executor.map(download_latest_state_release, STATES))
        RELEASES.write_text(json.dumps(releases, indent=2) + '\n')
    tables, summaries = zip(*(jobs_per_cell(release) for release in releases))
    table = arrow.concat_tables(tables).group_by(['grid_row', 'grid_col']).aggregate([
        ('all_jobs', 'sum'), ('high_pay_jobs', 'sum')])
    table = table.rename_columns(['grid_row', 'grid_col', 'all_jobs', 'high_pay_jobs'])
    table = table.sort_by([('grid_row', 'ascending'), ('grid_col', 'ascending')])
    parquet.write_table(table, JOBS_PER_CELL, compression='zstd')
    totals = {name: sum(summary[name] for summary in summaries) for name in ('all_jobs', 'high_pay_jobs')}
    for name, total in totals.items():
        assert int(table[name].to_numpy().sum()) == total
    print(json.dumps(dict(cells=len(table), **totals), indent=2), flush=True)


def industry_jobs_per_cell(release):
    """Grid nineteen private sectors and government, with each group's pay share.

    JT02 supplies private jobs by NAICS sector. Government is JT00 minus JT02.
    The nineteen private sectors use the block's private high-pay share;
    government uses its directly observed high-pay count. Together they reproduce
    each block's total high-pay jobs.
    """
    sectors = [f'CNS{number:02d}' for number in range(1, 21)]
    columns = ['w_geocode', 'C000', 'CE03', *sectors]
    types = {column: arrow.int64() for column in columns}
    all_jobs = read_columns(RAW / release['wac'], columns, types)
    private_filename = f"{release['state']}_wac_S000_JT02_{release['year']}.csv.gz"
    download(RAW / private_filename, LODES + release['state'] + '/wac/' + private_filename)
    private = read_columns(RAW / private_filename, columns, types)
    block_codes = all_jobs['w_geocode'].to_numpy()
    private_codes = private['w_geocode'].to_numpy()
    positions = np.searchsorted(block_codes, private_codes)
    if np.any(positions >= len(block_codes)) or np.any(block_codes[positions] != private_codes):
        raise ValueError(f"{release['state']}: private blocks absent from all-jobs file")

    def expand_private(column):
        values = np.zeros(len(block_codes), dtype='int64')
        values[positions] = private[column].to_numpy()
        return values

    total_jobs = all_jobs['C000'].to_numpy()
    high_pay_jobs = all_jobs['CE03'].to_numpy()
    private_total = expand_private('C000')
    private_high_pay = expand_private('CE03')
    government_jobs = total_jobs - private_total
    government_high_pay = high_pay_jobs - private_high_pay
    if np.any(government_jobs < 0) or np.any(government_high_pay < 0):
        raise ValueError(f"{release['state']}: private jobs exceed all jobs")
    private_sectors = np.column_stack([expand_private(column) for column in sectors[:19]])
    # Tiny private NAICS 92 counts belong to other services, matching the experiment.
    private_sectors[:, 18] += expand_private('CNS20')
    private_high_pay_share = np.divide(private_high_pay, private_total,
                                       out=np.zeros(len(block_codes)), where=private_total > 0)
    industry_jobs = np.column_stack([private_sectors, government_jobs])
    industry_high_pay = np.column_stack([private_sectors * private_high_pay_share[:, None],
                                         government_high_pay])
    np.testing.assert_array_equal(industry_jobs.sum(axis=1), total_jobs)
    np.testing.assert_allclose(industry_high_pay.sum(axis=1), high_pay_jobs, rtol=1e-14, atol=1e-9)
    blocks = read_workplace_blocks(release)
    cell_numbers, cell_positions = np.unique(blocks.grid_rows.astype('int64') * GRID_WIDTH
                                             + blocks.grid_columns, return_inverse=True)

    def cell_sums(values):
        return np.bincount(cell_positions, weights=values, minlength=len(cell_numbers))

    data = {'grid_row': (cell_numbers // GRID_WIDTH).astype('int32'),
            'grid_col': (cell_numbers % GRID_WIDTH).astype('int32'),
            'all_jobs': cell_sums(total_jobs).astype('int64'),
            'high_pay_jobs': cell_sums(high_pay_jobs).astype('int64')}
    for index, name in enumerate(INDUSTRIES):
        data[name] = cell_sums(industry_jobs[:, index]).astype('int64')
        data[name + '_hp'] = cell_sums(industry_high_pay[:, index])
    print(f"{release['state']}: {len(block_codes):,} blocks, {int(total_jobs.sum()):,} jobs, "
          f"{int(government_jobs.sum()):,} government jobs", flush=True)
    return arrow.table(data)


def build_industry_jobs():
    """Build the independent per-cell industry weights used by GDP and hold-outs."""
    releases = json.loads(RELEASES.read_text())
    tables = [industry_jobs_per_cell(release) for release in releases]
    value_columns = [name for name in tables[0].column_names if name not in ('grid_row', 'grid_col')]
    table = arrow.concat_tables(tables).group_by(['grid_row', 'grid_col']).aggregate([
        (name, 'sum') for name in value_columns])
    table = table.rename_columns(['grid_row', 'grid_col', *value_columns])
    table = table.sort_by([('grid_row', 'ascending'), ('grid_col', 'ascending')])
    parquet.write_table(table, INDUSTRY_JOBS_PER_CELL, compression='zstd')
    print(f'{len(table):,} industry-job cells written to {INDUSTRY_JOBS_PER_CELL}', flush=True)


if __name__ == '__main__':
    build()
    build_industry_jobs()

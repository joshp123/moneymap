"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

US workplace jobs per grid cell, from the US Census Bureau's LEHD
Origin-Destination Employment Statistics (LODES8). For each state and DC, the
latest S000_JT00 workplace file gives all jobs (C000) and high-pay jobs (CE03)
per 2020 census block; the crosswalk gives each block's internal point and
current county. Blocks are counted in the grid cell that contains their point.

Writes data/raw/lodes/releases.json and jobs_per_cell.parquet.

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

LODES = 'https://lehd.ces.census.gov/data/lodes/LODES8/'
RAW = ROOT / 'data/raw/lodes'
RELEASES = RAW / 'releases.json'
JOBS_PER_CELL = RAW / 'jobs_per_cell.parquet'
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


if __name__ == '__main__':
    build()

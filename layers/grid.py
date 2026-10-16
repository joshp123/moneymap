"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

The 30 arc-second grid and the tile format that every layer shares.

Every layer is one float32 value per cell of the GHS-POP 2025 grid: 43,202 by
21,384 cells, 1/120 degree each, from (-180.0079159313, 89.0995831776). The
Kummu GDP raster uses the same grid. Tiles are 120 by 120 cells of
little-endian float32, row-major from the north-west, at
data/layers/<layer>/<tile row>/<tile column>.bin. Tiles that would be all zero
are not written; the Worker reads a missing tile as zero. worker/index.js holds
the same grid constants.
"""
import math
from pathlib import Path
import zipfile

from affine import Affine
import numpy as np
import pyarrow.parquet as parquet
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
LAYERS_DIRECTORY = ROOT / 'data/layers'
BUILD_DIRECTORY = ROOT / 'data/build'
KUMMU_GDP_RASTER = ROOT / 'data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif'
KUMMU_GDP_2024_BAND = 8
GHS_POPULATION_ZIP = ROOT / 'data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip'
GRID_WIDTH, GRID_HEIGHT = 43202, 21384
GRID_TRANSFORM = Affine(0.008333333300326923, 0.0, -180.00791593130032, 0.0, -0.00833333329979504, 89.0995831776456)
TILE_SIZE = 120
EARTH_RADIUS_KM = 6371.0088


def open_zipped_raster(path):
    with zipfile.ZipFile(path) as archive:
        name, = [name for name in archive.namelist() if name.lower().endswith('.tif')]
    return rasterio.open(f'/vsizip/{path}/{name}')


def open_kummu_gdp_and_population():
    """Open the two source rasters that define the grid, after checking they share it."""
    if list(KUMMU_GDP_RASTER.parent.glob('*.aria2')):
        raise RuntimeError('GDP download is still running')
    gdp = rasterio.open(KUMMU_GDP_RASTER)
    population = open_zipped_raster(GHS_POPULATION_ZIP)
    for source in (gdp, population):
        if (source.width, source.height) != (GRID_WIDTH, GRID_HEIGHT):
            raise RuntimeError(f'Unexpected grid dimensions: {source.shape}')
        if source.transform != GRID_TRANSFORM:
            raise RuntimeError(f'Unexpected grid transform: {source.transform!r}')
        if source.crs != rasterio.crs.CRS.from_epsg(4326):
            raise RuntimeError(f'Unexpected CRS: {source.crs}')
    if gdp.descriptions[KUMMU_GDP_2024_BAND - 1] != 'gdp_2024':
        raise RuntimeError(f'GDP band {KUMMU_GDP_2024_BAND} is {gdp.descriptions[KUMMU_GDP_2024_BAND - 1]!r}, expected gdp_2024')
    return gdp, population


def read_window_zero_filled(source, band, window):
    """Read one window as float32, with no-data and NaN cells as zero."""
    values = source.read(band, window=window, masked=True).filled(0)
    return np.nan_to_num(values, nan=0).astype('<f4', copy=False)


def tile_row_strips():
    """Full-width windows, one row of tiles high, from north to south."""
    for row in range(0, GRID_HEIGHT, TILE_SIZE):
        yield Window(0, row, GRID_WIDTH, min(TILE_SIZE, GRID_HEIGHT - row))


def require_empty_layer_directory(layer):
    directory = LAYERS_DIRECTORY / layer
    if directory.exists() and any(directory.iterdir()):
        raise RuntimeError(f'{directory} is not empty; move it aside before rebuilding')


def write_layer_tiles(layer, strip_values, strip_row):
    """Write the non-zero tiles of one strip and return how many were written."""
    count = 0
    for column in range(0, strip_values.shape[1], TILE_SIZE):
        block = strip_values[:, column:column + TILE_SIZE]
        if not np.any(block):
            continue
        tile = np.zeros((TILE_SIZE, TILE_SIZE), dtype='<f4')
        tile[:block.shape[0], :block.shape[1]] = block
        directory = LAYERS_DIRECTORY / layer / str(strip_row // TILE_SIZE)
        directory.mkdir(parents=True, exist_ok=True)
        tile.tofile(directory / f'{column // TILE_SIZE}.bin')
        count += 1
    return count


def layer_tile_paths(layer):
    return sorted((LAYERS_DIRECTORY / layer).glob('*/*.bin'))


def layer_tile_total(layer):
    """Read every written tile back and sum it, to check the work product itself."""
    return sum(np.fromfile(path, dtype='<f4').sum(dtype='float64') for path in layer_tile_paths(layer))


def raster_profile(grid, dtype):
    return dict(driver='GTiff', width=grid.width, height=grid.height, count=1,
                crs=grid.crs, transform=grid.transform, dtype=dtype,
                tiled=True, blockxsize=256, blockysize=256, compress='deflate', BIGTIFF='IF_SAFER')


def bounding_window(grid, bounds):
    """The grid window covering (west, south, east, north), clipped to the grid."""
    left, top = ~grid.transform * (bounds[0], bounds[3])
    right, bottom = ~grid.transform * (bounds[2], bounds[1])
    col0, row0 = max(0, math.floor(left)), max(0, math.floor(top))
    col1, row1 = min(grid.width, math.ceil(right)), min(grid.height, math.ceil(bottom))
    return Window(col0, row0, col1 - col0, row1 - row0)


def window_strips(grid, bounds):
    window = bounding_window(grid, bounds)
    last_row = int(window.row_off + window.height)
    for row in range(int(window.row_off), last_row, TILE_SIZE):
        yield Window(window.col_off, row, window.width, min(TILE_SIZE, last_row - row))


class SparseCellCounts:
    """Per-cell counts from a Parquet table of grid_row, grid_col and value columns,
    read back as dense windows of the grid. Used for Overture places and stops and
    for LODES jobs."""

    def __init__(self, path, value_columns, width=GRID_WIDTH, height=GRID_HEIGHT):
        self.value_columns = tuple(value_columns)
        table = parquet.read_table(path, columns=['grid_row', 'grid_col', *self.value_columns])
        rows = table['grid_row'].to_numpy()
        columns = table['grid_col'].to_numpy()
        values = [table[name].to_numpy().astype('float64') for name in self.value_columns]
        inside = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
        self.totals = {name: float(value.sum(dtype='float64'))
                       for name, value in zip(self.value_columns, values)}
        self.outside_totals = {name: float(value[~inside].sum(dtype='float64'))
                               for name, value in zip(self.value_columns, values)}
        order = np.argsort(rows[inside], kind='stable')
        self.rows = rows[inside][order]
        self.columns = columns[inside][order]
        self.values = [value[inside][order] for value in values]

    def window(self, window):
        """One float64 plane per value column."""
        row_start, column_start = int(window.row_off), int(window.col_off)
        height, width = int(window.height), int(window.width)
        start, end = np.searchsorted(self.rows, [row_start, row_start + height])
        rows = self.rows[start:end] - row_start
        columns = self.columns[start:end] - column_start
        inside = (columns >= 0) & (columns < width)
        output = []
        for values in self.values:
            plane = np.zeros((height, width), dtype='float64')
            np.add.at(plane, (rows[inside], columns[inside]), values[start:end][inside])
            output.append(plane)
        return tuple(output)

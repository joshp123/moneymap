"""Written by AI on 2026.10.16 by model gpt-6.1-sol."""
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
GDP_PATH = ROOT / 'data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif'
POPULATION_ZIP = ROOT / 'data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip'
TILE_SIZE = 120


def open_sources():
    import zipfile
    if list(GDP_PATH.parent.glob('*.aria2')):
        raise RuntimeError('GDP download is still running')
    with zipfile.ZipFile(POPULATION_ZIP) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith('.tif')]
    if len(names) != 1:
        raise RuntimeError(f'Expected one population TIFF, found {names}')
    gdp = rasterio.open(GDP_PATH)
    population = rasterio.open(f'/vsizip/{POPULATION_ZIP}/{names[0]}')
    for source in (gdp, population):
        if (source.width, source.height) != (43202, 21384):
            raise RuntimeError(f'Unexpected grid dimensions: {source.shape}')
        if not np.allclose(tuple(source.transform)[:6], (1/120, 0, -180.0079159313, 0, -1/120, 89.0995831776), rtol=0, atol=1e-9):
            raise RuntimeError(f'Unexpected grid transform: {source.transform!r}')
        if source.crs != rasterio.crs.CRS.from_epsg(4326):
            raise RuntimeError(f'Unexpected CRS: {source.crs}')
    if gdp.transform != population.transform:
        raise RuntimeError(f'Grid transforms differ: {gdp.transform!r}, {population.transform!r}')
    if gdp.descriptions[7] != 'gdp_2024':
        raise RuntimeError(f'GDP band 8 is {gdp.descriptions[7]!r}, expected gdp_2024')
    return gdp, population


def clean_window(source, band, window):
    values = source.read(band, window=window, masked=True).filled(0)
    return np.nan_to_num(values, nan=0).astype('<f4', copy=False)


def build():
    output = ROOT / 'data/tiles'
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('data/tiles is not empty; move the old tiles aside before rebuilding')
    output.mkdir(parents=True, exist_ok=True)
    source_totals = np.zeros(2, dtype=np.float64)
    tile_count = 0
    gdp, population = open_sources()
    with gdp, population:
        print(json.dumps({'shape': gdp.shape, 'transform': tuple(gdp.transform), 'band': gdp.descriptions[7]}), flush=True)
        for row in range(0, gdp.height, TILE_SIZE):
            height = min(TILE_SIZE, gdp.height - row)
            # Read one strip, rather than repeatedly decompressing raster blocks.
            layers = [clean_window(source, band, Window(0, row, source.width, height))
                      for source, band in ((gdp, 8), (population, 1))]
            source_totals += [layer.sum(dtype=np.float64) for layer in layers]
            for col in range(0, gdp.width, TILE_SIZE):
                width = min(TILE_SIZE, gdp.width - col)
                tile = np.zeros((2, TILE_SIZE, TILE_SIZE), dtype='<f4')
                for index, layer in enumerate(layers):
                    tile[index, :height, :width] = layer[:, col:col+width]
                if not np.any(tile):
                    continue
                directory = output / str(row // TILE_SIZE)
                directory.mkdir(exist_ok=True)
                tile.tofile(directory / f'{col // TILE_SIZE}.bin')
                tile_count += 1
            if row // TILE_SIZE % 20 == 0:
                print(f'Row {row // TILE_SIZE}: {tile_count} tiles', flush=True)
    # Read the emitted files back to verify the actual work product.
    tile_totals = np.zeros(2, dtype=np.float64)
    for path in output.glob('*/*.bin'):
        tile_totals += np.fromfile(path, dtype='<f4').reshape(2, -1).sum(axis=1, dtype=np.float64)
    np.testing.assert_allclose(tile_totals, source_totals, rtol=1e-12, atol=0.01)
    report = {'tile_count': tile_count, 'bytes': tile_count * 115200,
              'source_totals': source_totals.tolist(), 'tile_totals': tile_totals.tolist()}
    (ROOT / 'data/tiling-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build()

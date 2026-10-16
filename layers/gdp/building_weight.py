"""Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

The building weight q: non-residential building volume squared over surface,
from GHSL GHS-BUILT-V and GHS-BUILT-S R2023A (2025). It favours tall buildings
over large sheds. The GHSL BUILT grid starts 0.8 cells east of the population
grid, so population column k receives 0.8 of BUILT column k-1 and 0.2 of BUILT
column k.
"""
from contextlib import contextmanager

import numpy as np
from rasterio.windows import Window

from layers.grid import ROOT, open_zipped_raster, read_window_zero_filled

NONRESIDENTIAL_VOLUME_ZIP = ROOT / 'data/raw/research-gdp/nres_v_30ss.zip'
NONRESIDENTIAL_SURFACE_ZIP = ROOT / 'data/raw/research-gdp/nres_s_30ss.zip'


@contextmanager
def open_nonresidential_volume_and_surface():
    with open_zipped_raster(NONRESIDENTIAL_VOLUME_ZIP) as volume, open_zipped_raster(NONRESIDENTIAL_SURFACE_ZIP) as surface:
        yield volume, surface


def check_built_grid_alignment(grid, volume, surface):
    """Return the BUILT grid's eastward offset in population cells, after checking it is 0.8."""
    assert volume.shape == surface.shape == (21384, 43201)
    assert volume.transform == surface.transform
    np.testing.assert_allclose([volume.transform.a, volume.transform.e, volume.transform.f],
                               [grid.transform.a, grid.transform.e, grid.transform.f], rtol=0, atol=1e-9)
    offset = (volume.transform.c - grid.transform.c) / grid.transform.a
    np.testing.assert_allclose(offset, 0.8, atol=1e-7)
    return offset


def building_weight_q(volume, surface, window, grid):
    """Compute q on BUILT cells, then shift it onto the population cells of window."""
    start = max(0, int(window.col_off) - 1)
    end = min(volume.width, int(window.col_off + window.width))
    source_window = Window(start, window.row_off, end - start, window.height)
    v = read_window_zero_filled(volume, 1, source_window).astype('float64')
    s = read_window_zero_filled(surface, 1, source_window).astype('float64')
    q = np.divide(v * v, s, out=np.zeros_like(v), where=s > 0)
    output = np.zeros((int(window.height), int(window.width)), dtype='float64')
    east_fraction = (volume.transform.c - grid.transform.c) / grid.transform.a
    for shift, fraction in ((1, east_fraction), (0, 1 - east_fraction)):
        target_start = max(int(window.col_off), start + shift)
        target_end = min(int(window.col_off + window.width), end + shift)
        if target_end > target_start:
            output[:, target_start-int(window.col_off):target_end-int(window.col_off)] += fraction * q[:, target_start-shift-start:target_end-shift-start]
    return output

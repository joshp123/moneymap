"""Written by AI on 2026.10.16 by model claude fable 5.1.

Shared grid tools for the land-value held-out tests: read the project's 30 arc-second
grids for a bounding box, build candidate weights, rasterise units, sum and score.

All grids are read on the GHS-POP grid (43,202 x 21,384, origin -180.0079, 89.0996).
GHS-BUILT grids are offset 0.8 cell east; they are shifted onto the POP grid as in
scripts/build_layers.py: POP column k = 0.8 x BUILT[k-1] + 0.2 x BUILT[k].
"""
import math, zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = ROOT / 'data/experiments/land-value'

POP_ZIP = ROOT / 'data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip'
KUMMU_TIF = ROOT / 'data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif'
GDP_V3_TIF = ROOT / 'data/gdp-v3/gdp.tif'
BUILT_V_ZIP = ROOT / 'data/raw/research-gdp/built_v_30ss.zip'
NRES_V_ZIP = ROOT / 'data/raw/research-gdp/nres_v_30ss.zip'
NRES_S_ZIP = ROOT / 'data/raw/research-gdp/nres_s_30ss.zip'
BUILT_S_ZIP = EXPERIMENTS / 'raw/ghs_built_s/GHS_BUILT_S_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip'
SPAM_TIF = EXPERIMENTS / 'raw/spam/spam2020-physical_area-all.tif'

EARTH_RADIUS_KM = 6371.0088
CELL_DEG = 1 / 120


def zip_raster_path(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        name, = [n for n in archive.namelist() if n.endswith('.tif')]
    return f'zip+file://{zip_path}!{name}'


def read_clean(dataset, band, window):
    data = dataset.read(band, window=window, boundless=True, fill_value=0).astype('float64')
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    data[data < 0] = 0
    return data


class Region:
    """All project grids for one bounding box, on the POP grid."""

    def __init__(self, west, south, east, north):
        with rasterio.open(zip_raster_path(POP_ZIP)) as pop:
            self.window = from_bounds(west, south, east, north, pop.transform).round_offsets().round_lengths()
            self.transform = pop.window_transform(self.window)
            self.pop = read_clean(pop, 1, self.window)
        self.height, self.width = self.pop.shape
        rows = np.arange(self.height)
        self.lat_centre = self.transform.f + (rows + 0.5) * self.transform.e
        cell_height_km = EARTH_RADIUS_KM * math.radians(CELL_DEG)
        self.cell_area_km2 = (cell_height_km * cell_height_km * np.cos(np.radians(self.lat_centre)))[:, None] * np.ones((1, self.width))
        self._cache = {}

    # ---- layers -------------------------------------------------------------------
    def layer(self, name):
        if name not in self._cache:
            self._cache[name] = getattr(self, f'_load_{name}')()
        return self._cache[name]

    def _load_gdp_kummu(self):
        with rasterio.open(KUMMU_TIF) as s:
            return read_clean(s, s.count, self.window)

    def _load_gdp_v3(self):
        with rasterio.open(GDP_V3_TIF) as s:
            return read_clean(s, 1, self.window)

    def _built_shifted(self, zip_path, transform_fn=None):
        """Read a BUILT grid for this window (plus one column west) and shift it onto POP cells."""
        with rasterio.open(zip_raster_path(zip_path)) as s:
            east_fraction = (s.transform.c - (self.transform.c - self.window.col_off * self.transform.a)) / s.transform.a
            # BUILT column j covers POP column j shifted east by east_fraction (0.8) cells
            col0 = int(self.window.col_off) - 1
            source = Window(col0, self.window.row_off, int(self.window.width) + 1, int(self.window.height))
            data = read_clean(s, 1, source)
        if transform_fn is not None:
            data = transform_fn(data)
        return east_fraction * data[:, :-1] + (1 - east_fraction) * data[:, 1:]

    def _load_built_v(self):
        return self._built_shifted(BUILT_V_ZIP)

    def _load_built_s(self):
        return self._built_shifted(BUILT_S_ZIP)

    def _load_nres_v(self):
        return self._built_shifted(NRES_V_ZIP)

    def _load_nres_s(self):
        return self._built_shifted(NRES_S_ZIP)

    def _load_q(self):
        """q = non-residential volume^2 / surface (height-weighted volume), computed on BUILT cells then shifted."""
        with rasterio.open(zip_raster_path(NRES_V_ZIP)) as v, rasterio.open(zip_raster_path(NRES_S_ZIP)) as s:
            col0 = int(self.window.col_off) - 1
            source = Window(col0, self.window.row_off, int(self.window.width) + 1, int(self.window.height))
            volume = read_clean(v, 1, source)
            surface = read_clean(s, 1, source)
            east_fraction = (v.transform.c - (self.transform.c - self.window.col_off * self.transform.a)) / v.transform.a
        q = np.divide(volume * volume, surface, out=np.zeros_like(volume), where=surface > 0)
        return east_fraction * q[:, :-1] + (1 - east_fraction) * q[:, 1:]

    def _load_cropland_ha(self):
        """SPAM 2020 physical crop area (ha per 5-arc-minute cell) spread evenly over the 100 POP cells inside."""
        with rasterio.open(SPAM_TIF) as s:
            spam = s.read(1).astype('float64')
            spam[~np.isfinite(spam) | (spam < 0)] = 0
            lon = self.transform.c + (np.arange(self.width) + 0.5) * self.transform.a
            cols = np.clip(((lon + 180) / (1 / 12)).astype(int), 0, s.width - 1)
            rows = np.clip(((90 - self.lat_centre) / (1 / 12)).astype(int), 0, s.height - 1)
        return spam[rows[:, None], cols[None, :]] / 100.0

    # ---- operators -----------------------------------------------------------------
    def access(self, field, tau_km):
        """Exponential-decay neighbourhood sum: sum_j field_j exp(-d_ij / tau), per km2. FFT with zero padding."""
        lat0 = float(np.mean(self.lat_centre))
        cy = EARTH_RADIUS_KM * math.radians(CELL_DEG)
        cx = cy * math.cos(math.radians(lat0))
        pad_y, pad_x = int(4 * tau_km / cy), int(4 * tau_km / cx)
        padded = np.pad(field, ((pad_y, pad_y), (pad_x, pad_x)))
        h, w = padded.shape
        yy = np.minimum(np.arange(h), h - np.arange(h)) * cy
        xx = np.minimum(np.arange(w), w - np.arange(w)) * cx
        kernel = np.exp(-np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2) / tau_km)
        kernel /= kernel.sum() * cx * cy
        out = np.real(np.fft.ifft2(np.fft.fft2(padded) * np.fft.fft2(kernel)))
        out = out[pad_y:pad_y + field.shape[0], pad_x:pad_x + field.shape[1]]
        return np.maximum(out, 0)

    def rasterize_units(self, geometries_with_ids):
        """Label raster by cell centre. geometries_with_ids: iterable of (geojson geometry dict or shapely geom, int id>0)."""
        shapes = [(g if hasattr(g, 'geom_type') else shape(g), i) for g, i in geometries_with_ids]
        return rasterize(shapes, out_shape=(self.height, self.width), transform=self.transform, fill=0, dtype='int32')

    def circle_mask(self, lon, lat, radius_km):
        lon_c = self.transform.c + (np.arange(self.width) + 0.5) * self.transform.a
        dx = (lon_c[None, :] - lon) * EARTH_RADIUS_KM * math.radians(1) * math.cos(math.radians(lat))
        dy = (self.lat_centre[:, None] - lat) * EARTH_RADIUS_KM * math.radians(1)
        return (dx * dx + dy * dy) <= radius_km * radius_km


def unit_sums(labels, field, n_units):
    return np.bincount(labels.ravel(), weights=field.ravel(), minlength=n_units + 1)[1:]


def candidate_weights(region, tau_km=40.0, gamma=0.25, include_built_s=True):
    """Fixed candidate cell weights. Parameters set before any held-out scoring."""
    pop = region.pop
    area = region.cell_area_km2
    pop_access = region.access(pop, tau_km)                     # people per km2 within ~tau km
    weights = {
        'population': pop,
        'population x access^0.25': pop * np.power(pop_access, gamma),
        'GDP v3 (workplace)': region.layer('gdp_v3'),
        'GDP Kummu (residence)': region.layer('gdp_kummu'),
        'built volume (all)': region.layer('built_v'),
        'built volume x access^0.25': region.layer('built_v') * np.power(pop_access, gamma),
        'non-residential q': region.layer('q'),
    }
    if include_built_s and BUILT_S_ZIP.exists():
        weights['built surface (all)'] = region.layer('built_s')
        weights['built surface x access^0.25'] = region.layer('built_s') * np.power(pop_access, gamma)
    for sensitivity_gamma in (0.15, 0.35, 0.5):   # sensitivity only; 0.25 is the proposed value
        weights[f'population x access^{sensitivity_gamma}'] = pop * np.power(pop_access, sensitivity_gamma)
    weights['area'] = area
    if SPAM_TIF.exists():
        weights['cropland (SPAM)'] = region.layer('cropland_ha')
    return weights


def score(predicted, actual):
    """predicted and actual: unit vectors. Returns misallocated share and median |log ratio| after scaling to the same total."""
    keep = actual > 0
    predicted = predicted[keep] / predicted[keep].sum() * actual[keep].sum()
    actual = actual[keep]
    misallocated = np.abs(predicted - actual).sum() / 2 / actual.sum()
    with np.errstate(divide='ignore'):
        log_ratio = np.log(np.where(predicted > 0, predicted, np.nan) / actual)
    return {'misallocated_share': float(misallocated), 'median_abs_log_ratio': float(np.nanmedian(np.abs(log_ratio))),
            'n_units': int(keep.sum())}


def mix(shares, weights):
    """Linear mix of unit-level shares. shares: dict name -> unit vector; weights: dict name -> coefficient."""
    out = None
    for name, coefficient in weights.items():
        s = shares[name] / shares[name].sum()
        out = s * coefficient if out is None else out + s * coefficient
    return out

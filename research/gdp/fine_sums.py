import numpy as np, rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from affine import Affine
def fine_sums(path, band, shapes, n, bounds, transforms=(lambda a: a,), sub=10):
    """Sum a 30 arc-second raster over polygons, splitting each cell into sub x sub parts so small polygons get their area share."""
    with rasterio.open(path) as ds:
        w = from_bounds(*bounds, ds.transform).round_offsets().round_lengths()
        arr = ds.read(band, window=w).astype('float64'); tr = ds.window_transform(w)
    arr[~np.isfinite(arr)] = 0
    ftr = tr * Affine.scale(1.0 / sub)
    lab = rasterize(shapes, out_shape=(arr.shape[0] * sub, arr.shape[1] * sub), transform=ftr, fill=0, dtype='int32')
    results = []
    for f in transforms:
        v = f(arr) / (sub * sub)
        fine = np.repeat(np.repeat(v.astype('float32'), sub, 0), sub, 1)
        results.append(np.bincount(lab.ravel(), weights=fine.ravel(), minlength=n + 1)[1:])
        del fine
    return results

def read_window(path, band, bounds):
    with rasterio.open(path) as ds:
        w = from_bounds(*bounds, ds.transform).round_offsets().round_lengths()
        arr = ds.read(band, window=w).astype('float64'); tr = ds.window_transform(w)
    arr[~np.isfinite(arr)] = 0
    return arr, tr

def fine_sums_arrays(arrays, tr, shapes, n, sub=10):
    ftr = tr * Affine.scale(1.0 / sub)
    shape = arrays[0].shape
    lab = rasterize(shapes, out_shape=(shape[0] * sub, shape[1] * sub), transform=ftr, fill=0, dtype='int32').ravel()
    out = []
    for v in arrays:
        fine = np.repeat(np.repeat((v / (sub * sub)).astype('float32'), sub, 0), sub, 1)
        out.append(np.bincount(lab, weights=fine.ravel(), minlength=n + 1)[1:]); del fine
    return out

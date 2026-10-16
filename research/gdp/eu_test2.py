import json, sys, numpy as np, rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]
BOUNDS = (-32.0, 27.0, 45.0, 72.0)
prev = json.load(open('/tmp/moneymap-research/eu_sums.json'))
feats = {f['properties']['NUTS_ID']: f for f in json.load(open(D + 'nuts3_2024_03m.geojson'))['features']}
kid = prev['ids']
shapes = [(feats[i]['geometry'], k + 1) for k, i in enumerate(kid)]
def read(path):
    with rasterio.open(path) as ds:
        w = from_bounds(*BOUNDS, ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=w).astype('float64'); tr = ds.window_transform(w)
    arr[~np.isfinite(arr)] = 0
    lab = rasterize(shapes, out_shape=arr.shape, transform=tr, fill=0, dtype='int32').ravel()
    return arr.ravel(), lab
def bc(lab, w): return np.bincount(lab, weights=w, minlength=len(kid) + 1)[1:].tolist()
pop, lab = read('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
for k in [1.2, 1.5, 2.0]: prev['pop^%s' % k] = bc(lab, pop ** k)
vol, lab = read('/vsizip/' + D + 'built_v_30ss.zip/GHS_BUILT_V_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
prev['vol'] = bc(lab, vol)
for k in [1.2, 1.5, 2.0]: prev['vol^%s' % k] = bc(lab, (vol / 1e5) ** k)
nv, lab = read('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
prev['nres_v^1.5'] = bc(lab, (nv / 1e5) ** 1.5)
json.dump(prev, open('/tmp/moneymap-research/eu_sums.json', 'w'))
print('ok')

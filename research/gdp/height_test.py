import sys, json, glob, numpy as np
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from fine_sums import read_window, fine_sums_arrays
D = '/tmp/moneymap-research/data/'
V = '/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'
S = '/vsizip/' + D + 'nres_s_30ss.zip/GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'
def derived(bounds):
    v, tr = read_window(V, 1, bounds); s, _ = read_window(S, 1, bounds)
    h = np.where(s > 0, v / np.maximum(s, 1), 0)          # average non-residential height, m
    return [v * h, v * np.sqrt(h), np.where(h >= 6, v, 0), np.where(h >= 9, v, 0)], tr
names = ['nres_vxh', 'nres_vxsqrth', 'nres_v_h6', 'nres_v_h9']
which = sys.argv[1]
if which == 'uk':
    geo = {}
    for p in glob.glob(D + 'lsoa/p*.geojson'):
        for f in json.load(open(p))['features']: geo[f['properties']['LSOA11CD']] = f['geometry']
    path = '/tmp/moneymap-research/uk_sums.json'; d = json.load(open(path)); shapes = [(geo[k], i + 1) for i, k in enumerate(d['ids'])]; bounds = (-6.0, 49.8, 2.0, 55.9)
elif which == 'eu':
    feats = {f['properties']['NUTS_ID']: f for f in json.load(open(D + 'nuts3_2024_03m.geojson'))['features']}
    path = '/tmp/moneymap-research/eu_sums.json'; d = json.load(open(path)); shapes = [(feats[k]['geometry'], i + 1) for i, k in enumerate(d['ids'])]; bounds = (-32.0, 27.0, 45.0, 72.0)
elif which == 'us':
    from shp import read_dbf, read_shp
    recs = read_dbf(D + 'county/cb_2024_us_county_500k.dbf'); geoms = read_shp(D + 'county/cb_2024_us_county_500k.shp')
    gm = {r['GEOID']: g for r, g in zip(recs, geoms)}
    path = '/tmp/moneymap-research/us_sums.json'; d = json.load(open(path)); shapes = [(gm[k], i + 1) for i, k in enumerate(d['ids'])]; bounds = (-125.0, 24.0, -66.5, 49.5)
arrs, tr = derived(bounds)
res = fine_sums_arrays(arrs, tr, shapes, len(d['ids']), sub=10 if which == 'uk' else 1)
for n, r in zip(names, res): d[n] = r.tolist()
json.dump(d, open(path, 'w')); print(which, 'ok')

import json, sys, numpy as np, rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds, Window
D = '/tmp/moneymap-research/data/'
REPO = sys.argv[1]
BOUNDS = (-32.0, 27.0, 45.0, 72.0)
feats = json.load(open(D + 'nuts3_2024_03m.geojson'))['features']
ids = [f['properties']['NUTS_ID'] for f in feats]
def inside(geom):
    def walk(c):
        if isinstance(c[0], (int, float)): yield c
        else:
            for x in c: yield from walk(x)
    xs = [p[0] for p in walk(geom['coordinates'])]; ys = [p[1] for p in walk(geom['coordinates'])]
    return min(xs) >= BOUNDS[0] and max(xs) <= BOUNDS[2] and min(ys) >= BOUNDS[1] and max(ys) <= BOUNDS[3]
keep = [i for i, f in enumerate(feats) if inside(f['geometry'])]
shapes = [(feats[i]['geometry'], k + 1) for k, i in enumerate(keep)]
kid = [ids[i] for i in keep]
def sums(path, band=1):
    with rasterio.open(path) as ds:
        w = from_bounds(*BOUNDS, ds.transform).round_offsets().round_lengths()
        arr = ds.read(band, window=w).astype('float64')
        tr = ds.window_transform(w)
    arr[~np.isfinite(arr)] = 0
    lab = rasterize(shapes, out_shape=arr.shape, transform=tr, fill=0, dtype='int32')
    return np.bincount(lab.ravel(), weights=arr.ravel(), minlength=len(kid) + 1)[1:]
pop = sums('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
nv = sums('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
ns = sums('/vsizip/' + D + 'nres_s_30ss.zip/GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
kum = sums(REPO + '/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif', band=8)
g = json.load(open('/tmp/moneymap-research/nuts3_2023.json'))
gi = g['dimension']['geo']['category']['index']; gv = g['value']
gdp = np.array([gv.get(str(gi[k]), np.nan) if k in gi else np.nan for k in kid], dtype=float)
out = {'ids': kid, 'pop': pop.tolist(), 'nres_v': nv.tolist(), 'nres_s': ns.tolist(), 'kummu2024': kum.tolist(), 'gdp2023_meur': gdp.tolist()}
json.dump(out, open('/tmp/moneymap-research/eu_sums.json', 'w'))
print('regions', len(kid), 'with gdp', int(np.isfinite(gdp).sum()))

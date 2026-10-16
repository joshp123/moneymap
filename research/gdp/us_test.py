import sys, csv, json, numpy as np, rasterio
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from shp import read_dbf, read_shp
from rasterio.features import rasterize
from rasterio.windows import from_bounds
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]
BOUNDS = (-125.0, 24.0, -66.5, 49.5)
recs = read_dbf(D + 'county/cb_2024_us_county_500k.dbf'); geoms = read_shp(D + 'county/cb_2024_us_county_500k.shp')
keep = [i for i, r in enumerate(recs) if r['STATEFP'] not in ('02', '15', '60', '66', '69', '72', '78')]
ids = [recs[i]['GEOID'] for i in keep]
shapes = [(geoms[i], k + 1) for k, i in enumerate(keep)]
def read(path, band=1):
    with rasterio.open(path) as ds:
        w = from_bounds(*BOUNDS, ds.transform).round_offsets().round_lengths()
        arr = ds.read(band, window=w).astype('float64'); tr = ds.window_transform(w)
    arr[~np.isfinite(arr)] = 0
    lab = rasterize(shapes, out_shape=arr.shape, transform=tr, fill=0, dtype='int32').ravel()
    return arr.ravel(), lab
def bc(lab, w): return np.bincount(lab, weights=w, minlength=len(ids) + 1)[1:].tolist()
out = {'ids': ids}
pop, lab = read('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif')
out['pop'] = bc(lab, pop)
for k in [1.2, 1.5]: out['pop^%s' % k] = bc(lab, pop ** k)
kum, lab = read(REPO + '/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif', band=8); out['kummu2024'] = bc(lab, kum)
nv, lab = read('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'); out['nres_v'] = bc(lab, nv)
out['nres_v^1.5'] = bc(lab, (nv / 1e5) ** 1.5)
vol, lab = read('/vsizip/' + D + 'built_v_30ss.zip/GHS_BUILT_V_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'); out['vol'] = bc(lab, vol)
out['vol^1.5'] = bc(lab, (vol / 1e5) ** 1.5)
gdp = {}
for r in csv.DictReader(open(D + 'cagdp1/CAGDP1__ALL_AREAS_2001_2024.csv', encoding='latin-1')):
    if (r.get('LineCode') or '').strip() == '3':
        try: gdp[r['GeoFIPS'].strip().strip('"')] = float(r['2024'])
        except (ValueError, TypeError): pass
out['gdp2024_kusd'] = [gdp.get(i, float('nan')) for i in ids]
json.dump(out, open('/tmp/moneymap-research/us_sums.json', 'w'))
print('counties', len(ids), 'with gdp', sum(1 for i in ids if i in gdp))

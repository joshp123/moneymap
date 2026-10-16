import sys, json, glob, numpy as np
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from fine_sums import fine_sums
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]
BOUNDS = (-6.0, 49.8, 2.0, 55.9)
geo = {}
for p in glob.glob(D + 'lsoa/p*.geojson'):
    for f in json.load(open(p))['features']: geo[f['properties']['LSOA11CD']] = f['geometry']
gva = json.load(open('/tmp/moneymap-research/uk_lsoa_gva.json'))
ids = [k for k in gva if k in geo]
shapes = [(geo[k], i + 1) for i, k in enumerate(ids)]
out = {'ids': ids, 'gva2023_mgbp': [gva[k]['gva'] for k in ids], 'lad': [gva[k]['lad'] for k in ids], 'msoa': [gva[k]['msoa'] for k in ids]}
P = '/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'
r = fine_sums(P, 1, shapes, len(ids), BOUNDS, (lambda a: a, lambda a: a ** 1.2, lambda a: a ** 1.5))
out['pop'], out['pop^1.2'], out['pop^1.5'] = [x.tolist() for x in r]
out['kummu2024'] = fine_sums(REPO + '/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif', 8, shapes, len(ids), BOUNDS)[0].tolist()
r = fine_sums('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, shapes, len(ids), BOUNDS, (lambda a: a, lambda a: (a / 1e5) ** 1.5))
out['nres_v'], out['nres_v^1.5'] = [x.tolist() for x in r]
r = fine_sums('/vsizip/' + D + 'built_v_30ss.zip/GHS_BUILT_V_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, shapes, len(ids), BOUNDS, (lambda a: a, lambda a: (a / 1e5) ** 1.5))
out['vol'], out['vol^1.5'] = [x.tolist() for x in r]
import os
ls = sys.argv[2] if len(sys.argv) > 2 else ''
if ls:
    r = fine_sums(ls, 1, shapes, len(ids), BOUNDS, (lambda a: np.where(a < 0, 0, a), lambda a: np.where(a < 0, 0, a) ** 1.2))
    out['landscan2022'], out['landscan^1.2'] = [x.tolist() for x in r]
json.dump(out, open('/tmp/moneymap-research/uk_sums.json', 'w'))
print('lsoas', len(ids), 'of', len(gva))

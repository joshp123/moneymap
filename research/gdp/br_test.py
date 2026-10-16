import sys, json, numpy as np
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from fine_sums import read_window, fine_sums_arrays
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]; B = (-74.5, -34.0, -28.5, 5.5)
fc = json.load(open(D + 'br_mun.geojson'))['features']
print(fc[0]['properties'])
ids = [str(f['properties']['codarea']) for f in fc]; shapes = [(f['geometry'], i + 1) for i, f in enumerate(fc)]
pib = {r['D1C']: float(r['V']) for r in json.load(open(D + 'br_pib_2023.json'))[1:] if r['V'] not in ('-', '...', 'X')}
out = {'ids': ids, 'gdp2023_kbrl': [pib.get(i, float('nan')) for i in ids]}
pa, ptr = read_window('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
ka, _ = read_window(REPO + '/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif', 8, B)
out['pop'], out['kummu2024'] = [x.tolist() for x in fine_sums_arrays([pa, ka], ptr, shapes, len(ids), sub=1)]
v, tr = read_window('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
s, _ = read_window('/vsizip/' + D + 'nres_s_30ss.zip/GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
h = np.where(s > 0, v / np.maximum(s, 1), 0)
out['nres_v'], out['nres_vxh'] = [x.tolist() for x in fine_sums_arrays([v, v * h], tr, shapes, len(ids), sub=1)]
json.dump(out, open('/tmp/moneymap-research/br_sums.json', 'w')); print('municipalities', len(ids), 'with pib', sum(1 for i in ids if i in pib))

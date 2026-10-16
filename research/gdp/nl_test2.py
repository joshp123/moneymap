import sys, json, numpy as np
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from fine_sums import read_window, fine_sums_arrays
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]; B = (3.2, 50.7, 7.3, 53.6)
fc = json.load(open(D + 'coropplus_2024.geojson'))['features']; gdp = json.load(open('/tmp/moneymap-research/nl_cp_gdp2023.json'))
ids = [f['properties']['statcode'] for f in fc]; shapes = [(f['geometry'], i + 1) for i, f in enumerate(fc)]
pa, ptr = read_window('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
pop = fine_sums_arrays([pa], ptr, shapes, len(ids))[0]
v, tr = read_window('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
s, _ = read_window('/vsizip/' + D + 'nres_s_30ss.zip/GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, B)
h = np.where(s > 0, v / np.maximum(s, 1), 0)
nv, nvh = fine_sums_arrays([v, v * h], tr, shapes, len(ids))
g = np.array([gdp.get(i, np.nan) for i in ids]); corop = np.array([i[:4] for i in ids])
tot = {k: [0.0, 0.0] for k in ['pop', 'nres_v mix0.5', 'nres_vxh mix0.5', 'nres_vxh mix0.25']}
for c in sorted(set(corop)):
    idx = np.where(corop == c)[0]
    if len(idx) < 2: continue
    a = g[idx] / g[idx].sum(); sp = pop[idx] / pop[idx].sum(); s1 = nv[idx] / nv[idx].sum(); s2 = nvh[idx] / nvh[idx].sum()
    preds = {'pop': sp, 'nres_v mix0.5': 0.5 * sp + 0.5 * s1, 'nres_vxh mix0.5': 0.5 * sp + 0.5 * s2, 'nres_vxh mix0.25': 0.25 * sp + 0.75 * s2}
    for k, p in preds.items(): tot[k][0] += g[idx].sum() * 0.5 * np.abs(p - a).sum(); tot[k][1] += g[idx].sum()
    for j, n in enumerate(idx):
        if ids[n] in ('CP2311', 'CP2323', 'CP4003', 'CP1703', 'CP2910'):
            print('%s %-28s actual %.3f | pop %.3f | nres_v %.3f | nres_vxh %.3f | vxh mix0.5 %.3f' % (ids[n], fc[n]['properties']['statnaam'], a[j], sp[j], s1[j], s2[j], 0.5 * sp[j] + 0.5 * s2[j]))
print('NL COROP-plus within COROP misallocated:', {k: round(v[0] / v[1], 3) for k, v in tot.items()})

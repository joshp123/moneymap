import sys, json, numpy as np
sys.path.insert(0, '/tmp/moneymap-research/scripts')
from fine_sums import fine_sums
D = '/tmp/moneymap-research/data/'; REPO = sys.argv[1]; BOUNDS = (3.2, 50.7, 7.3, 53.6)
fc = json.load(open(D + 'coropplus_2024.geojson'))['features']
gdp = json.load(open('/tmp/moneymap-research/nl_cp_gdp2023.json'))
ids = [f['properties']['statcode'] for f in fc]; shapes = [(f['geometry'], i + 1) for i, f in enumerate(fc)]
pop = fine_sums('/vsizip/' + REPO + '/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, shapes, len(ids), BOUNDS)[0]
nv = fine_sums('/vsizip/' + D + 'nres_v_30ss.zip/GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif', 1, shapes, len(ids), BOUNDS)[0]
kum = fine_sums(REPO + '/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif', 8, shapes, len(ids), BOUNDS)[0]
g = np.array([gdp.get(i, np.nan) for i in ids])
corop = np.array([i[:4] for i in ids])
for c in sorted(set(corop)):
    idx = np.where(corop == c)[0]
    if len(idx) < 2: continue
    for n in idx:
        a = g[n] / g[idx].sum(); sp = pop[n] / pop[idx].sum(); sv = nv[n] / nv[idx].sum(); sk = kum[n] / kum[idx].sum()
        print('%s %-34s actual %.3f | pop %.3f | nres_v %.3f | mix0.25 %.3f | kummu %.3f' % (ids[n], fc[n]['properties']['statnaam'], a, sp, sv, 0.25 * sp + 0.75 * sv, sk))

import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/br_sums.json')); ids = d['ids']
g = np.array(d['gdp2023_kbrl']); p = np.array(d['pop']); v = np.array(d['nres_vxh']); ok = np.isfinite(g) & (g > 0) & (p > 0)
G = collections.defaultdict(list)
for n in np.where(ok)[0]: G[ids[n][:2]].append(n)
G = [np.array(x) for x in G.values() if len(x) > 1]
for al in [0.25, 0.5, 0.75, 1.0]:
    t = s = 0.0
    for idx in G:
        a = g[idx] / g[idx].sum(); q = al * p[idx] / p[idx].sum() + (1 - al) * v[idx] / v[idx].sum(); t += g[idx].sum() * 0.5 * np.abs(q - a).sum(); s += g[idx].sum()
    print('Brazil alpha_pop %.2f misallocated %.3f' % (al, t / s))

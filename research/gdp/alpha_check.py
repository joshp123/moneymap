import json, sys, numpy as np, collections
def run(path, gkey, glen, label, excl_zzz=False):
    d = json.load(open(path)); ids = np.array(d['ids']); gdp = np.array(d[gkey], float); pop = np.array(d['pop']); nv = np.array(d['nres_v'])
    ok = np.isfinite(gdp) & (gdp > 0) & (pop > 0)
    if excl_zzz: ok &= np.array([not i.endswith('ZZZ') for i in ids])
    ids, gdp, pop, nv = ids[ok], gdp[ok], pop[ok], nv[ok]
    g = collections.defaultdict(list)
    for n, i in enumerate(ids): g[i[:glen]].append(n)
    G = [np.array(v) for v in g.values() if len(v) > 1]
    def mis(al):
        t = s = 0.0
        for idx in G:
            a = gdp[idx] / gdp[idx].sum(); p = al * pop[idx] / pop[idx].sum() + (1 - al) * nv[idx] / max(nv[idx].sum(), 1e-9)
            t += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); s += gdp[idx].sum()
        return t / s
    print(label, ' '.join('%.2f:%.3f' % (al, mis(al)) for al in [0, 0.25, 0.5, 0.75, 1.0]))
run('/tmp/moneymap-research/us_sums.json', 'gdp2024_kusd', 2, 'US county within state  ')
run('/tmp/moneymap-research/eu_sums.json', 'gdp2023_meur', 4, 'EU NUTS3 within NUTS2   ', True)
run('/tmp/moneymap-research/eu_sums.json', 'gdp2023_meur', 2, 'EU NUTS3 within country ', True)

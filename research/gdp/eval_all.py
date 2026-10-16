import json, numpy as np, collections
def load_uk():
    d = json.load(open('/tmp/moneymap-research/uk_sums.json'))
    names = [k for k in d if k not in ('ids', 'gva2023_mgbp', 'lad', 'msoa')]
    agg = collections.defaultdict(lambda: collections.defaultdict(float)); parent = {}
    for i in range(len(d['ids'])):
        m = d['msoa'][i]; agg[m]['gdp'] += d['gva2023_mgbp'][i]; parent[m] = d['lad'][i]
        for n in names: agg[m][n] += d[n][i]
    ks = list(agg); return ks, {n: np.array([agg[k][n] for k in ks]) for n in ['gdp'] + names}, [parent[k] for k in ks]
def load(path, gkey, glen):
    d = json.load(open(path)); ids = d['ids']
    names = [k for k in d if k not in ('ids', gkey)]
    keep = [i for i, k in enumerate(ids) if not k.endswith('ZZZ')]
    P = {n: np.array(d[n], float)[keep] for n in names}; P['gdp'] = np.array(d[gkey], float)[keep]
    return [ids[i] for i in keep], P, [ids[i][:glen] for i in keep]
def evaluate(label, ids, P, grp, proxies):
    ok = np.isfinite(P['gdp']) & (P['gdp'] > 0) & (P['pop'] > 0)
    g = collections.defaultdict(list)
    for n in np.where(ok)[0]: g[grp[n]].append(n)
    G = [np.array(v) for v in g.values() if len(v) > 1]
    def mis(w):
        t = s = 0.0
        for idx in G:
            a = P['gdp'][idx] / P['gdp'][idx].sum(); t += P['gdp'][idx].sum() * 0.5 * np.abs(w(idx) - a).sum(); s += P['gdp'][idx].sum()
        return t / s
    sh = lambda n, idx: P[n][idx] / max(P[n][idx].sum(), 1e-12)
    print('== %s: %d units in %d groups. population only: %.3f' % (label, sum(map(len, G)), len(G), mis(lambda idx: sh('pop', idx))))
    for n in proxies:
        curve = [(al, mis(lambda idx, al=al: al * sh('pop', idx) + (1 - al) * sh(n, idx))) for al in np.linspace(0, 1, 21)]
        best = min(curve, key=lambda x: x[1])
        print('   %-13s alone %.3f | mix alpha_pop=0.25 %.3f | 0.5 %.3f | best alpha_pop=%.2f %.3f' % (n, curve[0][1], dict(curve)[0.25], dict(curve)[0.5], best[0], best[1]))
prox = ['nres_v', 'nres_vxsqrth', 'nres_vxh', 'nres_v_h6', 'nres_v_h9', 'vol']
evaluate('UK MSOA within local authority', *load_uk(), prox)
evaluate('US county within state', *load('/tmp/moneymap-research/us_sums.json', 'gdp2024_kusd', 2), prox)
evaluate('EU NUTS3 within NUTS2', *load('/tmp/moneymap-research/eu_sums.json', 'gdp2023_meur', 4), prox)

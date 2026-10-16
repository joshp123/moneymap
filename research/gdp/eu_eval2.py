import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/eu_sums.json'))
ids = np.array(d['ids']); gdp = np.array(d['gdp2023_meur'])
names = [k for k in d if k not in ('ids', 'gdp2023_meur')]
P = {k: np.array(d[k]) for k in names}
ok = np.isfinite(gdp) & (gdp > 0) & (P['pop'] > 0) & np.array([not i.endswith('ZZZ') for i in ids])
ids, gdp = ids[ok], gdp[ok]; P = {k: v[ok] for k, v in P.items()}
def groups(level):
    g = collections.defaultdict(list)
    for n, i in enumerate(ids): g[i[:level]].append(n)
    return [np.array(v) for v in g.values() if len(v) > 1]
G = {4: groups(4), 2: groups(2)}
def ev(level, w):
    mis = tot = 0.0; logs = []
    for idx in G[level]:
        a = gdp[idx] / gdp[idx].sum(); p = w[idx] / w[idx].sum()
        mis += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); tot += gdp[idx].sum(); logs += list(np.abs(np.log(np.maximum(p, 1e-9) / a)))
    return mis / tot, float(np.median(logs))
def norm(x, idx): return x[idx] / x[idx].sum()
print('proxy                misalloc(in NUTS2) med|log|   misalloc(in country) med|log|')
for k in names:
    a = ev(4, P[k]); b = ev(2, P[k]); print('%-20s %.3f  %.3f      %.3f  %.3f' % (k, a[0], a[1], b[0], b[1]))
# mixes of pop and total volume
def evmix(level, n1, n2, al):
    mis = tot = 0.0
    for idx in G[level]:
        a = gdp[idx] / gdp[idx].sum(); p = al * norm(P[n1], idx) + (1 - al) * norm(P[n2], idx)
        mis += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); tot += gdp[idx].sum()
    return mis / tot
for n2 in ['vol', 'vol^1.5', 'nres_v', 'pop^1.5']:
    r = [(al, evmix(4, 'pop', n2, al)) for al in np.linspace(0, 1, 11)]
    print('mix pop +', n2, ' '.join('%.1f:%.3f' % x for x in r))
for code in ['NL32B', 'NL366', 'FR101', 'FR105', 'DE712', 'DE212', 'IE061', 'ITC4C', 'DEA23', 'DE300']:
    n = np.where(ids == code)[0]
    if not len(n): continue
    n = n[0]; idx = np.array([m for m in range(len(ids)) if ids[m][:4] == code[:4]])
    print(code, 'actual %.3f' % (gdp[n] / gdp[idx].sum()), ' '.join('%s %.3f' % (k, P[k][n] / P[k][idx].sum()) for k in ['pop', 'pop^1.5', 'vol', 'vol^1.5', 'nres_v', 'kummu2024']))

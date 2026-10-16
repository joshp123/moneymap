import json, sys, numpy as np, collections
d = json.load(open(sys.argv[1])); gkey = sys.argv[2]; grouplen = int(sys.argv[3]); examples = sys.argv[4].split(',') if len(sys.argv) > 4 else []
ids = np.array(d['ids']); gdp = np.array(d[gkey], dtype=float)
names = [k for k in d if k not in ('ids', gkey)]
P = {k: np.array(d[k], dtype=float) for k in names}
ok = np.isfinite(gdp) & (gdp > 0) & (P['pop'] > 0)
ids, gdp = ids[ok], gdp[ok]; P = {k: v[ok] for k, v in P.items()}
g = collections.defaultdict(list)
for n, i in enumerate(ids): g[i[:grouplen]].append(n)
G = [np.array(v) for v in g.values() if len(v) > 1]
def ev(w):
    mis = tot = 0.0; logs = []
    for idx in G:
        a = gdp[idx] / gdp[idx].sum(); p = w[idx] / w[idx].sum()
        mis += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); tot += gdp[idx].sum(); logs += list(np.abs(np.log(np.maximum(p, 1e-12) / a)))
    return mis / tot, float(np.median(logs))
print('units', len(ids), 'groups', len(G))
for k in names: print('  %-14s misallocated %.3f  median|log ratio| %.3f' % ((k,) + ev(P[k])))
def nz(x, idx): return x[idx] / x[idx].sum()
for n2 in [k for k in names if k != 'pop' and not k.startswith('kummu')]:
    best = min(((al, sum(gdp[idx].sum() * 0.5 * np.abs(al * nz(P['pop'], idx) + (1 - al) * nz(P[n2], idx) - gdp[idx] / gdp[idx].sum()).sum() for idx in G) / sum(gdp[idx].sum() for idx in G)) for al in np.linspace(0, 1, 21)), key=lambda x: x[1])
    print('  best mix pop+%s: alpha_pop=%.2f misallocated %.3f' % (n2, best[0], best[1]))
for code in examples:
    n = np.where(ids == code)[0]
    if not len(n): print(code, 'missing'); continue
    n = n[0]; idx = np.array([m for m in range(len(ids)) if ids[m][:grouplen] == code[:grouplen]])
    print('  %s actual share %.3f | ' % (code, gdp[n] / gdp[idx].sum()) + ' '.join('%s %.3f' % (k, P[k][n] / P[k][idx].sum()) for k in names))

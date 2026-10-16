import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/eu_sums.json'))
ids = np.array(d['ids']); gdp = np.array(d['gdp2023_meur'])
P = {k: np.array(d[k]) for k in ['pop', 'nres_v', 'nres_s', 'kummu2024']}
ok = np.isfinite(gdp) & (gdp > 0) & (P['pop'] > 0) & np.array([not i.endswith('ZZZ') for i in ids])
ids, gdp = ids[ok], gdp[ok]; P = {k: v[ok] for k, v in P.items()}
def groups(level):
    g = collections.defaultdict(list)
    for n, i in enumerate(ids): g[i[:level]].append(n)
    return [np.array(v) for v in g.values() if len(v) > 1]
def evaluate(level, proxy_share_fn):
    mis = 0.0; tot = 0.0; logs = []
    for idx in groups(level):
        a = gdp[idx] / gdp[idx].sum(); p = proxy_share_fn(idx)
        mis += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); tot += gdp[idx].sum()
        logs += list(np.abs(np.log(np.maximum(p, 1e-9) / a)))
    return mis / tot, float(np.median(logs)), float(np.mean(logs))
def mix(name, alpha):
    def f(idx):
        x = P['pop'][idx] / P['pop'][idx].sum(); y = P[name][idx] / P[name][idx].sum()
        return alpha * x + (1 - alpha) * y
    return f
def share(name):
    return lambda idx: P[name][idx] / P[name][idx].sum()
for level, label in [(4, 'NUTS3 within NUTS2'), (2, 'NUTS3 within country')]:
    print('==', label, 'groups', len(groups(level)))
    print('  kummu   misallocated %.3f  median|log| %.3f  mean|log| %.3f' % evaluate(level, share('kummu2024')))
    for name in ['nres_v', 'nres_s']:
        best = None
        for alpha in np.linspace(0, 1, 21):
            r = evaluate(level, mix(name, alpha))
            if alpha in (0, 0.5, 1) or abs(alpha - 0.3) < 1e-9 or abs(alpha-0.2)<1e-9 or abs(alpha-0.4)<1e-9: print('  %s alpha_pop=%.2f misallocated %.3f median|log| %.3f mean|log| %.3f' % ((name, alpha) + r))
            if best is None or r[0] < best[1][0]: best = (alpha, r)
        print('  BEST %s alpha_pop=%.2f misallocated %.3f median|log| %.3f' % (name, best[0], best[1][0], best[1][1]))
# held-out: fit alpha on half the countries, test on the other half
countries = sorted(set(i[:2] for i in ids))
rng = np.random.default_rng(0)
res = []
for rep in range(20):
    perm = rng.permutation(countries); A = set(perm[::2]); B = set(perm[1::2])
    def ev(level, f, cset):
        mis = tot = 0.0
        for idx in groups(level):
            if ids[idx[0]][:2] not in cset: continue
            a = gdp[idx] / gdp[idx].sum(); p = f(idx); mis += gdp[idx].sum() * 0.5 * np.abs(p - a).sum(); tot += gdp[idx].sum()
        return mis / tot
    alphas = np.linspace(0, 1, 21)
    fitA = alphas[np.argmin([ev(4, mix('nres_v', al), A) for al in alphas])]
    res.append((fitA, ev(4, mix('nres_v', fitA), B), ev(4, share('pop'), B), ev(4, share('kummu2024'), B)))
r = np.array(res)
print('held-out (fit on half the countries, test on other half, 20 splits): alpha mean %.2f range %.2f-%.2f; test misallocated mix %.3f vs pop-only %.3f vs kummu %.3f' % (r[:,0].mean(), r[:,0].min(), r[:,0].max(), r[:,1].mean(), r[:,2].mean(), r[:,3].mean()))
# examples
alpha = 0.3
for code in ['NL32B', 'NL366', 'NL32A', 'NL363', 'FR101', 'FR105', 'FR106', 'DE712', 'DE212', 'DE21H', 'DE600', 'BE100', 'IE061', 'ITC4C', 'ES300']:
    n = np.where(ids == code)[0]
    if not len(n): print(code, 'missing'); continue
    n = n[0]; idx = [m for m in range(len(ids)) if ids[m][:4] == code[:4]]
    a = gdp[n] / gdp[idx].sum()
    sp = P['pop'][n] / P['pop'][idx].sum(); sv = P['nres_v'][n] / P['nres_v'][idx].sum(); sk = P['kummu2024'][n] / P['kummu2024'][idx].sum()
    print('%s share of its NUTS2 GDP: actual %.3f | pop %.3f | nres_v %.3f | mix(0.3 pop) %.3f | kummu %.3f' % (code, a, sp, sv, alpha * sp + (1 - alpha) * sv, sk))

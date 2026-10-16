import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/uk_sums.json'))
agg = collections.defaultdict(lambda: np.zeros(4)); parent = {}
for i, k in enumerate(d['ids']):
    m = d['msoa'][i]; agg[m] += [d['gva2023_mgbp'][i], d['pop'][i], d['nres_v'][i], d['vol'][i]]; parent[m] = d['lad'][i]
groups = collections.defaultdict(list)
for m in agg: groups[parent[m]].append(agg[m])
groups = [np.array(v) for v in groups.values() if len(v) > 1]
lads = list(range(len(groups)))
def mis(al, col=2, sel=None):
    t = s = 0.0
    for gi, g in enumerate(groups):
        if sel is not None and gi not in sel: continue
        a = g[:, 0] / g[:, 0].sum(); p = al * g[:, 1] / g[:, 1].sum() + (1 - al) * g[:, col] / g[:, col].sum()
        t += g[:, 0].sum() * 0.5 * np.abs(p - a).sum(); s += g[:, 0].sum()
    return t / s
print('MSOA within LA, pop+nres_v:', ' '.join('%.1f:%.3f' % (al, mis(al)) for al in np.linspace(0, 1, 11)))
print('MSOA within LA, pop+vol   :', ' '.join('%.1f:%.3f' % (al, mis(al, 3)) for al in np.linspace(0, 1, 11)))
rng = np.random.default_rng(1); alphas = np.linspace(0, 1, 41); out = []
for rep in range(50):
    perm = rng.permutation(len(groups)); A = set(perm[: len(perm) // 2]); B = set(perm[len(perm) // 2:])
    fit = alphas[np.argmin([mis(al, 2, A) for al in alphas])]
    out.append((fit, mis(fit, 2, B), mis(1.0, 2, B)))
o = np.array(out); print('held-out LA halves (50 splits): fitted alpha_pop %.2f (%.2f-%.2f); test misallocated %.3f vs population-only %.3f' % (o[:, 0].mean(), o[:, 0].min(), o[:, 0].max(), o[:, 1].mean(), o[:, 2].mean()))

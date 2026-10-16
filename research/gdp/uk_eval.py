import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/uk_sums.json'))
names = [k for k in d if k not in ('ids', 'gva2023_mgbp', 'lad', 'msoa')]
print('totals: pop %.0f landscan %.0f gva %.0f' % (sum(d['pop']), sum(d.get('landscan2022', [0])), sum(d['gva2023_mgbp'])))
def aggregate(keyname):
    agg = collections.defaultdict(lambda: collections.defaultdict(float)); parent = {}
    for i, k in enumerate(d['ids']):
        key = d[keyname][i] if keyname else k
        agg[key]['gva'] += d['gva2023_mgbp'][i]
        for n in names: agg[key][n] += d[n][i]
        parent[key] = d['lad'][i]
    return agg, parent
def evaluate(agg, groupof, label, examples=()):
    groups = collections.defaultdict(list)
    for k in agg: groups[groupof(k)].append(k)
    groups = {g: v for g, v in groups.items() if len(v) > 1}
    print('==', label, 'units', sum(len(v) for v in groups.values()), 'groups', len(groups))
    res = {}
    for n in names + ['mix']:
        mis = tot = 0.0; logs = []
        for g, ks in groups.items():
            a = np.array([agg[k]['gva'] for k in ks]); 
            if n == 'mix':
                p1 = np.array([agg[k]['pop'] for k in ks]); p2 = np.array([agg[k]['nres_v'] for k in ks])
                p = 0.5 * p1 / p1.sum() + 0.5 * p2 / max(p2.sum(), 1e-9)
            else:
                p = np.array([agg[k][n] for k in ks]); p = p / max(p.sum(), 1e-12)
            A = a.sum(); a = a / A
            mis += A * 0.5 * np.abs(p - a).sum(); tot += A
            logs += list(np.abs(np.log(np.maximum(p, 1e-9) / np.maximum(a, 1e-9))))
        res[n] = mis / tot
        print('  %-14s misallocated %.3f  median|log ratio| %.3f' % (n if n != 'mix' else '0.5pop+0.5nres', mis / tot, np.median(logs)))
    for ex in examples:
        for g, ks in groups.items():
            if ex in ks:
                A = sum(agg[k]['gva'] for k in ks)
                print('  %s actual %.3f | ' % (ex, agg[ex]['gva'] / A) + ' '.join('%s %.3f' % (n, agg[ex][n] / sum(agg[k][n] for k in ks)) for n in names))
msoa, parent = aggregate('msoa')
evaluate(msoa, lambda k: parent[k], 'MSOA within local authority', ['Tower Hamlets 033', 'Hillingdon 031', 'Westminster 018', 'Manchester 054', 'Leeds 111'])
lad, _ = aggregate('lad')
evaluate(lad, lambda k: 'London' if k.startswith('E09') else 'rest', 'Local authority within London (and within rest of E&W)', ['E09000001', 'E09000033', 'E09000030', 'E09000017', 'E09000007'])
lsoa, parent2 = aggregate(None)
evaluate(lsoa, lambda k: parent2[k], 'LSOA within local authority')

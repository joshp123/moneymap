import json, numpy as np, collections
d = json.load(open('/tmp/moneymap-research/uk_sums.json'))
agg = collections.defaultdict(lambda: np.zeros(4)); parent = {}
for i in range(len(d['ids'])):
    m = d['msoa'][i]; agg[m] += [d['gva2023_mgbp'][i], d['pop'][i], d['nres_vxh'][i], d['kummu2024'][i]]; parent[m] = d['lad'][i]
kids = collections.defaultdict(list)
for m in agg: kids[parent[m]].append(m)
for m in ['Tower Hamlets 033', 'Hillingdon 031', 'Westminster 018', 'Manchester 054', 'Leeds 111', 'Birmingham 138']:
    if m not in agg: print(m, 'missing'); continue
    T = sum(agg[k] for k in kids[parent[m]]); x = agg[m] / T
    print('%-18s share of its local authority GVA: actual %.3f | population %.3f | proposed (0.5 pop + 0.5 NRES vol x height) %.3f' % (m, x[0], x[1], 0.5 * x[1] + 0.5 * x[2]))

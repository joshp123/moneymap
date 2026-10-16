import json, numpy as np, collections
us = json.load(open('/tmp/moneymap-research/us_sums.json')); ids = us['ids']
g = np.array(us['gdp2024_kusd'], float); k = np.array(us['kummu2024']); p = np.array(us['pop']); ok = np.isfinite(g)
i = ids.index('36061')
print('Manhattan share of CONUS: BEA %.4f | Kummu %.4f | population %.4f' % (g[i] / g[ok].sum(), k[i] / k[ok].sum(), p[i] / p[ok].sum()))
uk = json.load(open('/tmp/moneymap-research/uk_sums.json'))
lad = collections.defaultdict(lambda: np.zeros(3))
for j in range(len(uk['ids'])): lad[uk['lad'][j]] += [uk['gva2023_mgbp'][j], uk['kummu2024'][j], uk['pop'][j]]
T = sum(lad.values())
for code, name in [('E09000001', 'City of London'), ('E09000033', 'Westminster'), ('E09000030', 'Tower Hamlets'), ('E06000060', 'x')]:
    if code in lad: print('%s share of England+Wales: ONS GVA %.4f | Kummu %.4f | population %.4f' % (name, lad[code][0] / T[0], lad[code][1] / T[1], lad[code][2] / T[2]))
eu = json.load(open('/tmp/moneymap-research/eu_sums.json')); e = eu['ids']
G = np.array(eu['gdp2023_meur'], float); K = np.array(eu['kummu2024']); Pp = np.array(eu['pop'])
nl = [n for n, c in enumerate(e) if c.startswith('NL') and not c.endswith('ZZZ')]
for c in ['NL32B', 'NL366']:
    n = e.index(c); print('%s share of NL: Eurostat %.4f | Kummu %.4f | population %.4f' % (c, G[n] / G[nl].sum(), K[n] / K[nl].sum(), Pp[n] / Pp[nl].sum()))

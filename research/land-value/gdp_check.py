exec(open('/tmp/landvalue/pilot/nsw_grid.py').read().split("print('--- value-weighted")[0].split("best = None")[0])
with rasterio.open(f'{root}/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif') as s:
    g2 = np.nan_to_num(s.read(s.count, window=win).astype('float64')); g2[g2<0]=0
print('gdp grid shape', g2.shape, 'pop grid shape', pop.shape, 'gdp>0 cells', (g2>0).sum(), 'pop>0 cells', (pop>0).sum())
M = access(g2, 40)/cellarea; Mn = M/np.average(M, weights=g2+1e-12)
print('Mn quantiles over gdp cells', np.quantile(Mn[g2>0], [0.01,0.5,0.99]))
U = by_lga(g2*Mn**0.25); pred=U/U.sum()*LV.sum()
e=np.log(pred/LV); o=np.argsort(e)
for i in list(o[:4])+list(o[-4:]): print(names[i], round(LV[i]/1e9,1), round(pred[i]/1e9,1), region.get(names[i]))
gp = by_lga(g2)/np.maximum(by_lga(pop),1)
o=np.argsort(gp); print('GDP per head lowest', [(names[i], round(gp[i])) for i in o[:3]], 'highest', [(names[i], round(gp[i])) for i in o[-3:]])

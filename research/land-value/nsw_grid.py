"""Pilot: does GDP x market-access^gamma (+ farmland per ha) reproduce NSW Valuer General land totals by LGA?"""
import json, math, sys, re, csv, collections
import numpy as np, rasterio
from rasterio.windows import from_bounds
from rasterio.features import rasterize
root, nsw = sys.argv[1], sys.argv[2]
west, south, east, north = 139.0, -38.5, 155.0, -27.0
with rasterio.open(f'{root}/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif') as s:
    win = from_bounds(west, south, east, north, s.transform).round_offsets().round_lengths()
    gdp = s.read(s.count, window=win).astype('float64'); tr = s.window_transform(win)
    print('band', s.descriptions[s.count-1])
gdp = np.nan_to_num(gdp, nan=0.0); gdp[gdp < 0] = 0
pz = f'zip+file://{root}/data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip!GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif'
with rasterio.open(pz) as s:
    w2 = from_bounds(west, south, east, north, s.transform).round_offsets().round_lengths()
    pop = s.read(1, window=w2).astype('float64')
pop[pop < 0] = 0
h, w = gdp.shape; pop = pop[:h, :w]
lat0 = -33.0; cy = 0.926; cx = 0.926*math.cos(math.radians(lat0))  # km per cell
cellarea = cx*cy
# LGA raster
g = json.load(open(f'{nsw}/lga_geom.json'))
shapes = []; codes = {}
for k, f in enumerate([f for f in g['features'] if 'geometry' in f], start=1):
    rings = f['geometry']['rings']
    shapes.append(({'type': 'Polygon', 'coordinates': rings}, k)); codes[k] = (f['attributes']['lga_code_2021'], f['attributes']['lga_name_2021'])
lga = rasterize(shapes, out_shape=(h, w), transform=tr, fill=0, dtype='int32')
def access(field, tau_km):
    # exponential-decay market access via FFT convolution
    ky = np.fft.fftfreq(h); kx = np.fft.fftfreq(w)
    yy = np.minimum(np.arange(h), h-np.arange(h))*cy; xx = np.minimum(np.arange(w), w-np.arange(w))*cx
    d = np.sqrt(yy[:, None]**2 + xx[None, :]**2)
    k = np.exp(-d/tau_km); k /= k.sum()
    return np.maximum(np.real(np.fft.ifft2(np.fft.fft2(field)*np.fft.fft2(k))), 1e-9)
# Valuer General totals
sys.path.insert(0, '/nonexistent')
md = open(f'{nsw}/report2024.md').read().splitlines()
lv = {}
for i, l in enumerate(md):
    m = re.match(r'\|\s*([A-Z][A-Z \-]+?)\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|', l)
    if m: lv[m.group(1).strip()] = float(m.group(3).replace(',', ''))
    m2 = re.match(r'\|\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|', l)
    if m2: lv[md[i+1].strip()] = float(m2.group(2).replace(',', ''))
def norm(s):
    s = s.upper(); s = re.sub(r'\(.*?\)', '', s)
    for t in ['CITY OF ', ' COUNCIL', ' SHIRE', ' REGIONAL']: s = s.replace(t, '')
    return re.sub(r'[^A-Z]', '', s)
byname = {norm(n): k for k, (c, n) in codes.items()}
idx = {}
for n in lv:
    k = byname.get(norm(n)) or next((v for kk, v in byname.items() if kk.startswith(norm(n)) or norm(n).startswith(kk)), None)
    if k: idx[n] = k
region = {}
cur=None
for l in md:
    if l.startswith('Region: City of Sydney'): cur='city'
    elif l.startswith('Region: Greater Sydney'): cur='sydney'
    elif l.startswith('Region: Coastal NSW'): cur='coastal'
    elif l.startswith('Regional: Regional NSW'): cur='regional'
    m = re.match(r'\|\s*([A-Z][A-Z \-]+?)\s*\|\s*([\d,]+)\s*\|\s*\$', l)
    if m and cur: region[m.group(1).strip()] = cur
    if re.match(r'\|\s*\|\s*([\d,]+)\s*\|\s*\$', l) and cur: pass
for i,l in enumerate(md):
    if re.match(r'\|\s*\|\s*([\d,]+)\s*\|\s*\$', l):
        nm=md[i+1].strip(); region[nm] = {'RYDE':'sydney','SHELLHARBOUR':'coastal','COONAMBLE':'regional'}.get(nm,'regional')
names = sorted(idx); K = np.array([idx[n] for n in names]); LV = np.array([lv[n] for n in names])
print('matched LGAs', len(names), 'of', len(lv)); print('urban+coastal LGAs', None)
maxk = lga.max()+1
def by_lga(field): return np.bincount(lga.ravel(), weights=field.ravel(), minlength=maxk)[K]
area = by_lga(np.full((h, w), cellarea)); P = by_lga(pop); Y = by_lga(gdp)
URB = np.array([region.get(n)!='regional' for n in names])
def score(pred):
    # urban+coastal LGAs only; scale-free log error
    e = np.log(LV[URB]) - np.log(pred[URB]); e -= e.mean(); return np.sqrt((e**2).mean())
print(f'baseline population share: log-RMSE {score(P):.3f}; GDP share: {score(Y):.3f}; area share: {score(area):.3f}')
best = None
for tau in [3, 5, 10, 20, 40]:
    M = access(gdp, tau)/cellarea  # GDP density within ~tau km (per km2)
    Mn = M/np.average(M, weights=gdp+1e-12)
    for gam in [0, 0.25, 0.5, 0.75, 1.0]:
        U = by_lga(gdp*Mn**gam)
        # add farmland term p*area on cells, fit share s of total that is rural (grid search)
        for farm_share in [0, 0.05, 0.1, 0.15, 0.2]:
            pred = (1-farm_share)*U/U.sum() + farm_share*area/area.sum()
            sc = score(pred)
            if best is None or sc < best[0]: best = (sc, tau, gam, farm_share)
        if farm_share == 0.2 or True:
            pass
    print(f'tau {tau:>2} km: no-farm log-RMSE by gamma ' + ' '.join(f'{g}:{score(by_lga(gdp*Mn**g)):.3f}' for g in [0, 0.25, 0.5, 0.75, 1.0]))
print('best GDP-weighted (log-RMSE, tau km, gamma, farmland share):', best)
bestp=None
for tau in [3, 5, 10, 20, 40]:
    M = access(pop, tau)/cellarea; Mn = M/np.average(M, weights=pop+1e-12)
    row=[]
    for gam in [0, 0.25, 0.5, 0.75, 1.0]:
        U = by_lga(pop*Mn**gam); row.append(score(U))
        for fs in [0, 0.05, 0.1, 0.15, 0.2]:
            sc = score((1-fs)*U/U.sum() + fs*area/area.sum())
            if bestp is None or sc < bestp[0]: bestp=(sc,tau,gam,fs)
    print(f'POP tau {tau:>2} km: no-farm log-RMSE by gamma ' + ' '.join(f'{g}:{r:.3f}' for g,r in zip([0,0.25,0.5,0.75,1.0],row)))
print('best pop-weighted:', bestp)
best = bestp; gdp = pop
sc, tau, gam, fs = best
M = access(gdp, tau)/cellarea; Mn = M/np.average(M, weights=gdp+1e-12)
U = by_lga(gdp*Mn**gam); pred = ((1-fs)*U/U.sum() + fs*area/area.sum())*LV.sum()
for n in ['SYDNEY CITY', 'WOOLLAHRA', 'NORTH SYDNEY', 'BLACKTOWN', 'PENRITH', 'NEWCASTLE', 'WOLLONGONG', 'DUBBO REGIONAL', 'BROKEN HILL', 'MOREE PLAINS', 'BOURKE']:
    if n in idx:
        i = names.index(n); print(f'{n:15s} actual A${LV[i]/1e9:7.1f}bn  model {pred[i]/1e9:7.1f}  pop-share {P[i]/P.sum()*LV.sum()/1e9:7.1f}')
greater = [i for i, n in enumerate(names)]

print('--- value-weighted misallocation (share of total value in the wrong LGA) ---')
regions = np.array([region.get(n, 'regional') for n in names])
def misalloc(pred):
    pred = pred/pred.sum()*LV.sum()
    lga_err = np.abs(pred-LV).sum()/2/LV.sum()
    reg_err = sum(abs(pred[regions==r].sum()-LV[regions==r].sum()) for r in set(regions))/2/LV.sum()
    return lga_err, reg_err
res = {}
res['population share'] = by_lga(pop)
with rasterio.open(f'{root}/data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif') as s:
    g2 = np.nan_to_num(s.read(s.count, window=win).astype('float64')); g2[g2<0]=0
res['GDP share'] = by_lga(g2)
for tau in [20, 40, 80]:
    M = access(pop, tau)/cellarea; Mn = M/np.average(M, weights=pop+1e-12)
    for gam in [0.15, 0.25, 0.35]:
        U = by_lga(pop*Mn**gam)
        for fs in [0.0, 0.05, 0.10]:
            res[f'pop x access^{gam} (tau {tau} km) + farmland {fs:.0%}'] = (1-fs)*U/U.sum() + fs*area/area.sum()
rows = sorted(((misalloc(v), k, score(v)) for k, v in res.items()), key=lambda t: t[0][0])
for (le, re_), k, sc in rows[:6] + [r for r in rows if r[1] in ('population share', 'GDP share')]:
    print(f'{k:55s} LGA misallocation {le:.1%}  region misallocation {re_:.1%}  urban log-RMSE {sc:.3f}')

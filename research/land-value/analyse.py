import json,csv,collections,math,sys
base=sys.argv[1]
def wb(f):
    g=collections.defaultdict(dict)
    for r in json.load(open(f"{base}/{f}"))[1]:
        if r['value'] is not None: g[r['countryiso3code']][r['date']]=r['value']
    return g
lcu=wb('gdp_lcu.json'); usd=wb('gdp_usd.json'); pc=wb('wb_NY.GDP.PCAP.PP.KD.json'); big=wb('wb_EN.URB.MCTY.TL.ZS.json'); den=wb('wb_EN.POP.DNST.json'); urb=wb('wb_SP.URB.TOTL.IN.ZS.json')
def latest(d,y=None):
    if not d: return None
    if y and y in d: return d[y]
    return d[max(d)]
rows=list(csv.DictReader(open(f"{base}/land_all.csv")))
v=collections.defaultdict(dict)
for r in rows:
    if r['OBS_VALUE'] and r['INSTR_ASSET']=='N211N' and float(r['OBS_VALUE'])>0:
        v[(r['REF_AREA'],r['SECTOR'])][r['TIME_PERIOD']]=float(r['OBS_VALUE'])*10**int(r['UNIT_MULT'])
full={}; hh={}
for (a,s),d in v.items():
    yrs=[y for y in d if y in lcu.get(a,{})]
    if not yrs: continue
    y=max(yrs)
    if s=='S1': full[a]=(y,d[y]/lcu[a][y])
    if s=='S1M': hh[a]=(y,d[y]/lcu[a][y])
world=latest(usd['WLD'],'2024')
cov_full=sum(latest(usd[a],'2024') for a in full)
cov_hh=sum(latest(usd[a],'2024') for a in hh if a not in full)
print(f"world GDP 2024 USD {world/1e12:.1f}trn; full-land countries {len(full)} = {cov_full/world:.1%}; household-only {len([a for a in hh if a not in full])} = {cov_hh/world:.1%}")
ratios=[hh[a][1]/full[a][1] for a in full if a in hh and a not in ('MEX',)]
ratios.sort(); print('household share of total land: n',len(ratios),'min',round(ratios[0],2),'median',round(ratios[len(ratios)//2],2),'max',round(ratios[-1],2))
print('cty land/GDP gdppc_ppp pct_in_1m_cities density urban%')
X=[];Y=[]
for a,(y,r) in sorted(full.items(), key=lambda t:-t[1][1]):
    p=latest(pc.get(a)); b=latest(big.get(a)); dn=latest(den.get(a)); u=latest(urb.get(a))
    print(a,y,round(r,2),round(p) if p else None,round(b,1) if b else None,round(dn) if dn else None,round(u) if u else None)
    if a in ('MEX','HRV') or b is None: continue
    X.append((1,math.log(p),b/100,math.log(dn))); Y.append(math.log(r))
# simple OLS via normal equations
def ols(X,Y):
    k=len(X[0]); XtX=[[sum(x[i]*x[j] for x in X) for j in range(k)] for i in range(k)]; XtY=[sum(x[i]*y for x,y in zip(X,Y)) for i in range(k)]
    # gaussian elimination
    M=[row+[XtY[i]] for i,row in enumerate(XtX)]
    for i in range(k):
        piv=max(range(i,k),key=lambda r:abs(M[r][i])); M[i],M[piv]=M[piv],M[i]
        for r in range(k):
            if r!=i:
                f=M[r][i]/M[i][i]; M[r]=[a-f*b for a,b in zip(M[r],M[i])]
    beta=[M[i][k]/M[i][i] for i in range(k)]
    res=[y-sum(b*x for b,x in zip(beta,xx)) for xx,y in zip(X,Y)]
    return beta,res
import statistics as st
print('n',len(Y),'sd log ratio',round(st.pstdev(Y),3))
for cols,name in [((0,),'const'),((0,1),'gdppc'),((0,2),'big-city share'),((0,3),'density'),((0,1,2),'gdppc+big'),((0,1,2,3),'all')]:
    Xs=[[x[c] for c in cols] for x in X]
    beta,res=ols(Xs,Y)
    # leave-one-out
    loo=[]
    for i in range(len(Y)):
        b,_=ols(Xs[:i]+Xs[i+1:],Y[:i]+Y[i+1:]); loo.append(Y[i]-sum(bb*xx for bb,xx in zip(b,Xs[i])))
    print(f"{name:15s} beta={[round(b,2) for b in beta]} in-sample sd={st.pstdev(res):.3f} LOO rmse={math.sqrt(sum(e*e for e in loo)/len(loo)):.3f} (factor {math.exp(math.sqrt(sum(e*e for e in loo)/len(loo))):.2f})")

# ---- world total (inference) ----
Xs=[[x[0],x[1],x[2]] for x in X]; beta,res=ols(Xs,Y)
import statistics as st
tot={'official':0,'household_scaled':0,'modelled':0}; n_mod=0; missing=0
hh_share=0.63
countries=[c for c in usd if len(c)==3 and c in pc and latest(usd[c],'2024')]
# World Bank aggregates have iso3 codes too; drop known aggregates by requiring big-city share or density and a 2-letter id? use density + not aggregate list
aggregates=set(['WLD','HIC','LMC','LMY','MIC','UMC','LIC','EAS','ECS','LCN','MEA','NAC','SAS','SSF','ARB','CEB','EAP','EAR','ECA','EMU','EUU','FCS','HPC','IBD','IBT','IDA','IDB','IDX','LAC','LDC','LTE','MNA','OED','OSS','PRE','PSS','PST','SSA','SSD','SST','TEA','TEC','TLA','TMN','TSA','TSS','AFE','AFW','CSS','INX'])
chn=None
for c in countries:
    if c in aggregates: continue
    g=latest(usd[c],'2024')
    if c in full: tot['official']+=full[c][1]*g
    elif c in hh: tot['household_scaled']+=hh[c][1]/hh_share*g
    else:
        p=latest(pc.get(c)); b=latest(big.get(c)) or 0
        if not p: missing+=g; continue
        r=math.exp(beta[0]+beta[1]*math.log(p)+beta[2]*b/100); r=min(max(r,0.3),5)
        tot['modelled']+=r*g; n_mod+=1
        if c=='CHN': chn=(r,g)
T=sum(tot.values())
print({k:round(v/1e12,1) for k,v in tot.items()}, 'total USD trn', round(T/1e12,1), 'x world GDP', round(T/world,2), 'modelled countries', n_mod, 'GDP without covariates USD trn', round(missing/1e12,2))
print('China modelled land/GDP', round(chn[0],2), 'USD trn', round(chn[0]*chn[1]/1e12,1))

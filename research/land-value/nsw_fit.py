import json,csv,re,math,collections,statistics as st,sys
base=sys.argv[1]
d=json.load(open(f'{base}/reg_struct.json'))['data']
names={}
for cl in d['codelists']:
    if cl['id'].startswith('CL_LGA'):
        for c in cl['codes']: names[c['id']]=c['name']
vals=collections.defaultdict(dict)
for f in ['erp_lga.csv','inc_lga.csv']:
    for r in csv.DictReader(open(f'{base}/{f}')):
        if r['OBS_VALUE']:
            k=(r['LGA_2021'],r['MEASURE']); y=r['TIME_PERIOD']
            if y>=vals[k].get('_y','0'): vals[k]['_y']=y; vals[k]['v']=float(r['OBS_VALUE'])
def norm(s):
    s=s.upper(); s=re.sub(r'\(.*?\)','',s); s=s.replace('CITY OF ','').replace(' COUNCIL','').replace(' SHIRE','').replace(' REGIONAL','')
    return re.sub(r'[^A-Z]','',s)
abs_by={}
for code,n in names.items():
    if code.startswith('1') and len(code)==5:
        abs_by[norm(n)]=code
md=open(f'{base}/report2024.md').read()
lv={}
lines=md.splitlines()
pending=None
for i,l in enumerate(lines):
    m=re.match(r'\|\s*([A-Z][A-Z \-]+?)\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|',l)
    if m: lv[m.group(1).strip()]=float(m.group(3).replace(',',''))
    m2=re.match(r'\|\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|',l)
    if m2:
        # name on next non-empty line
        nm=lines[i+1].strip()
        lv[nm]=float(m2.group(2).replace(',',''))
rows=[]
for n,v in lv.items():
    k=norm(n)
    code=abs_by.get(k)
    if not code:
        cands=[c for kk,c in abs_by.items() if kk.startswith(k) or k.startswith(kk)]
        code=cands[0] if len(cands)==1 else None
    if not code: print('unmatched',n); continue
    pop=vals[(code,'ERP_P_20')].get('v'); den=vals[(code,'ERP_21')].get('v'); inc=vals[(code,'INCOME_3')].get('v'); area=vals[(code,'LAND')].get('v')
    if not (pop and den and inc): print('missing',n,pop,den,inc); continue
    rows.append((n,v,pop,den,inc*1e6,area))
print('matched',len(rows),'total LV A$bn',round(sum(r[1] for r in rows)/1e9))
def fit(xs,ys):
    mx,my=st.mean(xs),st.mean(ys); b=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs); a=my-b*mx
    res=[y-a-b*x for x,y in zip(xs,ys)]; return a,b,st.pstdev(res)
y_pc=[math.log(r[1]/r[2]) for r in rows]; y_inc=[math.log(r[1]/r[4]) for r in rows]; ld=[math.log(r[3]) for r in rows]
print('sd log(LV per person)',round(st.pstdev(y_pc),3),' sd log(LV/employee income)',round(st.pstdev(y_inc),3))
a,b,s=fit(ld,y_pc); print(f'log(LV/person) = {a:.2f} + {b:.3f} log(density); resid sd {s:.3f}')
a,b,s=fit(ld,y_inc); print(f'log(LV/income) = {a:.2f} + {b:.3f} log(density); resid sd {s:.3f}')
# urban-only (density > 100/km2)
u=[r for r in rows if r[3]>100]
a,b,s=fit([math.log(r[3]) for r in u],[math.log(r[1]/r[4]) for r in u]); print(f'urban LGAs n={len(u)}: log(LV/income) = {a:.2f} + {b:.3f} log(density); resid sd {s:.3f}; sd before {st.pstdev([math.log(r[1]/r[4]) for r in u]):.3f}')
# share of total LV that a pure income-weighted or pop-weighted split would put in Sydney City etc.
T=sum(r[1] for r in rows); I=sum(r[4] for r in rows); P=sum(r[2] for r in rows)
for n in ['SYDNEY CITY','WOOLLAHRA','BLACKTOWN','NEWCASTLE','DUBBO REGIONAL','MOREE PLAINS','BROKEN HILL']:
    r=[x for x in rows if x[0]==n][0]
    print(f'{n:15s} LV A${r[1]/1e9:6.1f}bn  pop-share-pred {r[2]/P*T/1e9:6.1f}  income-share-pred {r[4]/I*T/1e9:6.1f}  density {r[3]:.0f}')

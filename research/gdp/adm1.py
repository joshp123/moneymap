import csv, sys, collections
rows = list(csv.DictReader(sys.stdin))
print(list(rows[0].keys())[:8], len(rows))
c = collections.Counter(r['iso3'] for r in rows)
multi = {k:v for k,v in c.items() if v>1}
print('countries with >1 adm1 unit in table:', len(multi), 'units:', sum(multi.values()))
for iso in ['USA','GBR','NLD','DEU','FRA','JPN','BRA','CHN','IND','IDN','ITA','ESP','POL','KOR','MEX','RUS','CAN','AUS','TUR','BEL']:
    names = [r.get('Name') or r.get('NAME_1') or '' for r in rows if r['iso3']==iso]
    print(iso, c.get(iso), names[:6])

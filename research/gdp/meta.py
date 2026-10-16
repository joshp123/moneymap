import csv, sys
rows = list(csv.DictReader(sys.stdin))
a2 = [r for r in rows if r['YearRanges2'] not in ('NA','')]
a1 = [r for r in rows if r['YearRanges1'] not in ('NA','') and r['YearRanges2'] in ('NA','')]
a3 = [r for r in rows if r.get('YearRanges3') not in ('NA','', None)]
print('countries', len(rows), 'admin2 reported', len(a2), 'admin1-only reported', len(a1), 'admin3', len(a3))
print('ADMIN2:')
for r in a2: print(' ', r['iso3'], r['COUNTRY'], '|', r['YearRanges2'], '|', r['Source_2'][:80], '|', r['Notes_2'][:120])
print('ADMIN3:')
for r in a3: print(' ', r['iso3'], r['COUNTRY'], '|', r['YearRanges3'], '|', r['Source_3'][:80], '|', r['Notes_3'][:150])
print('ADMIN1 only:', ' '.join(r['iso3'] for r in a1))
for iso in ['USA','GBR','NLD','DEU','FRA','JPN','BRA','CHN','IND','IDN']:
    for r in rows:
        if r['iso3']==iso: print(iso, {k:v[:100] for k,v in r.items() if v not in ('NA','')})

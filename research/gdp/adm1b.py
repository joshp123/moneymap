import csv, sys
rows = list(csv.DictReader(sys.stdin))
for iso, pat in [('USA','New York'),('GBR','London'),('GBR','Westminster'),('GBR','Camden'),('NLD','Amsterdam'),('NLD','Rijnmond'),('NLD','Haarlem'),('USA','Washington')]:
    for r in rows:
        if r['iso3']==iso and pat.lower() in r['Subnat'].lower():
            print(iso, r['GID_nmbr'], r['Subnat'], 'slope', r['slope'], {y:r[y] for y in ['2018','2020','2021','2022','2023','2024']})
print([r['Subnat'] for r in rows if r['iso3']=='USA'][:15])

import zipfile, re, sys, xml.etree.ElementTree as ET
ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
path = sys.argv[1]; pats = [p.lower() for p in sys.argv[2].split('|')]; sheetfilter = sys.argv[3] if len(sys.argv)>3 else ''
z = zipfile.ZipFile(path)
ss = []
if 'xl/sharedStrings.xml' in z.namelist():
    for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
        ss.append(''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])))
wb = ET.fromstring(z.read('xl/workbook.xml'))
rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
rmap = {r.get('Id'): r.get('Target') for r in rels}
def colnum(ref):
    c = re.match(r'[A-Z]+', ref).group(0); n=0
    for ch in c: n = n*26 + ord(ch)-64
    return n
for s in wb.find('m:sheets', ns):
    name = s.get('name'); tgt = rmap[s.get('{%s}id' % ns['r'])]
    tgt = tgt.lstrip('/'); tgt = tgt if tgt.startswith('xl/') else 'xl/' + tgt
    if sheetfilter and not re.search(sheetfilter, name): 
        print('SHEET', name); continue
    root = ET.fromstring(z.read(tgt))
    rows = []
    for row in root.iter('{%s}row' % ns['m']):
        vals = {}
        for c in row.findall('m:c', ns):
            v = c.find('m:v', ns); t = c.get('t')
            if v is None:
                isel = c.find('m:is', ns)
                val = ''.join(x.text or '' for x in isel.iter('{%s}t' % ns['m'])) if isel is not None else None
            else:
                val = ss[int(v.text)] if t == 's' else v.text
            vals[colnum(c.get('r'))] = val
        rows.append([vals.get(i) for i in range(1, max(vals)+1)] if vals else [])
    print('=== SHEET', name, len(rows), 'rows')
    for r in rows[:int(sys.argv[4]) if len(sys.argv)>4 else 6]: print('  H', r[:8], '...', r[-3:] if len(r)>8 else '')
    for r in rows:
        if any(isinstance(x,str) and any(p in x.lower() for p in pats) for x in r[:4]):
            print('  ROW', r[:4], '...', r[-4:])

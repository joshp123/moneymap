import zipfile, re, sys, json, xml.etree.ElementTree as ET
ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
z = zipfile.ZipFile(sys.argv[1])
ss = [''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns)]
wb = ET.fromstring(z.read('xl/workbook.xml')); rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
def colnum(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0): n = n * 26 + ord(ch) - 64
    return n
out = {}
for s in wb.find('m:sheets', ns):
    if s.get('name') not in ('Table 1', 'Table 2'): continue
    tgt = rels[s.get('{%s}id' % ns['r'])].lstrip('/'); tgt = tgt if tgt.startswith('xl/') else 'xl/' + tgt
    header = None
    for row in ET.fromstring(z.read(tgt)).iter('{%s}row' % ns['m']):
        vals = {}
        for c in row.findall('m:c', ns):
            v = c.find('m:v', ns)
            if v is not None: vals[colnum(c.get('r'))] = ss[int(v.text)] if c.get('t') == 's' else v.text
        if not vals: continue
        r = [vals.get(i) for i in range(1, max(vals) + 1)]
        if r[0] == 'LSOA code': header = r; continue
        if header and r[0] and re.match(r'[EW]01', r[0]):
            y = header.index('2023')
            out[r[0]] = {'gva': float(r[y]), 'lad': r[2], 'msoa': r[1][:-1].strip()}
json.dump(out, open('/tmp/moneymap-research/uk_lsoa_gva.json', 'w'))
print(len(out), 'LSOAs; total GVA 2023 £m', round(sum(v['gva'] for v in out.values())))

import struct
def read_dbf(path):
    b = open(path, 'rb').read()
    n, hl, rl = struct.unpack('<IHH', b[4:12])
    fields = []; off = 32
    while b[off] != 0x0D:
        name = b[off:off + 11].split(b'\0')[0].decode(); ln = b[off + 16]; fields.append((name, ln)); off += 32
    recs = []
    for i in range(n):
        r = b[hl + i * rl + 1: hl + (i + 1) * rl]; d = {}; p = 0
        for name, ln in fields: d[name] = r[p:p + ln].decode('latin-1').strip(); p += ln
        recs.append(d)
    return recs
def read_shp(path):
    b = open(path, 'rb').read(); off = 100; geoms = []
    while off < len(b):
        clen = struct.unpack('>I', b[off + 4:off + 8])[0] * 2; rec = b[off + 8: off + 8 + clen]; off += 8 + clen
        st = struct.unpack('<i', rec[:4])[0]
        if st == 0: geoms.append(None); continue
        nparts, npts = struct.unpack('<ii', rec[36:44])
        parts = list(struct.unpack('<%di' % nparts, rec[44:44 + 4 * nparts])) + [npts]
        pts = struct.unpack('<%dd' % (2 * npts), rec[44 + 4 * nparts: 44 + 4 * nparts + 16 * npts])
        polys = []
        for a, z in zip(parts[:-1], parts[1:]):
            ring = [(pts[2 * k], pts[2 * k + 1]) for k in range(a, z)]
            area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))
            if area <= 0 or not polys: polys.append([ring])   # clockwise = outer ring
            else: polys[-1].append(ring)                      # counter-clockwise = hole
        geoms.append({'type': 'MultiPolygon', 'coordinates': polys})
    return geoms

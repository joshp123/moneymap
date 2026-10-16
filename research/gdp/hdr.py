import sys, rasterio
from rasterio.env import Env
with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".zip,.tif"):
    for p in sys.argv[1:]:
        with rasterio.open(p) as d:
            print(p.split('/')[-1], d.width, d.height, d.crs, repr(d.transform.c), repr(d.transform.f), repr(d.transform.a), repr(d.transform.e), d.dtypes, d.nodata, d.count, d.tags())

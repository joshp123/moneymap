"""Written by AI on 2026.10.16 by model claude fable 5.1.

Grid the NRW standard land values (Bodenrichtwerte, 1 January 2026) onto the project's 30 arc-second grid.

Zones overlap, so one value is chosen per 3 arc-second sub-pixel (about 90 m) with a land-cover rule:
  built-up zone (map colour classes 1, 2, 3, 7, not outer-area plots) > farmland (class 5) > forest (class 4).
Outer-area building-plot zones (class 6 or ERGNUTA=ASB) describe hypothetical plots and are ignored.
Overlapping farmland zones (arable and grassland on the same land) are averaged.

Writes data/experiments/land-value/nrw_official_grid.npz (value in euros per 30 arc-second cell, plus parts).
Usage: devenv shell -- python -I research/land-value/grid_nrw.py
"""
import sys, json, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pyarrow.parquet as pq
import rasterio
from rasterio.enums import MergeAlg
from rasterio.features import rasterize
from rasterio.transform import Affine
from shapely import from_wkb, make_valid
from landgrid import EXPERIMENTS, Region, EARTH_RADIUS_KM, CELL_DEG

NRW_BBOX = (5.85, 50.30, 9.48, 52.55)
FINE = 10   # sub-pixels per cell side


def rasterize_values(shapes, out_shape, transform, average=False):
    if not shapes:
        return np.zeros(out_shape)
    if not average:
        return rasterize(shapes, out_shape=out_shape, transform=transform, fill=0.0, dtype='float64', merge_alg=MergeAlg.replace)
    total = rasterize(shapes, out_shape=out_shape, transform=transform, fill=0.0, dtype='float64', merge_alg=MergeAlg.add)
    count = rasterize([(g, 1.0) for g, _ in shapes], out_shape=out_shape, transform=transform, fill=0.0, dtype='float64', merge_alg=MergeAlg.add)
    return np.divide(total, count, out=np.zeros_like(total), where=count > 0)


def main():
    region = Region(*NRW_BBOX)
    t = region.transform
    fine_transform = Affine(t.a / FINE, t.b, t.c, t.d, t.e / FINE, t.f)
    fine_shape = (region.height * FINE, region.width * FINE)

    table = pq.read_table(EXPERIMENTS / 'raw/nrw/brw_zones.parquet', columns=['FARBE', 'ERGNUTA', 'brw_eur_per_m2', 'geometry']).to_pydict()
    groups = {'inner': [], 'agri': [], 'forest': []}
    for colour, supplementary, value, wkb in zip(table['FARBE'], table['ERGNUTA'], table['brw_eur_per_m2'], table['geometry']):
        geom = from_wkb(wkb)
        if not geom.is_valid:
            geom = make_valid(geom)
        outer_area_plot = colour == '6' or (supplementary and 'ASB' in supplementary)
        if outer_area_plot:
            continue
        if colour in ('1', '2', '3', '7'):
            groups['inner'].append((geom, float(value)))
        elif colour == '5':
            groups['agri'].append((geom, float(value)))
        elif colour == '4':
            groups['forest'].append((geom, float(value)))
    print({k: len(v) for k, v in groups.items()})

    inner = rasterize_values(groups['inner'], fine_shape, fine_transform)
    agri = rasterize_values(groups['agri'], fine_shape, fine_transform, average=True)
    forest = rasterize_values(groups['forest'], fine_shape, fine_transform)
    price = np.where(inner > 0, inner, np.where(agri > 0, agri, forest))
    source = np.where(inner > 0, 1, np.where(agri > 0, 2, np.where(forest > 0, 3, 0)))

    fine_rows = np.arange(fine_shape[0])
    lat = fine_transform.f + (fine_rows + 0.5) * fine_transform.e
    pixel_height_m = EARTH_RADIUS_KM * 1000 * math.radians(CELL_DEG / FINE)
    pixel_area_m2 = (pixel_height_m * pixel_height_m * np.cos(np.radians(lat)))[:, None]

    def aggregate(fine):
        return fine.reshape(region.height, FINE, region.width, FINE).sum(axis=(1, 3))
    value_all = aggregate(price * pixel_area_m2)
    value_inner = aggregate(np.where(source == 1, price, 0) * pixel_area_m2)
    value_agri = aggregate(np.where(source == 2, price, 0) * pixel_area_m2)
    value_forest = aggregate(np.where(source == 3, price, 0) * pixel_area_m2)
    area_inner_km2 = aggregate(np.where(source == 1, pixel_area_m2, 0)) / 1e6
    area_covered_km2 = aggregate(np.where(source > 0, pixel_area_m2, 0)) / 1e6

    totals = {'value_eur_trn': value_all.sum() / 1e12, 'built_up_eur_trn': value_inner.sum() / 1e12,
              'farmland_eur_trn': value_agri.sum() / 1e12, 'forest_eur_trn': value_forest.sum() / 1e12,
              'built_up_area_km2': area_inner_km2.sum(), 'covered_area_km2': area_covered_km2.sum()}
    print(json.dumps(totals, indent=1))
    np.savez_compressed(EXPERIMENTS / 'nrw_official_grid.npz', value=value_all, value_inner=value_inner, value_agri=value_agri,
                        value_forest=value_forest, area_inner_km2=area_inner_km2, bbox=np.array(NRW_BBOX),
                        transform=np.array([t.a, t.b, t.c, t.d, t.e, t.f]))
    with rasterio.open(EXPERIMENTS / 'nrw_official_grid.tif', 'w', driver='GTiff', height=region.height, width=region.width, count=1,
                       dtype='float32', crs='EPSG:4326', transform=t, compress='deflate') as dst:
        dst.write(value_all.astype('float32'), 1)
    json.dump(totals, open(EXPERIMENTS / 'nrw_official_totals.json', 'w'), indent=1)


if __name__ == '__main__':
    main()

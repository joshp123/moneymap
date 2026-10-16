"""Written by AI on 2026.10.16 by model claude opus 5.5.

Smoke test of the land and building split: each US county's land share of
property value in moneymap's layers against the FHFA land share of
single-family home value (Davis, Larson, Oliner and Shui, 2022 cross-section).
FHFA covers single-family homes only, so compare the ordering, not the level.
"""
import csv
import sys
from pathlib import Path

import fiona
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import shape, mapping

ROOT = Path(__file__).resolve().parents[2]
LAND = ROOT / 'data/build/land_value/land_value.tif'
BUILDINGS = ROOT / 'data/build/building_value/building_value.tif'
COUNTIES = ROOT / 'data/raw/research-gdp/county/cb_2024_us_county_500k.shp'
FHFA = ROOT / 'data/experiments/land-value/us/fhfa_county_cross_section_2012_2022.csv'

fhfa = {}
with open(FHFA) as f:
    for row in csv.DictReader(f):
        share = row.get('land_share_of_property_value')
        if share not in (None, '', 'NA'):
            fhfa[row['geoid'][:5]] = (float(share), f"{row['county']}, {row['state']}")

ours = {}
with rasterio.open(LAND) as land, rasterio.open(BUILDINGS) as buildings, fiona.open(COUNTIES) as counties:
    for feature in counties:
        geoid = feature['properties']['GEOID']
        if geoid not in fhfa:
            continue
        geometry = [mapping(shape(feature['geometry']))]
        try:
            land_cells, _ = mask(land, geometry, crop=True, all_touched=False, nodata=0)
            building_cells, _ = mask(buildings, geometry, crop=True, all_touched=False, nodata=0)
        except ValueError:
            continue
        land_total = float(np.nansum(land_cells))
        building_total = float(np.nansum(building_cells))
        if land_total + building_total > 0:
            ours[geoid] = land_total / (land_total + building_total)

common = sorted(set(ours) & set(fhfa))
a = np.array([ours[g] for g in common]); b = np.array([fhfa[g][0] for g in common])
rank = lambda x: np.argsort(np.argsort(x))
print(f'counties compared: {len(common)}')
print(f'Pearson r: {np.corrcoef(a, b)[0, 1]:.3f}; Spearman rank r: {np.corrcoef(rank(a), rank(b))[0, 1]:.3f}')
print(f'median land share: moneymap {np.median(a):.2f}, FHFA {np.median(b):.2f}')
named = ['06075', '36061', '06085', '06037', '17031', '26163', '48201', '04013', '53033', '39035', '42003', '12086', '15003', '25025', '11001', '29510', '47157', '30031', '20015', '38015']
print(f"{'county':38} {'moneymap':>9} {'FHFA':>6}")
for g in named:
    if g in ours and g in fhfa:
        print(f'{fhfa[g][1][:38]:38} {ours[g]:9.2f} {fhfa[g][0]:6.2f}')

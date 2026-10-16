"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Score the production land raster on eight frozen official valuation tests.
Each test scales predictions to the observed total over its valued units. US
counties and tracts use the study's even-state hold-out without refitting.

    devenv shell -- python -m checks.land_value
"""
import argparse
import csv
import json
from pathlib import Path

import fiona
import numpy as np
from rasterio.features import rasterize
from shapely.geometry import shape

from layers.grid import ROOT
from checks.property_split import compare_layer, score_layer

EXPERIMENTS = ROOT / 'data/experiments/land-value'
BUILD = ROOT / 'data/build/land_value'
REPORT = ROOT / 'data/checks/land_value.json'


def read_rows(path):
    with path.open() as source:
        return list(csv.DictReader(source))


def read_units(path, key):
    """Keep polygon parts together under the valuation unit's identifier."""
    units = {}
    with fiona.open(path) as source:
        for feature in source:
            identifier = key(dict(feature.properties))
            if identifier is not None and feature.geometry is not None:
                units.setdefault(identifier, []).append(shape(dict(feature.geometry)))
    return units


def nrw_units():
    bounds = (5.85, 50.30, 9.48, 52.55)
    units = read_units(EXPERIMENTS / 'raw/nrw/dvg/dvg1_gemeinden_4326.geojson', lambda p: str(p['KN']))
    keys = sorted(units)
    official = np.load(EXPERIMENTS / 'nrw_official_grid.npz')
    from affine import Affine
    transform = Affine(*official['transform'])
    labels = rasterize([(geometry, index + 1) for index, key in enumerate(keys) for geometry in units[key]],
                       out_shape=official['value'].shape, transform=transform, fill=0, dtype='int32')
    values = np.bincount(labels.ravel(), weights=official['value'].ravel(), minlength=len(keys) + 1)[1:]
    return 'nrw_municipalities', units, dict(zip(keys, values)), bounds


def japan_units():
    raw = EXPERIMENTS / 'raw/japan'
    rows = read_rows(raw / 'japan_municipality_land_fy2025.csv')
    values = {}
    for row in rows:
        if row['land_category'] == '合計' and row['land_subcategory'] in ('', '合計', '総計', '計'):
            key = row['municipality_code']
            values[key] = values.get(key, 0.0) + float(row['assessed_value_yen'])
    if not values:
        for row in rows:
            if row['land_category'] == '合計' and row['municipality_code'] not in values:
                values[row['municipality_code']] = float(row['assessed_value_yen'])

    def taxing_body(properties):
        code = str(properties['N03_007'])
        return next((candidate for candidate in (code, code[:4] + '0', code[:3] + '00')
                     if candidate in values), None)

    units = read_units(raw / 'mlit_n03_2026/N03-20260101.geojson', taxing_body)
    return 'japan_municipalities', units, values, (122.9, 24.0, 146.1, 45.7)


def us_units():
    raw = EXPERIMENTS / 'us'
    # Alaska, Hawaii and territories were excluded from the research's lower-48 test.
    states = {'01', '04', '05', '06', '08', '09', '10', '11', '12', '13', '16', '17', '18', '19',
              '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33',
              '34', '35', '36', '37', '38', '39', '40', '41', '42', '44', '45', '46', '47', '48',
              '49', '50', '51', '53', '54', '55', '56'}
    land_shares = {row['geoid']: float(row['land_share_of_property_value'])
                   for row in read_rows(raw / 'fhfa_county_cross_section_2012_2022.csv')
                   if row['land_share_of_property_value']}
    values = {row['geoid']: land_shares[row['geoid']] * float(row['aggregate_value_owner_occupied_housing_usd'])
              for row in read_rows(raw / 'acs_2023_5yr_county_housing_value.csv')
              if row['geoid'] in land_shares and row['geoid'][:2] in states
              and row['aggregate_value_owner_occupied_housing_usd']}
    units = read_units(f"zip://{ROOT}/data/raw/research-gdp/county_500k.zip",
                       lambda p: str(p['GEOID']) if str(p['GEOID']) in values else None)
    return 'us_counties_residential_land', units, values, (-125.0, 24.4, -66.9, 49.5)


def denmark_units():
    raw = EXPERIMENTS / 'raw/denmark'
    values = {row['geoboundaries_adm2_shapeID']: float(row['taxable_land_value_dkk'])
              for row in read_rows(raw / 'tidy_denmark_kommune_taxable_land_value.csv')
              if row['year'] == '2025' and row['geoboundaries_adm2_shapeID'] and row['taxable_land_value_dkk']}
    units = read_units(raw / 'geoBoundaries-DNK-ADM2.geojson', lambda p: str(p['shapeID']))
    return 'denmark_municipalities', units, values, (8.0, 54.5, 15.3, 57.8)


LAND_TESTS = ('us_counties', 'us_tracts', 'nyc_districts', 'victoria_councils',
              'bc_municipalities', 'nrw_municipalities', 'japan_municipalities',
              'denmark_municipalities')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, help='Previous production land raster')
    parser.add_argument('--raster', type=Path, default=BUILD / 'land_value.tif')
    parser.add_argument('--report', type=Path, default=REPORT)
    arguments = parser.parse_args()
    results = []
    for name in LAND_TESTS:
        result = (compare_layer(arguments.raster, arguments.before, name) if arguments.before else
                  score_layer(arguments.raster, name))
        results.append(result)
        summary = ({period: result[period]['scores'] for period in ('before', 'after')}
                   if arguments.before else result['scores'])
        print(json.dumps(dict(test=name, **summary)), flush=True)
    periods = ('before', 'after') if arguments.before else ('production',)
    means = {period: float(np.mean([(result[period] if arguments.before else result)['scores']['misallocated_share']
                                   for result in results])) for period in periods}
    report = dict(tests=results, mean_misallocated_share=means,
                  valuation_units='Frozen Fable split study; US even-state hold-out')
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(mean_misallocated_share=means)), flush=True)


if __name__ == '__main__':
    main()

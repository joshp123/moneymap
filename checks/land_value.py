"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Score the built land-value raster against four held-out official valuations.
Each test scales predictions to the observed total over the valued units. The
production result retains its country-wide component shares; a separate local
normalisation reproduces the research test's half-and-half comparison.

    devenv shell -- python -m checks.land_value
"""
import csv
import json

import fiona
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from shapely.geometry import shape

from layers.grid import ROOT
from layers.land_value.allocation import allocate

EXPERIMENTS = ROOT / 'data/experiments/land-value'
BUILD = ROOT / 'data/build/land_value'
REPORT = ROOT / 'data/checks/land_value.json'
FABLE_MIX = '1/2 population x access^0.25 + 1/2 GDP v3'


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


def score(predicted, actual):
    predicted = predicted / predicted.sum() * actual.sum()
    with np.errstate(divide='ignore'):
        log_ratio = np.log(np.where(predicted > 0, predicted, np.nan) / actual)
    return dict(misallocated_share=float(np.abs(predicted - actual).sum() / (2 * actual.sum())),
                median_abs_log_ratio=float(np.nanmedian(np.abs(log_ratio))),
                n_units=len(actual), empty_units=int((predicted == 0).sum()))


def local_mix(population_weight, gdp):
    """Use the production rule, with this test area's components normalised equally."""
    return allocate(population_weight, gdp, np.ones(len(gdp), dtype='int32'),
                    np.array([0.0, 1.0]), np.array([0.0, population_weight.sum()]),
                    np.array([0.0, gdp.sum()])).astype('float64')


def evaluate(label, units, actual_by_code, bounds, land_value, population_weight, gdp):
    keys = [key for key in units if actual_by_code.get(key, 0) > 0]
    actual = np.array([actual_by_code[key] for key in keys])
    window = from_bounds(*bounds, land_value.transform).round_offsets().round_lengths()
    labels = rasterize([(geometry, index + 1) for index, key in enumerate(keys)
                        for geometry in units[key]],
                       out_shape=(int(window.height), int(window.width)),
                       transform=land_value.window_transform(window), fill=0, dtype='int32')

    def sums(source):
        values = source.read(1, window=window, masked=True).filled(0)
        return np.bincount(labels.ravel(), weights=values.ravel(), minlength=len(keys) + 1)[1:]

    built_values = sums(land_value)
    population_values = sums(population_weight)
    gdp_values = sums(gdp)
    fable = json.loads((EXPERIMENTS / f'{label}_scores.json').read_text())
    np.testing.assert_allclose(actual, [fable['per_unit'][key]['actual'] for key in keys], rtol=1e-12, atol=1e-3)
    # The saved research vectors let us change density and GDP separately.
    old_gdp = np.array([fable['per_unit'][key]['GDP v3 (workplace)'] for key in keys])
    density_only = score(local_mix(population_values, old_gdp), actual)
    scores = dict(fable=fable['scores'][FABLE_MIX],
                  production_density_old_gdp_local_mix=density_only,
                  production_local_mix=score(local_mix(population_values, gdp_values), actual),
                  production_layer=score(built_values, actual))
    report = dict(label=label, scores=scores, official_total=float(actual.sum()),
                  predicted_total_usd=float(built_values.sum()),
                  valued_units_without_geometry=[key for key in actual_by_code if key not in units],
                  per_unit={key: dict(actual=float(actual[index]), land_value=float(built_values[index]))
                            for index, key in enumerate(keys)})
    print(json.dumps(dict(label=label, scores=scores), ensure_ascii=False), flush=True)
    return report


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


def main():
    with rasterio.open(BUILD / 'land_value.tif') as land_value, \
            rasterio.open(BUILD / 'population_weight.tif') as population_weight, \
            rasterio.open(ROOT / 'data/build/gdp/gdp.tif') as gdp:
        results = [evaluate(*test(), land_value, population_weight, gdp)
                   for test in (nrw_units, japan_units, us_units, denmark_units)]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(dict(tests=results), indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()

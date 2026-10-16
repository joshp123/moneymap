"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Score building allocation candidates and the built layer against official values.
Each score compares spatial shares: the predicted total over the valued units is
scaled to the official total, without changing land/building component shares.

    devenv shell -- python -m checks.building_value --candidates
    devenv shell -- python -m checks.building_value
"""
import argparse
from contextlib import ExitStack
import csv
import json
import re

import fiona
import numpy as np
import rasterio
from rasterio.features import rasterize

from checks.land_value import EXPERIMENTS, read_rows, read_units, us_units
from layers.building_value import (BUILDING_BUILD_DIRECTORY, SELECTED_WEIGHT, allocate,
                                   weight_components)
from layers.gdp.build import GDP_BUILD_DIRECTORY
from layers.grid import (GHS_POPULATION_ZIP, ROOT, open_zipped_raster,
                         read_window_zero_filled, window_strips)

BUILDING_RASTER = ROOT / 'data/build/building_value/building_value.tif'
LAND_RASTER = ROOT / 'data/build/land_value/land_value.tif'
REPORT = ROOT / 'data/checks/building_value.json'


def normalise_council_name(name):
    name = re.sub(r'\(.*?\)', '', name.upper())
    for token in ('CITY OF ', 'SHIRE OF ', 'RURAL CITY OF ', 'BOROUGH OF ', ' CITY', ' SHIRE', ' RURAL'):
        name = name.replace(token, '')
    return re.sub(r'[^A-Z]', '', name)


def victoria_units():
    raw = EXPERIMENTS / 'raw/australia'
    with (raw / 'vic/2026-outcome-summary.Outcomes-Summary-2026.csv').open() as source:
        rows = list(csv.reader(source))
    group = ''
    columns = {}
    for index, (heading, label) in enumerate(zip(rows[0], rows[1])):
        if heading.strip():
            group = heading.strip().split()[-1]
        if label == 'Total':
            columns[group] = index
    boundary_path = raw / 'lga_vic.geojson'
    names = {}
    with fiona.open(boundary_path) as source:
        for feature in source:
            properties = dict(feature.properties)
            names[normalise_council_name(properties['lga_name_2021'])] = str(properties['lga_code_2021'])
    units = read_units(boundary_path, lambda p: str(p['lga_code_2021']))
    # https://www.merri-bek.vic.gov.au/my-council/about-council/renamingmerri-bek/
    names['MERRIBEK'] = names['MORELAND']
    values = {}
    for row in rows[2:]:
        if not row or not row[0].strip() or row[0].strip().lower().startswith('total'):
            continue
        name = normalise_council_name(row[0])
        code = names.get(name)
        if code is None:
            matches = [code for candidate, code in names.items() if candidate.startswith(name) or name.startswith(candidate)]
            if len(matches) != 1:
                raise ValueError(f'Victoria council has no unique boundary: {row[0]}')
            code = matches[0]
        land = float(row[columns['SV']].replace(',', ''))
        property_value = float(row[columns['CIV']].replace(',', ''))
        values[code] = dict(land_value=land, building_value=property_value - land, property_value=property_value)
    return dict(label='Victoria councils', units=units, values=values,
                bounds=(140.9, -39.3, 150.1, -33.9), official_year=2026,
                comparison='All assessed properties. Buildings are capital improved value minus site value; improvements can include structures beyond the buildings-only national stock.')


def british_columbia_units():
    raw = EXPERIMENTS / 'raw/bc'
    rows = read_rows(raw / 'tidy_bc_municipality_land_improvements_2026.csv')
    values = {row['municipality_boundary_LGL_ADMIN_AREA_ID']:
              dict(land_value=float(row['land_value_cad']), building_value=float(row['improvements_value_cad']),
                   property_value=float(row['total_value_cad']))
              for row in rows if row['municipality_boundary_LGL_ADMIN_AREA_ID'] and row['land_value_cad']}
    units = read_units(raw / 'bc_municipalities_ABMS_MUNICIPALITIES_SP_wgs84.geojson', lambda p: str(p['LGL_ADMIN_AREA_ID']))
    return dict(label='British Columbia municipalities', units=units, values=values,
                bounds=(-139.2, 48.2, -114.0, 60.1), official_year=2026,
                comparison='All-property market assessment at July 2025 values (2026 revised roll). Improvements include buildings and fixtures.')


def us_residential_units():
    _, units, land_values, bounds = us_units()
    rows = read_rows(EXPERIMENTS / 'us/acs_2023_5yr_county_housing_value.csv')
    values = {}
    for row in rows:
        code = row['geoid']
        if code in land_values:
            property_value = float(row['aggregate_value_owner_occupied_housing_usd'])
            land = land_values[code]
            values[code] = dict(land_value=land, building_value=property_value - land, property_value=property_value)
    return dict(label='US counties, owner-occupied residential diagnostic', units=units, values=values,
                bounds=bounds, official_year=2023,
                comparison='Not like-for-like: ACS owner-occupied homes exclude rented housing and commercial buildings. Buildings are inferred using FHFA residential land shares; this is a spatial diagnostic, not validation of all-building values.')


CANDIDATES = ('volume', 'population', 'population_gdp', 'population_gdp_volume')
CANDIDATE_REPORT = ROOT / 'data/checks/building_value_candidates.json'
SELECTION_REASON = (
    'Population has the lowest mean wrong-unit share but misses most of the Manhattan office-core share. '
    'The equal population/GDP/volume mix is adopted under the dense-core exception: it has the lowest '
    'NYC district wrong-unit share and median log error, and the second-lowest overall mean. '
    'It still over-allocates Manhattan core districts 101-106; the diagnostic shares remain in this report.')


def spatial_score(predicted, actual):
    """Compare shares, retaining zero predictions as infinite log errors."""
    predicted = predicted / predicted.sum() * actual.sum()
    with np.errstate(divide='ignore'):
        log_ratio = np.log(predicted / actual)
    return dict(misallocated_share=float(np.abs(predicted - actual).sum() / (2 * actual.sum())),
                median_abs_log_ratio=float(np.median(np.abs(log_ratio))),
                n_units=len(actual), empty_units=int((predicted == 0).sum()))


def evaluate(test, land_value, building_value=None, candidate_inputs=None):
    """Sum every candidate on the same cells and valuation boundaries."""
    metric = test.get('selection_metric', 'building_value')
    units, values = test['units'], test['values']
    keys = [key for key in units if key in values and values[key].get(metric, 0) > 0]
    actual = {component: np.array([values[key][component] for key in keys])
              for component in ('land_value', 'building_value', 'property_value')
              if all(component in values[key] and values[key][component] > 0 for key in keys)}
    shapes = [(geometry, index + 1) for index, key in enumerate(keys) for geometry in units[key]]
    candidates = CANDIDATES if candidate_inputs else ('production',)
    sums = {name: np.zeros(len(keys) + 1) for name in ('land_value', *candidates)}
    for window in window_strips(land_value, test['bounds']):
        labels = rasterize(shapes, out_shape=(int(window.height), int(window.width)),
                           transform=land_value.window_transform(window), fill=0, dtype='int32')
        sums['land_value'] += np.bincount(labels.ravel(),
            weights=read_window_zero_filled(land_value, 1, window).ravel(), minlength=len(keys) + 1)
        for candidate in candidates:
            cells = (candidate_inputs.values(window, candidate) if candidate_inputs else
                     read_window_zero_filled(building_value, 1, window))
            sums[candidate] += np.bincount(labels.ravel(), weights=cells.ravel(), minlength=len(keys) + 1)
    land = sums['land_value'][1:]
    predicted = {candidate: dict(land_value=land, building_value=sums[candidate][1:],
                                property_value=land + sums[candidate][1:]) for candidate in candidates}
    scores = {candidate: {component: spatial_score(prediction[component], actual[component])
                          for component in actual} for candidate, prediction in predicted.items()}
    result = {key: value for key, value in test.items() if key not in ('units', 'values')}
    result.update(n_units=len(keys), selection_metric=metric, scores=scores,
                  official_totals={component: float(value.sum()) for component, value in actual.items()},
                  production_totals_usd={candidate: {component: float(value.sum()) for component, value in prediction.items()}
                                         for candidate, prediction in predicted.items()},
                  valued_units_without_geometry=[key for key in values if key not in units],
                  per_unit={key: dict(actual=values[key],
                                     predicted_usd={candidate: {component: float(value[index])
                                                               for component, value in prediction.items()}
                                                    for candidate, prediction in predicted.items()})
                            for index, key in enumerate(keys)})
    print(json.dumps({key: value for key, value in result.items() if key != 'per_unit'}, ensure_ascii=False), flush=True)
    return result


class CandidateInputs:
    """Read the production components and apply its country-normalised rule."""

    def __init__(self, stack):
        _, self.country_of_unit, self.targets, self.component_sums = weight_components()
        self.ownership = stack.enter_context(rasterio.open(GDP_BUILD_DIRECTORY / 'control-ids.tif'))
        self.sources = dict(
            volume=stack.enter_context(rasterio.open(BUILDING_BUILD_DIRECTORY / 'built_volume.tif')),
            population=stack.enter_context(open_zipped_raster(GHS_POPULATION_ZIP)),
            gdp=stack.enter_context(rasterio.open(GDP_BUILD_DIRECTORY / 'gdp.tif')))
        self.previous_window = None

    def values(self, window, candidate):
        if window != self.previous_window:
            self.labels = self.country_of_unit[self.ownership.read(1, window=window)]
            self.components = {name: source.read(1, window=window, masked=True).filled(0)
                               for name, source in self.sources.items()}
            self.previous_window = window
        return allocate(self.components, self.labels, self.targets, self.component_sums, candidate)


def candidate_circles(land_value, inputs):
    from checks.circles import CIRCLES, cell_distances_km
    results = []
    selected = {'Cologne cathedral', 'Düsseldorf', 'Gelsenkirchen', 'Amsterdam', 'Rotterdam',
                'Midtown and Lower Manhattan', 'Bank', 'Tokyo Marunouchi', 'Sydney'}
    for name, latitude, longitude, radius in CIRCLES:
        if name not in selected:
            continue
        window, distances = cell_distances_km(land_value, latitude, longitude, radius)
        inside = distances <= radius
        land = float(read_window_zero_filled(land_value, 1, window)[inside].sum(dtype='float64'))
        buildings = {candidate: float(inputs.values(window, candidate)[inside].sum(dtype='float64'))
                     for candidate in CANDIDATES}
        result = dict(name=name, latitude=latitude, longitude=longitude, radius_km=radius,
                      land_value=land, building_value=buildings,
                      property_value={candidate: land + value for candidate, value in buildings.items()})
        print(json.dumps(result, ensure_ascii=False), flush=True)
        results.append(result)
    return results


def nyc_core_shares(results):
    """Expose the office core separately from the city-wide error average."""
    test = next(test for test in results if test['label'] == 'New York City community districts')
    groups = {'Manhattan': [str(code) for code in range(101, 113)],
              'Manhattan districts 101-106': [str(code) for code in range(101, 107)]}
    output = {}
    for name, keys in groups.items():
        actual_share = sum(test['per_unit'][key]['actual']['building_value'] for key in keys) / test['official_totals']['building_value']
        predicted_shares = {candidate: sum(test['per_unit'][key]['predicted_usd'][candidate]['building_value']
                                           for key in keys) / test['production_totals_usd'][candidate]['building_value']
                            for candidate in test['scores']}
        output[name] = dict(official_building_share=actual_share,
                            predicted_building_share=predicted_shares,
                            predicted_to_official_share={candidate: value / actual_share
                                                         for candidate, value in predicted_shares.items()})
    return output


def main():
    from sources.building_valuations import nyc_units
    from sources.european_property_values import european_units
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', action='store_true', help='Compare the four fixed within-country rules')
    arguments = parser.parse_args()
    with ExitStack() as stack:
        land_value = stack.enter_context(rasterio.open(LAND_RASTER))
        inputs = CandidateInputs(stack) if arguments.candidates else None
        built = None if inputs else stack.enter_context(rasterio.open(BUILDING_RASTER))
        results = [evaluate(test(), land_value, built, inputs)
                   for test in (victoria_units, british_columbia_units, us_residential_units,
                                nyc_units, european_units)]
        report = dict(tests=results, nyc_core_shares=nyc_core_shares(results))
        if inputs:
            report['mean_misallocated_share'] = {
                candidate: float(np.mean([test['scores'][candidate][test['selection_metric']]['misallocated_share']
                                          for test in results])) for candidate in CANDIDATES}
            report['selected_by_mean'] = min(report['mean_misallocated_share'], key=report['mean_misallocated_share'].get)
            report['selection_decision'] = dict(weight=SELECTED_WEIGHT, reason=SELECTION_REASON)
            report['circles'] = candidate_circles(land_value, inputs)
            print(json.dumps({key: report[key] for key in ('mean_misallocated_share', 'selected_by_mean')}, indent=2), flush=True)
    path = CANDIDATE_REPORT if arguments.candidates else REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()

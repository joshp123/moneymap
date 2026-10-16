"""Written by AI on 2026.10.17 by model gpt-6.1-sol.

Score the production building raster on Fable's frozen held-out valuation units.
US counties and tracts use even-FIPS lower-48 states, as in the experiment.

    devenv shell -- python -m checks.building_value
    devenv shell -- python -m checks.building_value --before path/to/previous.tif
"""
import argparse
import csv
import json
from pathlib import Path
import re

import fiona
import numpy as np

from checks.land_value import EXPERIMENTS, read_rows, read_units
from layers.building_value import BUILDING_BUILD_DIRECTORY
from layers.grid import ROOT

BUILDING_RASTER = BUILDING_BUILD_DIRECTORY / 'building_value.tif'
REPORT = ROOT / 'data/checks/building_value.json'
TESTS = ('us_counties', 'us_tracts', 'nyc_districts', 'victoria_councils', 'bc_municipalities')


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


def main():
    from checks.property_split import compare_layer, score_layer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, help='Previous production building raster for comparison')
    arguments = parser.parse_args()
    results = []
    for test_name in TESTS:
        result = (compare_layer(BUILDING_RASTER, arguments.before, test_name, 'building_value')
                  if arguments.before else score_layer(BUILDING_RASTER, test_name, 'building_value'))
        results.append(result)
        summary = ({version: {key: value for key, value in result[version].items() if key != 'per_unit'}
                    for version in ('before', 'after')} if arguments.before else
                   {key: value for key, value in result.items() if key != 'per_unit'})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    report = dict(weight='0.7 population share + 0.3 GDP share', tests=results)
    for version in ('before', 'after') if arguments.before else ('production',):
        scores = [test[version] if arguments.before else test for test in results]
        report[f'{version}_mean_misallocated_share'] = float(np.mean([score['scores']['misallocated_share'] for score in scores]))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()

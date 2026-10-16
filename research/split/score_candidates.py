"""Written by AI on 2026.10.17 by model claude fable 5.1.

Score the frozen land and building candidates on held-out official valuations.
The candidates and their exponents were fixed after explore_calibration.py,
which saw only US counties, tracts and ZIP codes in odd-FIPS states. Nothing
scored here was used to choose them: US units in even-FIPS states, New York
City, Victoria, British Columbia, North Rhine-Westphalia, Japan, Denmark and
Amsterdam.

Writes data/experiments/split/results.json and results.md.

    devenv shell -- python -m research.split.score_candidates
"""
import json
import math

import numpy as np

from layers.grid import EARTH_RADIUS_KM, GRID_TRANSFORM
from research.split.extract_cells import SPLIT_DIRECTORY
from research.split.rules import Country, load_test, rank, share_score, spatial_score, unit_sums

LAND_CANDIDATES = {
    'L0 current: ½ P·D^0.25 + ½ G': [(.5, 'PDY', .25, 0), (.5, 'G', 0, 0)],
    'L1: ½ P·D^0.5·Y² + ½ G': [(.5, 'PDY', .5, 2), (.5, 'G', 0, 0)],
    'L2: P·D^0.5·Y²': [(1, 'PDY', .5, 2)],
    'L3: P·D^0.5·Y': [(1, 'PDY', .5, 1)],
    'L4: ½ P·D^0.5·Y + ½ G·D^0.5': [(.5, 'PDY', .5, 1), (.5, 'GDY', .5, 0)],
}
BUILDING_CANDIDATES = {
    'B0 current: ⅓ P + ⅓ G + ⅓ V': [(1/3, 'P', 0, 0), (1/3, 'G', 0, 0), (1/3, 'V', 0, 0)],
    'B1: P': [(1, 'P', 0, 0)],
    'B2: 0.7 P + 0.3 G': [(.7, 'P', 0, 0), (.3, 'G', 0, 0)],
    'B3: P·Y^0.5': [(1, 'PDY', 0, .5)],
}
TESTS = ('us_counties', 'us_tracts', 'us_zips', 'nyc_districts', 'victoria_councils', 'bc_municipalities',
         'nrw_municipalities', 'japan_municipalities', 'denmark_municipalities', 'amsterdam_homes')
NAMED_COUNTIES = {'06085': 'Santa Clara (San Jose)', '06075': 'San Francisco', '15003': 'Honolulu*',
                  '29510': 'St Louis city*', '26163': 'Wayne (Detroit)', '36061': 'New York (Manhattan)',
                  '17031': 'Cook (Chicago)', '48201': 'Harris (Houston)', '53033': 'King (Seattle)'}
NAMED_CIRCLES = [('Düsseldorf 10 km', 'DEU', 51.2277, 6.7735, 10), ('Gelsenkirchen 10 km', 'DEU', 51.5177, 7.0857, 10),
                 ('Middlesbrough 10 km', 'GBR', 54.5742, -1.2350, 10), ('Cologne 10 km', 'DEU', 50.9413, 6.9583, 10),
                 ('Munich 10 km', 'DEU', 48.1374, 11.5755, 10), ('London (Bank) 10 km', 'GBR', 51.5133, -0.0886, 10)]


def held_out(test):
    """US units only in even-FIPS lower-48 states; every other test whole."""
    if not test['name'].startswith('us_'):
        return np.ones(len(test['keys']), dtype=bool)
    states = np.array([key[:2] for key in test['keys']])
    return (states.astype(int) % 2 == 0) & ~np.isin(states, ['02', '15', '72'])


def circle_mask(country, latitude, longitude, radius_km):
    cells = np.load(SPLIT_DIRECTORY / f'cells_{country.code}.npz')
    cell_latitude = np.radians(GRID_TRANSFORM.f + (cells['row'] + .5) * GRID_TRANSFORM.e)
    cell_longitude = np.radians(GRID_TRANSFORM.c + (cells['col'] + .5) * GRID_TRANSFORM.a)
    centre_latitude, centre_longitude = math.radians(latitude), math.radians(longitude)
    haversine = (np.sin((cell_latitude - centre_latitude) / 2) ** 2 +
                 math.cos(centre_latitude) * np.cos(cell_latitude) * np.sin((cell_longitude - centre_longitude) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine)) <= radius_km


def main():
    countries = {code: Country(code) for code in ('USA', 'DEU', 'JPN', 'DNK', 'AUS', 'CAN', 'NLD', 'GBR')}
    tests = {name: load_test(name) for name in TESTS}
    masks = {name: held_out(test) for name, test in tests.items()}
    land_sums = {(name, rule): unit_sums(tests[name], countries[tests[name]['country']].mix(terms)) * countries[tests[name]['country']].land_total
                 for name in TESTS for rule, terms in LAND_CANDIDATES.items()}
    building_sums = {(name, rule): unit_sums(tests[name], countries[tests[name]['country']].mix(terms)) * countries[tests[name]['country']].building_total
                     for name in TESTS for rule, terms in BUILDING_CANDIDATES.items()}
    results = dict(land={}, buildings={}, pairs={}, named_counties={}, named_circles={}, nyc_core={},
                   held_out_units={name: int(mask.sum()) for name, mask in masks.items()})
    lines = ['Written by AI on 2026.10.17 by model claude fable 5.1. Held-out scores of the frozen candidates.', '']

    # Land: wrong-area share / median |log ratio| on every test with official land values.
    land_tests = [name for name in TESTS if 'land_value' in tests[name]]
    lines += ['## Land value (wrong-area share / median absolute log ratio)', '',
              '| Land rule | ' + ' | '.join(land_tests) + ' | mean wrong-area |', '|---|' + '---:|' * (len(land_tests) + 1)]
    for rule in LAND_CANDIDATES:
        row = {}
        for name in land_tests:
            mask = masks[name]
            row[name] = spatial_score(land_sums[name, rule][mask], tests[name]['land_value'][mask])
        row['mean_wrong_area'] = float(np.mean([row[name]['wrong_area'] for name in land_tests]))
        results['land'][rule] = row
        lines.append(f'| {rule} | ' + ' | '.join(f"{row[name]['wrong_area']:.1%} / {row[name]['median_abs_log']:.2f}" for name in land_tests)
                     + f" | {row['mean_wrong_area']:.1%} |")

    building_tests = [name for name in TESTS if 'building_value' in tests[name]]
    lines += ['', '## Building value (wrong-area share / median absolute log ratio)', '',
              '| Building rule | ' + ' | '.join(building_tests) + ' | mean wrong-area |', '|---|' + '---:|' * (len(building_tests) + 1)]
    for rule in BUILDING_CANDIDATES:
        row = {}
        for name in building_tests:
            mask = masks[name]
            row[name] = spatial_score(building_sums[name, rule][mask], tests[name]['building_value'][mask])
        row['mean_wrong_area'] = float(np.mean([row[name]['wrong_area'] for name in building_tests]))
        results['buildings'][rule] = row
        lines.append(f'| {rule} | ' + ' | '.join(f"{row[name]['wrong_area']:.1%} / {row[name]['median_abs_log']:.2f}" for name in building_tests)
                     + f" | {row['mean_wrong_area']:.1%} |")

    # Pairs: the land share of property value, ordered against official shares, and property value placement.
    share_tests = [name for name in TESTS if 'fhfa_land_share' in tests[name] or ('land_value' in tests[name] and 'building_value' in tests[name])]
    property_tests = [name for name in TESTS if 'property_value' in tests[name]]
    lines += ['', '## Land share of property value: rank correlation with official shares (Spearman), and property value placement (wrong-area share)', '',
              '| Land rule | Building rule | ' + ' | '.join(f'ρ {name}' for name in share_tests) + ' | mean ρ | ' + ' | '.join(f'property {name}' for name in property_tests) + ' |',
              '|---|---|' + '---:|' * (len(share_tests) + 1 + len(property_tests))]
    for land_rule in LAND_CANDIDATES:
        for building_rule in BUILDING_CANDIDATES:
            row = dict(shares={}, property={})
            for name in share_tests:
                mask = masks[name]
                land, buildings = land_sums[name, land_rule], building_sums[name, building_rule]
                predicted_share = land / (land + buildings)
                official = (tests[name]['fhfa_land_share'] if 'fhfa_land_share' in tests[name]
                            else tests[name]['land_value'] / (tests[name]['land_value'] + tests[name]['building_value']))
                row['shares'][name] = share_score(predicted_share[mask], official[mask])
            for name in property_tests:
                mask = masks[name]
                row['property'][name] = spatial_score((land_sums[name, land_rule] + building_sums[name, building_rule])[mask],
                                                      tests[name]['property_value'][mask])
            row['mean_spearman'] = float(np.mean([row['shares'][name]['spearman'] for name in share_tests]))
            results['pairs'][f'{land_rule} | {building_rule}'] = row
            lines.append(f'| {land_rule} | {building_rule} | ' + ' | '.join(f"{row['shares'][name]['spearman']:.2f}" for name in share_tests)
                         + f" | {row['mean_spearman']:.2f} | " + ' | '.join(f"{row['property'][name]['wrong_area']:.1%}" for name in property_tests) + ' |')

    # Spread of the land share: our 10th-90th percentile against the official one.
    lines += ['', '## Spread of the land share (10th to 90th percentile of units)', '',
              '| Land rule | Building rule | ' + ' | '.join(share_tests) + ' |', '|---|---|' + '---:|' * len(share_tests)]
    official_row = []
    for name in share_tests:
        first = next(iter(results['pairs'].values()))['shares'][name]
        official_row.append(f"{first['official_p10']:.2f}-{first['official_p90']:.2f} (median {first['official_median']:.2f})")
    lines.append('| official | | ' + ' | '.join(official_row) + ' |')
    for key, row in results['pairs'].items():
        land_rule, building_rule = key.split(' | ')
        lines.append(f'| {land_rule} | {building_rule} | ' + ' | '.join(
            f"{row['shares'][name]['predicted_p10']:.2f}-{row['shares'][name]['predicted_p90']:.2f} (median {row['shares'][name]['predicted_median']:.2f})"
            for name in share_tests) + ' |')

    # Named counties: land share of property value for every pair.
    county = tests['us_counties']
    index = {key: position for position, key in enumerate(county['keys'])}
    lines += ['', '## Named US counties: land share of property value (FHFA single-family share in the first column; * = calibration half)', '',
              '| County | FHFA | ' + ' | '.join(f'{land} / {building}' for land in LAND_CANDIDATES for building in BUILDING_CANDIDATES) + ' |',
              '|---|---:|' + '---:|' * (len(LAND_CANDIDATES) * len(BUILDING_CANDIDATES))]
    for code, label in NAMED_COUNTIES.items():
        position = index[code]
        row = dict(fhfa=float(county['fhfa_land_share'][position]), ours={})
        for land_rule in LAND_CANDIDATES:
            for building_rule in BUILDING_CANDIDATES:
                land, buildings = land_sums['us_counties', land_rule][position], building_sums['us_counties', building_rule][position]
                row['ours'][f'{land_rule} | {building_rule}'] = float(land / (land + buildings))
        results['named_counties'][label] = row
        lines.append(f"| {label} | {row['fhfa']:.2f} | " + ' | '.join(f'{value:.2f}' for value in row['ours'].values()) + ' |')

    # Named circles in Europe: land share for every pair, plus land and building values for the current and candidate rules.
    lines += ['', '## Named European circles: land share of property value', '',
              '| Circle | ' + ' | '.join(f'{land} / {building}' for land in LAND_CANDIDATES for building in BUILDING_CANDIDATES) + ' |',
              '|---|' + '---:|' * (len(LAND_CANDIDATES) * len(BUILDING_CANDIDATES))]
    for label, code, latitude, longitude, radius in NAMED_CIRCLES:
        country = countries[code]
        inside = circle_mask(country, latitude, longitude, radius)
        land = {rule: float(country.mix(terms)[inside].sum() * country.land_total) for rule, terms in LAND_CANDIDATES.items()}
        buildings = {rule: float(country.mix(terms)[inside].sum() * country.building_total) for rule, terms in BUILDING_CANDIDATES.items()}
        row = dict(land_usd=land, buildings_usd=buildings,
                   share={f'{l} | {b}': land[l] / (land[l] + buildings[b]) for l in land for b in buildings})
        results['named_circles'][label] = row
        lines.append(f'| {label} | ' + ' | '.join(f'{value:.2f}' for value in row['share'].values()) + ' |')

    # New York City: Manhattan and its office core, share of the city's land and buildings.
    nyc = tests['nyc_districts']
    groups = {'Manhattan (101-112)': [str(code) for code in range(101, 113)], 'Manhattan core (101-106)': [str(code) for code in range(101, 107)]}
    lines += ['', '## New York City: share of the city total in Manhattan (official first)', '',
              '| Group | Component | official | ' + ' | '.join(list(LAND_CANDIDATES) + list(BUILDING_CANDIDATES)) + ' |',
              '|---|---|---:|' + '---:|' * (len(LAND_CANDIDATES) + len(BUILDING_CANDIDATES))]
    for group, codes in groups.items():
        positions = [nyc['keys'].index(code) for code in codes]
        for component, sums, candidates in (('land', land_sums, LAND_CANDIDATES), ('buildings', building_sums, BUILDING_CANDIDATES)):
            official_values = nyc['land_value' if component == 'land' else 'building_value']
            official_share = float(official_values[positions].sum() / official_values.sum())
            predicted = {rule: float(sums['nyc_districts', rule][positions].sum() / sums['nyc_districts', rule].sum()) for rule in candidates}
            results['nyc_core'][f'{group} {component}'] = dict(official=official_share, predicted=predicted)
            cells = [f'{predicted[rule]:.1%}' if rule in candidates else '' for rule in list(LAND_CANDIDATES) + list(BUILDING_CANDIDATES)]
            lines.append(f'| {group} | {component} | {official_share:.1%} | ' + ' | '.join(cells) + ' |')

    (SPLIT_DIRECTORY / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    (SPLIT_DIRECTORY / 'results.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()

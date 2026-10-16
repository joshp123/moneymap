"""Written by AI on 2026.10.17 by model claude fable 5.1.

Calibration only: try land and building rules on the US counties, tracts and
ZIP codes in states with an odd FIPS code. The even states, New York City and
every other country are held out for score_candidates.py and are not read here.

    devenv shell -- python -m research.split.explore_calibration
"""
import numpy as np

from research.split.rules import Country, load_test, share_score, spatial_score, unit_sums


def calibration_half(test):
    states = np.array([key[:2] for key in test['keys']])
    return (states.astype(int) % 2 == 1) & ~np.isin(states, ['02', '15', '72'])


def unit_values(test, country, land_rule, building_rule):
    land = unit_sums(test, country.mix(land_rule)) * country.land_total
    buildings = unit_sums(test, country.mix(building_rule)) * country.building_total
    return land, buildings


def main():
    usa = Country('USA')
    tests = {name: load_test(name) for name in ('us_counties', 'us_tracts', 'us_zips')}
    halves = {name: calibration_half(test) for name, test in tests.items()}
    print({name: int(half.sum()) for name, half in halves.items()}, 'calibration units')

    land_rules = {'½ P·D^0.25 + ½ G (current)': [(.5, 'PDY', .25, 0), (.5, 'G', 0, 0)]}
    for a in (.5, .75, 1.0):
        land_rules[f'½ P·D^{a} + ½ G'] = [(.5, 'PDY', a, 0), (.5, 'G', 0, 0)]
    for a in (.25, .5):
        for b in (1, 2):
            land_rules[f'½ P·D^{a}·Y^{b} + ½ G'] = [(.5, 'PDY', a, b), (.5, 'G', 0, 0)]
    for a in (.5, .75, 1.0):
        for b in (0, 1, 2):
            land_rules[f'P·D^{a}·Y^{b}'] = [(1, 'PDY', a, b)]
    for a in (.5, .75):
        land_rules[f'½ P·D^{a}·Y + ½ G·D^{a}'] = [(.5, 'PDY', a, 1), (.5, 'GDY', a, 0)]
    land_rules['¾ P·D^0.5·Y + ¼ G'] = [(.75, 'PDY', .5, 1), (.25, 'G', 0, 0)]
    land_rules['¾ P·D^0.75·Y + ¼ G'] = [(.75, 'PDY', .75, 1), (.25, 'G', 0, 0)]

    building_rules = {
        '⅓ P + ⅓ G + ⅓ V (current)': [(1/3, 'P', 0, 0), (1/3, 'G', 0, 0), (1/3, 'V', 0, 0)],
        'P': [(1, 'P', 0, 0)],
        '½ P + ½ V': [(.5, 'P', 0, 0), (.5, 'V', 0, 0)],
        '½ P + ½ G': [(.5, 'P', 0, 0), (.5, 'G', 0, 0)],
        '0.6 P + 0.4 J': [(.6, 'P', 0, 0), (.4, 'JDY', 0, 0)],
        '0.6 P + 0.4 G': [(.6, 'P', 0, 0), (.4, 'G', 0, 0)],
        '0.7 P + 0.3 G': [(.7, 'P', 0, 0), (.3, 'G', 0, 0)],
        'P·Y^0.5': [(1, 'PDY', 0, .5)],
        '0.6 P·Y^0.5 + 0.4 J': [(.6, 'PDY', 0, .5), (.4, 'JDY', 0, 0)],
    }

    print('\nLAND RULES, calibration half. County land: wrong-area / median |log|. Share: Spearman, p10-p90 of our share (FHFA p10-p90 in header).')
    county, tract, zips = tests['us_counties'], tests['us_tracts'], tests['us_zips']
    base_building = building_rules['P']
    fhfa = county['fhfa_land_share'][halves['us_counties']]
    print(f"FHFA county share p10-median-p90: {np.percentile(fhfa, 10):.2f} {np.median(fhfa):.2f} {np.percentile(fhfa, 90):.2f}; "
          f"tract: {np.percentile(tract['fhfa_land_share'][halves['us_tracts']], 10):.2f} "
          f"{np.median(tract['fhfa_land_share'][halves['us_tracts']]):.2f} {np.percentile(tract['fhfa_land_share'][halves['us_tracts']], 90):.2f}")
    print(f"{'land rule':34} {'county land':>14} {'county share':>22} {'tract land':>14} {'tract share':>22} {'zip share':>8}")
    for name, rule in land_rules.items():
        row = [f'{name:34}']
        for test_name, test in (('us_counties', county), ('us_tracts', tract)):
            half = halves[test_name]
            land, buildings = unit_values(test, usa, rule, base_building)
            score = spatial_score(land[half], test['land_value'][half])
            shares = share_score((land / (land + buildings))[half], test['fhfa_land_share'][half])
            row.append(f"{score['wrong_area']:6.3f} {score['median_abs_log']:6.3f}")
            row.append(f"{shares['spearman']:6.3f} {shares['predicted_p10']:5.2f}-{shares['predicted_p90']:4.2f}")
        land, buildings = unit_values(zips, usa, rule, base_building)
        half = halves['us_zips']
        row.append(f"{share_score((land / (land + buildings))[half], zips['fhfa_land_share'][half])['spearman']:6.3f}")
        print(' '.join(row))

    print('\nBUILDING RULES, calibration half, land rule fixed at ½ P·D^0.5·Y + ½ G. County buildings and tract buildings: wrong-area / median |log|; share Spearman.')
    land_rule = land_rules['½ P·D^0.5·Y^1 + ½ G']
    print(f"{'building rule':34} {'county bld':>14} {'county share':>12} {'tract bld':>14} {'tract share':>12}")
    for name, rule in building_rules.items():
        row = [f'{name:34}']
        for test_name, test in (('us_counties', county), ('us_tracts', tract)):
            half = halves[test_name]
            land, buildings = unit_values(test, usa, land_rule, rule)
            score = spatial_score(buildings[half], test['building_value'][half])
            shares = share_score((land / (land + buildings))[half], test['fhfa_land_share'][half])
            row.append(f"{score['wrong_area']:6.3f} {score['median_abs_log']:6.3f}")
            row.append(f"{shares['spearman']:12.3f}")
        print(' '.join(row))


if __name__ == '__main__':
    main()

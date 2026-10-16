"""Written by AI on 2026.10.16 by model claude fable 5.1.

United States, two held-out tests on fixed candidate weights:
  1. States (lower 48 + DC): all land, Larson 2015 (BEA WP2015-3), 2009 values, with agricultural shares.
  2. Counties (2,436): owner-occupied residential land = FHFA land share of property value (pooled 2012-2022)
     x ACS 2023 five-year aggregate value of owner-occupied homes. Residential land only; ACS top-codes
     homes above $2 million, which under-states the richest counties.

Usage: devenv shell -- python -I research/land-value/holdout_us.py
"""
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from landgrid import EXPERIMENTS, ROOT
from holdout_units import load_units, run

US = EXPERIMENTS / 'us'
COUNTIES = f'zip://{ROOT}/data/raw/research-gdp/county_500k.zip'
LOWER48_BBOX = (-125.0, 24.4, -66.9, 49.5)
STATE_FIPS = {'Alabama': '01', 'Arizona': '04', 'Arkansas': '05', 'California': '06', 'Colorado': '08', 'Connecticut': '09', 'Delaware': '10',
              'District of Columbia': '11', 'Florida': '12', 'Georgia': '13', 'Idaho': '16', 'Illinois': '17', 'Indiana': '18', 'Iowa': '19',
              'Kansas': '20', 'Kentucky': '21', 'Louisiana': '22', 'Maine': '23', 'Maryland': '24', 'Massachusetts': '25', 'Michigan': '26',
              'Minnesota': '27', 'Mississippi': '28', 'Missouri': '29', 'Montana': '30', 'Nebraska': '31', 'Nevada': '32', 'New Hampshire': '33',
              'New Jersey': '34', 'New Mexico': '35', 'New York': '36', 'North Carolina': '37', 'North Dakota': '38', 'Ohio': '39', 'Oklahoma': '40',
              'Oregon': '41', 'Pennsylvania': '42', 'Rhode Island': '44', 'South Carolina': '45', 'South Dakota': '46', 'Tennessee': '47',
              'Texas': '48', 'Utah': '49', 'Vermont': '50', 'Virginia': '51', 'Washington': '53', 'West Virginia': '54', 'Wisconsin': '55', 'Wyoming': '56'}


def main():
    # ---- states ----
    state_values, agricultural = {}, 0.0
    for row in csv.DictReader(open(US / 'larson_2015_state_land_value_2009.csv')):
        v = float(row['land_value_usd_billions']) * 1e9
        state_values[STATE_FIPS[row['state']]] = v
        agricultural += v * float(row['agricultural_share_of_value'])
    farm_share = agricultural / sum(state_values.values())
    print(f'US states (Larson 2009): ${sum(state_values.values())/1e12:.1f} trn, agricultural share {farm_share:.1%}')
    states = load_units(COUNTIES, 'STATEFP', None, key_fn=lambda p: str(p['STATEFP']) if str(p['STATEFP']) in state_values else None)
    run('us_states_larson2009', states, state_values, farm_share=farm_share, bbox=LOWER48_BBOX)

    # ---- counties ----
    land_share = {row['geoid']: float(row['land_share_of_property_value']) for row in csv.DictReader(open(US / 'fhfa_county_cross_section_2012_2022.csv'))
                  if row['land_share_of_property_value']}
    county_values, county_state = {}, {}
    for row in csv.DictReader(open(US / 'acs_2023_5yr_county_housing_value.csv')):
        g = row['geoid']
        if g in land_share and row['aggregate_value_owner_occupied_housing_usd'] and g[:2] in state_values:
            county_values[g] = land_share[g] * float(row['aggregate_value_owner_occupied_housing_usd'])
            county_state[g] = g[:2]
    print(f'US counties: {len(county_values)} with FHFA land share and ACS value; residential land ${sum(county_values.values())/1e12:.1f} trn')
    counties = load_units(COUNTIES, 'GEOID', 'NAME', where=lambda p: str(p['GEOID']) in county_values)
    run('us_counties_residential_land', counties, county_values, groups=county_state, bbox=LOWER48_BBOX)


if __name__ == '__main__':
    main()

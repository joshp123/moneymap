"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Official local building valuations used to compare spatial allocation rules.
"""
import json

from shapely.geometry import shape

from layers.grid import ROOT

NYC_RAW = ROOT / 'data/raw/building-value/nyc'


def nyc_units():
    """FY2024 final-roll market values over NYC's 59 community districts."""
    boundaries = json.loads((NYC_RAW / 'community-districts.geojson').read_text())
    units = {}
    for feature in boundaries['features']:
        code = str(int(feature['properties']['boro_cd']))
        # The other twelve polygons are parks and airports, not community districts.
        if int(code) % 100 < 20:
            units[code] = [shape(feature['geometry'])]
    rows = json.loads((NYC_RAW / 'market-values-by-district-2024.json').read_text())
    values = {}
    included_lots = 0
    for row in rows:
        if row.get('cpb_boro') is None or row.get('cpb_dist') is None:
            continue
        code = str(int(row['cpb_boro']) * 100 + int(row['cpb_dist']))
        if code in units:
            land = float(row['land_value'])
            total = float(row['property_value'])
            values[code] = dict(land_value=land, building_value=total - land, property_value=total)
            included_lots += int(row['lots'])
    total_buildings = sum(float(row['property_value']) - float(row['land_value']) for row in rows)
    return dict(
        label='New York City community districts', units=units, values=values,
        bounds=(-74.26, 40.49, -73.70, 40.92), official_year=2024,
        selection_metric='building_value', included_lots=included_lots,
        omitted_building_share=1 - sum(row['building_value'] for row in values.values()) / total_buildings,
        source='https://data.cityofnewyork.us/City-Government/Property-Valuation-and-Assessment-Data-Tax-Classes/8y4t-faws',
        comparison='FY2024 final assessment roll, ordinary real estate records (RECTYPE=1, PERIOD=3). '
                   'Buildings are DOF final market total minus market land, not assessed values. '
                   'Includes all property tax classes, including commercial property. '
                   'Compares shares within 59 community districts; parks, airports, invalid or absent community board identifiers, '
                   'and separate utility assessment records are outside the test. These are statutory DOF market valuations, '
                   'not transaction prices or national-account net building stocks.')

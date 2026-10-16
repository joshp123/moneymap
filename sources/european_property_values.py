"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

An Amsterdam-area residential property diagnostic from CBS 500 m statistics.
The observed proxy is mean WOZ value times the published dwelling count, summed
to fixed 2 km squares. It is not an official all-property aggregate: CBS rounds
dwelling counts and excludes missing and extreme values from the WOZ mean.
"""
import json
import urllib.parse
import urllib.request

from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import box, mapping, shape

from layers.grid import ROOT

RAW = ROOT / 'data/raw/building-value/europe'
WFS = 'https://service.pdok.nl/cbs/vierkantstatistieken500m/2023/wfs/v1_0'
DESCRIPTION = ('https://www.cbs.nl/nl-nl/longread/diversen/2025/'
               'statistische-gegevens-per-vierkant-en-postcode-2022-2023-2024/4-beschrijving-cijfers')
RD_BOUNDS = (110000, 478000, 132000, 494000)


def download_amsterdam_grid():
    """Save the official source geometries and the precise paginated requests."""
    RAW.mkdir(parents=True, exist_ok=True)
    features, requests = [], []
    while True:
        parameters = dict(service='WFS', request='GetFeature', version='2.0.0',
                          typeNames='Vierkant500M2023', outputFormat='application/json',
                          srsName='EPSG:28992', bbox=','.join(map(str, RD_BOUNDS)) + ',EPSG:28992',
                          count=1000, startIndex=len(features), sortBy='crs28992res500m',
                          propertyName='geom,crs28992res500m,aantalWoningen,gemiddeldeWozWaardeWoning')
        url = WFS + '?' + urllib.parse.urlencode(parameters)
        with urllib.request.urlopen(url, timeout=60) as response:
            page = json.load(response)['features']
        requests.append(url)
        features.extend(page)
        if len(page) < 1000:
            break
    (RAW / 'amsterdam_cbs_500m_2023.geojson').write_text(json.dumps(dict(
        type='FeatureCollection', crs=dict(type='name', properties=dict(name='EPSG:28992')),
        features=features)) + '\n')
    (RAW / 'sources.json').write_text(json.dumps(dict(
        provider='Statistics Netherlands (CBS), via PDOK', publication_year=2023,
        valuation_date='2022-01-01', licence='CC BY 4.0', requests=requests,
        year_choice='The 2024 WFS returned only missing/later-release codes for WOZ in all 1,564 Amsterdam-area source cells. The 2023 grid contains published WOZ values.',
        description=DESCRIPTION, rd_bounds=RD_BOUNDS,
        method='Within fixed 2 km RD squares, sum average WOZ in thousands of euros times dwelling count.',
        limitations='Residential land plus buildings only. Counts rounded to five; the WOZ mean excludes missing values and values below EUR 10,000 or above EUR 5 million. Its denominator differs from the full dwelling count.'),
        indent=2) + '\n')


def european_units():
    path = RAW / 'amsterdam_cbs_500m_2023.geojson'
    if not path.exists():
        download_amsterdam_grid()
    features = json.loads(path.read_text())['features']
    west, south, east, north = RD_BOUNDS
    totals = {}
    valid_cells = 0
    for feature in features:
        properties = feature['properties']
        code = properties['crs28992res500m']
        x, y = int(code[1:5]) * 100, int(code[6:10]) * 100
        if not west <= x < east or not south <= y < north:
            continue
        dwellings = properties['aantalWoningen']
        mean_woz = properties['gemiddeldeWozWaardeWoning']
        if dwellings <= 0 or mean_woz <= 0:
            continue
        key = (x // 2000 * 2000, y // 2000 * 2000)
        totals[key] = totals.get(key, 0) + dwellings * mean_woz * 1000
        valid_cells += 1
    units = {f'{x}_{y}': [shape(transform_geom('EPSG:28992', 'EPSG:4326',
                                             mapping(box(x, y, x + 2000, y + 2000))))]
             for x, y in sorted(totals)}
    values = {f'{x}_{y}': dict(property_value=value) for (x, y), value in sorted(totals.items())}
    return dict(label='Amsterdam-area residential WOZ diagnostic', units=units, values=values,
                bounds=transform_bounds('EPSG:28992', 'EPSG:4326', *RD_BOUNDS), country_code='NLD',
                official_year=2023, valuation_date='2022-01-01', selection_metric='property_value',
                source_url=DESCRIPTION, source_cells=valid_cells, unit_size_metres=2000,
                comparison='Residential land plus buildings only, not all-property or buildings-only validation. '
                           'Approximate totals from CBS 2023 mean WOZ times dwelling counts, in 2 km squares. '
                           'Valuation date 1 January 2022. Counts are rounded to five; the mean excludes missing '
                           'WOZ and values below EUR 10,000 or above EUR 5 million, so its denominator differs '
                           'from the full dwelling count. Squares cover the Amsterdam area, including nearby places.')


if __name__ == '__main__':
    result = european_units()
    print(json.dumps({key: value for key, value in result.items() if key not in ('units', 'values')}, indent=2))
    print(f"{len(result['values'])} squares; EUR {sum(v['property_value'] for v in result['values'].values()):,.0f}")

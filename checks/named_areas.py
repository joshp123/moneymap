"""Written by AI on 2026.10.17 by model gpt-6.1-sol.

Check produced area records against original grid and GDP control totals.
Direct point-in-polygon sampling independently checks centre-cell assignment.
The fractional and normalised options retain the earlier decision diagnostics.
No rasters are rewritten.

    devenv shell -- python -m checks.named_areas
    devenv shell -- python -m checks.named_areas --city-controls
"""
import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path

import numpy as np
import fiona
from fiona.transform import transform_geom
import rasterio
from rasterio.windows import Window
import shapely

from layers.grid import (BUILD_DIRECTORY, GRID_HEIGHT, GRID_TRANSFORM,
                         GRID_WIDTH, LAYERS_DIRECTORY, ROOT, TILE_SIZE)
from sources.regional_gdp import US_COMBINED_COUNTIES

CENTRE_SAMPLE_REPORT = ROOT / 'data/build/named-areas/centre-samples.json'
AREA_BUILD_REPORT = BUILD_DIRECTORY / 'named-areas/build-report.json'


LAYERS = ('population', 'bus_stops', 'tram_stops', 'rail_stops', 'gdp',
          'land_value', 'building_value')


def fractional_tile_sums(geometry):
    """Read real float32 tiles and intersect their cell rectangles with geometry."""
    inverse = ~GRID_TRANSFORM
    west, south, east, north = geometry.bounds
    first_column, first_row = inverse * (west, north)
    last_column, last_row = inverse * (east, south)
    first_column, first_row = max(0, math.floor(first_column)), max(0, math.floor(first_row))
    last_column, last_row = min(GRID_WIDTH, math.ceil(last_column)), min(GRID_HEIGHT, math.ceil(last_row))
    sums = {layer: 0. for layer in LAYERS}
    cell_area = abs(GRID_TRANSFORM.a * GRID_TRANSFORM.e)
    intersecting_cells = partial_cells = 0
    shapely.prepare(geometry)
    for tile_row in range(first_row // TILE_SIZE, (last_row - 1) // TILE_SIZE + 1):
        for tile_column in range(first_column // TILE_SIZE, (last_column - 1) // TILE_SIZE + 1):
            row_start, column_start = tile_row * TILE_SIZE, tile_column * TILE_SIZE
            columns, rows = np.meshgrid(np.arange(column_start, column_start + TILE_SIZE),
                                        np.arange(row_start, row_start + TILE_SIZE))
            left = GRID_TRANSFORM.c + columns * GRID_TRANSFORM.a
            top = GRID_TRANSFORM.f + rows * GRID_TRANSFORM.e
            cells = shapely.box(left, top + GRID_TRANSFORM.e, left + GRID_TRANSFORM.a, top)
            full = shapely.covers(geometry, cells)
            boundary = ~full & shapely.intersects(geometry, cells)
            fractions = full.astype('float64')
            fractions[boundary] = shapely.area(shapely.intersection(cells[boundary], geometry)) / cell_area
            intersecting_cells += int(np.count_nonzero(fractions))
            partial_cells += int(np.count_nonzero((fractions > 0) & (fractions < 1)))
            for layer in LAYERS:
                tile = LAYERS_DIRECTORY / layer / str(tile_row) / f'{tile_column}.bin'
                if tile.exists():
                    values = np.fromfile(tile, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)
                    sums[layer] += float(np.sum(values * fractions, dtype='float64'))
    return dict(totals=sums, intersecting_cells=intersecting_cells, partial_cells=partial_cells)


def country_targets(iso3):
    targets = {}
    for layer in ('gdp', 'land_value', 'building_value'):
        report = json.loads((BUILD_DIRECTORY / layer / 'conservation.json').read_text())
        record = report['countries'][iso3]
        target = record['source'] if layer == 'gdp' else record['total_usd2024']
        targets[layer] = dict(target=target, original_grid_sum=record['built'])
    return targets


def country_cells_without_coverage(geometry, iso3):
    """Count original-owner values in cells with no positive polygon coverage.

    The one-degree margin is checked against the original country layer sums;
    a non-zero residual is reported rather than assuming it contains all cells.
    """
    report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    country_ids = np.array([False] + [unit['country'] == iso3 for unit in report['units']])
    sums = {layer: 0. for layer in LAYERS}
    uncovered = {layer: 0. for layer in LAYERS}
    west, south, east, north = geometry.bounds
    inverse = ~GRID_TRANSFORM
    first_column, first_row = inverse * (west - 1, north + 1)
    last_column, last_row = inverse * (east + 1, south - 1)
    first_column, first_row = max(0, math.floor(first_column)), max(0, math.floor(first_row))
    last_column, last_row = min(GRID_WIDTH, math.ceil(last_column)), min(GRID_HEIGHT, math.ceil(last_row))
    shapely.prepare(geometry)
    cells_without_coverage = 0
    with rasterio.open(BUILD_DIRECTORY / 'gdp/control-ids.tif') as ownership:
        for tile_row in range(first_row // TILE_SIZE, (last_row - 1) // TILE_SIZE + 1):
            for tile_column in range(first_column // TILE_SIZE, (last_column - 1) // TILE_SIZE + 1):
                row_start, column_start = tile_row * TILE_SIZE, tile_column * TILE_SIZE
                labels = ownership.read(1, window=Window(column_start, row_start, TILE_SIZE, TILE_SIZE),
                                        boundless=True, fill_value=0)
                owned = country_ids[labels]
                if not np.any(owned):
                    continue
                rows, columns = np.where(owned)
                left = GRID_TRANSFORM.c + (column_start + columns) * GRID_TRANSFORM.a
                top = GRID_TRANSFORM.f + (row_start + rows) * GRID_TRANSFORM.e
                cells = shapely.box(left, top + GRID_TRANSFORM.e, left + GRID_TRANSFORM.a, top)
                covered = shapely.intersects(geometry, cells)
                partial = covered & ~shapely.covers(geometry, cells)
                covered[partial] = shapely.area(shapely.intersection(cells[partial], geometry)) > 0
                cells_without_coverage += int(np.count_nonzero(~covered))
                for layer in LAYERS:
                    path = LAYERS_DIRECTORY / layer / str(tile_row) / f'{tile_column}.bin'
                    if not path.exists():
                        continue
                    values = np.fromfile(path, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)[rows, columns]
                    sums[layer] += float(values.sum(dtype='float64'))
                    uncovered[layer] += float(values[~covered].sum(dtype='float64'))
    targets = country_targets(iso3)
    return dict(cells_without_coverage=cells_without_coverage,
                country_owned_sums_in_search_window=sums, uncovered_values=uncovered,
                uncovered_percent={layer: 100 * uncovered[layer] / value if value else 0
                                   for layer, value in sums.items()},
                search_window_residual={layer: record['original_grid_sum'] - sums[layer]
                                       for layer, record in targets.items()})


def coverage_fractions(geometry, cells):
    shapely.prepare(geometry)
    fractions = shapely.covers(geometry, cells).astype('float64')
    partial = (fractions == 0) & shapely.intersects(geometry, cells)
    fractions[partial] = shapely.area(shapely.intersection(cells[partial], geometry)) / abs(
        GRID_TRANSFORM.a * GRID_TRANSFORM.e)
    return fractions


def normalised_tile_sums(geometry, same_country_geometries, iso3):
    """Check a real area by exact intersections and same-country ownership.

    The denominator is the sum of every sibling's coverage, including overlaps.
    This reads the float32 tile work product, not the intermediate GDP raster.
    """
    report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    country_ids = np.array([False] + [unit['country'] == iso3 for unit in report['units']])
    index = shapely.STRtree(same_country_geometries)
    inverse = ~GRID_TRANSFORM
    west, south, east, north = geometry.bounds
    first_column, first_row = inverse * (west, north)
    last_column, last_row = inverse * (east, south)
    sums = {layer: 0. for layer in LAYERS}
    with rasterio.open(BUILD_DIRECTORY / 'gdp/control-ids.tif') as ownership:
        for tile_row in range(max(0, math.floor(first_row)) // TILE_SIZE,
                              (min(GRID_HEIGHT, math.ceil(last_row)) - 1) // TILE_SIZE + 1):
            for tile_column in range(max(0, math.floor(first_column)) // TILE_SIZE,
                                     (min(GRID_WIDTH, math.ceil(last_column)) - 1) // TILE_SIZE + 1):
                row_start, column_start = tile_row * TILE_SIZE, tile_column * TILE_SIZE
                labels = ownership.read(1, window=Window(column_start, row_start, TILE_SIZE, TILE_SIZE),
                                        boundless=True, fill_value=0)
                rows, columns = np.where(country_ids[labels])
                if not len(rows):
                    continue
                left = GRID_TRANSFORM.c + (column_start + columns) * GRID_TRANSFORM.a
                top = GRID_TRANSFORM.f + (row_start + rows) * GRID_TRANSFORM.e
                cells = shapely.box(left, top + GRID_TRANSFORM.e, left + GRID_TRANSFORM.a, top)
                numerator = coverage_fractions(geometry, cells)
                contributing = numerator > 0
                if not np.any(contributing):
                    continue
                cells, rows, columns = cells[contributing], rows[contributing], columns[contributing]
                denominator = np.zeros(len(cells), dtype='float64')
                tile_bounds = shapely.box(float(np.min(left)), float(np.min(top + GRID_TRANSFORM.e)),
                                         float(np.max(left + GRID_TRANSFORM.a)), float(np.max(top)))
                for sibling in index.query(tile_bounds):
                    denominator += coverage_fractions(same_country_geometries[sibling], cells)
                weights = numerator[contributing] / denominator
                for layer in LAYERS:
                    path = LAYERS_DIRECTORY / layer / str(tile_row) / f'{tile_column}.bin'
                    if path.exists():
                        values = np.fromfile(path, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)[rows, columns]
                        sums[layer] += float(np.sum(values * weights, dtype='float64'))
    return sums


def centre_tile_sums(geometry, same_country_geometries, iso3):
    """Assign real tile-cell centres with point queries, then nearest same-level.

    Reads source polygons and tiles independently of the builder's rasterisation.
    The source area bounds plus a one-degree margin form the sampling window;
    equality with the complete delivered record checks its sufficiency.
    """
    report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    country_ids = np.array([False] + [unit['country'] == iso3 for unit in report['units']])
    index = shapely.STRtree(same_country_geometries)
    target_index = next(i for i, candidate in enumerate(same_country_geometries)
                        if shapely.equals(candidate, geometry))
    inverse = ~GRID_TRANSFORM
    west, south, east, north = geometry.bounds
    first_column, first_row = inverse * (west - 1, north + 1)
    last_column, last_row = inverse * (east + 1, south - 1)
    sums = {layer: 0. for layer in LAYERS}
    assigned_cells = nearest_cells = 0
    with rasterio.open(BUILD_DIRECTORY / 'gdp/control-ids.tif') as ownership:
        for tile_row in range(max(0, math.floor(first_row)) // TILE_SIZE,
                              (min(GRID_HEIGHT, math.ceil(last_row)) - 1) // TILE_SIZE + 1):
            for tile_column in range(max(0, math.floor(first_column)) // TILE_SIZE,
                                     (min(GRID_WIDTH, math.ceil(last_column)) - 1) // TILE_SIZE + 1):
                row_start, column_start = tile_row * TILE_SIZE, tile_column * TILE_SIZE
                labels = ownership.read(1, window=Window(column_start, row_start, TILE_SIZE, TILE_SIZE),
                                        boundless=True, fill_value=0)
                rows, columns = np.where(country_ids[labels])
                if not len(rows):
                    continue
                points = shapely.points(GRID_TRANSFORM.c + (column_start + columns + .5) * GRID_TRANSFORM.a,
                                        GRID_TRANSFORM.f + (row_start + rows + .5) * GRID_TRANSFORM.e)
                matches = index.query(points, predicate='covered_by')
                assignments = np.zeros(len(points), dtype='uint32')
                # The last source polygon wins an exact shared-boundary tie,
                # matching the documented source-order raster burn convention.
                np.maximum.at(assignments, matches[0], matches[1] + 1)
                missing = assignments == 0
                assignments[missing] = index.nearest(points[missing]) + 1
                selected = assignments == target_index + 1
                assigned_cells += int(selected.sum())
                nearest_cells += int((selected & missing).sum())
                for layer in LAYERS:
                    path = LAYERS_DIRECTORY / layer / str(tile_row) / f'{tile_column}.bin'
                    if path.exists():
                        values = np.fromfile(path, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)[rows, columns]
                        sums[layer] += float(values[selected].sum(dtype='float64'))
    return dict(totals=sums, assigned_cells=assigned_cells, nearest_cells=nearest_cells,
                sampling_window='Source bounds plus one degree; compare with the complete static record.')


def gdp_control_comparisons(totals, units):
    comparisons = {'eurostat_nuts3': [], 'bea_counties': []}
    missing = {'eurostat_nuts3': [], 'bea_counties': []}
    for unit in units:
        if 'eurostat' in unit['source']:
            group, identifiers = 'eurostat_nuts3', ['nuts-' + unit['code']]
        elif unit['country'] == 'USA':
            group = 'bea_counties'
            identifiers = ['us-county-' + code for code in US_COMBINED_COUNTIES.get(unit['code'], (unit['code'],))]
        else:
            continue
        if any(identifier not in totals for identifier in identifiers):
            missing[group].append(dict(code=unit['code'], name=unit['name'], expected_records=identifiers))
            continue
        actual = sum(totals[identifier]['gdp'] for identifier in identifiers)
        error = 100 * (actual / unit['target'] - 1) if unit['target'] else 0
        comparisons[group].append(dict(code=unit['code'], name=unit['name'], country=unit['country'],
                                       original_official_gdp=unit['official'],
                                       official_units='current euros, 2023' if group == 'eurostat_nuts3' else 'current US dollars, 2024',
                                       grid_scale=unit['target'] / unit['official'] if unit['official'] else None,
                                       grid_control_target=unit['target'], area_gdp=actual,
                                       difference_percent=error, passes=abs(error) <= 1))
    control_results = {}
    for group, values in comparisons.items():
        ordered = sorted(values, key=lambda row: abs(row['difference_percent']), reverse=True)
        control_results[group] = dict(checked=len(values), failing=sum(not row['passes'] for row in values),
                                     missing=missing[group], worst_five=ordered[:5])
    return control_results


def check_built_areas(directory, build_report_path=AREA_BUILD_REPORT):
    """Compare the delivered static records with existing grid-control reports."""
    index = json.loads((directory / 'record-index.json').read_text())
    records = {}
    for filename in index['files']:
        path = directory / filename
        contents = path.read_bytes()
        if path.suffix == '.gz':
            contents = gzip.decompress(contents)
        records.update(json.loads(contents)['areas'])
    sums = defaultdict(lambda: {layer: 0. for layer in LAYERS})
    area_counts = defaultdict(int)
    for area in records.values():
        area_counts[area['country_code'], area['level']] += 1
        for layer in LAYERS:
            sums[area['country_code'], area['level']][layer] += area['totals'][layer]
    reports = {layer: json.loads((BUILD_DIRECTORY / layer / 'conservation.json').read_text())
               for layer in ('gdp', 'land_value', 'building_value')}
    population_by_owner = defaultdict(float)
    for unit in reports['gdp']['units']:
        population_by_owner[unit['country']] += unit['population']
    build = json.loads(build_report_path.read_text())
    conservation = []
    for coverage in build['coverage']:
        country, level = coverage['country'], coverage['level']
        source_country = coverage['country_code']
        owners = coverage.get('owners', [country])
        if country == 'FRA' and owners == ['FRA']:
            owners = ['FRA', 'GLP', 'MTQ', 'GUF', 'REU', 'MYT']
        totals = sums[source_country, level]
        tiling_level = level != 'place'
        checks = {}
        for layer in LAYERS:
            if layer in reports:
                expected = sum(reports[layer]['countries'][owner]['built'] for owner in owners)
            elif layer == 'population':
                expected = sum(population_by_owner[owner] for owner in owners)
            else:
                expected = coverage['owned_totals'][layer]
            unassigned = coverage['uncovered_totals'][layer]
            assigned_expected = expected if tiling_level else expected - unassigned
            difference = totals[layer] - assigned_expected
            percent = 100 * difference / expected if expected else (0 if not difference else None)
            checks[layer] = dict(expected_grid_total=expected, expected_assigned_total=assigned_expected,
                                 static_area_sum=totals[layer],
                                 difference=difference, difference_percent=percent,
                                 uncovered=unassigned,
                                 uncovered_percent=100 * unassigned / expected if expected else 0,
                                 passes=percent is not None and abs(percent) <= .01)
        conservation.append(dict(country=country, country_code=source_country, level=level, owners=owners,
                                 tiles_country=tiling_level,
                                 area_count=area_counts[source_country, level],
                                 reported_area_count=coverage['area_count'], layers=checks,
                                 source_area_count=coverage['source_area_count'],
                                 excluded_no_centre_count=coverage['excluded_no_centre_count'],
                                 nearest_fill=coverage['nearest_fill'],
                                 nearest_filled_cells=coverage['nearest_filled_cells'],
                                 nearest_filled_totals=coverage['nearest_filled_totals'],
                                 uncovered_cells=coverage['uncovered_cells'],
                                 passes=(area_counts[source_country, level] == coverage['area_count'] and
                                         all(check['passes'] for check in checks.values()))))
    control_results = gdp_control_comparisons({identifier: area['totals'] for identifier, area in records.items()},
                                             reports['gdp']['units'])
    direct_samples = []
    sample_path = CENTRE_SAMPLE_REPORT
    if sample_path.exists():
        for sample in json.loads(sample_path.read_text())['samples']:
            record = records.get(sample['id'])
            differences = ({layer: record['totals'][layer] - value for layer, value in sample['totals'].items()}
                           if record else None)
            direct_samples.append(dict(id=sample['id'], name=sample['name'],
                differences=differences,
                passes=record is not None and all(np.isclose(record['totals'][layer], value, rtol=1e-12, atol=.001)
                                                  for layer, value in sample['totals'].items())))
    paths = [path for path in directory.rglob('*') if path.is_file()]
    return dict(written_by='AI on 2026.10.17 by model gpt-6.1-sol',
                method='Independent record sums; GDP compared to original regional control targets, with source currency and national scale reported.',
                allocation_method=build['method'],
                control_scope_note='Original control targets are not adjusted for source-country groupings. A source country may combine several original grid owners, so some displayed areas contain value outside the original control ownership scope; these deviations remain in the reported errors.',
                country_owner_groups={code: record['grid_owners'] for code, record in build['countries'].items()},
                area_count=len(records), country_levels=conservation,
                failing_country_levels=sum(not row['passes'] for row in conservation),
                gdp_controls=control_results,
                independent_centre_samples=direct_samples,
                files=dict(count=len(paths), bytes=sum(path.stat().st_size for path in paths),
                           largest=sorted([dict(path=str(path.relative_to(directory)), bytes=path.stat().st_size)
                                           for path in paths], key=lambda row: row['bytes'], reverse=True)[:10]))


def check_us_cache(path):
    """Diagnose computed US sums without claiming static-file or page verification."""
    cache = json.loads(path.read_text())
    report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    units = [unit for unit in report['units'] if unit['country'] == 'USA']
    comparisons = gdp_control_comparisons(cache['totals'], units)['bea_counties']
    coverage = []
    for row in cache['coverage']:
        coverage.append(dict(level=row['level'], area_count=row['area_count'],
                             uncovered_totals=row['uncovered_totals'],
                             uncovered_percent={layer: 100 * row['uncovered_totals'][layer] / value if value else 0
                                                for layer, value in row['owned_totals'].items()}))
    return dict(written_by='AI on 2026.10.17 by model gpt-6.1-sol',
                method='Existing computed aggregation cache compared with original GDP build control targets. No new tile aggregation. This does not verify delivered static records or the page.',
                cache=str(path), cache_bytes=path.stat().st_size,
                sources=cache['fingerprint']['sources'],
                control_report='data/build/gdp/conservation.json',
                gdp_units='2024 grid GDP in PPP international dollars; original BEA values are 2024 current US dollars. Official within-country shares were scaled to the grid national total.',
                combined_county_method='Sum the Census counties in US_COMBINED_COUNTIES for each combined BEA control before comparing.',
                bea_counties=comparisons, coverage=coverage)


def read_selected_records(directory, identifiers):
    found = {}
    for filename in json.loads((directory / 'record-index.json').read_text())['files']:
        contents = (directory / filename).read_bytes()
        records = json.loads(gzip.decompress(contents) if filename.endswith('.gz') else contents)['areas']
        found.update({identifier: records[identifier] for identifier in identifiers & records.keys()})
        if found.keys() >= identifiers:
            return found
    raise ValueError(f'Missing delivered records: {sorted(identifiers - found.keys())}')


def new_york_cell_gap(city_geometry, county_geometries, controls):
    """Explain the NYC place/county difference with real cell centres and values."""
    unit_report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    units = unit_report['units']
    county_codes = {unit['code'] for unit in controls}
    is_us = np.array([False] + [unit['country'] == 'USA' for unit in units])
    is_city_county = np.array([False] + [unit['country'] == 'USA' and unit['code'] in county_codes for unit in units])
    county_union = shapely.union_all(county_geometries)
    west, south, east, north = city_geometry.bounds
    search_bounds = (west - 1, south - 1, east + 1, north + 1)
    source_directory = ROOT / 'data/sources/named-areas'
    with fiona.open('zip://' + str(source_directory / 'us-place-2025.zip')) as source:
        nearby_places = [(dict(feature['properties']), shapely.geometry.shape(feature['geometry']))
                         for feature in source.filter(bbox=search_bounds)]
    place_index = shapely.STRtree([geometry for _, geometry in nearby_places])
    inverse = ~GRID_TRANSFORM
    first_column, first_row = inverse * (search_bounds[0], search_bounds[3])
    last_column, last_row = inverse * (search_bounds[2], search_bounds[1])
    categories = {name: dict(cells=0, gdp_nonzero_cells=0, gdp=0.) for name in
                  ('city_centres', 'five_county_owners', 'county_union_centres',
                   'county_owned_outside_city', 'outside_both_city_and_county_outlines',
                   'county_outline_inside_city_outline_outside', 'city_centres_owned_by_other_counties',
                   'missing_in_other_place', 'missing_outside_all_places')}
    examples = []
    for geometry in (city_geometry, county_union):
        shapely.prepare(geometry)
    with rasterio.open(BUILD_DIRECTORY / 'gdp/control-ids.tif') as ownership:
        for tile_row in range(math.floor(first_row) // TILE_SIZE, (math.ceil(last_row)-1) // TILE_SIZE + 1):
            for tile_column in range(math.floor(first_column) // TILE_SIZE, (math.ceil(last_column)-1) // TILE_SIZE + 1):
                row_start, column_start = tile_row*TILE_SIZE, tile_column*TILE_SIZE
                owners = ownership.read(1, window=Window(column_start, row_start, TILE_SIZE, TILE_SIZE))
                rows, columns = np.where(is_us[owners])
                if not len(rows):
                    continue
                longitude = GRID_TRANSFORM.c + (column_start + columns + .5) * GRID_TRANSFORM.a
                latitude = GRID_TRANSFORM.f + (row_start + rows + .5) * GRID_TRANSFORM.e
                points = shapely.points(longitude, latitude)
                inside_city = shapely.covers(city_geometry, points)
                inside_counties = shapely.covers(county_union, points)
                county_owned = is_city_county[owners[rows, columns]]
                missing = county_owned & ~inside_city
                in_other_place = np.zeros(len(points), dtype=bool)
                other_place_names = {}
                if np.any(missing):
                    missing_indices = np.flatnonzero(missing)
                    matches = place_index.query(points[missing], predicate='covered_by')
                    in_other_place[missing_indices[matches[0]]] = True
                    for point_number, place_number in matches.T:
                        other_place_names[int(missing_indices[point_number])] = nearby_places[place_number][0]['NAME']
                path = LAYERS_DIRECTORY / 'gdp' / str(tile_row) / f'{tile_column}.bin'
                values = (np.fromfile(path, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)[rows, columns]
                          if path.exists() else np.zeros(len(rows)))
                masks = dict(city_centres=inside_city, five_county_owners=county_owned,
                    county_union_centres=inside_counties, county_owned_outside_city=missing,
                    outside_both_city_and_county_outlines=missing & ~inside_counties,
                    county_outline_inside_city_outline_outside=missing & inside_counties,
                    city_centres_owned_by_other_counties=inside_city & ~county_owned,
                    missing_in_other_place=missing & in_other_place,
                    missing_outside_all_places=missing & ~in_other_place)
                for name, selected in masks.items():
                    categories[name]['cells'] += int(selected.sum())
                    categories[name]['gdp_nonzero_cells'] += int(np.count_nonzero(values[selected]))
                    categories[name]['gdp'] += float(values[selected].sum(dtype='float64'))
                for number in np.flatnonzero(missing & (values > 0)):
                    unit = units[int(owners[rows[number], columns[number]])-1]
                    examples.append(dict(latitude=float(latitude[number]), longitude=float(longitude[number]),
                        grid_row=int(row_start+rows[number]), grid_column=int(column_start+columns[number]),
                        gdp=float(values[number]), original_county=unit['name'],
                        inside_county_outline=bool(inside_counties[number]),
                        other_place=other_place_names.get(int(number))))
    difference = shapely.symmetric_difference(city_geometry, county_union)
    area = shapely.geometry.shape(transform_geom('EPSG:4326', 'EPSG:6933', shapely.geometry.mapping(difference))).area / 1e6
    return dict(method='Direct production GDP tiles and original control-ids; point queries at cell centres against Census 2025 city and county source outlines. One-degree search margin; complete county/control sums check that it contains all relevant value.',
                categories=categories, source_city_equals_county_union=bool(shapely.equals(city_geometry, county_union)),
                source_city_county_symmetric_difference_km2=area,
                largest_missing_cells=sorted(examples, key=lambda row: row['gdp'], reverse=True)[:5])


def check_city_controls(directory):
    county_codes = ('36005', '36047', '36061', '36081', '36085')
    identifiers = {'us-place-3651000', 'nuts-FR101', *('us-county-'+code for code in county_codes)}
    records = read_selected_records(directory, identifiers)
    report = json.loads((BUILD_DIRECTORY / 'gdp/conservation.json').read_text())
    controls = [unit for unit in report['units'] if unit['country'] == 'USA' and unit['code'] in county_codes]
    paris_control = next(unit for unit in report['units'] if unit['code'] == 'FR101')
    raw_bea = sum(unit['official'] for unit in controls)
    grid_target = sum(unit['target'] for unit in controls)
    county_records = sum(records['us-county-'+code]['totals']['gdp'] for code in county_codes)
    city_gdp = records['us-place-3651000']['totals']['gdp']
    source_directory = ROOT / 'data/sources/named-areas'
    with fiona.open('zip://' + str(source_directory / 'us-place-2025.zip')) as source:
        city_geometry = next(shapely.geometry.shape(feature['geometry']) for feature in source
                             if feature['properties']['GEOID'] == '3651000')
    with fiona.open('zip://' + str(source_directory / 'us-county-2025.zip')) as source:
        county_geometries = [shapely.geometry.shape(feature['geometry']) for feature in source
                             if feature['properties']['GEOID'] in county_codes]
    gap = new_york_cell_gap(city_geometry, county_geometries, controls)
    paris_gdp = records['nuts-FR101']['totals']['gdp']
    return dict(written_by='AI on 2026.10.17 by model gpt-6.1-sol',
        artefact_directory=str(directory.relative_to(ROOT) if directory.is_absolute() else directory),
        grid_gdp_units='PPP international dollars, 2024 grid; source official values are reported separately in their original currencies.',
        equality_tolerance=dict(relative=8e-8, absolute=.01, reason='Existing GDP builder float32 conservation tolerance.'),
        new_york=dict(id='us-place-3651000', name='New York City', area_gdp=city_gdp,
            five_county_area_gdp=county_records, five_county_grid_control_target=grid_target,
            raw_bea_gdp=raw_bea, raw_bea_units='current US dollars, 2024', grid_scale=grid_target/raw_bea,
            difference_from_county_records=city_gdp-county_records,
            difference_from_county_records_percent=100*(city_gdp/county_records-1),
            equals_county_sum=bool(np.isclose(city_gdp, county_records, rtol=8e-8, atol=.01)),
            within_one_percent_of_scaled_bea=bool(abs(city_gdp/grid_target-1) <= .01),
            counties=[dict(code=unit['code'], name=unit['name'], raw_bea_gdp=unit['official'],
                grid_target=unit['target'], area_gdp=records['us-county-'+unit['code']]['totals']['gdp']) for unit in controls],
            direct_cell_diagnostic=gap,
            direct_city_record_difference=gap['categories']['city_centres']['gdp']-city_gdp,
            direct_county_record_difference=gap['categories']['five_county_owners']['gdp']-county_records),
        paris=dict(id='nuts-FR101', name='Paris', area_gdp=paris_gdp,
            raw_eurostat_gdp=paris_control['official'], raw_eurostat_units='current euros, 2023',
            grid_scale=paris_control['target']/paris_control['official'], grid_control_target=paris_control['target'],
            difference=paris_gdp-paris_control['target'],
            difference_percent=100*(paris_gdp/paris_control['target']-1),
            equals_scaled_control=bool(np.isclose(paris_gdp, paris_control['target'], rtol=8e-8, atol=.01))))


def emit_report(result, path):
    result.setdefault('written_by', 'AI on 2026.10.17 by model gpt-6.1-sol')
    output = json.dumps(result, indent=2) + '\n'
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output)
    print(output, end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path,
                        default=ROOT / 'data/raw/research-gdp/nuts3_2024_01m.geojson')
    parser.add_argument('--country', help='GISCO two-letter country code')
    parser.add_argument('--iso3', help='Original grid country code')
    parser.add_argument('--nuts', help='Check this NUTS_ID instead of a whole country')
    parser.add_argument('--uncovered', action='store_true', help='Measure original-country cells without coverage')
    parser.add_argument('--normalised', action='store_true', help='Normalise among same-level source polygons')
    parser.add_argument('--centres', action='store_true', help='Direct centre-cell sample with nearest same-level fill')
    parser.add_argument('--built', type=Path, default=ROOT / 'data/areas',
                        help='Generated static records directory; default data/areas')
    parser.add_argument('--build-report', type=Path, default=AREA_BUILD_REPORT,
                        help='Aggregation report; default data/build/named-areas/build-report.json')
    parser.add_argument('--city-controls', action='store_true', help='Check New York City and Paris against their original controls')
    parser.add_argument('--us-cache', type=Path, help='Diagnose existing US aggregation cache; no static-file verification')
    parser.add_argument('--report', type=Path, help='Save the JSON report as well as printing it')
    arguments = parser.parse_args()
    if arguments.city_controls:
        emit_report(check_city_controls(arguments.built), arguments.report)
        return
    if arguments.us_cache or not arguments.country:
        result = (check_us_cache(arguments.us_cache) if arguments.us_cache else
                  check_built_areas(arguments.built, arguments.build_report))
        emit_report(result, arguments.report)
        return
    if not arguments.country or not arguments.iso3:
        parser.error('--iso3 is required with --country')
    collection = json.loads(arguments.source.read_text())
    features = [feature for feature in collection['features']
                if feature['properties'].get('NUTS_ID') == arguments.nuts] if arguments.nuts else [
                    feature for feature in collection['features']
                    if feature['properties'].get('CNTR_CODE') == arguments.country
                    and feature['properties'].get('LEVL_CODE') == 3]
    if not features:
        raise ValueError('No matching source boundaries')
    geometry = shapely.union_all([shapely.geometry.shape(feature['geometry']) for feature in features])
    if arguments.normalised or arguments.centres:
        level = features[0]['properties']['LEVL_CODE']
        siblings = [shapely.geometry.shape(feature['geometry']) for feature in collection['features']
                    if feature['properties'].get('CNTR_CODE') == arguments.country
                    and feature['properties'].get('LEVL_CODE') == level]
        result = (centre_tile_sums(geometry, siblings, arguments.iso3) if arguments.centres else
                  dict(totals=normalised_tile_sums(geometry, siblings, arguments.iso3)))
        emit_report(dict(country=arguments.country, nuts=arguments.nuts, **result), arguments.report)
        return
    if arguments.uncovered:
        emit_report(country_cells_without_coverage(geometry, arguments.iso3), arguments.report)
        return
    result = fractional_tile_sums(geometry)
    result.update(source=str(arguments.source.relative_to(ROOT)), country=arguments.country,
                  nuts=arguments.nuts, source_features=len(features))
    if not arguments.nuts:
        result['country_comparison'] = country_targets(arguments.iso3)
        for layer, comparison in result['country_comparison'].items():
            comparison['fractional_sum'] = result['totals'][layer]
            comparison['difference'] = result['totals'][layer] - comparison['target']
            comparison['difference_percent'] = 100 * comparison['difference'] / comparison['target']
    emit_report(result, arguments.report)


if __name__ == '__main__':
    main()

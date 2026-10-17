"""Written by AI on 2026.10.17 by model gpt-6.

Build static named-area totals and browser lookup shards from the real tiles.

    devenv shell -- python -m named_areas.build
    devenv shell -- python -m named_areas.build --countries NL US --coverage-only
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
import math
import time

import numpy as np
import rasterio
from rasterio.windows import Window
import shapely
from shapely.geometry import mapping

from layers.grid import (ROOT, BUILD_DIRECTORY, GRID_TRANSFORM, GRID_WIDTH, GRID_HEIGHT,
                         LAYERS_DIRECTORY, TILE_SIZE)
from layers.gdp.cell_ownership import PolygonIndex, sum_by_unit
from layers.land_value.build import country_assignment
from sources.named_areas import DIRECTORY, SOURCES, load, polygon_geometry, validate

LAYERS = ('population', 'bus_stops', 'tram_stops', 'rail_stops', 'gdp', 'land_value', 'building_value')
OUTPUT = ROOT / 'data/areas'
CACHE = BUILD_DIRECTORY / 'named-areas'
MAX_FILE_BYTES = 20_000_000
MAX_TOTAL_BYTES = 200_000_000
RECORD_BATCH_BYTES = 1_500_000


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def write_json(path, value):
    contents = json_bytes(value)
    if path.suffix == '.gz':
        contents = gzip.compress(contents, compresslevel=9, mtime=0)
    if len(contents) > MAX_FILE_BYTES:
        raise RuntimeError(f'{path}: {len(contents):,} bytes exceeds {MAX_FILE_BYTES:,}; stop and report')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return len(contents)


def archive_superseded_files(output, generated_files, archive_root):
    generated = set(generated_files)
    stale_files = [path for path in sorted(output.rglob('*'))
                   if path.is_file() and path.relative_to(output).as_posix() not in generated]
    if not stale_files:
        return dict(directory=None, files=[])
    destination = archive_root / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    relative_paths = []
    for path in stale_files:
        relative = path.relative_to(output)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
        relative_paths.append(relative.as_posix())
    return dict(directory=destination.name, files=relative_paths)


def totals_dict(values):
    return {layer: float(value) for layer, value in zip(LAYERS, values)}


def grid_signature():
    signature = hashlib.sha256()
    for layer in LAYERS:
        for path in sorted((LAYERS_DIRECTORY / layer).glob('*/*.bin')):
            details = path.stat()
            signature.update(f'{path.relative_to(LAYERS_DIRECTORY)}:{details.st_size}:{details.st_mtime_ns}\n'.encode())
    for layer in ('gdp', 'land_value', 'building_value'):
        signature.update((BUILD_DIRECTORY / layer / 'conservation.json').read_bytes())
    return signature.hexdigest()


def aggregation_signature():
    components = [inspect.getsource(function) for function in
                  (aggregate_country, owner_tile_index, read_tiles, tile_window, PolygonIndex, sum_by_unit)]
    components.append(repr((LAYERS, tuple(GRID_TRANSFORM), GRID_WIDTH, GRID_HEIGHT, TILE_SIZE)))
    return hashlib.sha256('\n'.join(components).encode()).hexdigest()


def tile_window(tile_row, tile_column):
    return Window(tile_column * TILE_SIZE, tile_row * TILE_SIZE,
                  min(TILE_SIZE, GRID_WIDTH-tile_column*TILE_SIZE),
                  min(TILE_SIZE, GRID_HEIGHT-tile_row*TILE_SIZE))


def read_tiles(tile_row, tile_column, dimensions):
    values = np.zeros((len(LAYERS), *dimensions), dtype='float64')
    for index, layer in enumerate(LAYERS):
        path = LAYERS_DIRECTORY / layer / str(tile_row) / f'{tile_column}.bin'
        if path.exists():
            tile = np.fromfile(path, dtype='<f4').reshape(TILE_SIZE, TILE_SIZE)
            values[index] = tile[:dimensions[0], :dimensions[1]]
    return values


def owner_tile_index(ownership, country_of_unit, countries, metadata):
    """Find every tile with original-owned cells, including offshore cells."""
    group_for_owner = {owner: country for country, record in metadata.items() for owner in record['grid_owners']}
    tiles = defaultdict(list)
    for tile_row, row in enumerate(range(0, GRID_HEIGHT, TILE_SIZE)):
        window = Window(0, row, GRID_WIDTH, min(TILE_SIZE, GRID_HEIGHT-row))
        owners = country_of_unit[ownership.read(1, window=window)]
        for tile_column, column in enumerate(range(0, GRID_WIDTH, TILE_SIZE)):
            numbers = np.unique(owners[:, column:column+TILE_SIZE])
            groups = {group_for_owner[countries[number-1]] for number in numbers
                      if number and countries[number-1] in group_for_owner}
            for country in groups:
                tiles[country].append((tile_row, tile_column))
    return tiles


def aggregate_country(country, boundaries, metadata, ownership, country_of_unit, countries, tiles, levels=None):
    groups = defaultdict(list)
    for boundary in boundaries.values():
        if boundary.country == country and (levels is None or boundary.level in levels):
            groups[boundary.level].append(boundary)
    owner_numbers = {countries.index(code)+1: code for code in metadata[country]['grid_owners'] if code in countries}
    indices = {level: PolygonIndex(areas) for level, areas in groups.items()}
    centre_counts = {level: np.zeros(len(areas)+1, dtype='int64') for level, areas in groups.items()}
    valued_centre_counts = {level: np.zeros(len(areas)+1, dtype='int64') for level, areas in groups.items()}
    started = time.monotonic()
    # Eligibility uses all grid centres in the original country footprint, including zero-valued cells.
    for tile_number, (tile_row, tile_column) in enumerate(tiles, 1):
        window = tile_window(tile_row, tile_column)
        owner_ids = country_of_unit[ownership.read(1, window=window)]
        owned = np.isin(owner_ids, list(owner_numbers))
        values = read_tiles(tile_row, tile_column, (int(window.height), int(window.width)))
        occupied = owned & np.any(values != 0, axis=0)
        for level, index in indices.items():
            labels = index.labels(window, GRID_TRANSFORM)
            centre_counts[level] += np.bincount(labels[owned], minlength=len(index.controls)+1)
            valued_centre_counts[level] += np.bincount(labels[occupied], minlength=len(index.controls)+1)
        if tile_number % 500 == 0 or tile_number == len(tiles):
            print(f'{country}: centre census {tile_number}/{len(tiles)} tiles, {time.monotonic()-started:.1f}s', flush=True)
    excluded = {}
    eligible_counts = {}
    for level, areas in groups.items():
        eligible = [area for number, area in enumerate(areas, 1) if centre_counts[level][number] > 0]
        excluded[level] = [area.id for number, area in enumerate(areas, 1) if centre_counts[level][number] == 0]
        eligible_counts[level] = {area.id: dict(centre_cells=int(centre_counts[level][number]),
            valued_centre_cells=int(valued_centre_counts[level][number])) for number, area in enumerate(areas, 1)
            if centre_counts[level][number] > 0}
        groups[level] = eligible
        indices[level] = PolygonIndex(eligible) if eligible else None
    level_sums = {level: np.zeros((len(areas)+1, len(LAYERS))) for level, areas in groups.items()}
    total_fields = ('owned_totals', 'pre_fill_uncovered_totals', 'nearest_filled_totals', 'uncovered_totals')
    count_fields = ('owned_cells', 'pre_fill_uncovered_cells', 'nearest_filled_cells', 'uncovered_cells')
    def empty_metrics():
        return {**{key: 0 for key in count_fields}, **{key: np.zeros(len(LAYERS)) for key in total_fields}}
    reports = {level: dict(country=metadata[country]['iso3'], country_code=country, level=level,
        owners=list(owner_numbers.values()), area_count=len(areas),
        source_area_count=len(areas)+len(excluded[level]), excluded_no_centre_count=len(excluded[level]),
        excluded_no_centre_ids=excluded[level], centre_counts=eligible_counts[level],
        centre_count_definition='Grid centres inside the source outline and original grid country footprint; includes zero-valued cells. Valued centres have a nonzero value in at least one of the seven layers.',
        nearest_fill=level != 'place', **empty_metrics(),
        by_owner={code: empty_metrics() for code in owner_numbers.values()}) for level, areas in groups.items()}
    for tile_number, (tile_row, tile_column) in enumerate(tiles, 1):
        window = tile_window(tile_row, tile_column)
        owner_ids = country_of_unit[ownership.read(1, window=window)]
        owned = np.isin(owner_ids, list(owner_numbers))
        dimensions = (int(window.height), int(window.width))
        values = read_tiles(tile_row, tile_column, dimensions)
        occupied = owned & np.any(values != 0, axis=0)
        if not np.any(occupied):
            continue
        for level, areas in groups.items():
            index = indices[level]
            labels = index.labels(window, GRID_TRANSFORM) if index else np.zeros(dimensions, dtype='uint32')
            labels[~owned] = 0
            missing = occupied & (labels == 0)
            if level != 'place' and index:
                index.fill_nearest(labels, occupied, window, GRID_TRANSFORM)
            uncovered = occupied & (labels == 0)
            filled = missing & (labels > 0)
            for layer_number in range(len(LAYERS)):
                level_sums[level][:, layer_number] += sum_by_unit(labels, values[layer_number], len(areas))
            masks = dict(owned=occupied, pre_fill_uncovered=missing, nearest_filled=filled, uncovered=uncovered)
            report = reports[level]
            for prefix, mask in masks.items():
                report[prefix+'_cells'] += int(mask.sum())
                report[prefix+'_totals'] += values[:, mask].sum(axis=1)
                for number, code in owner_numbers.items():
                    selected = mask & (owner_ids == number)
                    report['by_owner'][code][prefix+'_cells'] += int(selected.sum())
                    report['by_owner'][code][prefix+'_totals'] += values[:, selected].sum(axis=1)
        if tile_number % 500 == 0 or tile_number == len(tiles):
            print(f'{country}: whole-cell totals {tile_number}/{len(tiles)} tiles, {time.monotonic()-started:.1f}s', flush=True)
    sums = {area.id: level_sums[level][number] for level, areas in groups.items() for number, area in enumerate(areas, 1)}
    for level, report in reports.items():
        report['area_totals'] = totals_dict(sum((sums[area.id] for area in groups[level]), np.zeros(len(LAYERS))))
        for record in [report, *report['by_owner'].values()]:
            for key in total_fields:
                record[key] = totals_dict(record[key])
    return {identifier: totals_dict(values) for identifier, values in sums.items()}, list(reports.values())


def display_geometry(geometry):
    simplified = shapely.simplify(geometry, .0005, preserve_topology=True)
    coordinates = shapely.get_coordinates(simplified)
    simplified = shapely.set_coordinates(simplified, np.round(coordinates, 5))
    return polygon_geometry(simplified)


def boundary_line_geometry(geometry):
    lines = [part for part in shapely.get_parts(geometry) if shapely.get_dimensions(part) == 1]
    return shapely.union_all(lines)


def approximate_area_km2(geometry):
    """Area on an equal-area sinusoidal projection; close enough to order nested areas by size."""
    def project(coordinates):
        longitude, latitude = coordinates[:, 0], coordinates[:, 1]
        return np.column_stack([longitude * np.cos(np.radians(latitude)), latitude]) * 111.195
    return shapely.transform(geometry, project).area


def write_artifacts(boundaries, metadata, totals, reports, hierarchy, sources):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'LICENCE.md').write_bytes((ROOT / 'named_areas/LICENCE.md').read_bytes())
    boundaries = {identifier: area for identifier, area in boundaries.items() if identifier in totals}
    outlines = {identifier: display_geometry(area.geometry) for identifier, area in boundaries.items()}
    records = {}
    for identifier, area in boundaries.items():
        records[identifier] = dict(id=identifier, code=area.code, name=area.name, level=area.level,
            country=metadata[area.country]['iso3'], country_code=area.country, source=area.source,
            bbox=[round(value, 5) for value in outlines[identifier].bounds], geometry=mapping(outlines[identifier]),
            totals=totals[identifier], **area.details)
    # Assign stable-size batches before adding parent references, leaving room for those references.
    batches, references, current, size, number = [], {}, {}, 0, 0
    for identifier in sorted(records):
        record = records[identifier]
        record_size = len(json_bytes(record)) + 1200
        if record_size > MAX_FILE_BYTES - 100:
            raise RuntimeError(f'Area outline {identifier} is {record_size:,} bytes; stop and report')
        if current and size + record_size > RECORD_BATCH_BYTES:
            batches.append((f'records/{number}.json.gz', current))
            current, size, number = {}, 0, number+1
        current[identifier] = record
        size += record_size
        references[identifier] = dict(id=identifier, name=record['name'], level=record['level'], file=f'records/{number}.json.gz',
            km2=round(approximate_area_km2(boundaries[identifier].geometry), 1))
    if current:
        batches.append((f'records/{number}.json.gz', current))
    sizes = {}
    for filename, batch in batches:
        for identifier, record in batch.items():
            record['parents'] = [references[parent] for parent in boundaries[identifier].parent_ids if parent in references]
        sizes[filename] = write_json(OUTPUT / filename, dict(areas=batch))
    print(f'Wrote {len(records):,} area records in {len(batches):,} files', flush=True)
    tile_features = defaultdict(list)
    tile_outline_features = defaultdict(list)
    for number, (identifier, geometry) in enumerate(outlines.items(), 1):
        clipped_parts = defaultdict(list)
        boundary_parts = defaultdict(list)
        for part in shapely.get_parts(geometry):
            source_boundary = part.boundary
            west, south, east, north = part.bounds
            for longitude in range(math.floor(west), min(180, math.ceil(east))):
                for latitude in range(max(-90, math.floor(south)), min(90, math.ceil(north))):
                    shard_bounds = shapely.box(longitude, latitude, longitude+1, latitude+1)
                    clipped = polygon_geometry(shapely.intersection(part, shard_bounds))
                    if not clipped.is_empty and clipped.area > 0:
                        clipped_parts[(longitude, latitude)].append(clipped)
                        boundary = boundary_line_geometry(shapely.intersection(source_boundary, shard_bounds))
                        if not boundary.is_empty:
                            boundary_parts[(longitude, latitude)].append(boundary)
        for tile, parts in clipped_parts.items():
            tile_features[tile].append(dict(type='Feature', properties=references[identifier],
                geometry=mapping(shapely.union_all(parts))))
            if boundary_parts[tile]:
                tile_outline_features[tile].append(dict(type='Feature',
                    properties={**references[identifier], 'source': boundaries[identifier].source},
                    geometry=mapping(shapely.union_all(boundary_parts[tile]))))
        if number % 10000 == 0:
            print(f'Lookup outlines: {number:,}/{len(outlines):,}', flush=True)
    viewport_index = dict(tile_degrees=1, levels={})
    for (longitude, latitude), features in sorted(tile_features.items()):
        filename = f'tiles/{longitude}_{latitude}.json.gz'
        sizes[filename] = write_json(OUTPUT / filename, dict(type='FeatureCollection', features=features))
        features_by_level, lines_by_level = defaultdict(list), defaultdict(list)
        for feature in features:
            reference = feature['properties']
            features_by_level[reference['level']].append({**feature,
                'properties': {**reference, 'source': boundaries[reference['id']].source}})
        for feature in tile_outline_features[(longitude, latitude)]:
            lines_by_level[feature['properties']['level']].append(feature)
        for level, hit_features in sorted(features_by_level.items()):
            filename = f'outlines/{level}/{longitude}_{latitude}.json.gz'
            sizes[filename] = write_json(OUTPUT / filename, dict(type='FeatureCollection', features=hit_features,
                outlines=dict(type='FeatureCollection', features=lines_by_level[level])))
            viewport_index['levels'].setdefault(level, {})[f'{longitude}_{latitude}'] = dict(
                file=filename, count=len(hit_features), bytes=sizes[filename])
    sizes['viewport-index.json'] = write_json(OUTPUT / 'viewport-index.json', viewport_index)
    sizes['record-index.json'] = write_json(OUTPUT / 'record-index.json', dict(files=[filename for filename, _ in batches]))
    sizes['sources.json'] = write_json(OUTPUT / 'sources.json', dict(files=sources, countries=metadata,
        editions=dict(gisco_lau=2024, gisco_nuts=2024, census=2025)))
    report = dict(method='Whole grid-cell values go to the area containing the cell centre, restricted to original grid country ownership. Valued gaps at tiling levels go to the nearest eligible same-level area of that country using layers.gdp.cell_ownership.PolygonIndex. US places have no nearest fill. Areas containing no original-country grid centre are excluded. No rescaling.',
        coverage=reports, hierarchy=hierarchy, source_files=sources, countries=metadata,
        output=dict(files=len(sizes), bytes=sum(sizes.values()), largest=sorted(sizes.items(), key=lambda pair: pair[1], reverse=True)[:10]))
    write_json(OUTPUT / 'manifest.json', dict(version=1, tile_degrees=1, countries=metadata,
        credits=['Source: Eurostat; © EuroGeographics for the administrative boundaries',
                 'US Census Bureau cartographic boundary files (public domain)'],
        licences='LICENCE.md', encoding='gzip', method=report['method'],
        viewport=dict(tile_degrees=1, index='viewport-index.json')))
    report['generated_files'] = sorted(set(sizes) | {'LICENCE.md', 'manifest.json'})
    report['superseded'] = archive_superseded_files(OUTPUT, report['generated_files'], CACHE / 'superseded')
    final_sizes = {str(path.relative_to(OUTPUT)): path.stat().st_size for path in OUTPUT.rglob('*') if path.is_file()}
    report['output'] = dict(files=len(final_sizes), bytes=sum(final_sizes.values()),
        encoding='gzip for records, click lookup and viewport shards',
        largest=sorted(final_sizes.items(), key=lambda pair: pair[1], reverse=True)[:10])
    write_json(CACHE / 'build-report.json', report)
    print(json.dumps(report['output'], indent=2), flush=True)
    if report['output']['bytes'] > MAX_TOTAL_BYTES:
        raise RuntimeError(f'Area artefacts total {report["output"]["bytes"]:,} bytes exceeds {MAX_TOTAL_BYTES:,}; stop and report')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--countries', nargs='+', help='GISCO country codes and/or US; default all source countries')
    parser.add_argument('--coverage-only', action='store_true', help='Write diagnostic report only; no browser artefacts')
    parser.add_argument('--levels', nargs='+', help='Only these levels in a coverage diagnostic')
    parser.add_argument('--fresh', action='store_true', help='Ignore existing per-country aggregation caches')
    arguments = parser.parse_args()
    if arguments.levels and not arguments.coverage_only:
        parser.error('--levels requires --coverage-only')
    source_records = []
    for name, url in SOURCES.items():
        if arguments.countries == ['US'] and not name.startswith('us-'):
            continue
        path = DIRECTORY / name
        validate(path)
        source_records.append(dict(file=name, url=url, bytes=path.stat().st_size,
            sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()))
    print('Reading source boundaries and parent links', flush=True)
    boundaries, metadata, hierarchy = load(arguments.countries)
    print(f'{len(boundaries):,} boundaries, {len(metadata)} countries', flush=True)
    countries, country_of_unit = country_assignment()
    tile_signature = grid_signature()
    CACHE.mkdir(parents=True, exist_ok=True)
    sums, coverage = {}, []
    with rasterio.open(BUILD_DIRECTORY / 'gdp/control-ids.tif') as ownership:
        print('Indexing original country-owned tiles', flush=True)
        tiles = owner_tile_index(ownership, country_of_unit, countries, metadata)
        for country in sorted(metadata):
            print(f'Aggregating {country}, {len(tiles[country]):,} tiles', flush=True)
            cache = CACHE / (country + ('-' + '-'.join(arguments.levels) if arguments.levels else '') + '.json')
            fingerprint = dict(sources=source_records, owners=metadata[country]['grid_owners'], levels=arguments.levels,
                aggregation_sha256=aggregation_signature(),
                source_reader_sha256=hashlib.file_digest((ROOT / 'sources/named_areas.py').open('rb'), 'sha256').hexdigest(),
                grid_signature=tile_signature,
                grid_ownership_mtime=(BUILD_DIRECTORY / 'gdp/control-ids.tif').stat().st_mtime_ns)
            previous = json.loads(cache.read_text()) if cache.exists() and not arguments.fresh else None
            if previous and previous.get('fingerprint') == fingerprint:
                country_sums, report = previous['totals'], previous['coverage']
                print(f'{country}: reused exact tile sums', flush=True)
            else:
                country_sums, report = aggregate_country(country, boundaries, metadata, ownership,
                    country_of_unit, countries, tiles[country], arguments.levels)
                cache.write_bytes(json_bytes(dict(fingerprint=fingerprint, totals=country_sums, coverage=report)))
            sums.update(country_sums)
            coverage.extend(report)
            for row in report:
                missing = row['uncovered_totals']
                print(f'{country} {row["level"]}: uncovered {row["uncovered_cells"]:,} occupied cells; '
                      f'GDP {missing["gdp"]:,.2f}, population {missing["population"]:,.2f}', flush=True)
    if arguments.coverage_only:
        write_json(CACHE / 'coverage-diagnostic.json', dict(coverage=coverage, countries=metadata))
    else:
        write_artifacts(boundaries, metadata, sums, coverage, hierarchy, source_records)


if __name__ == '__main__':
    main()

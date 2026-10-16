"""Written by AI on 2026.10.17 by model gpt-6.1-sol.

Score production rasters on the frozen valuation units from the split study.
US counties and tracts retain its even-state hold-out; cell-to-unit links are
unchanged, including the block-count split of cells spanning census tracts.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from layers.grid import ROOT

VALUATION_UNITS = ROOT / 'data/experiments/split'


@lru_cache(maxsize=8)
def country_cells(country):
    with np.load(VALUATION_UNITS / f'cells_{country}.npz') as cells:
        return cells['row'], cells['col']


def load_test(name):
    with np.load(VALUATION_UNITS / f'units_{name}.npz') as data:
        metadata = json.loads(str(data['meta']))
        test = dict(name=name, country=metadata['country'], keys=metadata['keys'],
                    cell_index=data['cell_index'], unit_index=data['unit_index'], weight=data['weight'])
        test.update({component: data[f'actual_{component}'] for component in metadata['components']})
    if name.startswith('us_'):
        states = np.array([key[:2] for key in test['keys']])
        test['held_out'] = (states.astype(int) % 2 == 0) & ~np.isin(states, ['02', '15', '72'])
    else:
        test['held_out'] = np.ones(len(test['keys']), dtype=bool)
    return test


@lru_cache(maxsize=4)
def raster_country_cells(raster_path, country):
    """Read each needed raster block once, keeping the study's cell order."""
    rows, columns = country_cells(country)
    values = np.zeros(len(rows), dtype='float64')
    with rasterio.open(raster_path) as source:
        block_height, block_width = source.block_shapes[0]
        block_columns = (source.width + block_width - 1) // block_width
        block_ids = (rows // block_height) * block_columns + columns // block_width
        order = np.argsort(block_ids, kind='stable')
        sorted_blocks = block_ids[order]
        boundaries = np.r_[0, np.nonzero(np.diff(sorted_blocks))[0] + 1, len(order)]
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            positions = order[start:end]
            row = int(rows[positions[0]] // block_height * block_height)
            column = int(columns[positions[0]] // block_width * block_width)
            window = Window(column, row, min(block_width, source.width - column),
                            min(block_height, source.height - row))
            cells = source.read(1, window=window, masked=True).filled(0)
            values[positions] = cells[rows[positions] - row, columns[positions] - column]
    return values


def unit_values(raster_path, test_name):
    test = load_test(test_name)
    cells = raster_country_cells(str(Path(raster_path).resolve()), test['country'])
    predicted = np.bincount(test['unit_index'],
                            weights=cells[test['cell_index']] * test['weight'],
                            minlength=len(test['keys']))
    return test, predicted


def spatial_score(predicted, actual):
    scaled = predicted / predicted.sum() * actual.sum()
    with np.errstate(divide='ignore'):
        log_ratio = np.log(scaled / actual)
    return dict(misallocated_share=float(np.abs(scaled - actual).sum() / (2 * actual.sum())),
                median_abs_log_ratio=float(np.median(np.abs(log_ratio))),
                n_units=len(actual), empty_units=int((predicted == 0).sum()))


def score_layer(raster_path, test_name, component='land_value'):
    test, predicted = unit_values(raster_path, test_name)
    held_out = test['held_out']
    actual = test[component]
    return dict(test=test_name, country=test['country'], component=component,
                scores=spatial_score(predicted[held_out], actual[held_out]),
                official_total=float(actual[held_out].sum()),
                predicted_total_usd=float(predicted[held_out].sum()),
                per_unit={key: dict(actual=float(actual[index]), predicted_usd=float(predicted[index]))
                          for index, key in enumerate(test['keys']) if held_out[index]})


def compare_layer(raster_path, before_raster_path, test_name, component='land_value'):
    after = score_layer(raster_path, test_name, component)
    before = score_layer(before_raster_path, test_name, component)
    return dict(test=test_name, country=after['country'], component=component,
                before=before, after=after)


def land_share_score(predicted, official):
    """Keep the frozen study's rank definition, including its treatment of ties."""
    rank = lambda values: np.argsort(np.argsort(values))
    return dict(spearman=float(np.corrcoef(rank(predicted), rank(official))[0, 1]),
                pearson=float(np.corrcoef(predicted, official)[0, 1]),
                predicted_p10=float(np.percentile(predicted, 10)),
                predicted_median=float(np.median(predicted)),
                predicted_p90=float(np.percentile(predicted, 90)),
                official_p10=float(np.percentile(official, 10)),
                official_median=float(np.median(official)),
                official_p90=float(np.percentile(official, 90)), n_units=len(official))


def score_pair(land_path, buildings_path, test_name):
    test, land = unit_values(land_path, test_name)
    _, buildings = unit_values(buildings_path, test_name)
    held_out = test['held_out']
    result = dict(test=test_name)
    official_share = (test['fhfa_land_share'] if 'fhfa_land_share' in test else
                      test['land_value'] / (test['land_value'] + test['building_value'])
                      if 'land_value' in test and 'building_value' in test else None)
    if official_share is not None:
        share = land / (land + buildings)
        result['land_share'] = land_share_score(share[held_out], official_share[held_out])
        result['per_unit_land_share'] = {
            key: dict(predicted=float(share[index]), official=float(official_share[index]))
            for index, key in enumerate(test['keys']) if held_out[index]}
    if 'property_value' in test:
        result['property_value'] = spatial_score((land + buildings)[held_out], test['property_value'][held_out])
    if test_name == 'nyc_districts':
        result['nyc_core'] = {}
        for name, codes in [('Manhattan', range(101, 113)), ('Manhattan core', range(101, 107))]:
            indices = [test['keys'].index(str(code)) for code in codes]
            result['nyc_core'][name] = {
                component: dict(predicted=float(prediction[indices].sum() / prediction.sum()),
                                official=float(test[component][indices].sum() / test[component].sum()))
                for component, prediction in [('land_value', land), ('building_value', buildings)]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-land', type=Path, required=True)
    parser.add_argument('--before-buildings', type=Path, required=True)
    parser.add_argument('--land', type=Path, default=ROOT / 'data/build/land_value/land_value.tif')
    parser.add_argument('--buildings', type=Path, default=ROOT / 'data/build/building_value/building_value.tif')
    parser.add_argument('--report', type=Path, default=ROOT / 'data/checks/property_split.json')
    arguments = parser.parse_args()
    results = []
    for name in ('us_counties', 'us_tracts', 'us_zips', 'nyc_districts', 'victoria_councils',
                 'bc_municipalities', 'amsterdam_homes'):
        result = dict(test=name, before=score_pair(arguments.before_land, arguments.before_buildings, name),
                      after=score_pair(arguments.land, arguments.buildings, name))
        results.append(result)
        print(json.dumps({period: {key: value for key, value in result[period].items()
                                   if key != 'per_unit_land_share'} for period in ('before', 'after')}), flush=True)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(dict(tests=results), indent=2) + '\n')


if __name__ == '__main__':
    main()

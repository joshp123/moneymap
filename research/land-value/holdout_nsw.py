"""Written by AI on 2026.10.16 by model claude fable 5.1.

NSW council areas: official land-only values (Valuer General, 1 July 2024) against candidate weights.
NSW is where the previous agent fitted its parameters, so this is calibration, not validation;
it is run first to check this code reproduces the earlier numbers and to score new candidates.

Usage: devenv shell -- python -I research/land-value/holdout_nsw.py
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I drops the script directory
import numpy as np
from landgrid import ROOT, EXPERIMENTS, Region, unit_sums, candidate_weights, score, mix

NSW = ROOT / 'data/research/land-value/nsw'
RURAL_SHARE_OF_NSW_LAND = 309.1 / 2981.6   # Valuer General report: rural $309bn of $2,982bn


def normalise(name):
    name = re.sub(r'\(.*?\)', '', name.upper())
    for token in ['CITY OF ', ' COUNCIL', ' SHIRE', ' REGIONAL']:
        name = name.replace(token, '')
    return re.sub(r'[^A-Z]', '', name)


def valuer_general_totals():
    lines = open(NSW / 'report2024.md').read().splitlines()
    values, regions, current = {}, {}, None
    for i, line in enumerate(lines):
        if line.startswith('Region: City of Sydney'): current = 'city'
        elif line.startswith('Region: Greater Sydney'): current = 'sydney'
        elif line.startswith('Region: Coastal NSW'): current = 'coastal'
        elif line.startswith('Regional: Regional NSW'): current = 'regional'
        m = re.match(r'\|\s*([A-Z][A-Z \-]+?)\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|', line)
        if m:
            values[m.group(1).strip()] = float(m.group(3).replace(',', '')); regions[m.group(1).strip()] = current
        m2 = re.match(r'\|\s*\|\s*([\d,]+)\s*\|\s*\$([\d,]+)\s*\|', line)
        if m2:
            name = lines[i + 1].strip()
            values[name] = float(m2.group(2).replace(',', ''))
            regions[name] = {'RYDE': 'sydney', 'SHELLHARBOUR': 'coastal'}.get(name, 'regional')
    return values, regions


def main():
    values, regions = valuer_general_totals()
    boundaries = json.load(open(NSW / 'lga_geom.json'))
    by_name = {}
    for f in boundaries['features']:
        if 'geometry' in f:
            by_name[normalise(f['attributes']['lga_name_2021'])] = {'type': 'Polygon', 'coordinates': f['geometry']['rings']}
    units = []
    for name, value in values.items():
        key = normalise(name)
        geom = by_name.get(key) or next((g for k, g in by_name.items() if k.startswith(key) or key.startswith(k)), None)
        if geom is None:
            print('unmatched', name); continue
        units.append((name, value, geom, regions[name]))
    print(f'{len(units)} councils matched, A${sum(u[1] for u in units)/1e9:,.0f}bn')

    region = Region(140.9, -37.6, 153.7, -28.1)
    labels = region.rasterize_units((u[2], i + 1) for i, u in enumerate(units))
    actual = np.array([u[1] for u in units])
    weights = candidate_weights(region)
    sums = {name: unit_sums(labels, field, len(units)) for name, field in weights.items()}

    results = {}
    def report(name, predicted):
        s = score(predicted, actual)
        # four-region misallocation
        pred_scaled = predicted / predicted.sum() * actual.sum()
        region_names = sorted(set(u[3] for u in units))
        reg = sum(abs(pred_scaled[[u[3] == r for u in units]].sum() - actual[[u[3] == r for u in units]].sum()) for r in region_names) / 2 / actual.sum()
        s['four_region_misallocated_share'] = float(reg)
        results[name] = s
        print(f'{name:55s} wrong council {s["misallocated_share"]:6.1%}   four regions {reg:5.1%}   median |log ratio| {s["median_abs_log_ratio"]:.3f}')

    for name, s in sums.items():
        if name in ('area', 'cropland (SPAM)'):
            continue
        report(name, s)
    print('--- with farmland: (1 - rural share) x urban weight + rural share x cropland or area ---')
    for urban in ['population', 'population x access^0.25', 'built volume (all)', 'built volume x access^0.25', 'GDP v3 (workplace)']:
        report(f'{urban} + cropland {RURAL_SHARE_OF_NSW_LAND:.0%}', mix(sums, {urban: 1 - RURAL_SHARE_OF_NSW_LAND, 'cropland (SPAM)': RURAL_SHARE_OF_NSW_LAND}))
    report('population x access^0.25 + area 5% (previous agent)', mix(sums, {'population x access^0.25': 0.95, 'area': 0.05}))
    print('--- fixed mixes ---')
    report('3/4 population + 1/4 GDP v3', mix(sums, {'population': 0.75, 'GDP v3 (workplace)': 0.25}))
    report('1/2 population + 1/2 GDP v3', mix(sums, {'population': 0.5, 'GDP v3 (workplace)': 0.5}))
    report('1/2 population x access^0.25 + 1/2 GDP v3', mix(sums, {'population x access^0.25': 0.5, 'GDP v3 (workplace)': 0.5}))
    for name in ('population x access^0.15', 'population x access^0.35', 'population x access^0.5'):
        report(name, sums[name])
    report('1/2 population + 1/2 built volume', mix(sums, {'population': 0.5, 'built volume (all)': 0.5}))
    report('1/2 population + 1/2 built volume, + cropland', mix(sums, {'population': 0.5 * (1 - RURAL_SHARE_OF_NSW_LAND), 'built volume (all)': 0.5 * (1 - RURAL_SHARE_OF_NSW_LAND), 'cropland (SPAM)': RURAL_SHARE_OF_NSW_LAND}))

    # worst councils for the two main candidates
    for name in ['population', 'population x access^0.25', 'built volume (all)']:
        pred = sums[name] / sums[name].sum() * actual.sum()
        ratio = np.log(pred / actual)
        order = np.argsort(ratio)
        print(f'\n{name}: most under-predicted ' + ', '.join(f'{units[i][0]} ({np.exp(ratio[i]):.2f}x)' for i in order[:4])
              + '; most over-predicted ' + ', '.join(f'{units[i][0]} ({np.exp(ratio[i]):.2f}x)' for i in order[-4:]))

    EXPERIMENTS.mkdir(parents=True, exist_ok=True)
    json.dump({'units': [{'name': u[0], 'land_value_aud': u[1], 'region': u[3]} for u in units], 'scores': results},
              open(EXPERIMENTS / 'nsw_scores.json', 'w'), indent=1)


if __name__ == '__main__':
    main()

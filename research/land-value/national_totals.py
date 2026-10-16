"""Written by AI on 2026.10.16 by model claude fable 5.1.

Independent re-derivation of national land totals from OECD Table 9B (land, net, N211N)
and a check of the model used for countries that publish nothing.

Usage: devenv shell -- python -I research/land-value/national_totals.py
Reads:  data/research/land-value/oecd/{land_all.csv, gdp_lcu.json, gdp_usd.json, wb_*.json}
Writes: data/experiments/land-value/national_totals.json
"""
import csv, json, math, collections, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OECD = ROOT / 'data/research/land-value/oecd'
OUT = ROOT / 'data/experiments/land-value/national_totals.json'

PARTIAL_REPORTERS = {'MEX', 'HRV', 'NZL'}   # S1 equals S1M or is zero: not a total-economy figure
HOUSEHOLD_SHARE_ASSUMED = 0.6               # households' share of all land, median of full reporters (matched years)
AGGREGATES = {'WLD','HIC','LMC','LMY','MIC','UMC','LIC','EAS','ECS','LCN','MEA','NAC','SAS','SSF','ARB','CEB','EAP','EAR','ECA','EMU','EUU','FCS','HPC','IBD','IBT','IDA','IDB','IDX','LAC','LDC','LTE','MNA','OED','OSS','PRE','PSS','PST','SSA','SSD','SST','TEA','TEC','TLA','TMN','TSA','TSS','AFE','AFW','CSS','INX'}


def world_bank_series(name):
    series = collections.defaultdict(dict)
    for record in json.load(open(OECD / name))[1]:
        if record['value'] is not None:
            series[record['countryiso3code']][record['date']] = record['value']
    return series


def latest(series, year=None):
    if not series:
        return None
    if year and year in series:
        return series[year]
    return series[max(series)]


def oecd_land():
    """{(iso3, sector): {year: value in national currency}} for 'Land, net'."""
    land = collections.defaultdict(dict)
    for row in csv.DictReader(open(OECD / 'land_all.csv')):
        if row['OBS_VALUE'] and row['INSTR_ASSET'] == 'N211N' and float(row['OBS_VALUE']) > 0:
            land[(row['REF_AREA'], row['SECTOR'])][row['TIME_PERIOD']] = float(row['OBS_VALUE']) * 10 ** int(row['UNIT_MULT'])
    return land


def ordinary_least_squares(X, Y):
    k = len(X[0])
    M = [[sum(x[i] * x[j] for x in X) for j in range(k)] + [sum(x[i] * y for x, y in zip(X, Y))] for i in range(k)]
    for i in range(k):
        pivot = max(range(i, k), key=lambda r: abs(M[r][i]))
        M[i], M[pivot] = M[pivot], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * b for a, b in zip(M[r], M[i])]
    return [M[i][k] / M[i][i] for i in range(k)]


def main():
    gdp_lcu = world_bank_series('gdp_lcu.json')
    gdp_usd = world_bank_series('gdp_usd.json')
    gdp_per_head_ppp = world_bank_series('wb_NY.GDP.PCAP.PP.KD.json')
    big_city_share = world_bank_series('wb_EN.URB.MCTY.TL.ZS.json')
    land = oecd_land()

    full, household_only = {}, {}
    for (iso3, sector), by_year in land.items():
        years = [y for y in by_year if y in gdp_lcu.get(iso3, {})]
        if not years:
            continue
        y = max(years)
        if sector == 'S1' and iso3 not in PARTIAL_REPORTERS:
            full[iso3] = {'year': y, 'land_lcu': by_year[y], 'land_to_gdp': by_year[y] / gdp_lcu[iso3][y]}
        if sector == 'S1M':
            household_only[iso3] = {'year': y, 'land_lcu': by_year[y], 'household_land_to_gdp': by_year[y] / gdp_lcu[iso3][y]}

    # households' share of all land, matched years
    shares = {}
    for iso3 in full:
        s1, hh = land[(iso3, 'S1')], land.get((iso3, 'S1M'), {})
        common = sorted(set(s1) & set(hh))
        if common:
            shares[iso3] = hh[common[-1]] / s1[common[-1]]
    share_values = sorted(shares.values())
    print(f'Full reporters: {len(full)}  {sorted(full)}')
    print(f'Household share of all land (matched years, n={len(share_values)}): min {share_values[0]:.2f}, '
          f'median {statistics.median(share_values):.2f}, max {share_values[-1]:.2f}')

    # US check of the household scaling: Fed/OECD household land 2015 vs BEA researchers' private land 2015 (Wentland et al 2023: $24.1 trn)
    us_hh_2015 = land[('USA', 'S1M')]['2015']
    print(f'US 2015 household land ${us_hh_2015/1e12:.1f} trn; Wentland et al private land $24.1 trn -> household share {us_hh_2015/24.1e12:.2f}')

    household_only_countries = {c: v for c, v in household_only.items() if c not in full and c not in PARTIAL_REPORTERS}
    print(f'Household-only reporters: {len(household_only_countries)}  {sorted(household_only_countries)}')

    # ---- model for non-reporters: fit on full reporters, score leave-one-out and on household-only reporters ----
    def covariates(iso3):
        p = latest(gdp_per_head_ppp.get(iso3))
        b = latest(big_city_share.get(iso3))
        return p, (b if b is not None else 0.0)

    fit_rows = [(iso3, math.log(v['land_to_gdp']), *covariates(iso3)) for iso3, v in sorted(full.items())]
    print('\nFull reporters: iso3 year land/GDP GDPpc(PPP) %pop in 1m+ cities')
    for (iso3, y, p, b), v in zip(fit_rows, (full[r[0]] for r in fit_rows)):
        print(f'  {iso3} {v["year"]} {math.exp(y):.2f} {p:,.0f} {b:.1f}')

    designs = {
        'constant': lambda p, b: [1.0],
        'big-city share': lambda p, b: [1.0, b / 100],
        'GDP per head': lambda p, b: [1.0, math.log(p)],
        'GDP per head + big-city share': lambda p, b: [1.0, math.log(p), b / 100],
    }
    results = {}
    hh_rows = [(iso3, math.log(v['household_land_to_gdp'] / HOUSEHOLD_SHARE_ASSUMED), *covariates(iso3))
               for iso3, v in sorted(household_only_countries.items()) if covariates(iso3)[0]]
    for name, design in designs.items():
        X = [design(p, b) for _, _, p, b in fit_rows]
        Y = [y for _, y, _, _ in fit_rows]
        beta = ordinary_least_squares(X, Y)
        loo = []
        for i in range(len(Y)):
            b_i = ordinary_least_squares(X[:i] + X[i + 1:], Y[:i] + Y[i + 1:])
            loo.append(Y[i] - sum(bb * xx for bb, xx in zip(b_i, X[i])))
        loo_rmse = math.sqrt(sum(e * e for e in loo) / len(loo))
        oos = [y - sum(bb * xx for bb, xx in zip(beta, design(p, b))) for _, y, p, b in hh_rows]
        oos_rmse = math.sqrt(sum(e * e for e in oos) / len(oos))
        oos_bias = sum(oos) / len(oos)
        implied = {c: math.exp(sum(bb * xx for bb, xx in zip(beta, design(*covariates(c))))) for c in ('CHN', 'IND', 'BRA', 'RUS', 'IDN', 'CHE')}
        results[name] = {'beta': beta, 'loo_factor': math.exp(loo_rmse), 'household_only_oos_factor': math.exp(oos_rmse),
                         'household_only_oos_bias_factor': math.exp(oos_bias), 'implied_land_to_gdp': implied}
        print(f'\n{name}: beta {[round(x, 2) for x in beta]}; leave-one-out error factor {math.exp(loo_rmse):.2f}; '
              f'on {len(hh_rows)} household-only countries (scaled by {HOUSEHOLD_SHARE_ASSUMED}): error factor {math.exp(oos_rmse):.2f}, bias ×{math.exp(oos_bias):.2f}')
        print('   implied land/GDP: ' + ', '.join(f'{c} {r:.2f}' for c, r in implied.items()))

    # ---- world total under the constant and big-city models ----
    world_gdp = latest(gdp_usd['WLD'], '2024')
    totals = {}
    for name in ('constant', 'big-city share'):
        beta = results[name]['beta']
        design = designs[name]
        parts = {'official': 0.0, 'household_scaled': 0.0, 'modelled': 0.0}
        for iso3, series in gdp_usd.items():
            if iso3 in AGGREGATES or len(iso3) != 3:
                continue
            g = latest(series, '2024')
            if not g:
                continue
            if iso3 in full:
                parts['official'] += full[iso3]['land_to_gdp'] * g
            elif iso3 in household_only_countries:
                parts['household_scaled'] += household_only_countries[iso3]['household_land_to_gdp'] / HOUSEHOLD_SHARE_ASSUMED * g
            else:
                p, b = covariates(iso3)
                if p is None:
                    p = 15000.0
                parts['modelled'] += math.exp(sum(bb * xx for bb, xx in zip(beta, design(p, b)))) * g
        total = sum(parts.values())
        totals[name] = {**{k: v / 1e12 for k, v in parts.items()}, 'total_usd_trn': total / 1e12, 'times_world_gdp': total / world_gdp}
        print(f'\nWorld total with "{name}" model for non-reporters: ' + ', '.join(f'{k} ${v:.0f} trn' for k, v in totals[name].items() if k != 'times_world_gdp')
              + f' ({totals[name]["times_world_gdp"]:.2f} × world GDP)')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({'full_reporters': full, 'household_only': household_only_countries, 'household_shares_matched_years': shares,
               'household_share_assumed': HOUSEHOLD_SHARE_ASSUMED, 'models': results, 'world_totals': totals}, open(OUT, 'w'), indent=1)


if __name__ == '__main__':
    main()

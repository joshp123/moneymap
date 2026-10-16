Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent). Figures were fetched or computed by the agent unless marked [inferred].

# Placing GDP where it is produced

## Problem

Kummu 2026 places each unit's GDP where people live (GDP per head × population). Its finest reported inputs are coarse (OECD TL3: the US has 179 BEA Economic Areas; London has "Camden and City of London"), and its 43,501 admin-2 units are machine-learning estimates. Job centres are badly under-counted:

- Manhattan gets 0.97% of mainland-US GDP (official 3.52%).
- City of London gets 0.05% of England and Wales GVA (official 4.98%).
- Westminster gets 0.73% (official 4.32%).

Most of the error comes from coarse control totals. No proxy fixes that alone.

## Tests run

"Misallocated" = share of GDP put in the wrong unit. Lower is better.

| Test (units, source) | Population | Proposed | Kummu |
|---|---|---|---|
| UK MSOA within local authority (7,199; ONS 2023) | 39.5% | **27.6%** | 39.5% |
| US county within state (3,057; BEA 2024) | 17.5% | **14.0%** | 15.6% |
| EU NUTS3 within NUTS2 (1,245; Eurostat 2023) | 9.9% | 9.5% | 3.6%* |
| NL COROP-plus within COROP (19; CBS 2023) | 7.2% | 7.4% | – |
| Brazil municipality within state (5,570; IBGE 2023) | 19.6% | 18.7% | 9.3%* |

\*Not independent: Kummu used these regions or similar data as inputs.

"Proposed" = 0.5 × population share + 0.5 × share of height-weighted non-residential volume.

- Calibration: on UK local authorities split in half 50 times, the best population weight was 0.18–0.30 (held-out error 39.4% → 26.8%). Best elsewhere: 0.45 (US), 0.70 (EU), 0.75 (Brazil). 0.5 helps or does no harm everywhere.
- Local examples (share of the local authority's GVA: actual / population / proposed): Heathrow 25% / 4% / 25%; Canary Wharf 60% / 2% / 16%; West End 26% / 4% / 11%; Manchester centre 24% / 2% / 7%. Office cores stay 2–4× too low, so fine official control totals matter most.

What failed:
- NRES volume alone: Paris gets 5% of Île-de-France (actual 32%); Manhattan 6% of New York State (actual 43%). [inferred] GHSL classes mixed-use cores as residential and under-estimates tall buildings.
- Plain NRES volume in the mix: pushes GDP into greenhouses and sheds (Haarlemmermeer/Aalsmeer/Uithoorn gets 37% of Groot-Amsterdam, actual 19%). Height weighting fixes this.
- NRES surface: worse than volume in every test.
- LandScan 2022 ambient population: 37.2% vs 39.5% in the UK test. Not worth adding.
- Population^1.2: helps coarse tests, not the MSOA test.
- Night lights: excluded; EOG VIIRS and NASA Black Marble need accounts.

Ready-made products: none better. Kummu is residence-based; Rossi-Hansberg & Zhang is 0.25° at best; Chen et al. 2022 ends in 2019; Wang & Sun 2022 is a 2005 base; Paprotny 2025 uses population and total built-up surface [inferred: not workplace-based].

## Grid alignment

GHS-BUILT-V NRES and GHS-BUILT-S NRES 2025, 4326, 30ss are 43,201 × 21,384 cells, origin (−180.0012492647, 89.0995831776): same cell size as GHS-POP but shifted 0.8 cell east. Shift: POP column k = 0.8 × BUILT[k−1] + 0.2 × BUILT[k]. Exact alternative: the 3ss files (432,002 × 213,822, origin −180.0004159313, 89.0920831777) nest 10 × 10 into GHS-POP cells; NRES-V 3ss zip is 365 MB. Licence CC BY 4.0.

## Official figures for checks

- New York County (Manhattan): GDP 2024 $1,006.7bn current dollars (BEA, 5 Feb 2026; 2023 $935.7bn).
- City of London: GDP 2024 £114.7bn; GVA £112.7bn (ONS, 23 Sep 2026).
- Westminster: GDP 2024 £102.5bn; GVA £100.2bn.
- Groot-Amsterdam (NUTS 2024 NL32B, was NL329): €162.9bn (2023); €172.5bn (2024 provisional).
- Groot-Rijnmond (NL366, was NL33C): €92.9bn (2023); €97.4bn (2024 provisional).
- Haarlemmermeer: no municipal figure. CBS "Haarlemmermeer en omgeving" (with Aalsmeer, Uithoorn): €31.2bn (2023), €33.0bn (2024 provisional), €137k per resident.
- Amsterdam municipality: €116.4bn (2023).

## Data

| File | Size |
|---|---|
| `GHS_BUILT_V_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip` | 39.6 MB |
| `GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip` | 37.3 MB |
| Kummu `polyg_adm1_gdp_perCapita_1990_2024.gpkg` / `polyg_adm2_...` | 13.0 / 41.8 MB |
| BEA `CAGDP1.zip` | 1.9 MB |
| Census `cb_2024_us_county_500k.zip` | 11.6 MB |
| Eurostat `nama_10r_3gdp` | ~1 MB (API) |
| GISCO `NUTS_RG_01M_2024_4326_LEVL_3.geojson` | 27.6 MB |
| ONS `uksmallareagvaestimates1998to2023.xlsx` | 14.9 MB |
| ONS LSOA Dec 2011 BGC V3 boundaries | ~44 MB (ArcGIS service, 18 pages) |
| Scottish data zone and NI SOA boundaries | not checked |
| CBS 85924NED and PDOK `coropplusgebied_gegeneraliseerd` | small (APIs) |
| Validation only: IBGE SIDRA 5938 and IBGE malhas | 1.6 / 3.6 MB |

Sources: GHSL `https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/` (`GHS_BUILT_V_GLOBE_R2023A/`, `GHS_BUILT_S_GLOBE_R2023A/`); Kummu https://zenodo.org/records/18429133; BEA `https://apps.bea.gov/regional/zip/`; Census `https://www2.census.gov/geo/tiger/GENZ2024/shp/`; Eurostat `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10r_3gdp`; GISCO `https://gisco-services.ec.europa.eu/distribution/v2/nuts/`; ONS https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates; CBS `https://opendata.cbs.nl/ODataApi/OData/85924NED`; PDOK `https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1`.

## Recommended method (agent)

1. Control units: finest official GDP. US counties (BEA 2024; map BEA's merged Virginia independent cities). UK small areas (ONS 2023). EU27 + AL, ME, MK, RS, TR: NUTS3 (Eurostat 2023). Netherlands: COROP-plus (CBS, 52 units). Elsewhere: Kummu units.
2. Keep Kummu country totals; replace only within-country shares: unit total = Kummu country total × official unit value ÷ official country sum. No currency, PPP or year conversion needed.
3. Weight each cell within its unit: 0.5 × population share + 0.5 × share of q, where q = NRES volume × NRES mean height = volume² ÷ surface, shifted onto the POP grid. No NRES in unit → population only.
4. Cell GDP = unit total × weight. Units too small to hold a cell centre go to the cell holding their centroid. Every unit and country total must be reproduced exactly.
5. One parameter, 0.5.

Claude's change: for "elsewhere", use Kummu's reported admin-1 units, not its machine-learned admin-2 units. In the US test, spreading from states (14.0%) beat Kummu's admin-2 estimates (15.6%).

## Validation plan

1. Hold-out by level: build with control totals one level coarser and score against finer official units. Measures: misallocated share; median |log(predicted ÷ actual)|.
2. Named places: circles at Bank, Canary Wharf, Heathrow, Midtown, Zuidas, Schiphol, Maasvlakte against official totals of the units inside.
3. Conservation: every unit and country total reproduced; global total stays $196.88 trillion.

## Experiment: Overture places as a workplace proxy

Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent). Code in `research/gdp/places_*.py`; outputs in `data/experiments/places/`.

Overture places release 2026-09-23.1: 80.5 million open places in 5.9 million cells (`scripts/extract_places.sql`, `data/raw/overture/places_per_cell.parquet`). "Workplace" places (13.9 million): office, finance, legal, professional, real estate, media, design, technical, telecoms, business-to-business (not agriculture), industrial, government offices, education offices, research institutes; list fixed before scoring. Licence CDLA Permissive 2.0 and Apache 2.0; credit "Overture Maps Foundation, overturemaps.org".

Share of GDP in the wrong unit (median |log ratio|), same production control totals:

| Weighting | US county in state | UK MSOA in LA | EU NUTS3 in NUTS2 | Brazil municipality in state |
|---|---|---|---|---|
| Population only | 17.35% (0.420) | 39.47% (0.669) | 9.87% (0.139) | 19.62% (0.545) |
| ½ pop + ½ q (v2) | 13.95% (0.258) | 27.86% (0.453) | 9.48% (0.134) | 18.64% (0.272) |
| ⅓ pop, ⅓ q, ⅓ workplace places | **11.58% (0.239)** | **24.66% (0.410)** | 7.46% (0.104) | **16.59% (0.266)** |

The ⅓ mix beats v2 in 49 of 50 US states, 265 of 316 UK local authorities, 192 of 232 EU NUTS2 regions and 18 of 26 Brazilian states. Circles (billions, 2021 international dollars), v2 → ⅓ mix: Midtown/Lower Manhattan 6 km 785 → 882; Tokyo Marunouchi 3 km 86 → 137; Bank 3 km 346 → 346; Zuidas 30 → 34; Schiphol 8 → 7; La Défense 92 → 87. Manhattan's share of New York State: 11.0% → 17.1% (official 43.4%).

Risk: workplace-place coverage in the tested countries is 3.9 (Brazil) to 16.8 (Germany) per 1,000 people; Japan 2.2, India 0.6, China 0.01. Claude's rule: use the places term only in control units with at least 3.9 workplace places per 1,000 residents (the lowest validated coverage); elsewhere keep ½ pop + ½ q.

Written by AI on 2026.10.16 by model gpt-6.1-sol; moved from the README and reorganised by model claude opus 5.5.

# How the numbers are calculated

A circle's totals are the sums of every 30 arc-second grid cell (about 1 km across) whose centre lies within the chosen great-circle distance of the clicked point. The table gives the same sums within each whole kilometre.

- **Population** is GHS-POP R2023A residents in 2025, unchanged.
- **GDP** is purchasing power parity (PPP), in 2021 international dollars. Country totals are Kummu et al.'s 2024 figures. Within each country, GDP is placed where it is produced, as described below.
- **Land value** excludes buildings, in 2024 US dollars at market exchange rates. National balance sheets and a fixed model supply country totals; density-weighted population and production GDP supply their spatial shares.
- **Stops** are bus, tram, and metro and train stops from OpenStreetMap via Overture Maps, counted in the cell that contains them.

All layers share one grid and tile format, described in `layers/grid.py`. The Worker (`worker/index.js`) reads the tiles and sums them.

## GDP

### Totals for each region

Keep each country's total from Kummu's 2024 GDP raster. Within the US, use BEA 2024 county GDP shares; within the UK, ONS 2023 small-area GVA shares for England and Wales LSOAs, Scottish data zones and Northern Ireland SOAs; within the Netherlands, CBS 2023 COROP-plus shares. Other EU27 countries and Albania, Montenegro, North Macedonia, Serbia and Turkey use Eurostat 2023 NUTS3 shares on GISCO 2024 boundaries. Everywhere else keeps Kummu's reported admin-1 unit totals, or the whole country where reported subnational data is absent. Official values supply shares only, without currency, year or PPP conversion. These are the control units (`sources/regional_gdp.py`).

Grid ownership uses cell centres in Kummu's reported polygons. Occupied coastal cells outside those polygons go to the nearest reported unit, preserving every source dollar. Allocation uses the finer official boundaries where available, including coastal enclaves omitted from Kummu's coarse outline. Remaining boundary gaps are filled with the nearest official unit in the same country. BEA's combined counties are joined before rasterisation. The five French overseas departments keep their separate Kummu country totals. Official shares use spatial unit sums, excluding unlocated extra-regio GDP (`layers/gdp/cell_ownership.py`).

### Within each region

Each control unit's GDP is spread over its cells by one rule (`layers/gdp/allocation.py`), in order of preference:

1. **US counties** split their GDP by twenty BEA CAGDP2 2024 industry shares. Each industry follows its LODES workplace jobs weighted by the block's high-pay share. An industry with GDP but no jobs in its county follows all high-pay jobs in that county. A county without high-pay jobs falls through to the next rule; all 3,115 counties have them.
2. **Units with at least 3.9 workplace places per 1,000 residents**, and with both population and building weight, use equal thirds of population, building weight q and workplace places.
3. **Other units** use half population and half q. A unit without q uses population; a unit without population uses q. If neither is present, the unit's total goes in the cell holding its centroid. This also covers units too small to contain a cell centre.

The building weight is q = non-residential building volume² / non-residential building surface, from GHSL's 2025 built-up grids. It favours tall buildings over large sheds. Compute q on the GHSL built-up grid, then shift it to the population grid: population column k receives 0.8 of built-up column k−1 and 0.2 of built-up column k (`layers/gdp/building_weight.py`).

Workplace places are Overture places in office, business-service, industrial, government-office and research categories (`sources/overture_places.sql`). Permanently closed places are excluded, with no confidence filter. The weights and threshold are fixed. There are 591 workplace places outside every control unit; they receive no allocation.

LODES8 workplace blocks use their crosswalk internal points on the same 30 arc-second grid (`sources/lodes_jobs.py`). The crosswalk county field supplies the current county geography, including Connecticut planning regions; block-code county prefixes are older. All 50 states and DC use their latest available `S000_JT00` release: 2023 except Alaska (2016) and Michigan (2021). The grid exactly reproduces 150,944,613 total jobs and 86,331,982 high-pay jobs. Cell ownership leaves 2,741 jobs, including 1,138 high-pay jobs, outside US-owned cells (0.0018% and 0.0013%); they supply no allocation weight. Cell mapping puts 0.471% of jobs in a neighbouring county, including 0.044% across state boundaries.

Nineteen private BEA sectors map to LODES `CNS01`–`CNS19` in the private-jobs file (`JT02`); its few `CNS20` jobs join other services. Each private industry's jobs are multiplied by private high-pay jobs divided by private total jobs in that block. Government jobs are all jobs (`JT00`) minus private jobs, and government high-pay jobs are the same difference in `CE03`. This keeps public schools and hospitals in government. High-pay means more than $3,333 a month. Summing industry weights reproduces the block's high-pay jobs (`sources/lodes_jobs.py`).

Suppressed CAGDP2 values are first solved from published accounting identities when only one term is missing. Remaining suppressed values share the residual of their nearest published parent in proportion to county industry jobs times state GDP per job. Published leaves remain intact apart from rescaling small BEA rounding differences to the county total. This is the fixed experiment rule, implemented in `sources/us_industry_gdp.py`. Country and county totals do not change.

### How the rule was chosen

Each step was checked against official GDP in hold-outs: give a coarse official region its official total, spread it with the rule, and score the result against the official figures of the finer units inside it. The measures are the share of GDP placed in the wrong unit and the median absolute log ratio. `checks/holdouts.py` reruns the tests below with the production allocation. Allocation is linear within each region, so it can run on per-unit sums; float32 rounding then happens per unit rather than per cell.

Workplace places (rule 2) against half population and half q, on the research's per-unit sums. US, EU and Brazil use cell centres; the UK uses 10 by 10 cell area fractions over LSOAs aggregated to MSOAs. The coverage threshold is evaluated for each coarse region. Seven of eight measures improve. Brazil's median absolute log ratio rises from 0.271781 to 0.272562 while its misplaced-GDP share improves from 18.639% to 17.475%. This trade-off was accepted on 16 October 2026 without tuning.

| Hold-out | Wrong GDP share, without → with places | Median absolute log ratio, without → with places |
|---|---:|---:|
| US county within state | 13.9505% → 11.5775% | 0.257668 → 0.238962 |
| UK MSOA within local authority | 27.8611% → 24.6816% | 0.452986 → 0.411275 |
| EU NUTS3 within NUTS2 | 9.4753% → 7.6471% | 0.134169 → 0.113103 |
| Brazil municipality within state | 18.6390% → 17.4750% | 0.271781 → 0.272562 |

US industries (rule 1): give each state its CAGDP2 2024 industry shares, normalised to its county GDP sum, and hold out BEA county totals. The production industry allocator is used for both cells and held-out counties. All 3,115 counties and 51 state/DC groups are included; DC contributes no within-state error. The adopted rule improves wrong-county GDP from 6.2128% to 5.0810%, reproducing the experiment to float32 rounding. Its median absolute log ratio is 0.146408, against 0.146553 for high-pay jobs alone.

| State → county hold-out | High-pay jobs only | Industry high-pay jobs |
|---|---:|---:|
| All US counties | 6.2128% | 5.0810% |
| Bay Area, nine counties | 12.2905% | 8.4027% |
| Seattle, King/Pierce/Snohomish | 7.1475% | 1.8625% |
| New York City, five boroughs | 11.2253% | 1.8427% |

The research behind these choices, including the alternatives that failed, is in [GDP method research](gdp-method-research.md) and `research/gdp/`.

### Conservation

The GDP build (`layers/gdp/build.py`) stops unless every unit, country and the world total is reproduced, and reads its tiles back to check them. Checked locally on 16 October 2026: all 48,314 control totals and 235 country totals pass float32 conservation. Maximum relative errors are 5.95 × 10⁻⁸ per unit and 2.00 × 10⁻⁸ per country. Source GDP is $196,879,262,625,395; built GDP is $196,879,262,607,198.09, a $18,196.91 float32 difference across $196.8792626 trillion. Tile read-back differs from the built-grid sum by $0.97 from float64 summation order. GDP has 15,476 tiles, 891,417,600 bytes.

All 3,115 US counties use industry high-pay jobs. Industry GDP without weighted jobs in its county uses the county high-pay fallback, covering 0.0834% of US GDP. The places rule applies to 16,757 other control units, holding 21.37% of world GDP. Against the previous build, every control target and cell owner is identical, and all 907,888,781 cells outside US counties have bit-for-bit identical GDP.

## Land value

`sources/land_value.py` supplies targets for the same 235 countries and territories as GDP. Fourteen countries use OECD Table 9B whole-economy land; thirteen use household land divided by 0.6. The latest land/GDP ratio in local currency scales each OECD figure to 2024 market-exchange-rate GDP. Mexico, Croatia and New Zealand do not count as whole-economy reporters. Taiwan uses DGBAS's 2024 land total of NT$134.12 trillion, converted at the Taiwan Central Bank's annual rate of NT$32.108 per US dollar.

The remaining 207 use the research's fixed big-city-share model: land/GDP = exp(0.1675025123 + 1.7479479322 × share of people in cities over one million). The coefficients reproduce the fit to the fourteen whole-economy reporters. GDP and city shares come from the World Bank; UN Statistics Division GDP fills twelve missing or older 2024 entries. Eighteen small territories without market GDP use Kummu PPP GDP multiplied by a named reference country's market/PPP ratio. They hold 0.0561% of world PPP GDP. Six territories retain their latest available, explicitly dated GDP from 2021–2023; missing city shares use zero, as in the research. Every target, source, year and conversion reference is written to `data/build/land_value/country_totals.csv`; raw-file provenance is in `data/raw/land-value/sources.json`.

`layers/land_value/` allocates each target using equal halves of normalised population × neighbourhood density^0.25 and normalised production GDP. Density uses an exponential great-circle kernel with a fixed 40 km scale. Population is summed onto a 5 arc-minute grid, convolved globally with latitude-specific spherical kernels, then bilinearly interpolated to cell centres. The kernel ends at 320 km and is renormalised; longitude is periodic. Cell country ownership is reused directly from the GDP build. There is no farmland or building term, and no parameter is fitted to the checked places.

### Totals and conservation

| National source | Countries and territories | Land value, USD trillion |
|---|---:|---:|
| OECD whole economy | 14 | 62.324887 |
| OECD household / 0.6 | 13 | 68.312411 |
| Taiwan DGBAS | 1 | 4.177152 |
| Big-city-share model | 207 | 104.427574 |
| World | 235 | 239.242023 |

The world total is slightly above the research's expected range. The research's $237.762 trillion total included the World Bank fragile/conflict aggregate as a country ($3.003 trillion) and omitted Taiwan ($4.177 trillion). Production uses only the 235 GDP country codes and fills missing or stale market GDP as described above; the model coefficients and allocation weights are unchanged.

All 235 country totals pass float32 conservation. Target land value is $239,242,023,248,406.94; the grid sums to $239,242,023,225,615.94, a $22,791 rounding difference. The maximum country relative error is 1.66 × 10⁻⁸. Tile read-back is $239,242,023,225,616.03, differing by nine cents from summation order. The layer has 15,608 tiles, 899,020,800 bytes.

### Held-out official valuations

`checks/land_value.py` sums the actual production grid over the research's official boundaries. Scores compare spatial shares, scaling the prediction to the official total within the valued area. The US comparison is residential land. All official unit keys and values match the research inputs.

| Hold-out | Units | Fable wrong-value share | Production wrong-value share | Production median absolute log ratio |
|---|---:|---:|---:|---:|
| NRW municipalities | 396 | 14.5663% | 14.7975% | 0.278170 |
| Japan municipalities | 1,719 | 19.1417% | 19.1453% | 0.655367 |
| US residential counties | 2,423 | 28.9009% | 28.8835% | 0.791316 |
| Denmark municipalities | 98 | 14.6723% | 14.7177% | 0.259357 |

The small differences come from global density, country-wide component normalisation and the newer US GDP layer. NRW with production density but locally normalised components scores 14.4721%; normalising components over Germany accounts for the remaining change. Updated US industry GDP changes its locally normalised score from 28.8891% to 28.8834%. The check report keeps these comparisons separately in `data/checks/land_value.json`.

The method research and independent review are in [land value research](land-value-research.md).

## Transit stops

Stops come from Overture Maps' OpenStreetMap-derived transit infrastructure, with class rules that reproduce Tom Forth's counts (`sources/overture_stops.sql`, [stop research](stops-research.md)). Stop tiles reproduce the source totals exactly: 4,167,514 bus, 51,083 tram and 138,265 metro and train stops. Amsterdam 5 km returns 684/352/33 against Tom's 696/345/33; Rotterdam 50 km returns 11,645/900/238 against 11,622/1,036/180.

## Circle checks

`checks/circles.py` queries the real Worker for 36 named circles and checks every total and cumulative kilometre row against direct sums over the GDP and land grids, GHS-POP and the stop counts. None of these reads a tile. Campus radii below the API's 3 km minimum use the existing 1 km or 2 km cumulative row. All checks pass; GDP, population and stops are unchanged by adding land. All 18 industry-experiment circles also match its results to float32 rounding.

GDP within US circles, in billions of 2021 international dollars:

| Circle | Radius km | High-pay jobs | Industry high-pay jobs |
|---|---:|---:|---:|
| Midtown and Lower Manhattan | 6 | 1049.396 | 1098.167 |
| Mountain View | 10 | 193.591 | 222.840 |
| Palo Alto | 10 | 174.936 | 205.788 |
| SF Financial District | 3 | 199.902 | 214.859 |
| San Jose | 10 | 196.174 | 177.562 |
| San Francisco | 10 | 278.429 | 277.589 |
| Cupertino | 5 | 48.397 | 40.786 |
| Menlo Park | 5 | 53.160 | 81.507 |
| Santa Clara | 5 | 117.293 | 113.899 |
| Seattle South Lake Union | 3 | 136.334 | 126.944 |
| Redmond | 5 | 61.712 | 91.873 |
| Apple Park | 1 | 20.910 | 18.985 |
| Meta, Menlo Park | 1 | 22.826 | 50.919 |
| Googleplex | 2 | 24.124 | 37.639 |
| Googleplex | 3 | 31.715 | 45.798 |
| Nvidia, Santa Clara | 1 | 10.430 | 10.574 |
| Nvidia, Santa Clara | 2 | 28.403 | 32.568 |
| Microsoft, Redmond | 1 | 26.743 | 52.290 |
| Microsoft, Redmond | 3 | 35.067 | 61.104 |
| Amazon, South Lake Union | 2 | 90.100 | 82.209 |

The non-US GDP circle results are unchanged. Preserve a circle report before rebuilding, then pass `--compare data/checks/circles-high-pay.json` to reproduce the old/new GDP comparison. Add `--unchanged-gdp` when checking a change that must preserve GDP.

Land within the requested circles, in billions of 2024 US dollars:

| Circle | Radius km | Land value |
|---|---:|---:|
| Cologne cathedral | 3 | 32.419 |
| Cologne cathedral | 10 | 143.068 |
| Düsseldorf | 10 | 126.221 |
| Gelsenkirchen | 10 | 102.359 |
| Amsterdam | 5 | 140.541 |
| Rotterdam | 50 | 996.207 |
| Midtown and Lower Manhattan | 6 | 1,096.066 |
| London Bank | 3 | 439.409 |
| Tokyo Marunouchi | 3 | 86.190 |
| Sydney | 10 | 440.398 |

Warm local preview queries including land take 2.15–2.63 ms for Rotterdam 50 km and 4.72–4.94 ms for Paris 100 km, excluding remote storage latency. The page was checked in Safari on desktop and at a 375 px responsive viewport, including switching all three modes and changing the radius.

## History

The site was built in five steps on 16 October 2026: Kummu's GDP as published; official regional controls and the building weight; workplace places and transit stops; US workplace jobs; US industry workplace jobs. Earlier grids and check results are kept locally under `data/`, outside git. The preceding high-pay build is in `data/build/gdp-high-pay/`, and its Worker results are in `data/checks/circles-high-pay.json`.

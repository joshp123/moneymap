Written by AI on 2026.10.16 by model gpt-6.1-sol; moved from the README and reorganised by model claude opus 5.5.

# How the numbers are calculated

A circle's totals are the sums of every 30 arc-second grid cell (about 1 km across) whose centre lies within the chosen great-circle distance of the clicked point. The table gives the same sums within each whole kilometre.

- **Population** is GHS-POP R2023A residents in 2025, unchanged.
- **GDP** is purchasing power parity (PPP), in 2021 international dollars. Country totals are Kummu et al.'s 2024 figures. Within each country, GDP is placed where it is produced, as described below.
- **Stops** are bus, tram, and metro and train stops from OpenStreetMap via Overture Maps, counted in the cell that contains them.

All layers share one grid and tile format, described in `layers/grid.py`. The Worker (`worker/index.js`) reads the tiles and sums them.

## GDP

### Totals for each region

Keep each country's total from Kummu's 2024 GDP raster. Within the US, use BEA 2024 county GDP shares; within the UK, ONS 2023 small-area GVA shares for England and Wales LSOAs, Scottish data zones and Northern Ireland SOAs; within the Netherlands, CBS 2023 COROP-plus shares. Other EU27 countries and Albania, Montenegro, North Macedonia, Serbia and Turkey use Eurostat 2023 NUTS3 shares on GISCO 2024 boundaries. Everywhere else keeps Kummu's reported admin-1 unit totals, or the whole country where reported subnational data is absent. Official values supply shares only, without currency, year or PPP conversion. These are the control units (`sources/regional_gdp.py`).

Grid ownership uses cell centres in Kummu's reported polygons. Occupied coastal cells outside those polygons go to the nearest reported unit, preserving every source dollar. Allocation uses the finer official boundaries where available, including coastal enclaves omitted from Kummu's coarse outline. Remaining boundary gaps are filled with the nearest official unit in the same country. BEA's combined counties are joined before rasterisation. The five French overseas departments keep their separate Kummu country totals. Official shares use spatial unit sums, excluding unlocated extra-regio GDP (`layers/gdp/cell_ownership.py`).

### Within each region

Each control unit's GDP is spread over its cells by one rule (`layers/gdp/allocation.py`), in order of preference:

1. **US counties** follow high-pay workplace jobs: LODES `CE03`, jobs paying more than $3,333 a month. A county without high-pay jobs would fall through to the next rule; all 3,115 counties have them.
2. **Units with at least 3.9 workplace places per 1,000 residents**, and with both population and building weight, use equal thirds of population, building weight q and workplace places.
3. **Other units** use half population and half q. A unit without q uses population; a unit without population uses q. If neither is present, the unit's total goes in the cell holding its centroid. This also covers units too small to contain a cell centre.

The building weight is q = non-residential building volume² / non-residential building surface, from GHSL's 2025 built-up grids. It favours tall buildings over large sheds. Compute q on the GHSL built-up grid, then shift it to the population grid: population column k receives 0.8 of built-up column k−1 and 0.2 of built-up column k (`layers/gdp/building_weight.py`).

Workplace places are Overture places in office, business-service, industrial, government-office and research categories (`sources/overture_places.sql`). Permanently closed places are excluded, with no confidence filter. The weights and threshold are fixed. There are 591 workplace places outside every control unit; they receive no allocation.

LODES8 workplace blocks use their crosswalk internal points on the same 30 arc-second grid (`sources/lodes_jobs.py`). The crosswalk county field supplies the current county geography, including Connecticut planning regions; block-code county prefixes are older. All 50 states and DC use their latest available `S000_JT00` release: 2023 except Alaska (2016) and Michigan (2021). The grid exactly reproduces 150,944,613 total jobs and 86,331,982 high-pay jobs. Cell ownership leaves 2,741 jobs, including 1,138 high-pay jobs, outside US-owned cells (0.0018% and 0.0013%); they supply no allocation weight. Cell mapping puts 0.471% of jobs in a neighbouring county, including 0.044% across state boundaries.

The California research summed block internal points directly; production keeps the 30″ cell-centre rule. Mountain View 10 km is $209.298bn at block points, $194.017bn after mapping those weights to cell centres, and $193.591bn with production county-cell ownership. One block containing 20,192 high-pay jobs moves from 9.758 km to a cell centre at 10.115 km, taking $10.553bn outside the circle. No weight or radius was adjusted.

### How the rule was chosen

Each step was kept only if it placed GDP better in hold-outs: give a coarse official region its official total, spread it with the rule, and score the result against the official figures of the finer units inside it. The measures are the share of GDP placed in the wrong unit and the median absolute log ratio. `checks/holdouts.py` reruns both tests below with the production allocation. Allocation is linear within each region, so it can run on per-unit sums; float32 rounding then happens per unit rather than per cell.

Workplace places (rule 2) against half population and half q, on the research's per-unit sums. US, EU and Brazil use cell centres; the UK uses 10 by 10 cell area fractions over LSOAs aggregated to MSOAs. The coverage threshold is evaluated for each coarse region. Seven of eight measures improve. Brazil's median absolute log ratio rises from 0.271781 to 0.272562 while its misplaced-GDP share improves from 18.639% to 17.475%. This trade-off was accepted on 16 October 2026 without tuning.

| Hold-out | Wrong GDP share, without → with places | Median absolute log ratio, without → with places |
|---|---:|---:|
| US county within state | 13.9505% → 11.5775% | 0.257668 → 0.238962 |
| UK MSOA within local authority | 27.8611% → 24.6816% | 0.452986 → 0.411275 |
| EU NUTS3 within NUTS2 | 9.4753% → 7.6471% | 0.134169 → 0.113103 |
| Brazil municipality within state | 18.6390% → 17.4750% | 0.271781 → 0.272562 |

US jobs (rule 1): four fixed candidates for spreading state GDP to counties, on the per-county sums from the GDP build. All 3,115 counties and 51 state and DC groups are included; DC contributes no within-state error. High-pay jobs place the least GDP in the wrong county.

| US state → county hold-out | Wrong GDP share | Median absolute log ratio |
|---|---:|---:|
| Rules 2 and 3 only | 11.5617% | 0.238842 |
| All jobs | 8.2829% | 0.165260 |
| High-pay jobs, selected | 6.2128% | 0.146553 |
| Half all jobs, half high-pay jobs | 6.9398% | 0.142179 |

The research behind these choices, including the alternatives that failed, is in [GDP method research](gdp-method-research.md) and `research/gdp/`.

### Conservation

The GDP build (`layers/gdp/build.py`) stops unless every unit, country and the world total is reproduced, and reads its tiles back to check them. Checked locally on 16 October 2026: all 48,314 control totals and 235 country totals pass float32 conservation. Maximum relative errors are 5.95 × 10⁻⁸ per unit and 2.01 × 10⁻⁸ per country. Source GDP is $196,879,262,625,395; built GDP is $196,879,262,608,239.22, a $17,155.78 float32 difference across $196.8792626 trillion. All 3,115 US counties use high-pay jobs; the places rule applies to 16,757 other control units, holding 21.37% of world GDP. GDP has 15,476 tiles, 891,417,600 bytes.

## Transit stops

Stops come from Overture Maps' OpenStreetMap-derived transit infrastructure, with class rules that reproduce Tom Forth's counts (`sources/overture_stops.sql`, [stop research](stops-research.md)). Stop tiles reproduce the source totals exactly: 4,167,514 bus, 51,083 tram and 138,265 metro and train stops. Amsterdam 5 km returns 684/352/33 against Tom's 696/345/33; Rotterdam 50 km returns 11,645/900/238 against 11,622/1,036/180.

## Circle checks

`checks/circles.py` queries the real Worker for 22 named circles and checks every total and cumulative kilometre row against direct sums over the GDP grid, GHS-POP and the stop counts. None of these reads a tile. Locally, Rotterdam 50 km and Paris 100 km each take a few milliseconds, excluding remote storage latency.

GDP within named circles, in billions of 2021 international dollars, across the builds:

| Circle | Radius km | Official controls and q | Plus workplace places | Plus US jobs (current) |
|---|---:|---:|---:|---:|
| Midtown and Lower Manhattan | 6 | 785.354 | 881.694 | 1049.396 |
| Bank | 3 | 346.180 | 346.228 | 346.228 |
| Canary Wharf | 3 | 61.561 | 61.569 | 61.569 |
| Zuidas | 3 | 30.367 | 34.467 | 34.467 |
| Schiphol | 3 | 7.826 | 6.531 | 6.531 |
| La Défense | 3 | 91.922 | 87.380 | 87.380 |
| Rotterdam | 50 | 536.525 | 532.599 | 532.599 |
| Tokyo Marunouchi | 3 | 86.342 | 86.342 | 86.342 |
| Shanghai Lujiazui | 3 | 78.854 | 78.854 | 78.854 |
| Beijing Guomao | 3 | 64.639 | 64.639 | 64.639 |
| Mountain View | 10 | | 126.848 | 193.591 |
| Palo Alto | 10 | | 114.755 | 174.936 |
| SF Financial District | 3 | | 139.082 | 199.902 |
| San Jose | 10 | | 236.012 | 196.174 |
| San Francisco | 10 | | 284.119 | 278.429 |
| Cupertino | 5 | | 47.174 | 48.397 |
| Menlo Park | 5 | | 33.010 | 53.160 |
| Santa Clara | 5 | | 80.081 | 117.293 |
| Seattle South Lake Union | 3 | | 76.399 | 136.334 |
| Redmond | 5 | | 36.606 | 61.712 |

Tokyo and the Chinese circles keep half population and half q because their control units fall below the places coverage threshold.

## History

The site was built in four steps on 16 October 2026: Kummu's GDP as published; official regional controls and the building weight; workplace places and transit stops; US workplace jobs. Each step changed only what the tables above show. Earlier grids and their check results are kept locally under `data/gdp-v2/` and `data/gdp-v3/`, outside git.

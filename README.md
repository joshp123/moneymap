Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised and rewritten by model claude opus 5.5.

# moneymap

Click anywhere on the map and choose a radius from 3 to 100 km. moneymap tells you how many people live inside the circle, how many bus, tram, metro and train stops it holds, how much GDP is produced there, and roughly what its land and buildings are worth.

It is live at https://moneymap.jjpcodes.com. It extends Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/), which counts people and stops, by adding GDP and property value.

The page has three modes: population (with stops), GDP, and property value (land plus buildings). Links choose a mode with `mode=gdp` or `mode=property`; older `mode=land` links open property mode.

## How good are the numbers?

Rough. moneymap was built in about a day by Josh directing AI agents, with little human review. Population and stops come straight from open data. GDP, land and building values are estimates: official national and regional totals, spread over a 1 km grid by simple rules. In tests against official figures, 5% to 30% of the value lands in the wrong small area, and some places are much further out, such as Tokyo's centre for land and Manhattan's core for buildings.

[How the numbers are calculated](docs/methodology.md) explains every number, the tests and the known errors, so that anyone can check the work and improve it.

## How it works

Each data layer is one value per 30 arc-second grid cell, stored as tiles in cloud object storage (the Site's R2 bucket). One server script, the Worker, serves the page and `/api/circle`, which sums the cells whose centres lie inside the circle. Python builds the tiles locally from the source data.

```text
worker/index.js           The website: page, circle API and authenticated tile sync endpoints
layers/                   Builds each layer's tiles into data/layers/
  grid.py                 The shared grid, tile format and readers
  population.py           Population layer
  transit_stops.py        Bus, tram and rail stop layers
  building_value.py       National building totals and the compared spatial weights
  gdp/                    GDP layer
    cell_ownership.py     Which regional unit owns each cell
    building_weight.py    Non-residential building weight
    allocation.py         How a unit's GDP is spread over its cells
    build.py              Regional totals, allocation, tiles and conservation checks
  land_value/             Land value excluding buildings
    density.py            Population density in a 40 km neighbourhood
    allocation.py         Equal shares of density-weighted population and GDP
    build.py              Country targets, allocation, tiles and conservation checks
sources/                  External data, extracted to the grid
  regional_gdp.py         Kummu admin-1 and official BEA, ONS, CBS and Eurostat GDP
  overture_places.sql     Workplace places per cell
  overture_stops.sql      Transit stops per cell
  lodes_jobs.py           US jobs and industry high-pay weights per cell
  us_industry_gdp.py      BEA industry shares and suppressed county values
  land_value.py           National land targets and their sources
  building_value.py       National building targets and model selection
  building_valuations.py  NYC official market land and building values
  european_property_values.py  Amsterdam residential WOZ diagnostic
checks/                   Evidence that the numbers are right
  holdouts.py             Scores the GDP rule against official figures held out
  circles.py              Compares the real Worker's answers with the grids
  land_value.py           Checks land against official held-out valuations
  building_value.py       Checks buildings and property against official valuations
deploy/
  build.sh                Builds the Sites artifact in dist/ and stamps the deployed commit
  validate-artifact.mjs   Checks the artifact is an ES module exporting default.fetch
  preview.mjs             Runs the real Worker locally, with data/ as the R2 bucket
  sync-tiles.mjs          Makes the Site's tiles match data/layers/
research/                 Experiments the method came from; the build does not use them, but two checks read their outputs
docs/                     Method and research notes
data/                     Inputs and outputs; local only, not in git
```

## Build and check locally

Tools come from `devenv.nix`; run commands from the repository root. Download these inputs first, under the names the code expects. The research notes sometimes use other names for the same files.

- Kummu GDP: `data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif` and `data/raw/research-gdp/polyg_adm1_gdp_perCapita_1990_2024.gpkg`.
- GHSL, all 2025, 30 arc-seconds: `data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip`, and in `data/raw/research-gdp/` the non-residential volume and surface `nres_v_30ss.zip` and `nres_s_30ss.zip`, and the total built volume `built_v_30ss.zip`.
- US, in `data/raw/research-gdp/`: `cagdp1/CAGDP1__ALL_AREAS_2001_2024.csv`, `cagdp2/CAGDP2__ALL_AREAS_2001_2024.csv`, `county/cb_2024_us_county_500k.shp` and `county_500k.zip`. `sources.lodes_jobs` downloads the LODES `S000_JT00`, `S000_JT02` and crosswalk files into `data/raw/lodes/`, records the releases in `releases.json`, and builds the jobs-by-industry grid from those recorded releases.
- UK, in `data/raw/research-gdp/`: `ons_small_area_gva_2023.xlsx` and the ONS 2011 LSOA boundaries as `lsoa/p*.geojson`. The loader downloads `scotland_dz2011.zip` and `ni_soa2011.zip` if missing.
- Netherlands and Europe, in `data/raw/research-gdp/`: `coropplus_2024.geojson` and the Eurostat 2023 NUTS3 GDP as `nuts3_2023.json`, which the loader does not download. It downloads the CBS table (`cbs_gdp2023.json`) and the GISCO boundaries (`nuts3_2024_01m.geojson`) if missing.
- Land, in `data/raw/land-value/`: `land_all.csv` (OECD Table 9B), `gdp_usd.json`, `gdp_lcu.json` and `wb_EN.URB.MCTY.TL.ZS.json` (World Bank GDP and big-city population), `un-gdp-usd.xlsx` (UN GDP) and `dgbas-table1-2024.xlsx` (Taiwan national wealth). Download URLs and Taiwan's exchange rate are in `sources.json` there.
- Buildings, in `data/raw/building-value/`: `oecd-buildings.csv` (OECD Table 9B building stocks), `gdp-per-head-ppp.json` (World Bank GDP per head at purchasing power parity, used to compare national models) and `dgbas-gdp-2024.xlsx` (Taiwan GDP). Download URLs are in `sources.json` there.
- Valuation checks: the held-out land valuations in `data/experiments/land-value/`, as listed in [the land research](docs/land-value-research.md), which the Victoria, British Columbia and US building checks reuse; NYC Department of Finance values and district boundaries in `data/raw/building-value/nyc/` (`market-values-by-district-2024.json`, `community-districts.geojson`); and the Amsterdam CBS grid in `data/raw/building-value/europe/`, downloaded if missing. Each folder has a `sources.json`.
- The GDP and land checks also read outputs of the research scripts: `data/experiments/places/` from `research/gdp/places_eval.py`, and `data/experiments/land-value/*_scores.json` and `nrw_official_grid.npz` from `research/land-value/`. The build does not need them.

```sh
nix shell nixpkgs#duckdb -c duckdb < sources/overture_places.sql
nix shell nixpkgs#duckdb -c duckdb < sources/overture_stops.sql
devenv shell -- python -m sources.lodes_jobs
devenv shell -- python -m layers.population
devenv shell -- python -m layers.transit_stops
devenv shell -- python -m layers.gdp.build
devenv shell -- python -m layers.land_value.build
devenv shell -- python -m layers.building_value
devenv shell -- python -m checks.holdouts
devenv shell -- python -m checks.land_value
devenv shell -- python -m checks.building_value
devenv shell -- python -m checks.building_value --candidates
devenv shell -- node deploy/preview.mjs
# In another shell, while the preview runs:
devenv shell -- python -m checks.circles
```

Builders write `data/layers/<layer>/<tile row>/<tile column>.bin` and reports in `data/build/`; checks write `data/checks/`. A builder will not overwrite an existing layer: move it aside first. The preview runs the real Worker at http://127.0.0.1:8787 with `data/` standing in for the R2 bucket. Deployment is in [AGENTS.md](AGENTS.md).

The land and building builds each write a `country_totals.csv` and `conservation.json` under `data/build/<layer>/`, with every country's target, source, data year and any GDP conversion reference. The building report also records the national model's leave-one-out scores.

## Licence and credits

The code is under the [MIT licence](LICENSE). The page is adapted from Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/), under CC BY 4.0. The data comes from many publishers, each with its own licence and required attribution; the stop layers derive from OpenStreetMap and are available under the ODbL. All are listed in [Credits and licences](docs/methodology.md#credits-and-licences).

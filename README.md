Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised and rewritten by model claude opus 5.5; land and building split updated on 2026.10.17 by model gpt-6.1-sol.

# moneymap

Click anywhere on the map and choose a radius from 3 to 100 km. moneymap tells you how many people live inside the circle, how many bus, tram, metro and train stops it holds, how much GDP is produced there, and roughly what its land and buildings are worth.

It is live at https://moneymap.jjpcodes.com. It extends Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/), which counts people and stops, by adding GDP and property value.

The page has three modes: population (with stops), GDP, and property value (land plus buildings). Links choose a mode with `mode=gdp` or `mode=property`; older `mode=land` links open property mode.

## How good are the numbers?

Rough. moneymap was built in about a day by Josh directing AI agents, with little human review. Population and stops come straight from open data. GDP, land and building values are estimates: official national and regional totals, spread over a 1 km grid by simple rules. In tests against official figures, 5% to 25% of GDP lands in the wrong small region; land and building errors reach 42% and 32% at US census-tract scale. Some places are much further out, such as Tokyo's centre for land and Manhattan's core for buildings.

[How the numbers are calculated](docs/methodology.md) explains every number, the tests and the known errors, so that anyone can check the work and improve it.

## How it works

Each data layer is one value per 30 arc-second grid cell, stored as tiles in cloud object storage (the Site's R2 bucket). One server script, the Worker, serves the page and `/api/circle`, which sums the cells whose centres lie inside the circle. Python builds the tiles locally from the source data.

The API also returns `place`: the nearest GeoNames `cities15000` point within 200 km, as `{name, country, distance_km}`, or `null`. Country names come from GeoNames `countryInfo.txt`. The Worker loads `data/places/cities.json` from R2 once per isolate and makes no third-party lookup calls. GeoNames is [CC BY 4.0](https://download.geonames.org/export/dump/).

National land and building totals come from balance sheets or simple GDP-based models. Land is split equally between production GDP and residents weighted by local density^0.5 and local income². Density and income use the same exponential 40 km neighbourhood. Buildings follow 70% population share and 30% production GDP share. Both rules preserve every country's total: $239.24 trillion of land and $224.78 trillion of buildings worldwide.

The October 17 split check reduced mean wrong-area share from 22.64% to 20.58% for land (eight tests) and from 19.91% to 18.23% for buildings (five tests). US tract-level land-share ordering improved, but county-level ordering worsened. Honolulu, St Louis, Detroit and Düsseldorf's centre remain problems; the [methodology](docs/methodology.md#known-problems-1) gives the figures.

```text
worker/index.js           The website: page, circle API and authenticated tile sync endpoints
layers/                   Builds each layer's tiles into data/layers/
  grid.py                 The shared grid, tile format and readers
  population.py           Population layer
  transit_stops.py        Bus, tram and rail stop layers
  building_value.py       Building totals spread by population and GDP
  gdp/                    GDP layer
    cell_ownership.py     Which regional unit owns each cell
    building_weight.py    Non-residential building weight
    allocation.py         How a unit's GDP is spread over its cells
    build.py              Regional totals, allocation, tiles and conservation checks
  land_value/             Land value excluding buildings
    density.py            Population density and income in a 40 km neighbourhood
    allocation.py         Equal shares of weighted residents and GDP
    build.py              Country targets, allocation, tiles and conservation checks
sources/                  External data, extracted to the grid
  named_areas.py          Downloads and parses GISCO 2024 and Census 2025 boundaries
  regional_gdp.py         Kummu admin-1 and official BEA, ONS, CBS and Eurostat GDP
  overture_places.sql     Workplace places per cell
  overture_stops.sql      Transit stops per cell
  lodes_jobs.py           US jobs and industry high-pay weights per cell
  us_industry_gdp.py      BEA industry shares and suppressed county values
  land_value.py           National land targets and their sources
  building_value.py       National building targets and model selection
  building_valuations.py  NYC official market land and building values
  european_property_values.py  Amsterdam residential WOZ diagnostic
  geonames.py             Compact worldwide place-name gazetteer
checks/                   Evidence that the numbers are right
  holdouts.py             Scores the GDP rule against official figures held out
  circles.py              Compares the real Worker's answers with the grids
  land_value.py           Checks land against official held-out valuations
  building_value.py       Checks buildings and property against official valuations
  property_split.py       Shared valuation sampling, scores and land-share checks
  named_areas.py          Checks named-area conservation and official regional GDP controls
  named_areas_http.mjs    Runs the served page's area selection and outline checks over HTTP
  named_areas_hosting.mjs Checks Worker area-file serving and sync discovery without uploading
named_areas/              Builds area totals and small static outline files from existing tiles
deploy/
  build.sh                Builds the Sites artifact in dist/ and stamps the deployed commit
  validate-artifact.mjs   Checks the artifact is an ES module exporting default.fetch
  preview.mjs             Runs the real Worker locally, with data/ as the R2 bucket
  sync-tiles.mjs          Syncs data/layers/, data/areas/ and places/cities.json
  areas.md               Area hosting, sync and optional GitHub release download steps
research/                 Experiments and frozen test inputs; not allocation code used by the build
docs/                     Method and research notes
data/                     Inputs and outputs; local only, not in git
  areas/                  Named-area records, click lookup and viewport outlines
```

## Build and check locally

Tools come from `devenv.nix`; run commands from the repository root. Download these inputs first, under the names the code expects. The research notes sometimes use other names for the same files.

- Kummu GDP: `data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif` and `data/raw/research-gdp/polyg_adm1_gdp_perCapita_1990_2024.gpkg`.
- GHSL, all 2025, 30 arc-seconds: `data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip`, and in `data/raw/research-gdp/` the non-residential volume and surface `nres_v_30ss.zip` and `nres_s_30ss.zip`. Total built volume is no longer needed by the building layer.
- US, in `data/raw/research-gdp/`: `cagdp1/CAGDP1__ALL_AREAS_2001_2024.csv`, `cagdp2/CAGDP2__ALL_AREAS_2001_2024.csv`, `county/cb_2024_us_county_500k.shp` and `county_500k.zip`. `sources.lodes_jobs` downloads the LODES `S000_JT00`, `S000_JT02` and crosswalk files into `data/raw/lodes/`, records the releases in `releases.json`, and builds the jobs-by-industry grid from those recorded releases.
- UK, in `data/raw/research-gdp/`: `ons_small_area_gva_2023.xlsx` and the ONS 2011 LSOA boundaries as `lsoa/p*.geojson`. The loader downloads `scotland_dz2011.zip` and `ni_soa2011.zip` if missing.
- Netherlands and Europe, in `data/raw/research-gdp/`: `coropplus_2024.geojson` and the Eurostat 2023 NUTS3 GDP as `nuts3_2023.json`, which the loader does not download. It downloads the CBS table (`cbs_gdp2023.json`) and the GISCO boundaries (`nuts3_2024_01m.geojson`) if missing.
- Land, in `data/raw/land-value/`: `land_all.csv` (OECD Table 9B), `gdp_usd.json`, `gdp_lcu.json` and `wb_EN.URB.MCTY.TL.ZS.json` (World Bank GDP and big-city population), `un-gdp-usd.xlsx` (UN GDP) and `dgbas-table1-2024.xlsx` (Taiwan national wealth). Download URLs and Taiwan's exchange rate are in `sources.json` there.
- Buildings, in `data/raw/building-value/`: `oecd-buildings.csv` (OECD Table 9B building stocks), `gdp-per-head-ppp.json` (World Bank GDP per head at purchasing power parity, used to compare national models) and `dgbas-gdp-2024.xlsx` (Taiwan GDP). Download URLs are in `sources.json` there.
- Valuation checks: the held-out land valuations in `data/experiments/land-value/`, as listed in [the land research](docs/land-value-research.md), which the Victoria, British Columbia and US building checks reuse; NYC Department of Finance values and district boundaries in `data/raw/building-value/nyc/` (`market-values-by-district-2024.json`, `community-districts.geojson`); and the Amsterdam CBS grid in `data/raw/building-value/europe/`, downloaded if missing. Each folder has a `sources.json`.
- The GDP checks read `data/experiments/places/` from `research/gdp/places_eval.py`. Land, building and split checks use frozen country-cell coordinates and cell-to-valuation-unit links in `data/experiments/split/{cells_*,units_*}.npz`, written by `research/split/extract_cells.py` and `research/split/units.py`. They sample the production rasters, not the experiment's stored candidate predictions. The build does not need these test files.

```sh
nix shell nixpkgs#duckdb -c duckdb < sources/overture_places.sql
nix shell nixpkgs#duckdb -c duckdb < sources/overture_stops.sql
devenv shell -- python -m sources.lodes_jobs
devenv shell -- python -m layers.population
devenv shell -- python -m layers.transit_stops
devenv shell -- python -m layers.gdp.build
devenv shell -- python -m layers.land_value.build
devenv shell -- python -m layers.building_value
devenv shell -- python -m sources.geonames
devenv shell -- python -m checks.holdouts
devenv shell -- python -m checks.land_value
devenv shell -- python -m checks.building_value
devenv shell -- node deploy/preview.mjs
# In another shell, while the preview runs:
devenv shell -- python -m checks.circles
```

Builders write `data/layers/<layer>/<tile row>/<tile column>.bin` and reports in `data/build/`; checks write `data/checks/`. A builder will not overwrite an existing layer: move it aside first. The preview runs the real Worker at http://127.0.0.1:8787 with `data/` standing in for the R2 bucket. Deployment is in [AGENTS.md](AGENTS.md).

The land and building builds each write a `country_totals.csv` and `conservation.json` under `data/build/<layer>/`, with every country's target, source, data year and any GDP conversion reference. The building report also records the national model's leave-one-out scores.

## Build named areas

Named areas add municipalities and NUTS regions from Eurostat GISCO (2024),
and places, counties and states from the US Census Bureau (2025). Their totals
come from the existing seven tile layers; this build does not change the grids.
Each cell belongs wholly to the area containing its centre. At levels that
tile a country, valued cells outside every polygon go to the nearest area of
the same level and country, using the grid builder's ownership code. US places
leave countryside unassigned; clicking there selects the county. Areas with
no grid cell centre are omitted. Countries use the existing grid ownership.
France includes its separately owned overseas regions; Norway includes
Svalbard and Jan Mayen, and Cyprus includes northern Cyprus.

```sh
devenv shell -- python -m sources.named_areas
devenv shell -- python -m named_areas.build
devenv shell -- python -m checks.named_areas --built data/areas --report data/build/named-areas/checks.json
PORT=8788 devenv shell -- node deploy/preview.mjs
# In another shell, while the preview runs:
devenv shell -- node checks/named_areas_http.mjs http://127.0.0.1:8788
devenv shell -- node checks/named_areas_hosting.mjs
```

Downloads are cached in `data/sources/named-areas/`. The builder writes static
files into `data/areas/`, including the source URLs and licence notices.
Records, click lookup and viewport outlines use gzip encoding (`.json.gz`);
the browser decompresses them as it loads them. The viewport index gives
per-level shard counts, so dense views can be skipped before fetching outlines.
Outline linework follows the source polygon boundaries, without shard-edge strokes.
Build diagnostics and check reports stay in `data/build/named-areas/`. The preview and live page load `/areas/...` from their
own origin. See [area hosting and release downloads](deploy/areas.md).
The European boundary data retains Eurostat's non-commercial terms and
EuroGeographics notice, separately from the code's MIT licence.

GDP comparisons use the official regional controls scaled to the grid's
country totals: Eurostat euros and BEA US dollars cannot be compared directly
with the grid's PPP international dollars. The checks report both values.
US places do not cover the countryside. Each level in the picker is found
independently at the clicked point, including the county beneath a city that
spans several counties. The build report records coverage gaps and
municipality-to-region boundary mismatches, nearest assignments and omitted
areas at each level.

`sources.geonames` downloads `cities15000.zip` and `countryInfo.txt` from the [GeoNames dump](https://download.geonames.org/export/dump/) into `data/raw/geonames/` if missing. It writes compact `[name, country, latitude, longitude, population]` rows to `data/places/cities.json`. The default tile sync includes this file; selecting `places` syncs it alone, with the same MD5 comparison and hidden-stdin credentials. Deploy the updated Worker before its first upload. Until the file is present, `place` is `null`; the numeric results are unaffected.

To compare a rebuild with rasters preserved before it:

```sh
devenv shell -- python -m checks.land_value --before data/build/land_value-before-split/land_value.tif
devenv shell -- python -m checks.building_value --before data/build/building_value-before-split/building_value.tif
devenv shell -- python -m checks.property_split --before-land data/build/land_value-before-split/land_value.tif --before-buildings data/build/building_value-before-split/building_value.tif
devenv shell -- python research/smoke/land_share_vs_fhfa.py --report data/checks/fhfa-after-split.json
```

The US land and building scores retain the split study's held-out even-numbered states in the contiguous US. The FHFA smoke test separately checks all 2,436 counties with usable residential land shares. These measure residential value, not commercial property.

## Licence and credits

The code is under the [MIT licence](LICENSE). The page is adapted from Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/), under CC BY 4.0. The data comes from many publishers, each with its own licence and required attribution; the stop layers derive from OpenStreetMap and are available under the ODbL. All are listed in [Credits and licences](docs/methodology.md#credits-and-licences).

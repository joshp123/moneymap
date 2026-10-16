Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.

# moneymap

Choose a radius from 3 to 100 km and click the map to see the population, GDP and land value inside the circle, anywhere in the world. Population mode also counts bus, tram, metro and train stops; `mode=gdp` selects GDP and `mode=land` selects land value. It is live at https://moneymap.jjpcodes.com and extends Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/).

[How the numbers are calculated](docs/methodology.md). US county GDP is split by BEA industry and spread by that industry's LODES workplace jobs, weighted by high-pay share. Other countries retain their existing rule.

Land value excludes buildings and uses 2024 US dollars at market exchange rates. National totals follow OECD and Taiwan DGBAS balance sheets, or the fixed big-city-share model. Within each country, half follows population weighted by nearby density and half follows production GDP.

## How it works

Each data layer is one value per 30 arc-second grid cell, stored as tiles in the Site's R2 bucket. One Worker serves the page and `/api/circle`, which sums the cells whose centres lie inside the circle. Python builds the tiles locally from the source data.

```text
worker/index.js           The website: page, circle API and authenticated tile sync endpoints
layers/                   Builds each layer's tiles into data/layers/
  grid.py                 The shared grid, tile format and readers
  population.py           Population layer
  transit_stops.py        Bus, tram and rail stop layers
  gdp/                    GDP layer
    cell_ownership.py     Which regional unit owns each cell
    building_weight.py    Non-residential building weight q
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
checks/                   Evidence that the numbers are right
  holdouts.py             Scores the GDP rule against official figures held out
  circles.py              Compares the real Worker's answers with the grids
  land_value.py           Checks land against official held-out valuations
deploy/
  build.sh                Builds the Sites artifact in dist/ and stamps the deployed commit
  validate-artifact.mjs   Checks the artifact is an ES module exporting default.fetch
  preview.mjs             Runs the real Worker locally, with data/ as the R2 bucket
  sync-tiles.mjs          Makes the Site's tiles match data/layers/
research/                 Experiments the method came from; the build does not use them
docs/                     Method and research notes
data/                     Inputs and outputs; local only, not in git
```

## Build and check locally

Tools come from `devenv.nix`; run commands from the repository root. Download these inputs first:

- `data/raw/kummu/rast_gdpTot_1990_2024_30arcsec.tif` and Kummu's admin-1 GeoPackage in `data/raw/research-gdp/`.
- BEA CAGDP2 2024 CSV in `data/raw/research-gdp/cagdp2/`; LODES `S000_JT00`, `S000_JT02` and crosswalk files in `data/raw/lodes/`. `sources.lodes_jobs` builds the industry grid from these pinned releases.
- `data/raw/ghspop/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip`.
- GHSL non-residential volume and surface (`nres_v_30ss.zip`, `nres_s_30ss.zip`) and the official GDP tables and boundaries in `data/raw/research-gdp/`, as listed in [the research](docs/gdp-method-research.md). The loader fetches missing Scotland and Northern Ireland boundaries, GISCO NUTS boundaries and the CBS table.
- Land inputs in `data/raw/land-value/`: OECD Table 9B, World Bank GDP and big-city population, UN GDP and Taiwan DGBAS national wealth. Download URLs and Taiwan's exchange rate are recorded in `sources.json` there. The four held-out valuation datasets are in `data/experiments/land-value/`, as listed in [the land research](docs/land-value-research.md).

```sh
nix shell nixpkgs#duckdb -c duckdb < sources/overture_places.sql
nix shell nixpkgs#duckdb -c duckdb < sources/overture_stops.sql
devenv shell -- python -m sources.lodes_jobs
devenv shell -- python -m layers.population
devenv shell -- python -m layers.transit_stops
devenv shell -- python -m layers.gdp.build
devenv shell -- python -m layers.land_value.build
devenv shell -- python -m checks.holdouts
devenv shell -- python -m checks.land_value
devenv shell -- node deploy/preview.mjs
# In another shell, while the preview runs:
devenv shell -- python -m checks.circles
```

Builders write `data/layers/<layer>/<tile row>/<tile column>.bin` and reports in `data/build/`; checks write `data/checks/`. A builder will not overwrite an existing layer: move it aside first. The preview runs the real Worker at http://127.0.0.1:8787 with `data/` standing in for the R2 bucket. Deployment is in [AGENTS.md](AGENTS.md).

The land build also writes `data/build/land_value/country_totals.csv`, with every country's target, source, data year and any GDP conversion reference, plus its country conservation report.

## Sources

- [Kummu et al. (2025)](https://doi.org/10.1038/s41597-025-04487-x), [13 March 2026 release](https://zenodo.org/records/18429133), CC BY 4.0: band 8, `gdp_2024`, of `rast_gdpTot_1990_2024_30arcsec.tif`, and reported admin-1 polygons. The release specifies 2021 international dollars; the embedded 2017 unit tag is stale.
- [GHSL](https://human-settlement.emergency.copernicus.eu/): GHS-POP R2023A population, GHS-BUILT-V and GHS-BUILT-S R2023A non-residential volume and surface, all 2025, WGS84, 30 arc-seconds, CC BY 4.0.
- BEA [CAGDP1](https://apps.bea.gov/regional/zip/CAGDP1.zip), county GDP 2024, and [CAGDP2](https://apps.bea.gov/regional/zip/CAGDP2.zip), county and state GDP by industry 2024; [US Census](https://www2.census.gov/geo/tiger/GENZ2024/shp/), county boundaries 2024. US government data.
- [US Census Bureau, LEHD Origin-Destination Employment Statistics (LODES8)](https://lehd.ces.census.gov/data/lodes/LODES8/), workplace jobs and block internal points, public domain.
- Land: [OECD Table 9B](https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&df[id]=DSD_NASEC10@DF_TABLE9B), [Taiwan DGBAS national wealth](https://eng.stat.gov.tw/cl.aspx?n=2411), [World Bank GDP](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD) and [big-city population](https://data.worldbank.org/indicator/EN.URB.MCTY.TL.ZS) (CC BY 4.0), [UN national accounts](https://unstats.un.org/unsd/snaama/) and [Taiwan Central Bank exchange rates](https://www.cbc.gov.tw/en/).
- [ONS small-area GVA 2023](https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates); ONS 2011 LSOA boundaries, [Scottish data zones](https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip), [Northern Ireland SOAs](https://www.nisra.gov.uk/files/nisra/publications/SOA2011_Esri_Shapefile_0.zip). Open Government Licence.
- [Eurostat regional GDP](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10r_3gdp?unit=MIO_EUR&time=2023) and [GISCO NUTS 2024 boundaries](https://gisco-services.ec.europa.eu/distribution/v2/nuts/), Eurostat reuse terms.
- [CBS 85924NED](https://opendata.cbs.nl/ODataApi/OData/85924NED), GDP 2023; [PDOK COROP-plus 2024 boundaries](https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1), CC BY 4.0.
- Workplace places: [Overture Maps Foundation](https://overturemaps.org/), release 2026-09-23.1, [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/) and [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- Transit stops: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), via [Overture Maps Foundation](https://overturemaps.org/), release 2026-09-23.1, [ODbL](https://opendatacommons.org/licenses/odbl/1-0/). Extraction rules are in `sources/overture_stops.sql` and [the stop research](docs/stops-research.md).
- Page adapted from [Tom Forth's Population around a point](https://www.tomforth.co.uk/circlepopulations/), CC BY 4.0. Map © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); [Leaflet](https://leafletjs.com/).

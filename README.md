Written by AI on 2026.10.16 by model gpt-6.1-sol.

# moneymap

Choose a radius from 3 to 100 km and click the map to see population, GDP and GDP per head. Population is the default mode; `mode=gdp` selects GDP. One Worker serves the page and circle API. The public site is https://moneymap.jjpcodes.com.

GDP is purchasing power parity (PPP), in 2021 international dollars. Population is for 2025; GDP country totals are for 2024.

## GDP allocation

Keep each country's total from Kummu's 2024 GDP raster. Within the US, use BEA 2024 county GDP shares; within the UK, ONS 2023 small-area GVA shares for England and Wales LSOAs, Scottish data zones and Northern Ireland SOAs; within the Netherlands, CBS 2023 COROP-plus shares. Other EU27 countries and Albania, Montenegro, North Macedonia, Serbia and Turkey use Eurostat 2023 NUTS3 shares on GISCO 2024 boundaries. Everywhere else keeps Kummu's reported admin-1 unit totals, or the whole country where reported subnational data is absent. Official values supply shares only, without currency, year or PPP conversion.

Within each unit, distribute half its GDP by population share and half by its share of `q = non-residential building volume² / non-residential building surface`. Compute q on the GHSL built-up grid, then shift it to the population grid: POP column k receives 0.8 of BUILT column k−1 and 0.2 of BUILT column k. A unit without q uses population; a unit without population uses q. If neither is present, put the unit's total in the cell holding its centroid. This also covers units too small to contain a cell centre. The population weight is fixed at 0.5.

Grid ownership uses cell centres in Kummu's reported polygons. Occupied coastal cells outside those polygons go to the nearest reported unit, preserving every source dollar. Allocation uses the finer official boundaries where available, including coastal enclaves omitted from Kummu’s coarse outline. Remaining boundary gaps are filled with the nearest official unit in the same country. BEA's combined counties are joined before rasterisation. The five French overseas departments keep their separate Kummu country totals. Official shares use spatial unit sums, excluding unlocated extra-regio GDP. Allocation contributions are checked per unit before summing, including centroid contributions where small units share a grid cell.

## Sources

- [Kummu et al. (2025)](https://doi.org/10.1038/s41597-025-04487-x), [13 March 2026 release](https://zenodo.org/records/18429133), CC BY 4.0: band 8, `gdp_2024`, of `rast_gdpTot_1990_2024_30arcsec.tif`, and reported admin-1 polygons. The release specifies 2021 international dollars; the embedded 2017 unit tag is stale.
- [GHSL](https://human-settlement.emergency.copernicus.eu/): GHS-POP R2023A population, GHS-BUILT-V and GHS-BUILT-S R2023A non-residential volume and surface, all 2025, WGS84, 30 arc-seconds, CC BY 4.0.
- [BEA CAGDP1](https://apps.bea.gov/regional/zip/CAGDP1.zip), county GDP 2024; [US Census](https://www2.census.gov/geo/tiger/GENZ2024/shp/), county boundaries 2024. US government data.
- [ONS small-area GVA 2023](https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates); ONS 2011 LSOA boundaries, [Scottish data zones](https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip), [Northern Ireland SOAs](https://www.nisra.gov.uk/files/nisra/publications/SOA2011_Esri_Shapefile_0.zip). Open Government Licence.
- [Eurostat regional GDP](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10r_3gdp?unit=MIO_EUR&time=2023) and [GISCO NUTS 2024 boundaries](https://gisco-services.ec.europa.eu/distribution/v2/nuts/), Eurostat reuse terms.
- [CBS 85924NED](https://opendata.cbs.nl/ODataApi/OData/85924NED), GDP 2023; [PDOK COROP-plus 2024 boundaries](https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1), CC BY 4.0.
- Page adapted from [Tom Forth's Population around a point](https://www.tomforth.co.uk/circlepopulations/), CC BY 4.0. Map © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); [Leaflet](https://leafletjs.com/).

## Build and check locally

Tools come from `devenv.nix`; no global Python or npm installation is needed. Keep the Kummu TIFF in `data/raw/kummu/`, the population ZIP in `data/raw/ghspop/`, and research inputs in `data/raw/research-gdp/`, as listed in [the research](docs/gdp-method-research.md). The control loader fetches missing Scotland/NI boundary ZIPs, GISCO 1:1m boundaries and the complete CBS 2023 table. The comparison check also fetches ONS's national GDP table. Kummu's admin-1 GeoPackage must be present there.

```sh
devenv shell -- python scripts/build_layers.py
devenv shell -- python scripts/check_gdp_layers.py --holdout-only
devenv shell -- node scripts/preview.mjs
# In another shell, while the preview is running:
devenv shell -- python scripts/check_gdp_layers.py --places-only
```

The builder reads bounded strips and writes `data/layers/<layer>/<tileRow>/<tileCol>.bin`. Each tile is one 120 × 120 plane of little-endian float32 values, row-major from the north-west. Layers are `population` and `gdp`; missing tiles and edge padding are zero. Move a previous `data/layers/` directory aside before rebuilding. The old `data/tiles/` remains available for migration and v1 comparison.

The build writes the GDP grid and control IDs under `data/gdp-v2/`, plus `conservation.json` with every unit and country target and result, and tile read-back totals. `checks.json` holds the US state-to-county hold-out, named circles, official reference conversions and local query timings. The hold-out uses the production allocation function, without fitting the weight. The named checks compare the real Worker's API to the built raster and original population source. Local timings exclude remote R2 latency and platform overhead.

The preview imports the actual Worker and supplies a filesystem-backed R2 binding at http://127.0.0.1:8787. Stop it with Ctrl-C.

Checked locally on 16 October 2026: all 48,314 control totals and 235 country totals agree within float32 rounding. The global GDP total remains $196.8792626 trillion. The US state-to-county hold-out misallocates 13.95% of GDP, against 17.35% for population only and 15.40% for Kummu with the same state totals. The Manhattan 6 km circle rises from $285.766 billion to $785.354 billion. It contains 57.95% of Manhattan's population and 82.05% of its q, so the fixed mix places 70.00% of Manhattan's $1,021.743 billion control total there, plus $70.166 billion from other counties. No weight was fitted to these places.

## Upload and retire the old tiles

Deployment and upload are separate from local builds. Use the Sites skill's source workflow to build, validate, push and package the project. `.openai/hosting.json` retains the existing Site ID and `TILES` R2 binding. Preserve public access when deploying.

```sh
devenv shell -- node scripts/upload-tiles.mjs https://moneymap.jjpcodes.com
# Only after verifying that the new layers are live:
devenv shell -- node scripts/upload-tiles.mjs https://moneymap.jjpcodes.com --delete-old
```

Enter one JSON line at hidden stdin with `uploadToken` and, for a private Site, `siteAccessToken`. Credentials never belong in arguments or files. Upload checks authenticated HEAD before PUT, skips existing objects of the expected size, retries temporary failures and reports progress. It assumes fixed layer content; size checks do not detect a changed dataset of the same size. Cleanup enumerates the preserved local `data/tiles/` list and calls the authenticated DELETE endpoint restricted to legacy `tiles/<row>/<col>.bin` objects. It cannot delete new layers. Both modes report files, bytes, elapsed time and failures.

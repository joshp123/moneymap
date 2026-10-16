Written by AI on 2026.10.16 by model gpt-6.1-sol.

# moneymap

Choose a radius from 3 to 100 km and click the map to see population, GDP and GDP per head. Population mode also shows bus, tram, metro and train stops. Population is the default mode; `mode=gdp` selects GDP. One Worker serves the page and circle API. The public site is https://moneymap.jjpcodes.com. V3 GDP and the stop display are currently local changes.

GDP is purchasing power parity (PPP), in 2021 international dollars. Population is for 2025; GDP country totals are for 2024.

## GDP allocation

Keep each country's total from Kummu's 2024 GDP raster. Within the US, use BEA 2024 county GDP shares; within the UK, ONS 2023 small-area GVA shares for England and Wales LSOAs, Scottish data zones and Northern Ireland SOAs; within the Netherlands, CBS 2023 COROP-plus shares. Other EU27 countries and Albania, Montenegro, North Macedonia, Serbia and Turkey use Eurostat 2023 NUTS3 shares on GISCO 2024 boundaries. Everywhere else keeps Kummu's reported admin-1 unit totals, or the whole country where reported subnational data is absent. Official values supply shares only, without currency, year or PPP conversion.

The existing v2 grid distributes half each unit's GDP by population share and half by its share of `q = non-residential building volume² / non-residential building surface`. Compute q on the GHSL built-up grid, then shift it to the population grid: POP column k receives 0.8 of BUILT column k−1 and 0.2 of BUILT column k. A unit without q uses population; a unit without population uses q. If neither is present, put the unit's total in the cell holding its centroid. This also covers units too small to contain a cell centre.

V3 uses equal thirds population, q and workplace-place shares where a control unit has at least 3.9 workplace places per 1,000 residents and both population and q. Other units retain v2, including its fallbacks. Workplace categories come from `scripts/extract_places.sql`; permanently closed places are excluded, with no confidence filter. The weights and threshold are fixed. Seven of eight hold-out measures improve. Brazil's median absolute log ratio rises from 0.271781 to 0.272562 while its misplaced-GDP share improves from 18.639% to 17.475%. This trade-off was accepted on 16 October 2026 without tuning. Results are in `data/gdp-v3/holdouts.json`.

| Hold-out | Wrong GDP share, v2 → v3 | Median absolute log ratio, v2 → v3 |
|---|---:|---:|
| US county within state | 13.9505% → 11.5775% | 0.257668 → 0.238962 |
| UK MSOA within local authority | 27.8611% → 24.6816% | 0.452986 → 0.411275 |
| EU NUTS3 within NUTS2 | 9.4753% → 7.6471% | 0.134169 → 0.113103 |
| Brazil municipality within state | 18.6390% → 17.4750% | 0.271781 → 0.272562 |

Grid ownership uses cell centres in Kummu's reported polygons. Occupied coastal cells outside those polygons go to the nearest reported unit, preserving every source dollar. Allocation uses the finer official boundaries where available, including coastal enclaves omitted from Kummu’s coarse outline. Remaining boundary gaps are filled with the nearest official unit in the same country. BEA's combined counties are joined before rasterisation. The five French overseas departments keep their separate Kummu country totals. Official shares use spatial unit sums, excluding unlocated extra-regio GDP. Allocation contributions are checked per unit before summing, including centroid contributions where small units share a grid cell.

## Sources

- [Kummu et al. (2025)](https://doi.org/10.1038/s41597-025-04487-x), [13 March 2026 release](https://zenodo.org/records/18429133), CC BY 4.0: band 8, `gdp_2024`, of `rast_gdpTot_1990_2024_30arcsec.tif`, and reported admin-1 polygons. The release specifies 2021 international dollars; the embedded 2017 unit tag is stale.
- [GHSL](https://human-settlement.emergency.copernicus.eu/): GHS-POP R2023A population, GHS-BUILT-V and GHS-BUILT-S R2023A non-residential volume and surface, all 2025, WGS84, 30 arc-seconds, CC BY 4.0.
- [BEA CAGDP1](https://apps.bea.gov/regional/zip/CAGDP1.zip), county GDP 2024; [US Census](https://www2.census.gov/geo/tiger/GENZ2024/shp/), county boundaries 2024. US government data.
- [ONS small-area GVA 2023](https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates); ONS 2011 LSOA boundaries, [Scottish data zones](https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip), [Northern Ireland SOAs](https://www.nisra.gov.uk/files/nisra/publications/SOA2011_Esri_Shapefile_0.zip). Open Government Licence.
- [Eurostat regional GDP](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10r_3gdp?unit=MIO_EUR&time=2023) and [GISCO NUTS 2024 boundaries](https://gisco-services.ec.europa.eu/distribution/v2/nuts/), Eurostat reuse terms.
- [CBS 85924NED](https://opendata.cbs.nl/ODataApi/OData/85924NED), GDP 2023; [PDOK COROP-plus 2024 boundaries](https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1), CC BY 4.0.
- Workplace places: [Overture Maps Foundation](https://overturemaps.org/), release 2026-09-23.1, [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/) and [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- Transit stops: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), via [Overture Maps Foundation](https://overturemaps.org/), release 2026-09-23.1, [ODbL](https://opendatacommons.org/licenses/odbl/1-0/). Extraction rules are in `scripts/extract_stops.sql` and [the stop research](docs/stops-research.md).
- Page adapted from [Tom Forth's Population around a point](https://www.tomforth.co.uk/circlepopulations/), CC BY 4.0. Map © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); [Leaflet](https://leafletjs.com/).

## Build and check locally

Tools come from `devenv.nix`; no global Python or npm installation is needed. Keep the Kummu TIFF in `data/raw/kummu/`, the population ZIP in `data/raw/ghspop/`, and research inputs in `data/raw/research-gdp/`, as listed in [the research](docs/gdp-method-research.md). The control loader fetches missing Scotland/NI boundary ZIPs, GISCO 1:1m boundaries and the complete CBS 2023 table. The comparison check also fetches ONS's national GDP table. Kummu's admin-1 GeoPackage must be present there.

```sh
devenv shell -- python scripts/build_stop_layers.py
devenv shell -- python scripts/check_gdp_v3.py
devenv shell -- python scripts/build_layers.py
devenv shell -- node scripts/preview.mjs
# In another shell, while the preview is running:
devenv shell -- python scripts/check_v3_circles.py
```

The builders read bounded strips and write `data/layers/<layer>/<tileRow>/<tileCol>.bin`. Each tile is one 120 × 120 plane of little-endian float32 values, row-major from the north-west. Layers are `population`, `gdp`, `bus_stops`, `tram_stops` and `rail_stops`; missing tiles and edge padding are zero. Keep `data/raw/overture/stops_per_cell.parquet` and `places_per_cell.parquet` locally. Move an existing stop layer aside before rebuilding it. The GDP builder preserves existing population tiles and requires the previous GDP tile directory to be moved aside. The v2 GDP tiles are preserved under `data/gdp-v2/tiles/`. Population tiles are unchanged.

Stop tiles reproduce the Parquet totals exactly: 4,167,514 bus, 51,083 tram and 138,265 metro/train stops. Amsterdam 5 km returns 684/352/33; Rotterdam 50 km returns 11,645/900/238. The builder reads all tiles back and writes `data/gdp-v3/stops.json`.

The four v3 hold-outs call the production allocation function on the research's per-held-out-unit population, q and workplace sums. Linearity permits aggregation before allocation; float32 rounding occurs at the held-out unit rather than each cell. US, EU and Brazil use cell centres; UK uses 10 by 10 cell area fractions over LSOAs aggregated to MSOAs. The coverage gate is evaluated for each coarse control group. The checker records input hashes and confirms the current Parquet workplace total matches the researched input. The preserved v2 preview baseline for the ten named circles is `data/gdp-v3/v2-api.json`.

The previous build's GDP grid, control IDs, conservation and checks remain under `data/gdp-v2/`. The builder writes GDP, control IDs and conservation under `data/gdp-v3/`. The circle checker compares the real Worker's API with v2 and v3 rasters, verifies cumulative rows and stop counts against Parquet, and times 50 km and 100 km queries. Local timings exclude remote R2 latency and platform overhead.

The preview imports the actual Worker and supplies a filesystem-backed R2 binding at http://127.0.0.1:8787. Stop it with Ctrl-C.

Checked locally on 16 October 2026: all 48,314 control totals and 235 country totals agree within float32 rounding. Their targets are identical to v2. Maximum relative errors are 5.95 × 10⁻⁸ per unit and 2.01 × 10⁻⁸ per country. Source GDP is $196,879,262,625,395; built GDP is $196,879,262,622,990.6, a $2,404 float32 difference across $196.8792626 trillion. GDP tile read-back differs from the built-grid sum by $0.1875 from float64 summation order. Population tile read-back also matches the unchanged source grid.

The places term applies to 19,769 of 48,314 control units, containing $71.505363 trillion or 36.3194% of world GDP. There are 591 workplace places outside the existing control-unit mask; they receive no allocation, preserving the v2 grid ownership. GDP has 15,599 tiles totalling 898,502,400 bytes.

All ten circles below were checked through the real Worker in the local preview. V2 values were saved from its API before rebuilding; both versions match their respective rasters, and population is unchanged. All cumulative GDP rows match the v3 raster; cumulative population matches v2. Values are billions of 2021 international dollars.

| Circle | Radius km | V2 GDP | V3 GDP |
|---|---:|---:|---:|
| Midtown and Lower Manhattan | 6 | 785.354 | 881.694 |
| Tokyo Marunouchi | 3 | 86.342 | 86.342 |
| Bank | 3 | 346.180 | 346.228 |
| Canary Wharf | 3 | 61.561 | 61.569 |
| Zuidas | 3 | 30.367 | 34.467 |
| Schiphol | 3 | 7.826 | 6.531 |
| La Défense | 3 | 91.922 | 87.380 |
| Rotterdam | 50 | 536.525 | 532.599 |
| Shanghai Lujiazui | 3 | 78.854 | 78.854 |
| Beijing Guomao | 3 | 64.639 | 64.639 |

The Tokyo and Chinese circles retain v2 because their control units fall below the places coverage threshold. Local query timings were 6.97/2.68 ms for Rotterdam 50 km and 8.34/6.72 ms for Paris 100 km, two successive runs with filesystem-backed tiles. The stop totals and every cumulative stop row match the source Parquet for Amsterdam and Rotterdam. Results are in `data/gdp-v3/circles.json` and `conservation.json`. Population and GDP modes were also checked in Safari; the preview was stopped afterwards.

## Upload and retire the old tiles

Deployment and upload are separate from local builds. Use the Sites skill's source workflow to build, validate, push and package the project. `.openai/hosting.json` retains the existing Site ID and `TILES` R2 binding. Preserve public access when deploying.

Before a v3 upload, the uploader needs the three stop layer names and a way to replace existing GDP objects. Its current size-only resume check would skip changed GDP tiles. No upload was attempted during this local build.

```sh
devenv shell -- node scripts/upload-tiles.mjs https://moneymap.jjpcodes.com
# Only after verifying that the new layers are live:
devenv shell -- node scripts/upload-tiles.mjs https://moneymap.jjpcodes.com --delete-old
```

Enter one JSON line at hidden stdin with `uploadToken` and, for a private Site, `siteAccessToken`. Credentials never belong in arguments or files. Upload checks authenticated HEAD before PUT, skips existing objects of the expected size, retries temporary failures and reports progress. It assumes fixed layer content; size checks do not detect a changed dataset of the same size. Cleanup enumerates the preserved local `data/tiles/` list and calls the authenticated DELETE endpoint restricted to legacy `tiles/<row>/<col>.bin` objects. It cannot delete new layers. Both modes report files, bytes, elapsed time and failures.

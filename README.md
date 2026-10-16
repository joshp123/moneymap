Written by AI on 2026.10.16 by model gpt-6.1-sol.

# moneymap

Click a map and choose a radius from 3 to 100 km to see estimated GDP, population and GDP per head. The page and circle API run in one Worker, with binary raster tiles in the `TILES` R2 binding. Land value is out of scope.

GDP is purchasing power parity (PPP), in 2021 international dollars. These are roughly US dollars adjusted so that a dollar buys the same amount everywhere. Regional GDP is shared out by where people live, so job centres with few residents are under-counted. Small circles mostly reflect population.

## Sources

- [Kummu et al. (2025)](https://doi.org/10.1038/s41597-025-04487-x), [13 March 2026 release](https://zenodo.org/records/18429133), CC BY 4.0: `rast_gdpTot_1990_2024_30arcsec.tif`, band 8 (`gdp_2024`). The release changes the unit to 2021 international dollars; the embedded 2017 unit tag is stale.
- [GHSL GHS-POP R2023A](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php), CC BY 4.0: 2025 population, WGS84, 30 arc-seconds. This is also the population used to construct the 2024 GDP layer.
- Page adapted from [Tom Forth's Population around a point](https://www.tomforth.co.uk/circlepopulations/), CC BY 4.0. Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); map library [Leaflet](https://leafletjs.com/).

## Build tiles

Run commands from this repository root. Tools are managed by devenv; there are no npm dependencies.

Place the GDP TIFF under `data/raw/kummu/` and `GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip` under `data/raw/ghspop/`. Let downloads finish first.

```sh
devenv shell -- python scripts/build_tiles.py
```

The builder checks the grids and band, reads strips with bounded memory, and writes `data/tiles/<row>/<col>.bin`. Every file contains 120 × 120 little-endian float32 GDP values followed by the same number of population values, from north-west in row order. Missing values and edge padding are zero; empty tiles are omitted. Non-empty output directories must be moved aside before rebuilding. The builder reads tiles back and compares global totals with the source values; its report is `data/tiling-report.json`.

## Local preview and checks

```sh
devenv shell -- node scripts/preview.mjs
# http://127.0.0.1:8787
devenv shell -- python scripts/check-circles.py
```

The preview imports the actual Worker and supplies a local filesystem implementation of R2. The check reads source rasters directly, compares all whole-kilometre cumulative results with the local API, times each query, and queries Tom's live population API. Results go to `data/circle-checks.json`. Local timings exclude remote R2 latency and Worker platform overhead.

## Upload after deployment

The owner-private Site is https://moneymap.jjpcodes.chatgpt.site (slug `moneymap`). Its project ID and `TILES` binding are in `.openai/hosting.json`. The runtime secret `UPLOAD_TOKEN` is configured in Sites. This repository is the Site project root.

```sh
devenv shell -- node scripts/upload-tiles.mjs https://moneymap.jjpcodes.chatgpt.site
```

Enter one JSON line at the hidden stdin prompt with `uploadToken` and `siteAccessToken`. Do not put credentials in arguments or files. The Site access token is sent in `OAI-Sites-Authorization`. Upload uses 48 concurrent requests and retries temporary failures. An authenticated HEAD check skips existing tiles of the expected size, so an interrupted upload can be rerun. This assumes the same fixed dataset; it does not detect different content of the same size.

Use the Sites skill source workflow to build, validate, push and package this repository, then deploy with the owner-private operation. No deployment is needed for local preview.

## Verified locally on 16 October 2026

15,498 tiles, 1,785,369,600 bytes (1.663 GiB). Source and tile GDP totals both equal $196,879,262,625,395. Source population totals 8,191,988,536.181239; tiles total 8,191,988,536.181205. The 0.000034 difference is floating-point addition order.

All nine requested circles and every whole-kilometre row match the separate source-raster calculation within floating-point rounding. Tom's live population API differs by 0.008% to 0.737%; no values were tuned. The initial local HTTP queries took 32.1 ms for Rotterdam at 50 km and 5.9 ms for Paris at 100 km. These are local filesystem timings, not deployed R2 timings. The page was also inspected in a browser with the real Rotterdam data.

Runtime credentials are held by Sites and are not stored in this repository. The page, API and tile format are unchanged for deployment.

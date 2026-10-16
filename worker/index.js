// Written by AI on 2026.10.16 by model gpt-6.1-sol.
const GRID = {
  width: 43202, height: 21384,
  west: -180.00791593130032, north: 89.0995831776456,
  pixelWidth: 0.008333333300326923, pixelHeight: 0.00833333329979504, tileSize: 120,
};
const EARTH_RADIUS_KM = 6371.0088;
const RADIANS = Math.PI / 180;
const TILE_CELLS = GRID.tileSize ** 2;
const TILE_BYTES = TILE_CELLS * 4;
const LAYERS = ['gdp', 'population', 'bus_stops', 'tram_stops', 'rail_stops', 'land_value', 'building_value'];
const PLACES_KEY = 'places/cities.json';
let placesPromise;

async function nearestPlace(bucket, latitude, longitude) {
  if (!placesPromise) {
    placesPromise = (async () => {
      const object = await bucket.get(PLACES_KEY);
      if (!object) {
        placesPromise = undefined;
        return [];
      }
      return JSON.parse(new TextDecoder().decode(await object.arrayBuffer()));
    })().catch(error => { placesPromise = undefined; throw error; });
  }
  const places = await placesPromise;
  // The best-known nearby place: the largest population divided by distance squared
  // (distances under 1 km count as 1 km), within 200 km. Bank picks London, not a
  // small district that happens to be nearer.
  const latitudeRadians = latitude * RADIANS;
  const maximumAngle = 200 / EARTH_RADIUS_KM;
  let best = null, bestScore = 0, bestDistance = 0;
  for (const place of places) {
    const placeLatitude = place[2] * RADIANS;
    if (Math.abs(placeLatitude - latitudeRadians) > maximumAngle) continue;
    const haversine = Math.sin((placeLatitude - latitudeRadians) / 2) ** 2 +
      Math.cos(latitudeRadians) * Math.cos(placeLatitude) * Math.sin((place[3] - longitude) * RADIANS / 2) ** 2;
    const distance = 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, haversine)));
    if (distance > 200) continue;
    const score = place[4] / Math.max(distance, 1) ** 2;
    if (score > bestScore) {
      best = place;
      bestScore = score;
      bestDistance = distance;
    }
  }
  return best ? { name: best[0], country: best[1], distance_km: bestDistance } : null;
}

function circleParameters(searchParams) {
  const values = ['lat', 'long', 'distance_km'].map(name => {
    const value = searchParams.get(name);
    return value === null || value.trim() === '' ? NaN : Number(value);
  });
  const [latitude, longitude, radius] = values;
  if (!values.every(Number.isFinite) || latitude < -90 || latitude > 90 ||
      longitude < -180 || longitude > 180 || radius < 3 || radius > 100) {
    return null;
  }
  return { latitude, longitude, radius };
}

function totals(gdp, population, busStops, tramStops, railStops, landValue, buildingValue) {
  return { gdp, population, land_value: landValue, building_value: buildingValue, gdp_per_head: population > 0 ? gdp / population : null,
    bus_stops: Math.round(busStops), tram_stops: Math.round(tramStops), rail_stops: Math.round(railStops) };
}

async function circle(bucket, { latitude, longitude, radius }) {
  const latitudeRadians = latitude * RADIANS;
  const angularRadius = radius / EARTH_RADIUS_KM;
  const latitudeOffset = angularRadius / RADIANS;
  const reachesPole = Math.abs(latitudeRadians) + angularRadius >= Math.PI / 2;
  const longitudeOffset = reachesPole ? 180 :
    Math.asin(Math.sin(angularRadius) / Math.cos(latitudeRadians)) / RADIANS;
  const firstRow = Math.max(0, Math.floor((GRID.north - latitude - latitudeOffset) / GRID.pixelHeight));
  const lastRow = Math.min(GRID.height - 1, Math.floor((GRID.north - latitude + latitudeOffset) / GRID.pixelHeight));
  const firstColumn = Math.max(0, Math.floor(((reachesPole ? -180 : longitude - longitudeOffset) - GRID.west) / GRID.pixelWidth));
  const lastColumn = Math.min(GRID.width - 1, Math.floor(((reachesPole ? 180 : longitude + longitudeOffset) - GRID.west) / GRID.pixelWidth));
  const gdpByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const populationByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const busStopsByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const tramStopsByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const railStopsByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const landValueByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const buildingValueByKilometre = new Float64Array(Math.ceil(radius) + 1);
  const tileCoordinates = [];
  for (let tileRow = Math.floor(firstRow / GRID.tileSize); tileRow <= Math.floor(lastRow / GRID.tileSize); tileRow++) {
    for (let tileColumn = Math.floor(firstColumn / GRID.tileSize); tileColumn <= Math.floor(lastColumn / GRID.tileSize); tileColumn++) {
      tileCoordinates.push([tileRow, tileColumn]);
    }
  }
  for (let batchStart = 0; batchStart < tileCoordinates.length; batchStart += 16) {
    await Promise.all(tileCoordinates.slice(batchStart, batchStart + 16).map(async ([tileRow, tileColumn]) => {
      const layers = await Promise.all(LAYERS.map(async layer => {
        const object = await bucket.get(`layers/${layer}/${tileRow}/${tileColumn}.bin`);
        if (!object) return null;
        const bytes = await object.arrayBuffer();
        if (bytes.byteLength !== TILE_BYTES) throw new Error(`Invalid tile size: ${layer}/${tileRow}/${tileColumn}`);
        return new DataView(bytes);
      }));
      const [gdpValues, populationValues, busStopValues, tramStopValues, railStopValues, landValues, buildingValues] = layers;
      if (layers.every(layer => layer === null)) return;
      const rowStart = tileRow * GRID.tileSize;
      const columnStart = tileColumn * GRID.tileSize;
      for (let row = Math.max(firstRow, rowStart); row <= Math.min(lastRow, rowStart + GRID.tileSize - 1); row++) {
        const cellLatitude = (GRID.north - (row + 0.5) * GRID.pixelHeight) * RADIANS;
        const latitudeDistance = Math.sin((cellLatitude - latitudeRadians) / 2) ** 2;
        const cosineProduct = Math.cos(latitudeRadians) * Math.cos(cellLatitude);
        for (let column = Math.max(firstColumn, columnStart); column <= Math.min(lastColumn, columnStart + GRID.tileSize - 1); column++) {
          const cellIndex = (row - rowStart) * GRID.tileSize + column - columnStart;
          const gdp = gdpValues ? gdpValues.getFloat32(cellIndex * 4, true) : 0;
          const population = populationValues ? populationValues.getFloat32(cellIndex * 4, true) : 0;
          const busStops = busStopValues ? busStopValues.getFloat32(cellIndex * 4, true) : 0;
          const tramStops = tramStopValues ? tramStopValues.getFloat32(cellIndex * 4, true) : 0;
          const railStops = railStopValues ? railStopValues.getFloat32(cellIndex * 4, true) : 0;
          const landValue = landValues ? landValues.getFloat32(cellIndex * 4, true) : 0;
          const buildingValue = buildingValues ? buildingValues.getFloat32(cellIndex * 4, true) : 0;
          if (gdp === 0 && population === 0 && busStops === 0 && tramStops === 0 && railStops === 0 && landValue === 0 && buildingValue === 0) continue;
          const cellLongitude = GRID.west + (column + 0.5) * GRID.pixelWidth;
          const haversine = latitudeDistance + cosineProduct * Math.sin((cellLongitude - longitude) * RADIANS / 2) ** 2;
          const distance = 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, haversine)));
          if (distance <= radius) {
            const kilometre = Math.ceil(distance);
            gdpByKilometre[kilometre] += gdp;
            populationByKilometre[kilometre] += population;
            busStopsByKilometre[kilometre] += busStops;
            tramStopsByKilometre[kilometre] += tramStops;
            railStopsByKilometre[kilometre] += railStops;
            landValueByKilometre[kilometre] += landValue;
            buildingValueByKilometre[kilometre] += buildingValue;
          }
        }
      }
    }));
  }
  let gdp = gdpByKilometre[0];
  let population = populationByKilometre[0];
  let busStops = busStopsByKilometre[0];
  let tramStops = tramStopsByKilometre[0];
  let railStops = railStopsByKilometre[0];
  let landValue = landValueByKilometre[0];
  let buildingValue = buildingValueByKilometre[0];
  const cumulative = [];
  for (let kilometre = 1; kilometre <= Math.ceil(radius); kilometre++) {
    gdp += gdpByKilometre[kilometre];
    population += populationByKilometre[kilometre];
    busStops += busStopsByKilometre[kilometre];
    tramStops += tramStopsByKilometre[kilometre];
    railStops += railStopsByKilometre[kilometre];
    landValue += landValueByKilometre[kilometre];
    buildingValue += buildingValueByKilometre[kilometre];
    if (kilometre <= radius) cumulative.push({ distance_km: kilometre, ...totals(gdp, population, busStops, tramStops, railStops, landValue, buildingValue) });
  }
  return { lat: latitude, long: longitude, distance_km: radius, ...totals(gdp, population, busStops, tramStops, railStops, landValue, buildingValue), cumulative };
}

// deploy/sync-tiles.mjs lists, writes and deletes data here. Without the token these paths do not exist.
// GET /__upload/layers/<layer>/ returns {key: etag}; R2's etag is the MD5 of the tile.
// PUT and DELETE /__upload/layers/<layer>/<tileRow>/<tileColumn>.bin write or remove one tile.
const TILE_SYNC_PATH = new RegExp(`^/__upload/(layers/(?:${LAYERS.join('|')})/)(?:(\\d+)/(\\d+)\\.bin)?$`);
const notFound = () => new Response('Not found', { status: 404 });

async function objectEtags(bucket, prefix) {
  const etags = {};
  let cursor;
  do {
    const page = await bucket.list({ prefix, cursor });
    for (const object of page.objects) etags[object.key] = object.etag;
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return etags;
}

async function handleTileSyncRequest(request, env, pathname) {
  if (!env.UPLOAD_TOKEN || request.headers.get('Authorization') !== `Bearer ${env.UPLOAD_TOKEN}`) return notFound();
  if (pathname === '/__upload/places/') {
    if (request.method !== 'GET') return notFound();
    const etags = await objectEtags(env.TILES, PLACES_KEY);
    return Response.json(Object.fromEntries(Object.entries(etags).filter(([key]) => key === PLACES_KEY)));
  }
  if (pathname === `/__upload/${PLACES_KEY}`) {
    if (request.method !== 'PUT') return notFound();
    const bytes = await request.arrayBuffer();
    try { JSON.parse(new TextDecoder().decode(bytes)); }
    catch { return new Response('Invalid place JSON', { status: 400 }); }
    await env.TILES.put(PLACES_KEY, bytes);
    placesPromise = undefined;
    return new Response(null, { status: 201 });
  }
  const match = TILE_SYNC_PATH.exec(pathname);
  if (!match) return notFound();
  const [, layerPrefix, tileRow, tileColumn] = match;
  if (tileRow === undefined) {
    return request.method === 'GET' ? Response.json(await objectEtags(env.TILES, layerPrefix)) : notFound();
  }
  if (Number(tileRow) >= Math.ceil(GRID.height / GRID.tileSize) || Number(tileColumn) >= Math.ceil(GRID.width / GRID.tileSize)) {
    return new Response('Invalid tile coordinates', { status: 400 });
  }
  const key = `${layerPrefix}${tileRow}/${tileColumn}.bin`;
  if (request.method === 'PUT') {
    const bytes = await request.arrayBuffer();
    if (bytes.byteLength !== TILE_BYTES) return new Response('Invalid tile size', { status: 400 });
    await env.TILES.put(key, bytes);
    return new Response(null, { status: 201 });
  }
  if (request.method === 'DELETE') {
    await env.TILES.delete(key);
    return new Response(null, { status: 204 });
  }
  return notFound();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/__upload/')) return handleTileSyncRequest(request, env, url.pathname);
    if (request.method === 'GET' && url.pathname === '/') {
      return new Response(page, { headers: { 'content-type': 'text/html; charset=utf-8' } });
    }
    if (request.method === 'GET' && url.pathname === '/api/circle') {
      const parameters = circleParameters(url.searchParams);
      if (!parameters) return new Response('Use lat from -90 to 90, long from -180 to 180 and distance_km from 3 to 100.', { status: 400 });
      const [result, place] = await Promise.all([
        circle(env.TILES, parameters), nearestPlace(env.TILES, parameters.latitude, parameters.longitude),
      ]);
      return Response.json({ ...result, place });
    }
    return notFound();
  },
};

// deploy/build.sh replaces the placeholder with the deployed git commit.
const SOURCE_COMMIT = '__MONEYMAP_SOURCE_COMMIT__';
const SOURCE_REPOSITORY = 'https://github.com/joshp123/moneymap';
const deployedCommit = SOURCE_COMMIT.replace(/-dirty$/, '');
const liveVersion = SOURCE_COMMIT.startsWith('__') ? 'local preview'
  : `<a href="${SOURCE_REPOSITORY}/commit/${deployedCommit}">${deployedCommit.slice(0, 7)}</a>` +
    (SOURCE_COMMIT.endsWith('-dirty') ? ' plus uncommitted changes' : '');

const page = `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>moneymap: population around a point</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <style>
        input[type="range"] {
            width: 220px;
            max-width: 80%;
        }

        #map {
            margin: auto;
            width: 100%;
            max-width: 900px;
            height: 100%;
            border: 1px solid #333;
            box-sizing: border-box;
        }

        p {
            text-align: left;
            font-size: smaller;
        }

        body {
            max-width: 900px;
            margin: 0 auto;
            font-family: sans-serif;
            text-align: center;
            padding: 0 2px;
            box-sizing: border-box;
        }

        h1 {
            text-transform: uppercase;
            background-color: #183551;
            color: white;
            margin: 0;
            padding: 0.2em;
        }

        h2,
        h3,
        h4 {
            text-align: left;
        }

        h3 {
            margin-top: 2.5em;
            font-size: 0.9em;
        }

        #pageHolder {
            text-align: left;
        }

        p {
            margin: 1em;
            text-align: left;
        }

        #bringSitesMapHolder {
            position: relative;
            height: min(540px, 58vh);
        }

        #leftMask {
            position: absolute;
            background-color: rgba(60, 0, 0, 0);
            top: 0;
            left: 0;
            height: 100%;
            display: block;
            z-index: 999;
            width: 4%;
        }

        #rightMask {
            position: absolute;
            background-color: rgba(60, 0, 0, 0);
            top: 0;
            right: 0;
            height: 100%;
            display: block;
            z-index: 999;
            width: 4%;
        }

        #table {
            overflow-x: auto;
        }

        table {
            width: 100%;
            text-align: center;
            border: 1px solid black;
        }

        th, td {
            padding: 4px 2px;
        }

        th {
            background-color: #F0F0F0;
        }

        td {
            background-color: #F8F8F8;
        }

        #myChart {
            height: 400px;
        }

        #maincounter {
            line-height: 1;
            margin-top: 0.1em;
            margin-bottom: 0.15em;
            font-size: 3.6em;
            font-weight: bold;
        }

        .mode-switch {
            display: flex;
            justify-content: center;
            margin: 0.5em;
        }

        .mode-switch button {
            min-height: 38px;
            padding: 0.35em 0.9em;
            border: 1px solid #183551;
            background: #F0F0F0;
            color: #183551;
            font: inherit;
            cursor: pointer;
        }

        .mode-switch button[aria-pressed="true"] {
            background: #183551;
            color: white;
        }

        .tagline {
            text-align: center;
            font-style: italic;
            font-size: smaller;
            color: #555;
            margin: 0.3em;
        }

        .controls {
            text-align: center;
            margin: 0.4em;
        }

        .controls input {
            vertical-align: middle;
        }

        #resultlabel, #secondarycounter, #stopcounter, #billionairecounter {
            margin: 0.35em 1em;
        }

        #resultlabel {
            text-align: center;
            color: #444;
        }

        #copyimage {
            border: 1px solid #183551;
            background: #183551;
            color: white;
            font: inherit;
            padding: 0.3em 0.9em;
            cursor: pointer;
        }

        #copyimage:disabled {
            background: #F0F0F0;
            color: #888;
            border-color: #ccc;
            cursor: default;
        }

        #secondarycounter, #stopcounter, #billionairecounter {
            text-align: center;
        }

        .share-image {
            margin: 0.5em 1em;
            text-align: center;
        }

        #copyimage {
            padding: 0.35em 0.7em;
            font: inherit;
        }

        .methodology-note {
            background: rgba(255, 255, 255, 0.92);
            padding: 3px 7px;
            font-size: 13px;
            font-weight: 600;
            line-height: 1.4;
        }

        .methodology-note a {
            color: #183551;
        }

        @media (max-width: 500px) {
            .leaflet-bottom.leaflet-left .methodology-note {
                margin-bottom: 24px;
                font-size: 12px;
            }
        }

        .howitworks {
            margin-top: 1.5em;
        }

        @media (max-width: 400px) {
            h1 { font-size: 1.6em; }
            #maincounter { font-size: 2.7em; }
            table { font-size: 12px; }
            .population-table { font-size: 10px; }
        }

        ul,
        ol {
            text-align: left;
            font-size: smaller;
        }

        pre,
        code {
            background: whitesmoke !important;
            padding: 3px !important;
            text-align: left;
            max-width: 95%;
            overflow-x: scroll;
        }

        img {
            display: block;
            text-align: left;
            max-width: 95%;
            width: 600px;
        }

        th {
            background-color: #F0F0F0;
            position: sticky;
            top: 0;
        }

        footer p {
            margin-top: 2em;
            text-align: center;
            font-size: smaller;
        }

        .top {
            margin-top: 0.2em;
            margin-bottom: 0.4em;
            text-align: center;
            font-size: smaller;
        }
    </style>
</head>
<body>
<h1 id="heading">Population around a point</h1>
<p class="tagline">&ldquo;This is the worst website I&rsquo;ve seen in my life.&rdquo; Some guy on Twitter, 2026</p>
<div class="mode-switch" role="group" aria-label="Display">
<button type="button" id="populationmode" aria-pressed="true">Population</button>
<button type="button" id="gdpmode" aria-pressed="false">GDP</button>
<button type="button" id="propertymode" aria-pressed="false">Property value</button>
</div>
<p class="controls">Pick a radius, then click anywhere on the map: <input type="range" id="range" min="3" value="5" max="100" step="1" aria-label="Radius in kilometres"> <label for="range" id="rangelabel">5</label> km.</p>
<div id="bringSitesMapHolder"><div id="leftMask"></div><div id="rightMask"></div><div id="map"></div></div>
<p id="resultlabel">Population within circle in 2025:</p>
<p style="text-align:center" id="maincounter" aria-live="polite">--</p>
<p id="stopcounter" hidden></p>
<p id="secondarycounter"></p>
<p id="billionairecounter" hidden></p>
<p class="share-image"><button type="button" id="copyimage" disabled>Copy image</button> <span id="imagestatus" role="status"></span></p>
<p id="status" role="status" style="text-align:center">Click on the map to calculate.</p>
<h2>Give me the data!</h2>
<div id="table"></div>
<p class="howitworks">How property value works: Each country's total value of land and of buildings comes from its official national balance sheet, or from a simple model based on GDP where none is published. Within each country, land follows population, local density, local income and GDP, and buildings follow population and GDP. <a href="${SOURCE_REPOSITORY}/blob/main/docs/methodology.md">Full methodology</a>.</p>
<h2>Sources and credits</h2>
<p>Based on <a href="https://www.tomforth.co.uk/circlepopulations/">Tom Forth's Population around a point tool and page</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>GDP, 2024: <a href="https://doi.org/10.1038/s41597-025-04487-x">Kummu et al. (2025)</a>, <a href="https://zenodo.org/records/18429133">March 2026 release</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Regional GDP: <a href="https://www.bea.gov/data/gdp/gdp-county-metro-and-other-areas">BEA (2024)</a>, <a href="https://www.ons.gov.uk/economy/grossdomesticproductgdp">ONS (2023)</a>, <a href="https://ec.europa.eu/eurostat/web/regions/database">Eurostat (2023)</a> and <a href="https://www.cbs.nl/en-gb/figures">CBS (2023)</a>. Built-up volume and surface, 2025: GHSL <a href="https://ghsl.jrc.ec.europa.eu/ghs_buV2023.php">GHS-BUILT-V</a> and <a href="https://ghsl.jrc.ec.europa.eu/ghs_buS2023.php">GHS-BUILT-S</a> R2023A, European Commission Joint Research Centre (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Population, 2025: <a href="https://ghsl.jrc.ec.europa.eu/ghs_pop2023.php">GHS-POP R2023A, European Commission Joint Research Centre</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Workplace places: <a href="https://overturemaps.org/">Overture Maps Foundation</a>, September 2026 (<a href="https://cdla.dev/permissive-2-0/">CDLA Permissive 2.0</a> and <a href="https://www.apache.org/licenses/LICENSE-2.0">Apache 2.0</a>).</p>
<p>US workplace jobs: US Census Bureau, <a href="https://lehd.ces.census.gov/data/lodes/LODES8/">LEHD Origin-Destination Employment Statistics</a> (public domain).</p>
<p>Transit stops: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, via <a href="https://overturemaps.org/">Overture Maps Foundation</a> (<a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a>).</p>
<p>Land and building value, 2024: <a href="https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&amp;df[id]=DSD_NASEC10@DF_TABLE9B">OECD Table 9B</a> and <a href="https://eng.stat.gov.tw/cl.aspx?n=2411">Taiwan DGBAS national wealth statistics</a>. <a href="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD">GDP</a> and <a href="https://data.worldbank.org/indicator/EN.URB.MCTY.TL.ZS">population in large cities</a>: World Bank (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). Additional GDP: <a href="https://unstats.un.org/unsd/snaama/">UN Statistics Division</a> and <a href="https://eng.stat.gov.tw/News_Content.aspx?n=2336&amp;s=235628">Taiwan DGBAS national accounts</a>. Taiwan exchange rate: <a href="https://www.cbc.gov.tw/en/">Taiwan Central Bank</a>.</p>
<p>Billionaire net worths: Forbes real-time profiles, for example <a href="https://www.forbes.com/profile/elon-musk/">Elon Musk</a>, 16 October 2026.</p>
<p>Map: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, tiles from the <a href="https://operations.osmfoundation.org/policies/tiles/">OpenStreetMap Foundation</a>.</p>
<p>Place names: <a href="https://www.geonames.org/">GeoNames</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Boundaries and statistics notices: &copy; EuroGeographics for the administrative boundaries. Source: Eurostat; moneymap derives regional shares from these figures, and Eurostat is not responsible for the results. Contains public sector information licensed under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>. Contains OS data &copy; Crown copyright and database right 2026. Copyright Scottish Government, contains Ordnance Survey data &copy; Crown copyright and database right 2026. Source: NISRA; contains Ordnance Survey of Northern Ireland information licensed under the Open Government Licence v3.0. Full citations are in <a href="${SOURCE_REPOSITORY}/blob/main/docs/methodology.md">How the numbers are calculated</a>.</p>
<footer><p>Source code (MIT licence): <a href="${SOURCE_REPOSITORY}">github.com/joshp123/moneymap</a> · <a href="${SOURCE_REPOSITORY}/blob/main/docs/methodology.md">How the numbers are calculated</a> · Live version: ${liveVersion}</p></footer>
<script>
var map = L.map('map').setView([20, 0], 2);
var CirclesLayer = L.featureGroup().addTo(map);
var selectedPoint = null;
var pendingRequest = null;
var lastResult = null;
var params = new URLSearchParams(location.search);
var mode = params.get('mode') === 'land' ? 'property' : ['gdp', 'property'].includes(params.get('mode')) ? params.get('mode') : 'population';
if (params.get('mode') === 'land') {
  params.set('mode', 'property');
  history.replaceState({}, '', '?' + params);
}
var range = document.getElementById('range');
var numberFormat = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
function money(value) {
  if (value === null) return 'No population';
  if (value >= 1e12) return '$' + Number((value / 1e12).toPrecision(3)) + ' trillion';
  if (value >= 1e9) return '$' + Number((value / 1e9).toPrecision(3)) + ' billion';
  if (value >= 1e6) return '$' + Number((value / 1e6).toPrecision(3)) + ' million';
  return '$' + numberFormat.format(value);
}
// What the circle could buy, said the way a person would: the nearest comparison on a
// ladder with at least one rung per order of magnitude, a count of Freddo bars, and Elon.
// People: Forbes real-time profiles, 16 October 2026. Things: approximate US list prices,
// 2025-26; Salvator Mundi's 2017 sale price. A Freddo is about 30p ($0.40).
// [singular, plural, value in US dollars]
var ELON_MUSK = ['Elon Musk', 'Elon Musks', 908.5e9];
var FREDDO_BAR = ['Freddo bar', 'Freddo bars', 0.40];
var COMPARISON_LADDER = [
  ['Jeff Bezos', 'Jeff Bezoses', 369.8e9], ['Larry Page', 'Larry Pages', 279.3e9],
  ['Mark Zuckerberg', 'Mark Zuckerbergs', 243.3e9], ['Jensen Huang', 'Jensen Huangs', 186e9],
  ['Warren Buffett', 'Warren Buffetts', 151.1e9], ['Bill Gates', 'Bill Gateses', 117.7e9],
  ['Michael Bloomberg', 'Michael Bloombergs', 94.9e9], ['Mukesh Ambani', 'Mukesh Ambanis', 83.4e9],
  ['Masayoshi Son', 'Masayoshi Sons', 60.4e9], ['Peter Thiel', 'Peter Thiels', 36.4e9],
  ['Phil Knight', 'Phil Knights', 25.4e9], ['James Dyson', 'James Dysons', 14.7e9],
  ['Steven Spielberg', 'Steven Spielbergs', 7.9e9], ['George Lucas', 'George Lucases', 5.4e9],
  ['Michael Jordan', 'Michael Jordans', 4.7e9], ['Oprah', 'Oprahs', 3.4e9],
  ['Taylor Swift', 'Taylor Swifts', 2.0e9], ['Rihanna', 'Rihannas', 1.0e9],
  ['Salvator Mundi', 'Salvator Mundis', 450.3e6], ['Gulfstream G700', 'Gulfstream G700s', 78e6],
  ['Bugatti Tourbillon', 'Bugatti Tourbillons', 4.1e6], ['Lamborghini Revuelto', 'Lamborghini Revueltos', 608e3],
  ['Tesla Model Y', 'Tesla Model Ys', 45e3], ['iPhone 17 Pro', 'iPhone 17 Pros', 1099],
];
var CLOSEST_RATIO = 0.25, FURTHEST_RATIO = 10;
function shortMoney(value) {
  var scaled = function (amount, suffix) { return '$' + (amount >= 10 ? numberFormat.format(Math.round(amount)) : amount.toFixed(1)) + suffix; };
  if (value >= 1e9) return scaled(value / 1e9, 'bn');
  if (value >= 1e6) return scaled(value / 1e6, 'm');
  if (value >= 1e4) return '$' + numberFormat.format(Math.round(value / 1e3)) + 'k';
  if (value >= 100) return '$' + numberFormat.format(Math.round(value));
  return '$' + value.toFixed(2);
}
function inWords(count) {
  var rounded = function (amount) { return String(Number(amount.toPrecision(2))); };
  if (count >= 1e12) return rounded(count / 1e12) + ' trillion';
  if (count >= 1e9) return rounded(count / 1e9) + ' billion';
  if (count >= 1e6) return rounded(count / 1e6) + ' million';
  return numberFormat.format(Math.round(count));
}
function howMany(ratio, item) {
  var article = /^[AEIOU]/.test(item[0]) ? 'an ' : 'a ';
  if (ratio < 0.3) return 'a quarter of ' + article + item[0];
  if (ratio < 0.4) return 'a third of ' + article + item[0];
  if (ratio < 0.6) return 'half ' + article + item[0];
  if (ratio < 0.85) return 'three-quarters of ' + article + item[0];
  if (ratio < 1.3) return 'one ' + item[0];
  if (ratio < 1.75) return 'one and a half ' + item[1];
  return numberFormat.format(Math.round(ratio)) + ' ' + item[1];
}
function inElonMusks(value) {
  var ratio = value / ELON_MUSK[2];
  var amount = ratio >= CLOSEST_RATIO ? howMany(ratio, ELON_MUSK)
    : (ratio * 100).toLocaleString('en-GB', { maximumSignificantDigits: 2 }) + '% of an Elon Musk';
  return amount + ' (' + shortMoney(ELON_MUSK[2]) + ')';
}
function inBillionaires(value) {
  if (!(value > 0)) return { text: "That's not even one Freddo bar, or 0% of an Elon Musk." };
  var nearest = COMPARISON_LADDER
    .map(function (item) { return { item: item, ratio: value / item[2] }; })
    .filter(function (match) { return match.ratio >= CLOSEST_RATIO && match.ratio <= FURTHEST_RATIO; })
    .sort(function (a, b) { return Math.abs(Math.log(a.ratio)) - Math.abs(Math.log(b.ratio)); })[0];
  var phrases = [];
  if (nearest) phrases.push(howMany(nearest.ratio, nearest.item) + ' (' + shortMoney(nearest.item[2]) + (nearest.ratio >= 1.3 ? ' each' : '') + ')');
  phrases.push(inWords(value / FREDDO_BAR[2]) + ' Freddo bars (30p each)');
  return { text: "That's about " + phrases.join(', ') + ' or ' + inElonMusks(value) + '.' };
}
function perHead(value) {
  return value === null ? '' : '$' + numberFormat.format(value);
}
// Where the circle is, from the nearest named place the API returns.
function whereText() {
  if (!lastResult) return 'within the circle';
  var radius = 'within ' + lastResult.distance_km + ' km of ';
  var place = lastResult.place;
  if (!place) return radius + Math.abs(lastResult.lat).toFixed(2) + '°' + (lastResult.lat >= 0 ? 'N' : 'S') + ' ' + Math.abs(lastResult.long).toFixed(2) + '°' + (lastResult.long >= 0 ? 'E' : 'W');
  var name = place.name + ', ' + place.country.replace(/^The /, 'the ');
  return place.distance_km <= 10 ? radius + name : radius + 'a point ' + Math.round(place.distance_km) + ' km from ' + name;
}
function resultLabel() {
  if (mode === 'property') return 'Land and buildings ' + whereText() + ' (2024, US dollars):';
  if (mode === 'gdp') return 'GDP ' + whereText() + ' in 2024 (PPP, international dollars):';
  return 'People living ' + whereText() + ' in 2025:';
}
function renderResult() {
  var isGDP = mode === 'gdp';
  var isProperty = mode === 'property';
  var heading = isProperty ? 'Property value' : isGDP ? 'GDP' : 'Population';
  document.getElementById('heading').textContent = heading + ' around a point';
  document.title = 'moneymap: ' + (isGDP ? 'GDP' : heading.toLowerCase()) + ' around a point';
  document.getElementById('populationmode').setAttribute('aria-pressed', String(mode === 'population'));
  document.getElementById('gdpmode').setAttribute('aria-pressed', String(isGDP));
  document.getElementById('propertymode').setAttribute('aria-pressed', String(isProperty));
  document.getElementById('resultlabel').textContent = resultLabel();
  document.getElementById('maincounter').textContent = lastResult ? (isProperty ? money(lastResult.land_value + lastResult.building_value) : isGDP ? money(lastResult.gdp) : numberFormat.format(lastResult.population)) : '--';
  var secondary = '';
  if (lastResult) {
    if (isProperty) secondary = 'Land ' + money(lastResult.land_value) + ' · Buildings ' + money(lastResult.building_value);
    else secondary = (isGDP ? 'Population in 2025: ' + numberFormat.format(lastResult.population) : 'GDP in 2024: ' + money(lastResult.gdp)) + (lastResult.gdp_per_head === null ? '' : ' · ' + perHead(lastResult.gdp_per_head) + ' per person');
  }
  document.getElementById('secondarycounter').textContent = secondary;
  document.getElementById('billionairecounter').hidden = !isProperty || !lastResult;
  var scale = isProperty && lastResult ? inBillionaires(lastResult.land_value + lastResult.building_value) : null;
  document.getElementById('billionairecounter').textContent = scale ? scale.text : '';
  document.getElementById('stopcounter').hidden = mode !== 'population' || !lastResult;
  document.getElementById('stopcounter').textContent = lastResult ? 'The circle also contains ' + numberFormat.format(lastResult.bus_stops) + ' bus stops, ' + numberFormat.format(lastResult.tram_stops) + ' tram stops, and ' + numberFormat.format(lastResult.rail_stops) + ' metro and train stops.' : '';
  document.getElementById('copyimage').disabled = !lastResult;
  document.getElementById('imagestatus').textContent = '';
  renderTable();
}
function drawShareCard() {
  var width = 1200, height = 675, headerHeight = 64, mapSide = height - headerHeight;
  var panelLeft = mapSide + 36, panelWidth = width - panelLeft - 36;
  var canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  var context = canvas.getContext('2d');
  context.textBaseline = 'top';
  context.fillStyle = 'white';
  context.fillRect(0, 0, width, height);
  context.fillStyle = '#183551';
  context.fillRect(0, 0, width, headerHeight);
  context.fillStyle = 'white';
  context.textAlign = 'center';
  context.font = 'bold 34px sans-serif';
  context.fillText(document.getElementById('heading').textContent.toUpperCase(), width / 2, 15);

  // A square of the map around the circle, scaled to fill the left of the card.
  var mapElement = map.getContainer();
  var mapBounds = mapElement.getBoundingClientRect();
  var mapSize = map.getSize();
  var side = Math.min(mapSize.x, mapSize.y);
  var centre = selectedPoint ? map.latLngToContainerPoint(selectedPoint) : L.point(mapSize.x / 2, mapSize.y / 2);
  var cropLeft = Math.min(Math.max(centre.x - side / 2, 0), mapSize.x - side);
  var cropTop = Math.min(Math.max(centre.y - side / 2, 0), mapSize.y - side);
  var scale = mapSide / side;
  context.save();
  context.beginPath();
  context.rect(0, headerHeight, mapSide, mapSide);
  context.clip();
  context.translate(0, headerHeight);
  context.scale(scale, scale);
  context.translate(-cropLeft, -cropTop);
  context.fillStyle = '#ddd';
  context.fillRect(0, 0, mapSize.x, mapSize.y);
  mapElement.querySelectorAll('.leaflet-tile-loaded').forEach(function (tile) {
    var bounds = tile.getBoundingClientRect();
    if (tile.naturalWidth && bounds.width && bounds.height) {
      context.globalAlpha = Number(getComputedStyle(tile).opacity);
      context.drawImage(tile, bounds.left - mapBounds.left - mapElement.clientLeft,
        bounds.top - mapBounds.top - mapElement.clientTop, bounds.width, bounds.height);
    }
  });
  context.globalAlpha = 1;
  CirclesLayer.eachLayer(function (circle) {
    var bounds = circle.getBounds();
    var northWest = map.latLngToContainerPoint(bounds.getNorthWest());
    var southEast = map.latLngToContainerPoint(bounds.getSouthEast());
    context.beginPath();
    context.ellipse((northWest.x + southEast.x) / 2, (northWest.y + southEast.y) / 2,
      (southEast.x - northWest.x) / 2, (southEast.y - northWest.y) / 2, 0, 0, 2 * Math.PI);
    context.fillStyle = circle.options.fillColor || circle.options.color;
    context.globalAlpha = circle.options.fillOpacity;
    context.fill();
    context.strokeStyle = circle.options.color;
    context.lineWidth = 3 / scale;
    context.globalAlpha = circle.options.opacity;
    context.stroke();
  });
  context.restore();
  context.textAlign = 'right';
  context.font = '13px sans-serif';
  var credit = '© OpenStreetMap contributors';
  var creditWidth = context.measureText(credit).width + 12;
  context.fillStyle = 'rgba(255, 255, 255, 0.9)';
  context.fillRect(mapSide - creditWidth, height - 20, creditWidth, 20);
  context.fillStyle = '#183551';
  context.fillText(credit, mapSide - 6, height - 17);

  // The figures, left-aligned in the right-hand panel.
  context.textAlign = 'left';
  function drawWrapped(text, y, font, colour, lineHeight) {
    context.font = font;
    context.fillStyle = colour;
    var line = '';
    text.split(' ').forEach(function (word) {
      var next = line ? line + ' ' + word : word;
      if (line && context.measureText(next).width > panelWidth) {
        context.fillText(line, panelLeft, y);
        y += lineHeight;
        line = word;
      } else line = next;
    });
    context.fillText(line, panelLeft, y);
    return y + lineHeight;
  }
  var where = whereText();
  var y = drawWrapped(where.charAt(0).toUpperCase() + where.slice(1), headerHeight + 34, 'bold 30px sans-serif', '#183551', 38);
  var unit = mode === 'property' ? 'Land and buildings, 2024, US dollars' : mode === 'gdp' ? 'GDP in 2024, PPP international dollars' : 'People living there in 2025';
  y = drawWrapped(unit, y + 18, '20px sans-serif', '#555', 26);
  y = drawWrapped(document.getElementById('maincounter').textContent, y + 4, 'bold 64px sans-serif', 'black', 72);
  y = drawWrapped(document.getElementById('secondarycounter').textContent, y + 4, '22px sans-serif', 'black', 30);
  var detail = document.getElementById(mode === 'property' ? 'billionairecounter' : 'stopcounter');
  if (!detail.hidden) drawWrapped(detail.textContent, y + 10, '20px sans-serif', 'black', 27);
  drawWrapped('moneymap.jjpcodes.com', height - 92, 'bold 34px sans-serif', '#183551', 40);
  drawWrapped('Read the methodology before posting a screenshot on Twitter pwning me', height - 44, '15px sans-serif', '#183551', 20);
  return new Promise(function (resolve, reject) {
    canvas.toBlob(function (blob) {
      if (blob) resolve(blob);
      else reject(new Error('Could not create the PNG'));
    }, 'image/png');
  });
}
async function copyImage() {
  var button = document.getElementById('copyimage');
  var status = document.getElementById('imagestatus');
  button.disabled = true;
  status.textContent = '';
  var blobPromise = Promise.resolve().then(drawShareCard);
  try {
    if (navigator.clipboard && window.ClipboardItem) {
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blobPromise })]);
        status.textContent = 'Image copied. Paste it into your post.';
        return;
      } catch (error) {
        // The same PNG is still available when clipboard permission is denied.
      }
    }
    var url = URL.createObjectURL(await blobPromise);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'moneymap.png';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    status.textContent = 'Image downloaded.';
  } catch (error) {
    status.textContent = 'Could not create the image. Please try again.';
  } finally {
    button.disabled = !lastResult;
  }
}
function renderTable() {
  if (!lastResult) {
    document.getElementById('table').textContent = '';
    return;
  }
  var showStops = mode === 'population';
  var showProperty = mode === 'property';
  var tableHTML = '<table' + (showStops ? ' class="population-table"' : '') + '><thead><tr><th>Radius (km)</th>' + (showProperty ? '<th>Land</th><th>Buildings</th><th>Total</th>' : '<th>Population</th><th>GDP</th><th>GDP per head</th>') + (showStops ? '<th>Bus stops</th><th>Tram stops</th><th>Metro and train stops</th>' : '') + '</tr></thead><tbody>';
  lastResult.cumulative.forEach(function (row) {
    tableHTML += '<tr><td>' + row.distance_km + '</td>' + (showProperty ? '<td>' + money(row.land_value) + '</td><td>' + money(row.building_value) + '</td><td>' + money(row.land_value + row.building_value) + '</td>' : '<td>' + numberFormat.format(row.population) + '</td><td>' + money(row.gdp) + '</td><td>' + perHead(row.gdp_per_head) + '</td>') + (showStops ? '<td>' + numberFormat.format(row.bus_stops) + '</td><td>' + numberFormat.format(row.tram_stops) + '</td><td>' + numberFormat.format(row.rail_stops) + '</td>' : '') + '</tr>';
  });
  document.getElementById('table').innerHTML = tableHTML + '</tbody></table>';
}
function changeMode(nextMode) {
  mode = nextMode;
  var url = new URL(location.href);
  if (mode !== 'population') url.searchParams.set('mode', mode);
  else url.searchParams.delete('mode');
  history.replaceState({}, '', url);
  renderResult();
}
document.getElementById('populationmode').addEventListener('click', function () { changeMode('population'); });
document.getElementById('gdpmode').addEventListener('click', function () { changeMode('gdp'); });
document.getElementById('propertymode').addEventListener('click', function () { changeMode('property'); });
document.getElementById('copyimage').addEventListener('click', copyImage);
renderResult();
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  crossOrigin: 'anonymous',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
var reloadControl = L.Control.extend({
  options: { position: 'topright' },
  onAdd: function () {
    var container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
    var button = L.DomUtil.create('a', '', container);
    button.href = '#';
    button.style.cssText = 'padding:4px;width:70px;cursor:pointer';
    button.textContent = 'Reset Map';
    L.DomEvent.disableClickPropagation(container);
    L.DomEvent.on(button, 'click', function (event) {
      L.DomEvent.preventDefault(event);
      if (pendingRequest) pendingRequest.abort();
      selectedPoint = null;
      CirclesLayer.clearLayers();
      map.setView([20, 0], 2);
      lastResult = null;
      renderResult();
      document.getElementById('table').textContent = '';
      document.getElementById('status').textContent = 'Click on the map to calculate.';
      history.replaceState({}, '', location.pathname + (mode === 'population' ? '' : '?mode=' + mode));
    });
    return container;
  }
});
map.addControl(new reloadControl());
var methodologyNote = L.control({ position: 'bottomleft' });
methodologyNote.onAdd = function () {
  var note = L.DomUtil.create('div', 'leaflet-control methodology-note');
  note.innerHTML = '<a href="${SOURCE_REPOSITORY}/blob/main/docs/methodology.md">Read the methodology before posting a screenshot on Twitter pwning me</a>';
  L.DomEvent.disableClickPropagation(note);
  return note;
};
methodologyNote.addTo(map);
function drawcircles(latitude, longitude, zoom) {
  CirclesLayer.clearLayers();
  L.circle([latitude, longitude], { radius: 1000 * Number(range.value) }).addTo(CirclesLayer);
  if (zoom !== undefined) map.setView([latitude, longitude], zoom);
  else map.fitBounds(CirclesLayer.getBounds());
}
async function requestData(latitude, longitude) {
  if (pendingRequest) pendingRequest.abort();
  var controller = new AbortController();
  pendingRequest = controller;
  lastResult = null;
  renderResult();
  document.getElementById('table').textContent = '';
  document.getElementById('status').textContent = 'Calculating…';
  var params = new URLSearchParams({ lat: latitude.toFixed(5), long: longitude.toFixed(5), distance_km: range.value, zoom: map.getZoom() });
  if (mode !== 'population') params.set('mode', mode);
  history.replaceState({}, '', '?' + params);
  try {
    var response = await fetch('/api/circle?' + params, { signal: controller.signal });
    if (!response.ok) throw new Error(await response.text());
    var result = await response.json();
    lastResult = result;
    renderResult();
    document.getElementById('status').textContent = '';
  } catch (error) {
    if (error.name !== 'AbortError') document.getElementById('status').textContent = 'Could not calculate: ' + error.message;
  }
}
map.on('click', function (event) {
  selectedPoint = [event.latlng.lat, Math.max(-180, Math.min(180, event.latlng.wrap().lng))];
  drawcircles(selectedPoint[0], selectedPoint[1]);
  requestData(selectedPoint[0], selectedPoint[1]);
});
map.on('zoomend', function () {
  var url = new URL(location.href);
  if (url.searchParams.has('lat')) {
    url.searchParams.set('zoom', map.getZoom());
    history.replaceState({}, '', url);
  }
});
range.addEventListener('input', function () { document.getElementById('rangelabel').textContent = range.value; });
range.addEventListener('change', function () {
  if (selectedPoint) {
    drawcircles(selectedPoint[0], selectedPoint[1]);
    requestData(selectedPoint[0], selectedPoint[1]);
  }
});
if (['lat', 'long', 'distance_km'].every(function (name) { return params.has(name) && params.get(name).trim() !== ''; })) {
  var latitude = Number(params.get('lat'));
  var longitude = Number(params.get('long'));
  var radius = Number(params.get('distance_km'));
  var zoom = params.has('zoom') ? Number(params.get('zoom')) : undefined;
  if (Number.isFinite(latitude) && Math.abs(latitude) <= 90 && Number.isFinite(longitude) && Math.abs(longitude) <= 180 && Number.isFinite(radius) && radius >= 3 && radius <= 100) {
    range.value = radius;
    document.getElementById('rangelabel').textContent = range.value;
    selectedPoint = [latitude, longitude];
    drawcircles(latitude, longitude, Number.isFinite(zoom) ? zoom : undefined);
    requestData(latitude, longitude);
  }
}
</script>
</body>
</html>`;

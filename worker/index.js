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
const LAYERS = ['gdp', 'population', 'bus_stops', 'tram_stops', 'rail_stops'];

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

function totals(gdp, population, busStops, tramStops, railStops) {
  return { gdp, population, gdp_per_head: population > 0 ? gdp / population : null,
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
      const [gdpValues, populationValues, busStopValues, tramStopValues, railStopValues] = layers;
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
          if (gdp === 0 && population === 0 && busStops === 0 && tramStops === 0 && railStops === 0) continue;
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
  const cumulative = [];
  for (let kilometre = 1; kilometre <= Math.ceil(radius); kilometre++) {
    gdp += gdpByKilometre[kilometre];
    population += populationByKilometre[kilometre];
    busStops += busStopsByKilometre[kilometre];
    tramStops += tramStopsByKilometre[kilometre];
    railStops += railStopsByKilometre[kilometre];
    if (kilometre <= radius) cumulative.push({ distance_km: kilometre, ...totals(gdp, population, busStops, tramStops, railStops) });
  }
  return { lat: latitude, long: longitude, distance_km: radius, ...totals(gdp, population, busStops, tramStops, railStops), cumulative };
}

// deploy/sync-tiles.mjs lists, writes and deletes one layer's tiles here. Without the token these paths do not exist.
// GET /__upload/layers/<layer>/ returns {key: etag}; R2's etag is the MD5 of the tile.
// PUT and DELETE /__upload/layers/<layer>/<tileRow>/<tileColumn>.bin write or remove one tile.
const TILE_SYNC_PATH = new RegExp(`^/__upload/(layers/(?:${LAYERS.join('|')})/)(?:(\\d+)/(\\d+)\\.bin)?$`);
const notFound = () => new Response('Not found', { status: 404 });

async function layerTileEtags(bucket, prefix) {
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
  const match = TILE_SYNC_PATH.exec(pathname);
  if (!match) return notFound();
  const [, layerPrefix, tileRow, tileColumn] = match;
  if (tileRow === undefined) {
    return request.method === 'GET' ? Response.json(await layerTileEtags(env.TILES, layerPrefix)) : notFound();
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
      return Response.json(await circle(env.TILES, parameters));
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
            padding: 0.4em;
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
            height: 520px;
            max-height: 55vh;
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
            margin-top: 0.4em;
            margin-bottom: 0.4em;
            font-size: 4em;
            font-weight: bold;
        }

        .mode-switch {
            display: flex;
            justify-content: center;
            margin: 1em;
        }

        .mode-switch button {
            min-height: 44px;
            padding: 0.6em 1em;
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

        #secondarycounter, #stopcounter {
            text-align: center;
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
<div class="mode-switch" role="group" aria-label="Display">
<button type="button" id="populationmode" aria-pressed="true">Population</button>
<button type="button" id="gdpmode" aria-pressed="false">GDP</button>
</div>
<p style="text-align:center">GDP and population within a distance, from any point in the world.</p>
<p style="text-align:center">Select a radius and click on the map.</p>
<p style="text-align:center"><input type="range" id="range" min="3" value="5" max="100" step="1">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<label for="range" id="rangelabel">5</label> km.</p>
<div id="bringSitesMapHolder"><div id="leftMask"></div><div id="rightMask"></div><div id="map"></div></div>
<p id="resultlabel">Population within circle in 2025:</p>
<p style="text-align:center" id="maincounter" aria-live="polite">--</p>
<p id="stopcounter" hidden></p>
<p id="secondarycounter"></p>
<p id="status" role="status" style="text-align:center">Click on the map to calculate.</p>
<h2>Give me the data!</h2>
<div id="table"></div>
<h2>Sources and credits</h2>
<p>Based on <a href="https://www.tomforth.co.uk/circlepopulations/">Tom Forth's Population around a point tool and page</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>GDP, 2024: <a href="https://doi.org/10.1038/s41597-025-04487-x">Kummu et al. (2025)</a>, <a href="https://zenodo.org/records/18429133">March 2026 release</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Regional GDP: <a href="https://www.bea.gov/data/gdp/gdp-county-metro-and-other-areas">BEA (2024)</a>, <a href="https://www.ons.gov.uk/economy/grossdomesticproductgdp">ONS (2023)</a>, <a href="https://ec.europa.eu/eurostat/web/regions/database">Eurostat (2023)</a> and <a href="https://www.cbs.nl/en-gb/figures">CBS (2023)</a>. Built-up volume and surface, 2025: GHSL <a href="https://ghsl.jrc.ec.europa.eu/ghs_buV2023.php">GHS-BUILT-V</a> and <a href="https://ghsl.jrc.ec.europa.eu/ghs_buS2023.php">GHS-BUILT-S</a> R2023A, European Commission Joint Research Centre (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Population, 2025: <a href="https://ghsl.jrc.ec.europa.eu/ghs_pop2023.php">GHS-POP R2023A, European Commission Joint Research Centre</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>Workplace places: <a href="https://overturemaps.org/">Overture Maps Foundation</a>, September 2026 (<a href="https://cdla.dev/permissive-2-0/">CDLA Permissive 2.0</a> and <a href="https://www.apache.org/licenses/LICENSE-2.0">Apache 2.0</a>).</p>
<p>US workplace jobs: US Census Bureau, <a href="https://lehd.ces.census.gov/data/lodes/LODES8/">LEHD Origin-Destination Employment Statistics</a> (public domain).</p>
<p>Transit stops: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, via <a href="https://overturemaps.org/">Overture Maps Foundation</a> (<a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a>).</p>
<p>Map: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.</p>
<footer><p>Source code (MIT licence): <a href="${SOURCE_REPOSITORY}">github.com/joshp123/moneymap</a> · <a href="${SOURCE_REPOSITORY}/blob/main/docs/methodology.md">How the numbers are calculated</a> · Live version: ${liveVersion}</p></footer>
<script>
var map = L.map('map').setView([20, 0], 2);
var CirclesLayer = L.featureGroup().addTo(map);
var selectedPoint = null;
var pendingRequest = null;
var lastResult = null;
var params = new URLSearchParams(location.search);
var mode = params.get('mode') === 'gdp' ? 'gdp' : 'population';
var range = document.getElementById('range');
var numberFormat = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
function money(value) {
  if (value === null) return 'No population';
  if (value >= 1e12) return '$' + (value / 1e12).toFixed(1) + ' trillion';
  if (value >= 1e9) return '$' + (value / 1e9).toFixed(1) + ' billion';
  if (value >= 1e6) return '$' + (value / 1e6).toFixed(1) + ' million';
  return '$' + numberFormat.format(value);
}
function perHead(value) {
  return value === null ? '' : '$' + numberFormat.format(value);
}
function renderResult() {
  var isGDP = mode === 'gdp';
  document.getElementById('heading').textContent = isGDP ? 'GDP around a point' : 'Population around a point';
  document.title = 'moneymap: ' + (isGDP ? 'GDP' : 'population') + ' around a point';
  document.getElementById('populationmode').setAttribute('aria-pressed', String(!isGDP));
  document.getElementById('gdpmode').setAttribute('aria-pressed', String(isGDP));
  document.getElementById('resultlabel').textContent = isGDP ? 'GDP within circle in 2024 (PPP, 2021 international dollars):' : 'Population within circle in 2025:';
  document.getElementById('maincounter').textContent = lastResult ? (isGDP ? money(lastResult.gdp) : numberFormat.format(lastResult.population)) : '--';
  document.getElementById('secondarycounter').textContent = lastResult ? (isGDP ? 'Population in 2025: ' + numberFormat.format(lastResult.population) : 'GDP in 2024: ' + money(lastResult.gdp)) + (lastResult.gdp_per_head === null ? '' : ' · ' + perHead(lastResult.gdp_per_head) + ' per person') : '';
  document.getElementById('stopcounter').hidden = isGDP || !lastResult;
  document.getElementById('stopcounter').textContent = lastResult ? 'The circle also contains ' + numberFormat.format(lastResult.bus_stops) + ' bus stops, ' + numberFormat.format(lastResult.tram_stops) + ' tram stops, and ' + numberFormat.format(lastResult.rail_stops) + ' metro and train stops.' : '';
  renderTable();
}
function renderTable() {
  if (!lastResult) {
    document.getElementById('table').textContent = '';
    return;
  }
  var showStops = mode === 'population';
  var tableHTML = '<table' + (showStops ? ' class="population-table"' : '') + '><thead><tr><th>Radius (km)</th><th>Population</th><th>GDP</th><th>GDP per head</th>' + (showStops ? '<th>Bus stops</th><th>Tram stops</th><th>Metro and train stops</th>' : '') + '</tr></thead><tbody>';
  lastResult.cumulative.forEach(function (row) {
    tableHTML += '<tr><td>' + row.distance_km + '</td><td>' + numberFormat.format(row.population) + '</td><td>' + money(row.gdp) + '</td><td>' + perHead(row.gdp_per_head) + '</td>' + (showStops ? '<td>' + numberFormat.format(row.bus_stops) + '</td><td>' + numberFormat.format(row.tram_stops) + '</td><td>' + numberFormat.format(row.rail_stops) + '</td>' : '') + '</tr>';
  });
  document.getElementById('table').innerHTML = tableHTML + '</tbody></table>';
}
function changeMode(nextMode) {
  mode = nextMode;
  var url = new URL(location.href);
  if (mode === 'gdp') url.searchParams.set('mode', 'gdp');
  else url.searchParams.delete('mode');
  history.replaceState({}, '', url);
  renderResult();
}
document.getElementById('populationmode').addEventListener('click', function () { changeMode('population'); });
document.getElementById('gdpmode').addEventListener('click', function () { changeMode('gdp'); });
renderResult();
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
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
      history.replaceState({}, '', location.pathname + (mode === 'gdp' ? '?mode=gdp' : ''));
    });
    return container;
  }
});
map.addControl(new reloadControl());
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
  if (mode === 'gdp') params.set('mode', 'gdp');
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

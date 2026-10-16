// Written by AI on 2026.10.16 by model gpt-6.1-sol.
const GRID = {
  width: 43202, height: 21384,
  west: -180.00791593130032, north: 89.0995831776456,
  pixelWidth: 0.008333333300326923, pixelHeight: 0.00833333329979504, tileSize: 120,
};
const EARTH_RADIUS_KM = 6371.0088;
const RADIANS = Math.PI / 180;
const TILE_CELLS = GRID.tileSize ** 2;
const TILE_BYTES = TILE_CELLS * 8;

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

function totals(gdp, population) {
  return { gdp, population, gdp_per_head: population > 0 ? gdp / population : null };
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
  const tileCoordinates = [];
  for (let tileRow = Math.floor(firstRow / GRID.tileSize); tileRow <= Math.floor(lastRow / GRID.tileSize); tileRow++) {
    for (let tileColumn = Math.floor(firstColumn / GRID.tileSize); tileColumn <= Math.floor(lastColumn / GRID.tileSize); tileColumn++) {
      tileCoordinates.push([tileRow, tileColumn]);
    }
  }
  for (let batchStart = 0; batchStart < tileCoordinates.length; batchStart += 16) {
    await Promise.all(tileCoordinates.slice(batchStart, batchStart + 16).map(async ([tileRow, tileColumn]) => {
      const object = await bucket.get(`tiles/${tileRow}/${tileColumn}.bin`);
      if (!object) return;
      const bytes = await object.arrayBuffer();
      if (bytes.byteLength !== TILE_BYTES) throw new Error(`Invalid tile size: ${tileRow}/${tileColumn}`);
      const values = new DataView(bytes);
      const rowStart = tileRow * GRID.tileSize;
      const columnStart = tileColumn * GRID.tileSize;
      for (let row = Math.max(firstRow, rowStart); row <= Math.min(lastRow, rowStart + GRID.tileSize - 1); row++) {
        const cellLatitude = (GRID.north - (row + 0.5) * GRID.pixelHeight) * RADIANS;
        const latitudeDistance = Math.sin((cellLatitude - latitudeRadians) / 2) ** 2;
        const cosineProduct = Math.cos(latitudeRadians) * Math.cos(cellLatitude);
        for (let column = Math.max(firstColumn, columnStart); column <= Math.min(lastColumn, columnStart + GRID.tileSize - 1); column++) {
          const cellIndex = (row - rowStart) * GRID.tileSize + column - columnStart;
          const gdp = values.getFloat32(cellIndex * 4, true);
          const population = values.getFloat32((TILE_CELLS + cellIndex) * 4, true);
          if (gdp === 0 && population === 0) continue;
          const cellLongitude = GRID.west + (column + 0.5) * GRID.pixelWidth;
          const haversine = latitudeDistance + cosineProduct * Math.sin((cellLongitude - longitude) * RADIANS / 2) ** 2;
          const distance = 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, haversine)));
          if (distance <= radius) {
            const kilometre = Math.ceil(distance);
            gdpByKilometre[kilometre] += gdp;
            populationByKilometre[kilometre] += population;
          }
        }
      }
    }));
  }
  let gdp = gdpByKilometre[0];
  let population = populationByKilometre[0];
  const cumulative = [];
  for (let kilometre = 1; kilometre <= Math.ceil(radius); kilometre++) {
    gdp += gdpByKilometre[kilometre];
    population += populationByKilometre[kilometre];
    if (kilometre <= radius) cumulative.push({ distance_km: kilometre, ...totals(gdp, population) });
  }
  return { lat: latitude, long: longitude, distance_km: radius, ...totals(gdp, population), cumulative };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const upload = /^\/__upload\/(tiles\/(\d+)\/(\d+)\.bin)$/.exec(url.pathname);
    if (upload && (request.method === 'PUT' || request.method === 'HEAD')) {
      if (!env.UPLOAD_TOKEN || request.headers.get('Authorization') !== `Bearer ${env.UPLOAD_TOKEN}`) {
        return new Response('Not found', { status: 404 });
      }
      if (Number(upload[2]) >= Math.ceil(GRID.height / GRID.tileSize) || Number(upload[3]) >= Math.ceil(GRID.width / GRID.tileSize)) {
        return new Response('Invalid tile coordinates', { status: 400 });
      }
      if (request.method === 'HEAD') {
        const object = await env.TILES.head(upload[1]);
        return new Response(null, { status: object ? 200 : 404, headers: object ? { 'content-length': String(object.size) } : {} });
      }
      const bytes = await request.arrayBuffer();
      if (bytes.byteLength !== TILE_BYTES) return new Response('Invalid tile size', { status: 400 });
      await env.TILES.put(upload[1], bytes);
      return new Response(null, { status: 201 });
    }
    if (request.method === 'GET' && url.pathname === '/') {
      return new Response(page, { headers: { 'content-type': 'text/html; charset=utf-8' } });
    }
    if (request.method === 'GET' && url.pathname === '/api/circle') {
      const parameters = circleParameters(url.searchParams);
      if (!parameters) return new Response('Use lat from -90 to 90, long from -180 to 180 and distance_km from 3 to 100.', { status: 400 });
      return Response.json(await circle(env.TILES, parameters));
    }
    return new Response('Not found', { status: 404 });
  },
};

const page = `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>moneymap: GDP around a point</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <style>
        input {
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
            padding-left: 2px;
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

        table {
            width: 100%;
            text-align: center;
            border: 1px solid black;
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

        #gdpcounter {
            line-height: 1;
            margin-top: 0.4em;
            margin-bottom: 0.4em;
            font-size: 4em;
            font-weight: bold;
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

        .top {
            margin-top: 0.2em;
            margin-bottom: 0.4em;
            text-align: center;
            font-size: smaller;
        }
    </style>
</head>
<body>
<h1>GDP around a point</h1>
<p style="text-align:center">GDP and population within a distance, from any point in the world.</p>
<p style="text-align:center">Select a radius and click on the map.</p>
<p style="text-align:center"><input type="range" id="range" min="3" value="5" max="100" step="1">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<label for="range" id="rangelabel">5</label> km.</p>
<div id="bringSitesMapHolder"><div id="leftMask"></div><div id="rightMask"></div><div id="map"></div></div>
<p>Estimated GDP within the circle in 2024:</p>
<p style="text-align:center" id="gdpcounter" aria-live="polite">--</p>
<p style="text-align:center" id="populationcounter"></p>
<p style="text-align:center" id="perheadcounter"></p>
<p id="status" role="status" style="text-align:center">Click on the map to calculate.</p>
<p>GDP at purchasing power parity, in 2021 international dollars, which are roughly US dollars adjusted so that a dollar buys the same amount everywhere.</p>
<p>These are estimates. Official regional GDP is shared out by where people live, not where they work. Places with many jobs and few residents (city centres, ports, airports and business parks) are under-counted, and small circles mostly reflect population.</p>
<h2>Give me the data!</h2>
<div id="table"></div>
<h2>Sources and credits</h2>
<p>Adapted from <a href="https://www.tomforth.co.uk/circlepopulations/">Tom Forth's original Population around a point tool and page</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).</p>
<p>GDP: <a href="https://doi.org/10.1038/s41597-025-04487-x">Kummu et al. (2025)</a>, <a href="https://zenodo.org/records/18429133">13 March 2026 data release</a>, 2024 layer (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). Population: <a href="https://ghsl.jrc.ec.europa.eu/ghs_pop2023.php">GHSL GHS-POP R2023A, 2025</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). Both use a 30 arc-second grid. Each cell is counted when its centre is inside the circle.</p>
<p>Map: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.</p>
<script>
var map = L.map('map').setView([20, 0], 2);
var CirclesLayer = L.featureGroup().addTo(map);
var selectedPoint = null;
var pendingRequest = null;
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
  return value === null ? 'No population' : '$' + numberFormat.format(value) + ' per person';
}
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
      document.getElementById('gdpcounter').textContent = '--';
      document.getElementById('populationcounter').textContent = '';
      document.getElementById('perheadcounter').textContent = '';
      document.getElementById('table').textContent = '';
      document.getElementById('status').textContent = 'Click on the map to calculate.';
      history.replaceState({}, '', location.pathname);
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
  document.getElementById('gdpcounter').textContent = '--';
  document.getElementById('populationcounter').textContent = '';
  document.getElementById('perheadcounter').textContent = '';
  document.getElementById('table').textContent = '';
  document.getElementById('status').textContent = 'Calculating…';
  var params = new URLSearchParams({ lat: latitude.toFixed(5), long: longitude.toFixed(5), distance_km: range.value, zoom: map.getZoom() });
  history.replaceState({}, '', '?' + params);
  try {
    var response = await fetch('/api/circle?' + params, { signal: controller.signal });
    if (!response.ok) throw new Error(await response.text());
    var result = await response.json();
    document.getElementById('gdpcounter').textContent = money(result.gdp);
    document.getElementById('populationcounter').textContent = numberFormat.format(result.population) + ' people (2025)';
    document.getElementById('perheadcounter').textContent = perHead(result.gdp_per_head);
    document.getElementById('status').textContent = '';
    var tableHTML = '<table><thead><tr><th>Radius (km)</th><th>GDP</th><th>Population</th><th>GDP per head</th></tr></thead><tbody>';
    result.cumulative.forEach(function (row) {
      tableHTML += '<tr><td>' + row.distance_km + '</td><td>' + money(row.gdp) + '</td><td>' + numberFormat.format(row.population) + '</td><td>' + perHead(row.gdp_per_head) + '</td></tr>';
    });
    document.getElementById('table').innerHTML = tableHTML + '</tbody></table>';
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
    drawcircles(selectedPoint[0], selectedPoint[1], map.getZoom());
    requestData(selectedPoint[0], selectedPoint[1]);
  }
});
var params = new URLSearchParams(location.search);
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

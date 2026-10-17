// Written by AI on 2026.10.17 by model gpt-6.
// Runs the lookup functions from the served page against real area files over HTTP.
// devenv shell -- node checks/named_areas_http.mjs http://127.0.0.1:8788
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createContext, runInContext } from 'node:vm';

const origin = process.argv[2] || 'http://127.0.0.1:8788';
const reportPath = process.argv[3] || 'data/build/named-areas/selection.json';
const response = await fetch(origin);
assert.equal(response.status, 200, 'Preview page must load');
const html = await response.text();
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, 'Page must contain its inline script');
new Function(script);
const lookupStart = script.indexOf('function pointInAreaRing(');
const lookupEnd = script.indexOf('function showAreaControls(', lookupStart);
assert.ok(lookupStart >= 0 && lookupEnd > lookupStart, 'Page lookup functions must be present');
const baseDeclaration = script.match(/var areaFilesBase = [^;]+;/)?.[0];
const cacheDeclaration = script.match(/var areaFileCache = [^;]+;/)?.[0];
const cacheBytesDeclaration = script.match(/var areaFileCacheBytes = [^;]+;/)?.[0];
assert.ok(baseDeclaration && cacheDeclaration && cacheBytesDeclaration, 'Page file loader state must be present');
assert.match(baseDeclaration, /['"]\/areas\/['"]/, 'Area files must use the page origin');

const requests = [];
const context = createContext({
  Response, DecompressionStream,
  fetch: async (path, options) => {
    const url = new URL(path, origin);
    const started = performance.now();
    const result = await fetch(url, options);
    const bytes = await result.arrayBuffer();
    requests.push({ path: url.pathname, status: result.status, bytes: bytes.byteLength, milliseconds: Math.round(performance.now() - started) });
    return new Response(bytes, { status: result.status, headers: result.headers });
  },
});
runInContext(baseDeclaration + '\n' + cacheDeclaration + '\n' + cacheBytesDeclaration + '\n' + script.slice(lookupStart, lookupEnd), context);

const locations = [
  { name: 'Amsterdam', latitude: 52.3731, longitude: 4.8922, expected: /^Amsterdam$/i, country: /Netherlands|Nederland/i },
  { name: 'Heidelberg', latitude: 49.4106, longitude: 8.7153, expected: /Heidelberg/i, country: /Germany|Deutschland/i },
  { name: 'Annecy', latitude: 45.8992, longitude: 6.1294, expected: /^Annecy$/i, country: /France/i },
  { name: 'San Francisco', latitude: 37.7749, longitude: -122.4194, expected: /San Francisco/i, country: /United States/i },
  { name: 'Austin', latitude: 30.2672, longitude: -97.7431, expected: /^Austin(?: city)?$/i, country: /United States/i },
  { name: 'Manhattan', latitude: 40.7831, longitude: -73.9712, expected: /^New York(?: city)?$/i, country: /United States/i },
  { name: 'Davis', latitude: 38.5449, longitude: -121.7405, expected: /^Davis(?: city)?$/i, country: /United States/i },
  { name: 'Rural Yolo County', latitude: 38.8, longitude: -121.85, expected: /^Yolo(?: County)?$/i, country: /United States/i, level: 'county' },
];
const layerNames = ['population', 'gdp', 'bus_stops', 'tram_stops', 'rail_stops', 'land_value', 'building_value'];
const levels = { lau: 0, place: 0, nuts3: 1, county: 1, nuts2: 2, state: 2, nuts1: 3, country: 4 };
const results = [];
for (const location of locations) {
  const references = await context.findNamedAreasAt(location.latitude, location.longitude);
  const reference = context.chooseNamedArea(references, null);
  assert.ok(reference, location.name + ': click must resolve an area');
  const selected = await context.loadNamedArea(reference);
  assert.match(selected.name, location.expected, location.name + ': click must pick the expected area');
  if (location.level) assert.equal(selected.level, location.level, location.name + ': rural click must fall back to its county');
  else assert.ok(['lau', 'place'].includes(selected.level), location.name + ': smallest area must be a municipality or place');
  const chain = references;
  const areas = [];
  let previousLevel = -1;
  for (const entry of chain) {
    const area = await context.loadNamedArea(entry);
    assert.equal(area.id, entry.id, 'Referenced area must exist in its record file');
    assert.equal(area.name, entry.name, 'Row label must match its loaded area');
    assert.ok(levels[area.level] > previousLevel, location.name + ': row levels must progress towards the country');
    previousLevel = levels[area.level];
    assert.ok(['Polygon', 'MultiPolygon'].includes(area.geometry.type), area.name + ': outline must be a polygon');
    assert.ok(['gisco', 'census'].includes(area.source), area.name + ': boundary source must be present for map and share-card credits');
    assert.ok(context.areaContainsPoint(area, location.longitude, location.latitude), area.name + ': full outline must contain the clicked point');
    for (const layer of layerNames) assert.ok(Number.isFinite(area.totals[layer]) && area.totals[layer] >= 0, area.name + ': ' + layer + ' must be a non-negative number');
    areas.push({ id: area.id, name: area.name, level: area.level, geometry: area.geometry.type, totals: area.totals });
  }
  assert.equal(areas.at(-1).level, 'country', location.name + ': final row entry must be the country');
  assert.match(areas.at(-1).name, location.country);
  if (location.name === 'Amsterdam') assert.deepEqual(areas.map(area => area.level), ['lau', 'nuts3', 'nuts2', 'nuts1', 'country']);
  if (location.name === 'Austin') assert.match(areas.find(area => area.level === 'county')?.name || '', /Travis/, 'Austin click must include Travis County');
  if (location.name === 'Manhattan') assert.match(areas.find(area => area.level === 'county')?.name || '', /^New York(?: County)?$/, 'Manhattan click must include New York County');
  if (location.name === 'San Francisco') {
    const fitBounds = Array.from(context.mainAreaBounds(selected.geometry));
    assert.ok(selected.bbox[0] < -123, 'San Francisco source must retain its remote Farallon Islands');
    assert.ok(fitBounds[0] > -123 && fitBounds[2] - fitBounds[0] < 0.3, 'San Francisco fit must frame the main city, excluding the Farallons');
    selected.fitBounds = fitBounds;
  }
  results.push({ click: { name: location.name, latitude: location.latitude, longitude: location.longitude }, areas, ...(selected.fitBounds ? { fit_bounds: selected.fitBounds } : {}) });
  console.log(location.name + ': ' + areas.map(area => area.name).join(' › ') + ' | population ' + Math.round(selected.totals.population).toLocaleString('en-GB') + ' | GDP ' + selected.totals.gdp.toPrecision(8));
}
const amsterdamReferences = await context.findNamedAreasAt(52.3731, 4.8922);
const province = amsterdamReferences.find(reference => reference.level === 'nuts2');
assert.ok(province, 'Amsterdam row must include its province');
const utrechtReferences = await context.findNamedAreasAt(52.0907, 5.1214);
const stickyReference = context.chooseNamedArea(utrechtReferences, province.level);
assert.equal(stickyReference.level, 'nuts2', 'A second map click must retain the chosen province level');
assert.match(stickyReference.name, /^Utrecht$/, 'Province-level click must select Utrecht province');
assert.ok(utrechtReferences.some(reference => reference.level === 'lau'), 'Sticky province selection must retain the municipality in the row');
const stickyArea = await context.loadNamedArea(stickyReference);
const davisReferences = await context.findNamedAreasAt(38.5449, -121.7405);
const cityReference = context.chooseNamedArea(davisReferences, 'place');
const cityPreference = context.preferredAreaLevel(null, cityReference, true);
const ruralReferences = await context.findNamedAreasAt(38.8, -121.85);
const ruralReference = context.chooseNamedArea(ruralReferences, cityPreference);
assert.equal(ruralReference.level, 'county', 'City preference must fall back to county at a rural point');
const retainedCityPreference = context.preferredAreaLevel(cityPreference, ruralReference, false);
assert.equal(retainedCityPreference, 'place', 'A rural fallback must preserve the explicit city preference');
const nextCity = context.chooseNamedArea(davisReferences, retainedCityPreference);
assert.equal(nextCity.level, 'place', 'The next city click after a rural fallback must return to city level');
const manifest = await context.loadAreaFile('manifest.json');
const viewportIndex = await context.loadAreaFile(manifest.viewport.index);
const viewportBounds = [4.7, 52.2, 5.1, 52.5];
const plan = context.planAreaOutlines(viewportIndex, viewportBounds, 'nuts2');
assert.equal(plan.skipped, false, 'A local province view must show outlines');
assert.ok(plan.files.length > 0 && plan.files.length <= 64, 'Viewport must request a bounded set of visible outline shards');
const viewportFeatures = [];
let hoverFeatures = 0;
for (const file of plan.files) {
  const entry = Object.entries(viewportIndex.levels.nuts2).find(([, tile]) => tile.file === file);
  assert.ok(entry, 'Every planned shard must belong to the selected level');
  const [longitude, latitude] = entry[0].split('_').map(Number);
  assert.ok(longitude < viewportBounds[2] && longitude + 1 > viewportBounds[0] && latitude < viewportBounds[3] && latitude + 1 > viewportBounds[1], 'Every requested outline shard must intersect the viewport');
  const shard = await context.loadAreaFile(file);
  assert.ok(shard.features.every(feature => feature.properties.level === 'nuts2'), 'Hover polygons must be from the current level');
  assert.ok(shard.features.every(feature => feature.properties.source === 'gisco'), 'European viewport features must carry their boundary credit source');
  hoverFeatures += shard.features.length;
  for (const feature of shard.outlines.features) {
    assert.ok(['LineString', 'MultiLineString'].includes(feature.geometry.type), 'Visible outlines must use boundary linework');
    viewportFeatures.push(feature);
  }
}
assert.ok(viewportFeatures.length > 0 && hoverFeatures > 0, 'Viewport must load visible boundaries and hover hit polygons');
const hoveredId = viewportFeatures[0].properties.id;
const hoverStyles = viewportFeatures.map(feature => context.areaOutlineStyle(feature.properties.id, hoveredId));
assert.ok(hoverStyles.some(style => style.weight === 3 && style.opacity === 0.9), 'Hovered boundary must be highlighted');
assert.ok(hoverStyles.every((style, index) => style.weight === (viewportFeatures[index].properties.id === hoveredId ? 3 : 1)), 'Hover must highlight only the hovered area across its visible parts');
const densePlan = context.planAreaOutlines(viewportIndex, [-180, -90, 180, 90], 'lau');
assert.equal(densePlan.skipped, true, 'A dense world municipality view must skip outline downloads');
assert.equal(densePlan.files.length, 0, 'Skipped outline views must plan no network requests');
assert.ok(context.areaFileCache.size <= 64 && context.areaFileCacheBytes <= 64 * 1024 * 1024, 'Area cache must stay bounded');
assert.ok(requests.every(request => request.status === 200), 'Every requested static file must load');
assert.ok(requests.every(request => request.bytes <= 20_000_000), 'Each requested static file must be no larger than 20 MB');
const report = {
  checked_at: new Date().toISOString(), origin,
  method: 'Exact lookup and file-loader functions extracted from the HTTP page and executed with native HTTP fetch; no browser or rendering verification.',
  results, requests,
  sticky_level: { from: province.name, to: stickyArea.name, level: stickyArea.level, row: Array.from(utrechtReferences, reference => ({ name: reference.name, level: reference.level })) },
  sticky_city_fallback: { preference: cityPreference, rural_level: ruralReference.level, retained_preference: retainedCityPreference, next_city: nextCity.name, next_level: nextCity.level },
  viewport: { bounds: viewportBounds, files: Array.from(plan.files), count: plan.count, line_features: viewportFeatures.length, hover_features: hoverFeatures, highlighted_id: hoveredId, dense_world_skipped: densePlan.skipped },
  total_requested_bytes: requests.reduce((sum, request) => sum + request.bytes, 0),
  largest_requested_file: requests.reduce((largest, request) => request.bytes > largest.bytes ? request : largest),
};
await mkdir(dirname(reportPath), { recursive: true });
await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log('Passed click rows, county fallback, sticky province selection, San Francisco fit and viewport/hover checks; report: ' + reportPath);

// Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.
// Makes the Site's tiles match data/layers/: uploads new and changed tiles, then deletes tiles that no longer exist locally.
//   node deploy/sync-tiles.mjs <site origin> [layer ...] [--dry-run]
// Layers default to all of them. --dry-run lists the remote tiles and reports what would change, without changing anything.
// Enter one JSON line on hidden stdin: {"uploadToken": "..."}, plus "siteAccessToken" for a private Site.
// A tile is unchanged when R2's etag, the MD5 of its bytes, equals the MD5 of the local file.
import { createHash } from 'node:crypto';
import { readdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';

const LAYERS = ['population', 'gdp', 'bus_stops', 'tram_stops', 'rail_stops', 'land_value', 'building_value'];
const TILE_BYTES = 120 * 120 * 4;
const dataDirectory = resolve(import.meta.dirname, '../data');
const [originArgument, ...rest] = process.argv.slice(2);
const dryRun = rest.includes('--dry-run');
const selectedLayers = rest.filter(argument => argument !== '--dry-run');
const layers = selectedLayers.length ? selectedLayers : LAYERS;
if (!originArgument || layers.some(layer => !LAYERS.includes(layer))) {
  throw new Error(`Usage: node deploy/sync-tiles.mjs <site origin> [${LAYERS.join('|')} ...] [--dry-run]`);
}
const origin = new URL(originArgument);
if (!['https:', 'http:'].includes(origin.protocol)) throw new Error('Expected an HTTP origin');

async function localTileKeys(layer) {
  const keys = [];
  for (const row of await readdir(join(dataDirectory, 'layers', layer))) {
    if (!/^\d+$/.test(row)) continue;
    for (const column of await readdir(join(dataDirectory, 'layers', layer, row))) {
      if (/^\d+\.bin$/.test(column)) keys.push(`layers/${layer}/${row}/${column}`);
    }
  }
  // An empty or missing layer would delete every remote tile; that is never the intent.
  if (!keys.length) throw new Error(`data/layers/${layer} has no tiles; build it first`);
  return keys;
}

console.log('Enter one credentials JSON line on hidden stdin.');
// Raw mode disables terminal echo. Read bytes directly so Enter works in raw mode.
async function credentialsLine() {
  if (!process.stdin.isTTY) {
    const lines = createInterface({ input: process.stdin });
    try { for await (const line of lines) return line; }
    finally { lines.close(); }
    throw new Error('Missing credentials line');
  }
  process.stdin.setRawMode(true);
  process.stdin.resume();
  try {
    return await new Promise((resolve, reject) => {
      let input = '';
      function onData(chunk) {
        for (const character of chunk.toString()) {
          if (character === '\u0003') { cleanup(); reject(new Error('Cancelled')); return; }
          if (character === '\r' || character === '\n') { cleanup(); resolve(input); return; }
          if (character === '\u007f') input = input.slice(0, -1);
          else input += character;
        }
      }
      function cleanup() { process.stdin.off('data', onData); }
      process.stdin.on('data', onData);
    });
  } finally { process.stdin.setRawMode(false); process.stdin.pause(); }
}
let credentials;
try { credentials = JSON.parse(await credentialsLine()); }
catch { throw new Error('Could not read credentials JSON from stdin'); }
if (!credentials?.uploadToken) throw new Error('uploadToken is required');
const headers = {
  Authorization: `Bearer ${credentials.uploadToken}`,
  ...(credentials.siteAccessToken ? { 'OAI-Sites-Authorization': `Bearer ${credentials.siteAccessToken}` } : {}),
};

// Retries timeouts, server errors and rate limits; returns the final response.
async function request(path, method, body) {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(new URL(`/__upload/${path}`, origin), {
        method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(60000),
      });
      if (response.status < 500 && response.status !== 429 || attempt === 2) return response;
      await response.body?.cancel();
    } catch (error) { if (attempt === 2) throw error; }
    await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
  }
}

async function remoteTileEtags(layer) {
  const response = await request(`layers/${layer}/`, 'GET');
  if (!response.ok) throw new Error(`Listing ${layer}: ${response.status}. Is the current Worker deployed?`);
  return response.json();
}

// Plan every layer before changing anything, so a missing local layer stops the whole sync.
const plans = [];
for (const layer of layers) {
  const [localKeys, remoteEtags] = await Promise.all([localTileKeys(layer), remoteTileEtags(layer)]);
  const local = new Set(localKeys);
  const uploads = [];
  for (const key of localKeys) {
    const bytes = await readFile(join(dataDirectory, key));
    if (bytes.length !== TILE_BYTES) throw new Error(`Unexpected tile size: ${key}`);
    if (remoteEtags[key] !== createHash('md5').update(bytes).digest('hex')) uploads.push(key);
  }
  const deletions = Object.keys(remoteEtags).filter(key => !local.has(key));
  const plan = { layer, local: localKeys.length, remote: Object.keys(remoteEtags).length,
    unchanged: localKeys.length - uploads.length, uploads, deletions };
  plans.push(plan);
  console.log(JSON.stringify({ layer, local: plan.local, remote: plan.remote, unchanged: plan.unchanged,
    upload: uploads.length, delete: deletions.length }));
}
if (dryRun) process.exit(0);

const operations = plans.flatMap(({ layer, uploads, deletions }) => [
  ...uploads.map(key => ({ layer, key, method: 'PUT' })),
  ...deletions.map(key => ({ layer, key, method: 'DELETE' })),
]);
const summaries = new Map(plans.map(({ layer, unchanged }) => [layer, { uploaded: 0, deleted: 0, unchanged, failures: 0, bytes: 0 }]));
let next = 0, done = 0, failures = 0;
const startedAt = Date.now();
const progressLine = () => `${done}/${operations.length} changes, ${failures} failed, ${((Date.now() - startedAt) / 1000).toFixed(1)}s`;
const progress = setInterval(() => console.log(progressLine()), 5000);
try {
  await Promise.all(Array.from({ length: 24 }, async () => {
    while (next < operations.length) {
      const { layer, key, method } = operations[next++];
      const summary = summaries.get(layer);
      try {
        const body = method === 'PUT' ? await readFile(join(dataDirectory, key)) : undefined;
        const response = await request(key, method, body);
        await response.body?.cancel();
        if (response.status !== (method === 'PUT' ? 201 : 204)) throw new Error(`${method} ${key}: ${response.status}`);
        if (method === 'PUT') { summary.uploaded++; summary.bytes += body.length; }
        else summary.deleted++;
      } catch (error) {
        failures++;
        summary.failures++;
        console.error(`${key}: ${error.message}`);
      } finally { done++; }
    }
  }));
  console.log(`Finished: ${progressLine()}`);
  for (const [layer, summary] of summaries) console.log(JSON.stringify({ layer, ...summary }));
  if (failures) process.exitCode = 1;
} finally { clearInterval(progress); }

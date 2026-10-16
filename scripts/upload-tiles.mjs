// Written by AI on 2026.10.16 by model gpt-6.1-sol.
import { readFile, readdir, stat } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createInterface } from 'node:readline';

const deleteOldTiles = process.argv.includes('--delete-old');
const origin = new URL(process.argv[2]);
if (!['https:', 'http:'].includes(origin.protocol)) throw new Error('Expected an HTTP origin');
const root = resolve(deleteOldTiles ? 'data/tiles' : 'data/layers');
const paths = [];
for (const layer of deleteOldTiles ? [''] : ['population', 'gdp']) {
  for (const row of await readdir(join(root, layer))) {
    if (!/^\d+$/.test(row)) continue;
    for (const col of await readdir(join(root, layer, row))) {
      if (/^\d+\.bin$/.test(col)) paths.push(layer ? `${layer}/${row}/${col}` : `${row}/${col}`);
    }
  }
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
async function request(path, method, body) {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(new URL(`/__upload/${deleteOldTiles ? 'tiles' : 'layers'}/${path}`, origin), {
        method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(30000),
      });
      if (response.status < 500 && response.status !== 429 || attempt === 2) return response;
      await response.body?.cancel();
    } catch (error) { if (attempt === 2) throw error; }
    await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
  }
}
let next = 0, uploaded = 0, skipped = 0, deleted = 0, failures = 0, processedBytes = 0;
const startedAt = Date.now();
function progressLine() {
  const elapsedSeconds = ((Date.now() - startedAt) / 1000).toFixed(1);
  return `${uploaded + skipped + deleted + failures}/${paths.length} files: ${uploaded} uploaded, ${deleted} deleted, ${skipped} already present, ${failures} failed; ${processedBytes} bytes ${deleteOldTiles ? 'deleted' : 'uploaded'}; ${elapsedSeconds}s`;
}
const progress = setInterval(() => console.log(progressLine()), 5000);
try {
  await Promise.all(Array.from({ length: 8 }, async () => {
    while (next < paths.length) {
      const path = paths[next++];
      try {
        if (deleteOldTiles) {
          const bytes = (await stat(join(root, path))).size;
          const response = await request(path, 'DELETE');
          await response.body?.cancel();
          if (response.status !== 204) throw new Error(`DELETE ${path}: ${response.status}`);
          deleted++;
          processedBytes += bytes;
          continue;
        }
        const existing = await request(path, 'HEAD');
        if (existing.ok && Number(existing.headers.get('Content-Length')) === 57600) { skipped++; continue; }
        if (existing.status !== 404) throw new Error(`HEAD ${path}: ${existing.status} or unexpected tile size`);
        const bytes = await readFile(join(root, path));
        if (bytes.length !== 57600) throw new Error(`Unexpected tile size: ${path}`);
        const response = await request(path, 'PUT', bytes);
        await response.body?.cancel();
        if (response.status !== 201) throw new Error(`PUT ${path}: ${response.status}`);
        uploaded++;
        processedBytes += bytes.length;
      } catch (error) {
        failures++;
        console.error(`${path}: ${error.message}`);
      }
    }
  }));
  console.log(`Finished: ${progressLine()}`);
  if (failures) process.exitCode = 1;
} finally { clearInterval(progress); }

// Written by AI on 2026.10.16 by model gpt-6.1-sol.
import { readFile, readdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createInterface } from 'node:readline';

const origin = new URL(process.argv[2]);
if (!['https:', 'http:'].includes(origin.protocol)) throw new Error('Expected an HTTP origin');
const root = resolve('data/tiles');
const paths = [];
for (const row of await readdir(root)) {
  if (!/^\d+$/.test(row)) continue;
  for (const col of await readdir(join(root, row))) {
    if (/^\d+\.bin$/.test(col)) paths.push(`${row}/${col}`);
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
if (!credentials?.uploadToken || !credentials?.siteAccessToken) throw new Error('Both uploadToken and siteAccessToken are required');
const headers = {
  Authorization: `Bearer ${credentials.uploadToken}`,
  'OAI-Sites-Authorization': `Bearer ${credentials.siteAccessToken}`,
};
async function request(path, method, body) {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(new URL(`/__upload/tiles/${path}`, origin), {
        method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(30000),
      });
      if (response.status < 500 && response.status !== 429 || attempt === 2) return response;
      await response.body?.cancel();
    } catch (error) { if (attempt === 2) throw error; }
    await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
  }
}
let next = 0, uploaded = 0, skipped = 0;
const progress = setInterval(() => console.log(`${uploaded + skipped}/${paths.length}: ${uploaded} uploaded, ${skipped} already present`), 5000);
try {
  await Promise.all(Array.from({ length: 6 }, async () => {
    while (next < paths.length) {
      const path = paths[next++];
      const existing = await request(path, 'HEAD');
      if (existing.ok && Number(existing.headers.get('Content-Length')) === 115200) { skipped++; continue; }
      if (existing.status !== 404) throw new Error(`HEAD ${path}: ${existing.status} or unexpected tile size`);
      const bytes = await readFile(join(root, path));
      if (bytes.length !== 115200) throw new Error(`Unexpected tile size: ${path}`);
      const response = await request(path, 'PUT', bytes);
      await response.body?.cancel();
      if (response.status !== 201) throw new Error(`PUT ${path}: ${response.status}`);
      uploaded++;
    }
  }));
  console.log(`Finished ${paths.length} tiles: ${uploaded} uploaded, ${skipped} already present.`);
} finally { clearInterval(progress); }

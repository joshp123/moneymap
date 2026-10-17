// Written by AI on 2026.10.17 by model gpt-6.
// Exercises the real Worker with an in-memory R2 bucket; never uploads or deletes local data.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir, stat } from 'node:fs/promises';
import { join, relative, resolve } from 'node:path';
import { createContext, runInContext } from 'node:vm';
import worker from '../worker/index.js';

const objects = new Map();
const etag = bytes => createHash('md5').update(Buffer.from(bytes)).digest('hex');
const env = {
  UPLOAD_TOKEN: 'in-memory-check-only',
  TILES: {
    async get(key) {
      const bytes = objects.get(key);
      return bytes ? { etag: etag(bytes), arrayBuffer: async () => bytes } : null;
    },
    async put(key, bytes) { objects.set(key, bytes); },
    async delete(key) { objects.delete(key); },
    async list({ prefix }) {
      return { objects: [...objects].filter(([key]) => key.startsWith(prefix))
        .map(([key, bytes]) => ({ key, etag: etag(bytes) })), truncated: false };
    },
  },
};
async function request(path, method = 'GET', body, authenticated = false, extraHeaders = {}) {
  return worker.fetch(new Request('https://check.invalid' + path, { method, body,
    headers: { ...(authenticated ? { Authorization: `Bearer ${env.UPLOAD_TOKEN}` } : {}), ...extraHeaders } }), env);
}

assert.equal((await request('/__upload/areas/')).status, 404);
const bytes = await readFile(new URL('../data/areas/manifest.json', import.meta.url));
assert.equal((await request('/__upload/areas/manifest.json', 'PUT', bytes, true)).status, 201);
const listed = await (await request('/__upload/areas/', 'GET', undefined, true)).json();
assert.deepEqual(Object.keys(listed), ['areas/manifest.json']);
const served = await request('/areas/manifest.json');
assert.equal(served.status, 200);
assert.deepEqual(Buffer.from(await served.arrayBuffer()), bytes);
assert.match(served.headers.get('content-type'), /application\/json/);
assert.equal((await request('/areas/manifest.json', 'GET', undefined, false,
  { 'If-None-Match': served.headers.get('etag') })).status, 304);
assert.equal((await request('/areas/missing.json')).status, 404);
assert.equal((await request('/__upload/areas/not-a-file', 'PUT', bytes, true)).status, 404);
assert.equal((await request('/__upload/areas/manifest.json', 'DELETE', undefined, true)).status, 204);
assert.equal((await request('/areas/manifest.json')).status, 404);

// Run the sync command's own file discovery without running a sync or reading credentials.
const syncSource = await readFile(new URL('../deploy/sync-tiles.mjs', import.meta.url), 'utf8');
const discoveryStart = syncSource.indexOf('async function localDataKeys(');
const discoveryEnd = syncSource.indexOf("console.log('Enter one credentials", discoveryStart);
const dataDirectory = resolve(import.meta.dirname, '../data');
const context = createContext({ readdir, join, relative, dataDirectory });
runInContext(syncSource.slice(discoveryStart, discoveryEnd), context);
const keys = await context.localDataKeys('areas');
assert.ok(keys.includes('areas/manifest.json'));
assert.ok(keys.some(key => /^areas\/records\/.+\.json\.gz$/.test(key)));
assert.ok(keys.every(key => /^areas\//.test(key)));
const sizes = await Promise.all(keys.map(async key => (await stat(join(dataDirectory, key))).size));
assert.ok(Math.max(...sizes) <= 20_000_000);
assert.ok(sizes.reduce((sum, size) => sum + size, 0) <= 200_000_000);
console.log(JSON.stringify({ worker_area_get: 200, authenticated_put: 201, authenticated_list: 200,
  authenticated_delete: 204, unauthenticated_upload: 404, conditional_get: 304,
  sync_discovery_files: keys.length, bytes: sizes.reduce((sum, size) => sum + size, 0),
  largest_file_bytes: Math.max(...sizes), live_sync_run: false }, null, 2));

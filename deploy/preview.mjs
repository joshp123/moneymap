// Written by AI on 2026.10.16 by model gpt-6.1-sol; reorganised by model claude opus 5.5.
// Runs the real Worker at http://127.0.0.1:8787 with a filesystem stand-in for the Site's R2 bucket.
// The bucket is data/ by default, so the Worker reads data/layers/. Stop with Ctrl-C.
//   node deploy/preview.mjs [bucket directory]
// Set UPLOAD_TOKEN to accept deploy/sync-tiles.mjs, for example against an empty bucket directory.
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import worker from '../worker/index.js';

const projectDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bucketDirectory = resolve(process.argv[2] || resolve(projectDirectory, 'data'));
const port = Number(process.env.PORT || 8787);
function objectPath(key) {
  if (!/^layers\/[a-z_]+\/(\d+\/(\d+\.bin)?)?$/.test(key)) throw new Error(`Invalid key: ${key}`);
  return resolve(bucketDirectory, key);
}
async function filesUnder(directory) {
  const entries = await readdir(directory, { recursive: true, withFileTypes: true }).catch(error => {
    if (error.code === 'ENOENT') return [];
    throw error;
  });
  return entries.filter(entry => entry.isFile()).map(entry => resolve(entry.parentPath, entry.name));
}
// R2 lists keys in lexicographic order, at most 1,000 at a time; its etag is the MD5 of the object.
async function list({ prefix, cursor }) {
  const keys = (await filesUnder(objectPath(prefix))).map(path => relative(bucketDirectory, path)).sort();
  const start = cursor ? keys.findIndex(key => key > cursor) : 0;
  const page = start === -1 ? [] : keys.slice(start, start + 1000);
  const objects = await Promise.all(page.map(async key => ({
    key, etag: createHash('md5').update(await readFile(resolve(bucketDirectory, key))).digest('hex'),
  })));
  const truncated = start !== -1 && start + 1000 < keys.length;
  return { objects, truncated, ...(truncated ? { cursor: page.at(-1) } : {}) };
}
const env = {
  UPLOAD_TOKEN: process.env.UPLOAD_TOKEN,
  TILES: {
    async get(key) {
      try {
        const bytes = await readFile(objectPath(key));
        return { arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
      } catch (error) {
        if (error.code === 'ENOENT') return null;
        throw error;
      }
    },
    async put(key, bytes) {
      const path = objectPath(key);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, new Uint8Array(bytes));
    },
    async delete(key) {
      await rm(objectPath(key), { force: true });
    },
    list,
  },
};
createServer(async (incoming, outgoing) => {
  try {
    const requestOptions = { method: incoming.method, headers: incoming.headers };
    if (incoming.method !== 'GET' && incoming.method !== 'HEAD') {
      requestOptions.body = incoming;
      requestOptions.duplex = 'half';
    }
    const request = new Request(new URL(incoming.url, `http://127.0.0.1:${port}`), requestOptions);
    const response = await worker.fetch(request, env);
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  } catch (error) {
    console.error(error);
    outgoing.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' });
    outgoing.end('Could not complete the request. See the preview log.');
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`moneymap preview: http://127.0.0.1:${port}, bucket ${bucketDirectory}`);
});

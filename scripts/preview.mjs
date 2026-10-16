// Written by AI on 2026.10.16 by model gpt-6.1-sol.
import { createServer } from 'node:http';
import { readFile, stat, mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import worker from '../worker/index.js';

const projectDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dataDirectory = resolve(projectDirectory, 'data');
const port = Number(process.env.PORT || 8787);
function tilePath(key) {
  if (!/^layers\/(gdp|population)\/\d+\/\d+\.bin$/.test(key)) throw new Error('Invalid tile key');
  return resolve(dataDirectory, key);
}
const env = {
  UPLOAD_TOKEN: process.env.UPLOAD_TOKEN,
  TILES: {
    async get(key) {
      try {
        const bytes = await readFile(tilePath(key));
        return { arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
      } catch (error) {
        if (error.code === 'ENOENT') return null;
        throw error;
      }
    },
    async head(key) {
      try { return { size: (await stat(tilePath(key))).size }; }
      catch (error) {
        if (error.code === 'ENOENT') return null;
        throw error;
      }
    },
    async put(key, bytes) {
      const path = tilePath(key);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, new Uint8Array(bytes));
    },
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
  console.log(`moneymap preview: http://127.0.0.1:${port}`);
});

// Serves the built Studio bundle (engine/src/brasscribe_engine/static) as plain files, with no
// engine behind it, for the browser tests in this directory. Usage: node browser/serve.mjs [port]
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "engine", "src", "brasscribe_engine", "static");
const port = Number(process.argv[2] ?? 8798);
const types = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".woff2": "font/woff2", ".ttf": "font/ttf", ".sf2": "application/octet-stream", ".txt": "text/plain",
};

createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname)).replace(/^([/\\])+/, "");
  const file = join(root, path || "index.html");
  let ok = file.startsWith(root + sep) || file === root;
  try {
    ok &&= statSync(file).isFile();
  } catch {
    ok = false;
  }
  if (!ok) {
    res.writeHead(404, { "content-type": "text/plain" }).end("not found");
    return;
  }
  res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`studio static on http://127.0.0.1:${port}/`));

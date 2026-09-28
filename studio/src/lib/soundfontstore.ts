// SoundFont bytes kept across visits in IndexedDB, revalidated with the server's ETag.
//
// Chromium's HTTP cache does not keep the 195 MB band SoundFont (the entry is over its size limit),
// with or without Cache-Control, so without this every visit downloads it again. IndexedDB works
// over plain http on the LAN too, where the Cache API is not available (it needs a secure context).
// A stored copy costs one conditional request (304, no body) per page.

export interface StoredFont {
  url: string;
  etag: string | null;
  lastModified: string | null;
  blob: Blob;
}

export interface FontStore {
  get(url: string): Promise<StoredFont | undefined>;
  put(entry: StoredFont): Promise<void>;
}

type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

/**
 * The SoundFont at `url` as bytes: from the store when the server says it is unchanged (304) or
 * cannot be reached, else downloaded and stored. Without a store (no IndexedDB), a plain fetch.
 */
export async function soundFontBytes(url: string, store: FontStore | null = openFontStore(), fetchImpl: Fetch = fetch): Promise<ArrayBuffer> {
  const stored = await store?.get(url).catch(() => undefined);
  if (stored && (stored.etag || stored.lastModified)) {
    const headers: Record<string, string> = {};
    if (stored.etag) headers["If-None-Match"] = stored.etag;
    if (stored.lastModified) headers["If-Modified-Since"] = stored.lastModified;
    let res: Response | null = null;
    try {
      // no-store: the HTTP cache neither answers nor keeps it; the 304 reaches this code as is.
      res = await fetchImpl(url, { cache: "no-store", headers });
    } catch {
      return stored.blob.arrayBuffer();
    }
    if (res.status === 304) return stored.blob.arrayBuffer();
    if (res.ok) return keep(url, res, store);
    return stored.blob.arrayBuffer();
  }
  const res = await fetchImpl(url, store ? { cache: "no-store" } : undefined);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return store ? keep(url, res, store) : res.arrayBuffer();
}

async function keep(url: string, res: Response, store: FontStore | null): Promise<ArrayBuffer> {
  // As a Blob first: Chromium can keep a large blob on disk, so storing it adds no second copy in memory.
  const blob = await res.blob();
  const etag = res.headers.get("ETag");
  const lastModified = res.headers.get("Last-Modified");
  if (store && (etag || lastModified)) await store.put({ url, etag, lastModified, blob }).catch(() => undefined);
  return blob.arrayBuffer();
}

const DB = "brasscribe-studio";
const STORE = "soundfonts";

/** The IndexedDB store, or null where IndexedDB is missing. */
export function openFontStore(): FontStore | null {
  const idb = (globalThis as { indexedDB?: IDBFactory }).indexedDB;
  if (!idb) return null;
  let db: Promise<IDBDatabase> | null = null;
  const open = () =>
    (db ??= new Promise<IDBDatabase>((resolve, reject) => {
      const req = idb.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "url" });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
      req.onblocked = () => reject(new Error("IndexedDB blocked"));
    }));
  const run = <T>(mode: IDBTransactionMode, f: (s: IDBObjectStore) => IDBRequest<T>) =>
    open().then((d) => new Promise<T>((resolve, reject) => {
      const tx = d.transaction(STORE, mode);
      const req = f(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    }));
  return {
    get: (url) => run("readonly", (s) => s.get(url) as IDBRequest<StoredFont | undefined>),
    put: (entry) => run("readwrite", (s) => s.put(entry)).then(() => undefined),
  };
}

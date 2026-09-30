// The hash route: "#/runs/<id>/<tab>?a=1" -> name "runs", args ["<id>", "<tab>"], query "a=1".

export interface Route {
  name: string;
  args: string[];
  query: URLSearchParams;
}

/** A path segment decoded; a malformed escape ("%E0%A4%A") is kept as written instead of throwing. */
export function decodeSegment(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export function parseHash(hash: string, fallback = "runs"): Route {
  const raw = hash.replace(/^#\/?/, "") || fallback;
  const q = raw.indexOf("?");
  const path = q < 0 ? raw : raw.slice(0, q);
  const [name, ...args] = path.split("/");
  return { name, args: args.map(decodeSegment), query: new URLSearchParams(q < 0 ? "" : raw.slice(q + 1)) };
}

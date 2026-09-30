// The only module that talks to the engine. Views call these functions and
// never build URLs themselves.
import type {
  AdapterInfo, AudioRef, BenchRun, Comparison, Composition, ConformanceReport, ConformanceRun, DatasetInfo, Health, Job, JobCreate,
  JobEvent, Manifest, ParityReport, ProfileInfo, Reference, RoundTrip, Source, StageFiles, SuiteInfo,
  SuiteRun, ValidationIssue, PartSources,
} from "./types";

/** The engine answered 404 for a route it does not have (as opposed to a missing resource). */
export class MissingEndpoint extends Error {
  constructor(readonly endpoint: string) {
    super(`The engine does not provide ${endpoint} yet.`);
  }
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** The browser could not reach the engine at all (not running, or the connection dropped). */
export class Unreachable extends Error {}

/** The engine did not answer in time. */
export class TimedOut extends Error {
  constructor(readonly seconds: number) {
    super(`no answer within ${seconds} s`);
  }
}

/** Default time to wait for an answer; long reads (audio, scores) pass their own. */
const TIMEOUT_S = 60;

/** A request a view no longer needs was cancelled (it left, or asked again). Not an error to show. */
export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

/** Aborts when any of `signals` does (AbortSignal.any, where the browser lacks it). */
export function anySignal(signals: AbortSignal[]): AbortSignal {
  if (typeof AbortSignal.any === "function") return AbortSignal.any(signals);
  const c = new AbortController();
  for (const s of signals) {
    if (s.aborted) {
      c.abort(s.reason);
      break;
    }
    s.addEventListener("abort", () => c.abort(s.reason), { once: true });
  }
  return c.signal;
}

/** Options a call takes: `signal` cancels the request, which then rejects with an AbortError (see isAbort). */
export interface CallOptions {
  signal?: AbortSignal;
}

async function request(path: string, init: RequestInit = {}, timeoutS = TIMEOUT_S): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutS * 1000);
  const own = init.signal ?? null;
  try {
    return await fetch(url(path), { ...init, signal: own ? anySignal([own, timeout]) : timeout });
  } catch (e) {
    // The caller's own cancel is passed on as an AbortError; only our deadline is a time-out.
    if (own?.aborted) throw new DOMException("The request was cancelled.", "AbortError");
    if (timeout.aborted) throw new TimedOut(timeoutS);
    throw new Unreachable(e instanceof Error ? e.message : String(e));
  }
}

let base = "";
export function setBase(url: string): void {
  base = url.replace(/\/$/, "");
}
export function url(path: string): string {
  return base + path;
}

async function fail(r: Response, endpoint: string): Promise<never> {
  const text = await r.text();
  let detail: unknown;
  try {
    detail = JSON.parse(text).detail;
  } catch {
    detail = undefined;
  }
  // Unknown /v1 paths fall through to the static file mount, which answers a
  // plain 404; FastAPI routes answer JSON with a specific detail.
  if (r.status === 404 && (detail === undefined || detail === "Not Found")) throw new MissingEndpoint(endpoint);
  if (r.status === 405) throw new MissingEndpoint(endpoint);
  const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? JSON.stringify(detail) : text || r.statusText;
  throw new ApiError(r.status, msg);
}

async function get<T>(path: string, endpoint = path, timeoutS = TIMEOUT_S, opts: CallOptions = {}): Promise<T> {
  const r = await request(path, { headers: { Accept: "application/json" }, signal: opts.signal }, timeoutS);
  if (!r.ok) return fail(r, endpoint);
  return (await r.json()) as T;
}

async function send<T>(method: string, path: string, body?: unknown, endpoint = path): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: "application/json" } };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { ...init.headers, "Content-Type": "application/json" };
  }
  // Sends may start long work (a benchmark suite, MuseScore); give them longer.
  const r = await request(path, init, 600);
  if (!r.ok) return fail(r, endpoint);
  return (await r.json()) as T;
}

export async function fetchBytes(path: string, endpoint = path, opts: CallOptions = {}): Promise<ArrayBuffer> {
  const r = await request(path, { signal: opts.signal }, 300);
  if (!r.ok) return fail(r, endpoint);
  return r.arrayBuffer();
}

export async function fetchText(path: string, endpoint = path, opts: CallOptions = {}): Promise<string> {
  const r = await request(path, { signal: opts.signal }, 120);
  if (!r.ok) return fail(r, endpoint);
  return r.text();
}

const enc = encodeURIComponent;

export const api = {
  health: () => get<Health>("/v1/health"),
  profiles: () => get<ProfileInfo[]>("/v1/profiles"),
  jobs: () => get<Job[]>("/v1/jobs"),
  job: (id: string, opts?: CallOptions) => get<Job>(`/v1/jobs/${enc(id)}`, undefined, undefined, opts),
  manifest: (id: string, opts?: CallOptions) => get<Manifest>(`/v1/jobs/${enc(id)}/manifest`, "GET /v1/jobs/{id}/manifest", undefined, opts),
  composition: (id: string, opts?: CallOptions) => get<Composition>(`/v1/jobs/${enc(id)}/composition`, undefined, undefined, opts),
  musicxmlUrl: (id: string) => url(`/v1/jobs/${enc(id)}/musicxml`),
  renderedAudioUrl: (id: string) => url(`/v1/jobs/${enc(id)}/audio`),
  midiUrl: (id: string) => url(`/v1/jobs/${enc(id)}/midi`),
  pdfUrl: (id: string) => url(`/v1/jobs/${enc(id)}/pdf`),
  inputAudioUrl: (id: string) => url(`/v1/jobs/${enc(id)}/input`),
  cancel: (id: string) => send<Job>("DELETE", `/v1/jobs/${enc(id)}`),
  /** Remove a finished run's files (the artifact cache is kept). */
  deleteRun: async (id: string): Promise<void> => {
    const r = await request(`/v1/runs/${enc(id)}`, { method: "DELETE" });
    if (!r.ok) await fail(r, "DELETE /v1/runs/{id}");
  },
  uploadAndRun: (file: File, profile: string, title?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("profile", profile);
    if (title) fd.append("title", title);
    return send<Job>("POST", "/v1/jobs/upload", fd);
  },
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return send<AudioRef>("POST", "/v1/audio", fd);
  },
  // Fields the engine defaults (difficulty, muscriptor, lineup…) may be left out.
  createJob: (body: Omit<JobCreate, "difficulty" | "muscriptor" | "lead"> & Partial<Pick<JobCreate, "difficulty" | "muscriptor" | "lead">>) =>
    send<Job>("POST", "/v1/jobs", body as JobCreate),
  eventsUrl: (id: string, after = -1) => url(`/v1/jobs/${enc(id)}/events?after=${after}`),
  suites: () => get<SuiteInfo[]>("/v1/suites"),
  runSuite: (name: string, mode: "cached" | "live" = "cached") =>
    send<BenchRun>("POST", `/v1/suites/${enc(name)}/run?mode=${mode}`),

  // Inspection, comparison, benchmarks, registry.
  stages: (id: string, opts?: CallOptions) => get<StageFiles[]>(`/v1/jobs/${enc(id)}/stages`, "GET /v1/jobs/{id}/stages", undefined, opts),
  stageFileUrl: (id: string, stage: string, name: string) =>
    url(`/v1/jobs/${enc(id)}/stages/${enc(stage)}/files/${enc(name)}`),
  references: () => get<Reference[]>("/v1/references", "GET /v1/references"),
  referenceFileUrl: (ref: string, name: string) => url(`/v1/references/${enc(ref)}/files/${enc(name)}`),
  compare: (id: string, against: { reference: string } | { job: string }, opts?: CallOptions) => {
    const q = "reference" in against ? `reference=${enc(against.reference)}` : `job=${enc(against.job)}`;
    return get<Comparison>(`/v1/jobs/${enc(id)}/compare?${q}`, "GET /v1/jobs/{id}/compare", undefined, opts);
  },
  rerun: (id: string, body: { allow_heavy: boolean; cold?: string[] } = { allow_heavy: true }) =>
    send<Job>("POST", `/v1/jobs/${enc(id)}/rerun`, body, "POST /v1/jobs/{id}/rerun"),
  roundtrip: (id: string) => get<RoundTrip>(`/v1/jobs/${enc(id)}/roundtrip`, "GET /v1/jobs/{id}/roundtrip"),
  runRoundtrip: (id: string) => send<RoundTrip>("POST", `/v1/jobs/${enc(id)}/roundtrip`, undefined, "POST /v1/jobs/{id}/roundtrip"),
  validation: (id: string) => get<ValidationIssue[]>(`/v1/jobs/${enc(id)}/validation`, "GET /v1/jobs/{id}/validation"),
  partSources: (id: string) => get<PartSources>(`/v1/jobs/${enc(id)}/part-sources`, "GET /v1/jobs/{id}/part-sources"),
  suiteHistory: (suite?: string) =>
    get<SuiteRun[]>(`/v1/suites/history?limit=500${suite ? `&suite=${enc(suite)}` : ""}`, "GET /v1/suites/history"),
  adapters: () => get<AdapterInfo[]>("/v1/registry/adapters", "GET /v1/registry/adapters"),
  datasets: () => get<DatasetInfo[]>("/v1/registry/datasets", "GET /v1/registry/datasets"),
  parity: () => get<ParityReport[]>("/v1/parity", "GET /v1/parity"),
  // The summary report only: the full dump of every case's files is far too large for a page.
  conformance: (opts?: CallOptions) => get<ConformanceReport[]>("/v1/conformance", "GET /v1/conformance", 20, opts),
  conformanceRun: (opts?: CallOptions) => get<ConformanceRun>("/v1/conformance/run", "GET /v1/conformance/run", undefined, opts),
  startConformanceRun: () => send<ConformanceRun>("POST", "/v1/conformance/run", undefined, "POST /v1/conformance/run"),
  sources: () => get<Source[]>("/v1/sources", "GET /v1/sources"),
};

/** Subscribe to a job's progress. Returns a function that closes the stream. */
export function subscribe(id: string, onEvent: (e: JobEvent) => void, onEnd?: () => void): () => void {
  const es = new EventSource(api.eventsUrl(id));
  const handler = (m: MessageEvent) => {
    try {
      onEvent(JSON.parse(m.data) as JobEvent);
    } catch {
      /* ignore malformed lines */
    }
  };
  for (const t of ["message", "job", "stage", "log"]) es.addEventListener(t, handler as EventListener);
  es.onerror = () => {
    // The engine closes the stream once the job is finished.
    es.close();
    onEnd?.();
  };
  return () => es.close();
}

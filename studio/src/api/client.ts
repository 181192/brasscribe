// The only module that talks to the engine. Views call these functions and
// never build URLs themselves.
import type {
  AdapterInfo, AudioRef, BenchRun, Comparison, Composition, ConformanceReport, DatasetInfo, Health, Job, JobCreate,
  JobEvent, Manifest, ParityReport, ProfileInfo, Reference, RoundTrip, Source, StageFiles, SuiteInfo,
  SuiteRun, ValidationIssue,
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

async function get<T>(path: string, endpoint = path): Promise<T> {
  const r = await fetch(url(path), { headers: { Accept: "application/json" } });
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
  const r = await fetch(url(path), init);
  if (!r.ok) return fail(r, endpoint);
  return (await r.json()) as T;
}

export async function fetchBytes(path: string, endpoint = path): Promise<ArrayBuffer> {
  const r = await fetch(url(path));
  if (!r.ok) return fail(r, endpoint);
  return r.arrayBuffer();
}

export async function fetchText(path: string, endpoint = path): Promise<string> {
  const r = await fetch(url(path));
  if (!r.ok) return fail(r, endpoint);
  return r.text();
}

const enc = encodeURIComponent;

export const api = {
  health: () => get<Health>("/v1/health"),
  profiles: () => get<ProfileInfo[]>("/v1/profiles"),
  jobs: () => get<Job[]>("/v1/jobs"),
  job: (id: string) => get<Job>(`/v1/jobs/${enc(id)}`),
  manifest: (id: string) => get<Manifest>(`/v1/jobs/${enc(id)}/manifest`, "GET /v1/jobs/{id}/manifest"),
  composition: (id: string) => get<Composition>(`/v1/jobs/${enc(id)}/composition`),
  musicxmlUrl: (id: string) => url(`/v1/jobs/${enc(id)}/musicxml`),
  renderedAudioUrl: (id: string) => url(`/v1/jobs/${enc(id)}/audio`),
  midiUrl: (id: string) => url(`/v1/jobs/${enc(id)}/midi`),
  pdfUrl: (id: string) => url(`/v1/jobs/${enc(id)}/pdf`),
  inputAudioUrl: (id: string) => url(`/v1/jobs/${enc(id)}/input`),
  cancel: (id: string) => send<Job>("DELETE", `/v1/jobs/${enc(id)}`),
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
  createJob: (body: JobCreate) =>
    send<Job>("POST", "/v1/jobs", body),
  eventsUrl: (id: string, after = -1) => url(`/v1/jobs/${enc(id)}/events?after=${after}`),
  suites: () => get<SuiteInfo[]>("/v1/suites"),
  runSuite: (name: string, mode: "cached" | "live" = "cached") =>
    send<BenchRun>("POST", `/v1/suites/${enc(name)}/run?mode=${mode}`),

  // Inspection, comparison, benchmarks, registry.
  stages: (id: string) => get<StageFiles[]>(`/v1/jobs/${enc(id)}/stages`, "GET /v1/jobs/{id}/stages"),
  stageFileUrl: (id: string, stage: string, name: string) =>
    url(`/v1/jobs/${enc(id)}/stages/${enc(stage)}/files/${enc(name)}`),
  references: () => get<Reference[]>("/v1/references", "GET /v1/references"),
  referenceFileUrl: (ref: string, name: string) => url(`/v1/references/${enc(ref)}/files/${enc(name)}`),
  compare: (id: string, against: { reference: string } | { job: string }) => {
    const q = "reference" in against ? `reference=${enc(against.reference)}` : `job=${enc(against.job)}`;
    return get<Comparison>(`/v1/jobs/${enc(id)}/compare?${q}`, "GET /v1/jobs/{id}/compare");
  },
  rerun: (id: string, body: { allow_heavy: boolean; cold?: string[] } = { allow_heavy: true }) =>
    send<Job>("POST", `/v1/jobs/${enc(id)}/rerun`, body, "POST /v1/jobs/{id}/rerun"),
  roundtrip: (id: string) => get<RoundTrip>(`/v1/jobs/${enc(id)}/roundtrip`, "GET /v1/jobs/{id}/roundtrip"),
  runRoundtrip: (id: string) => send<RoundTrip>("POST", `/v1/jobs/${enc(id)}/roundtrip`, undefined, "POST /v1/jobs/{id}/roundtrip"),
  validation: (id: string) => get<ValidationIssue[]>(`/v1/jobs/${enc(id)}/validation`, "GET /v1/jobs/{id}/validation"),
  suiteHistory: (suite?: string) =>
    get<SuiteRun[]>(`/v1/suites/history?limit=500${suite ? `&suite=${enc(suite)}` : ""}`, "GET /v1/suites/history"),
  adapters: () => get<AdapterInfo[]>("/v1/registry/adapters", "GET /v1/registry/adapters"),
  datasets: () => get<DatasetInfo[]>("/v1/registry/datasets", "GET /v1/registry/datasets"),
  parity: () => get<ParityReport[]>("/v1/parity", "GET /v1/parity"),
  conformance: () => get<ConformanceReport[]>("/v1/conformance", "GET /v1/conformance"),
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

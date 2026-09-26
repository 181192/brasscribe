// Wire types. Most are generated from engine/openapi.json (npm run gen:api);
// the hand-written ones cover payloads the OpenAPI document leaves open
// (Composition extras, SSE events, manifests, pass-through reports).
import type { components } from "./schema";

type S = components["schemas"];
export type Job = S["Job"];
export type StageState = S["StageState"];
export type ProfileInfo = S["ProfileInfo"];
export type SuiteInfo = S["SuiteInfo"];
export type SuiteResult = S["SuiteResult"];
export type Check = S["Check"];
export type Health = S["Health"];
export type Artifact = S["Artifact"];
export type AudioRef = S["AudioRef"];
export type JobCreate = S["JobCreate"];

export interface Note {
  pitch: number;
  start: number;
  dur: number;
  confidence?: number;
  sources?: string[];
  onset_s?: number | null;
  offset_s?: number | null;
  [k: string]: unknown;
}
export interface Voice {
  id: string;
  role: string;
  notes: Note[];
  instrument_hint?: string | null;
  layer?: string | null;
  [k: string]: unknown;
}
/** A free-time (ad lib.) passage: [start, end) in ticks and seconds. */
export interface FreeRegion {
  start: number;
  end: number;
  start_s: number;
  end_s: number;
  tempo_bpm?: number;
  notation?: string;
  label?: string;
}
export interface Composition {
  title: string;
  voices: Voice[];
  meters: { tick: number; beats: number; beat_unit?: number }[];
  keys: { tick: number; fifths: number; mode?: string }[];
  beat_times?: number[];
  first_downbeat?: number;
  ticks_per_beat?: number;
  free_regions?: FreeRegion[];
  [k: string]: unknown;
}

/** One Server-Sent Event payload (engine schemas.JobEvent). */
export interface JobEvent {
  id: number;
  run: string;
  type: "job" | "stage" | "log";
  time?: number;
  status?: string;
  stage?: string;
  kind?: string;
  seconds?: number;
  device?: string;
  fraction?: number;
  message?: string;
  error?: string;
  stages?: string[];
  [k: string]: unknown;
}

export type Manifest = Record<string, unknown> & {
  run_id: string;
  profile: string;
  pipeline?: string;
  title?: string;
  status?: string;
  input?: { path: string; sha256: string; bytes: number };
  git?: { sha: string; branch?: string; dirty?: boolean };
  host?: Record<string, string>;
  seconds?: number;
  devices?: string[];
  stages?: ManifestStage[];
  options?: Record<string, unknown>;
  params?: Record<string, unknown>;
  outputs?: Record<string, string>;
};
export interface ManifestStage {
  stage: string;
  kind: string;
  status: string;
  key?: string;
  seconds?: number;
  outputs?: Record<string, string>;
  adapter?: { name: string; version?: string; device?: string; heavy?: boolean; models?: { name: string; sha256: string }[] } | null;
  provenance?: Record<string, unknown>;
  matches_cache?: boolean;
}

export type FileRef = S["FileRef"];
export type StageFiles = S["StageArtifacts"];
export type Reference = S["Reference"];
export type PartDiff = S["PartComparison"];
export type Comparison = S["Comparison"];
export type RoundTrip = S["Roundtrip"];
export type ValidationIssue = S["ValidationIssue"];
export type SuiteRun = S["SuiteHistoryEntry"];
export type BenchRun = S["BenchRun"];
export type AdapterInfo = S["AdapterInfo"];
export type DatasetInfo = S["Dataset"];
export type Source = S["Source"];
export type ConformanceRun = S["ConformanceRun"];

/** A converted-model parity report (models/convert/reports/*.json), passed through as-is. */
export interface ParityReport {
  _file?: string;
  model?: string;
  device?: string;
  threshold_f1?: number;
  reference?: Record<string, unknown>;
  artifacts?: Record<string, { size_bytes?: number; sha256?: string }>;
  parity?: Record<string, Record<string, unknown>>;
  latency?: Record<string, unknown>;
  [k: string]: unknown;
}
/** A Rust-core conformance report (data/runs/core-conformance/**.json), passed through as-is. */
export type ConformanceReport = Record<string, unknown> & { _file?: string };


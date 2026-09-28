// Folds a job's Server-Sent Events into the state the stage graph shows.
import type { Job, JobEvent } from "../api/types";

export interface StageView {
  name: string;
  kind?: string | null;
  status: string;
  seconds?: number | null;
  /** Of `seconds`: waiting for the machine-wide GPU mutex, and running. */
  queue_wait_s?: number | null;
  run_s?: number | null;
  device?: string | null;
  cacheHit: boolean;
  startedAt?: number;
}

export interface RunView {
  id: string;
  status: string;
  error?: string | null;
  stages: StageView[];
  lastEventId: number;
  log: string[];
}

const CACHE = new Set(["cached", "imported"]);

export function fromJob(job: Job): RunView {
  return {
    id: job.id,
    status: job.status,
    error: job.error,
    stages: job.stages.map((s) => ({ ...s, cacheHit: CACHE.has(s.status) })),
    lastEventId: -1,
    log: [],
  };
}

export function reduce(state: RunView, e: JobEvent): RunView {
  if (e.id <= state.lastEventId) return state; // replayed after a reconnect
  const next: RunView = { ...state, lastEventId: e.id };
  if (e.type === "job") {
    if (e.status) next.status = e.status;
    if (e.error) next.error = e.error;
    if (e.stages && !state.stages.length) {
      next.stages = e.stages.map((name) => ({ name, status: "pending", cacheHit: false }));
    }
  } else if (e.type === "stage" && e.stage) {
    const stages = [...state.stages];
    let i = stages.findIndex((s) => s.name === e.stage);
    if (i < 0) {
      stages.push({ name: e.stage, status: "pending", cacheHit: false });
      i = stages.length - 1;
    }
    const s = { ...stages[i] };
    if (e.kind) s.kind = e.kind;
    if (e.status) {
      s.status = e.status;
      s.cacheHit = CACHE.has(e.status);
      if (e.status === "started") s.startedAt = e.time;
    }
    if (e.seconds !== undefined) s.seconds = e.seconds;
    if (e.queue_wait_s !== undefined) s.queue_wait_s = e.queue_wait_s;
    if (e.run_s !== undefined) s.run_s = e.run_s;
    if (e.device) s.device = e.device;
    stages[i] = s;
    next.stages = stages;
    if (e.status === "failed" && e.error) next.log = [...state.log, `${e.stage}: ${e.error}`];
  } else if (e.type === "log" && e.message) {
    next.log = [...state.log.slice(-199), e.stage ? `${e.stage}: ${e.message}` : e.message];
  }
  return next;
}

export function totals(v: RunView): { done: number; total: number; cached: number; seconds: number } {
  const finished = new Set(["cached", "imported", "ran", "skipped"]);
  return {
    done: v.stages.filter((s) => finished.has(s.status)).length,
    total: v.stages.length,
    cached: v.stages.filter((s) => s.cacheHit).length,
    seconds: v.stages.reduce((a, s) => a + (s.seconds ?? 0), 0),
  };
}

"""Job DAG: stages with content-addressed caching.

A pipeline is a list of stages. Each stage reads the job's source audio or
files produced by earlier stages, and writes files into its own output
directory. For every stage the executor:

1. computes the cache key from stage name, parameters, input content hashes and
   code/adapter fingerprints;
2. on a cache hit, links the cached files into the run (status "cached");
3. otherwise, if a reuse directory holds this stage's outputs in the
   song-pipeline layout and every input it was made from matches byte for byte,
   imports them into the cache (status "imported");
4. otherwise runs the stage (status "ran") and stores its outputs. A stage
   forced to run cold while a cache entry exists is compared with that entry.
"""

from __future__ import annotations

import fnmatch
import shutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .adapters import AdapterRegistry
from .cache import ArtifactCache, Entry
from .hashing import digest_of_files, sha256_json, source_fingerprint

SOURCE = "source"
CACHE_SCHEMA = 1


@dataclass(frozen=True)
class Input:
    stage: str  # upstream stage name, or SOURCE for the job's input audio
    file: str | None = None  # one output file of that stage; None means its whole output directory


@dataclass
class Stage:
    name: str
    kind: str  # beats | stems | layers | transcribe | arrange | export
    inputs: dict[str, Input]
    run: Callable[[StageContext], None]
    params: dict = field(default_factory=dict)
    adapter: str | None = None
    code: tuple[Path, ...] = ()
    outputs: tuple[str, ...] = ()  # expected output files (glob patterns)
    reuse_subdir: str | None = None  # where the outputs sit in a song-pipeline output directory


@dataclass
class Pipeline:
    profile: str
    pipeline: str
    stages: list[Stage]
    outputs: dict[str, tuple[str, str]]  # final name -> (stage, file)
    params: dict = field(default_factory=dict)

    def stage(self, name: str) -> Stage:
        return next(s for s in self.stages if s.name == name)


@dataclass
class StageResult:
    stage: str
    kind: str
    status: str  # cached | imported | ran | failed | skipped
    key: str
    out_dir: Path
    files: dict[str, str]
    seconds: float = 0.0  # wall clock: queue_wait_s + run_s
    queue_wait_s: float = 0.0  # waiting for the machine-wide GPU mutex
    inputs: dict[str, str] = field(default_factory=dict)
    adapter: dict | None = None
    provenance: dict = field(default_factory=dict)
    matches_cache: bool | None = None
    error: str | None = None

    @property
    def run_s(self) -> float:
        return max(0.0, self.seconds - self.queue_wait_s)

    def record(self) -> dict:
        d = {"stage": self.stage, "kind": self.kind, "status": self.status, "key": self.key,
             "seconds": round(self.seconds, 3), "queue_wait_s": round(self.queue_wait_s, 3),
             "run_s": round(self.run_s, 3), "inputs": self.inputs, "outputs": self.files,
             "outputs_digest": digest_of_files(self.files) if self.files else None}
        if self.adapter:
            d["adapter"] = self.adapter
        if self.provenance:
            d["provenance"] = self.provenance
        if self.matches_cache is not None:
            d["matches_cache"] = self.matches_cache
        if self.error:
            d["error"] = self.error
        return d


class StageFailed(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage


class Cancelled(RuntimeError):
    pass


@dataclass
class StageContext:
    stage: Stage
    out: Path
    inputs: dict[str, Path]
    executor: Executor

    @property
    def params(self) -> dict:
        return self.stage.params

    def log(self, message: str) -> None:
        self.executor.emit({"type": "log", "stage": self.stage.name, "message": message})

    def adapter(self, name: str, src: Path, dst: Path, env: dict[str, str] | None = None) -> float:
        return self.executor.adapters.run(name, src, dst, env=env, allow_heavy=self.executor.allow_heavy, log=self.log,
                                          waited=lambda s: self.executor.add_wait(self.stage.name, s))


class Executor:
    def __init__(self, cache: ArtifactCache, adapters: AdapterRegistry, emit: Callable[[dict], None] | None = None,
                 reuse_dir: Path | None = None, allow_heavy: bool = True, cold: set[str] | None = None,
                 cancel: threading.Event | None = None):
        self.cache = cache
        self.adapters = adapters
        self._emit = emit or (lambda e: None)
        self.reuse_dir = Path(reuse_dir) if reuse_dir else None
        self.allow_heavy = allow_heavy
        self.cold = cold or set()
        self.cancel = cancel or threading.Event()
        self._fingerprints: dict[tuple, str] = {}
        self._waits: dict[str, float] = {}
        self._waits_lock = threading.Lock()

    def add_wait(self, stage: str, seconds: float) -> None:
        """Time a stage spent waiting for the GPU mutex; kept apart from the time it ran."""
        with self._waits_lock:
            self._waits[stage] = self._waits.get(stage, 0.0) + seconds

    def _take_wait(self, stage: str) -> float:
        with self._waits_lock:
            return self._waits.pop(stage, 0.0)

    def emit(self, event: dict) -> None:
        self._emit({"time": time.time(), **event})

    def _is_cold(self, stage: Stage) -> bool:
        return any(c in ("all", stage.name, stage.kind) or (c.endswith("*") and stage.name.startswith(c[:-1])) for c in self.cold)

    def _code(self, stage: Stage) -> str:
        if stage.code not in self._fingerprints:
            self._fingerprints[stage.code] = source_fingerprint(*stage.code) if stage.code else ""
        return self._fingerprints[stage.code]

    def key(self, stage: Stage, input_digests: dict[str, str]) -> str:
        return sha256_json({
            "schema": CACHE_SCHEMA, "stage": stage.name, "kind": stage.kind, "params": stage.params,
            "inputs": input_digests, "code": self._code(stage),
            "adapter": self.adapters.fingerprint(stage.adapter) if stage.adapter else None,
        })

    def _reuse_candidate(self, stage: Stage, pipeline: Pipeline, results: dict[str, StageResult],
                         source_digest: str) -> tuple[Path, list[str]] | None:
        if self.reuse_dir is None or stage.reuse_subdir is None or not stage.outputs:
            return None
        base = self.reuse_dir / stage.reuse_subdir
        if not base.is_dir():
            return None
        files = sorted({p.name for pat in stage.outputs for p in base.glob(pat) if p.is_file()})
        if not files or any(not any(fnmatch.fnmatch(f, pat) for f in files) for pat in stage.outputs):
            return None
        # Only import outputs that were made from the same inputs: every upstream file
        # this stage reads must exist in the reuse layout with identical content.
        for inp in stage.inputs.values():
            if inp.stage == SOURCE:
                continue
            up = pipeline.stage(inp.stage)
            if up.reuse_subdir is None:
                return None
            wanted = [inp.file] if inp.file else list(results[inp.stage].files)
            for f in wanted:
                p = self.reuse_dir / up.reuse_subdir / f
                if not p.exists() or self.cache.hashes.file(p) != results[inp.stage].files[f]:
                    return None
        return base, files

    def run(self, pipeline: Pipeline, source: Path, run_dir: Path) -> dict[str, StageResult]:
        source = Path(source)
        source_digest = self.cache.hashes.file(source)
        stages_dir = Path(run_dir) / "stages"
        results: dict[str, StageResult] = {}
        self.results = results
        total = len(pipeline.stages)
        for index, stage in enumerate(pipeline.stages):
            if self.cancel.is_set():
                raise Cancelled("cancelled")
            inputs: dict[str, Path] = {}
            digests: dict[str, str] = {}
            for name, inp in stage.inputs.items():
                if inp.stage == SOURCE:
                    inputs[name], digests[name] = source, source_digest
                    continue
                up = results[inp.stage]
                if inp.file:
                    inputs[name], digests[name] = up.out_dir / inp.file, up.files[inp.file]
                else:
                    inputs[name], digests[name] = up.out_dir, digest_of_files(up.files)
            key = self.key(stage, digests)
            out = stages_dir / stage.name
            adapter = self.adapters.describe(stage.adapter) if stage.adapter else None
            self.emit({"type": "stage", "stage": stage.name, "kind": stage.kind, "status": "started", "key": key,
                       "fraction": round(index / total, 4)})
            res = StageResult(stage.name, stage.kind, "failed", key, out, {}, inputs=digests, adapter=adapter)
            t0 = time.time()
            try:
                entry = self.cache.lookup(key)
                cold = self._is_cold(stage)
                if entry and not cold:
                    self._materialize(entry, out)
                    res.status, res.files, res.provenance = "cached", entry.files, entry.provenance
                else:
                    cand = None if cold or entry else self._reuse_candidate(stage, pipeline, results, source_digest)
                    if cand:
                        base, files = cand
                        entry = self.cache.store(key, stage.name, base, files, {"imported_from": str(base)})
                        self._materialize(entry, out)
                        res.status, res.files, res.provenance = "imported", entry.files, entry.provenance
                    else:
                        res.files = self._execute(stage, out, inputs)
                        res.status = "ran"
                        if entry:
                            res.matches_cache = self._equivalent(out, res.files, entry)
                            res.provenance = {"compared_with_cache": key}
                        else:
                            self.cache.store(key, stage.name, out, list(res.files), {"ran": True})
            except Exception as e:  # noqa: BLE001 - reported on the stage, then re-raised
                res.seconds = time.time() - t0
                res.queue_wait_s = min(self._take_wait(stage.name), res.seconds)
                res.error = f"{type(e).__name__}: {e}"
                results[stage.name] = res
                self.emit({"type": "stage", "stage": stage.name, "kind": stage.kind, "status": "failed",
                           "error": res.error, "trace": traceback.format_exc(limit=5)})
                raise StageFailed(stage.name, res.error) from e
            res.seconds = time.time() - t0
            res.queue_wait_s = min(self._take_wait(stage.name), res.seconds)
            results[stage.name] = res
            event = {"type": "stage", "stage": stage.name, "kind": stage.kind, "status": res.status,
                     "seconds": round(res.seconds, 3), "queue_wait_s": round(res.queue_wait_s, 3),
                     "run_s": round(res.run_s, 3), "key": key, "fraction": round((index + 1) / total, 4)}
            if adapter:
                event["device"] = adapter["device"]
            if res.matches_cache is not None:
                event["matches_cache"] = res.matches_cache
            self.emit(event)
        return results

    def _equivalent(self, out: Path, files: dict[str, str], entry: Entry) -> bool:
        """Same files with the same content; MusicXML is compared after canonicalising
        music21's random part/instrument ids and the encoding date."""
        if set(files) != set(entry.files):
            return False
        for rel, digest in files.items():
            if digest == entry.files[rel]:
                continue
            if not rel.endswith(".musicxml"):
                return False
            from .compare import canonical_musicxml

            if canonical_musicxml((out / rel).read_text()) != canonical_musicxml(self.cache.path(entry, rel).read_text()):
                return False
        return True

    def _materialize(self, entry: Entry, out: Path) -> None:
        if out.exists():
            shutil.rmtree(out)
        self.cache.materialize(entry, out)

    def _execute(self, stage: Stage, out: Path, inputs: dict[str, Path]) -> dict[str, str]:
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        stage.run(StageContext(stage, out, inputs, self))
        files = {p.relative_to(out).as_posix(): self.cache.hashes.file(p) for p in sorted(out.rglob("*")) if p.is_file()}
        if not files:
            raise StageFailed(stage.name, "stage produced no output files")
        missing = [pat for pat in stage.outputs if not any(fnmatch.fnmatch(f, pat) for f in files)]
        if missing:
            raise StageFailed(stage.name, f"missing outputs {missing}")
        return files

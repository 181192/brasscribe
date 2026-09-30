# brasscribe-engine

The Python engine: it turns a recording into a brass-band score and serves the HTTP API that Studio and
the Play apps use. Bandroom (Mac and Windows) installs and runs this same engine.

- **Pipeline.** A profile picks the stages a recording goes through (`profiles.py`). Stages form a DAG
  with a content-addressed cache (`dag.py`, `cache.py`); `runner.py` writes each run to
  `<data>/runs/<run-id>/`: `composition.json`, MusicXML, PDF, MIDI and MP3 under `outputs/`, each
  stage's files, and a manifest of what ran.
- **Models** run as subprocesses behind a `<input> <output>` contract, each in its own environment under
  [`ml/adapters/`](../ml/adapters) (`adapters.py`). The engine never imports model code. Heavy models
  take a machine-wide GPU lock (`gpulock.py`).
- **Symbolic stages** (quantization, spelling, arranging, MusicXML) come from the
  [`music`](../music/README.md) library.
- **HTTP service** (`api.py`, FastAPI): Studio in the browser on the same computer, and companion mode
  for the Play apps on the LAN, with pairing, per-device tokens (`companion.py`) and Bonjour/mDNS
  advertisement as `_brasscribe._tcp` (`discovery.py`). The contract is the committed
  [`openapi.json`](openapi.json); the apps generate their clients from it.
- **Studio** is served at `/` from the committed bundle in `src/brasscribe_engine/static/`
  (built from [`studio/`](../studio/README.md)), so the engine runs without Node.

## Running

From the repository root, after `pixi install`:

```sh
pixi run brasscribe profiles                    # the transcription profiles
pixi run brasscribe run take.wav --profile solo --out data/runs/my-take
pixi run studio                                 # engine + Studio on http://127.0.0.1:8765/, opens a browser
pixi run serve --lan                            # listen on the LAN, print the URL and a 6-digit pairing code
curl -s http://127.0.0.1:8765/v1/health
```

Other commands: `bench` (benchmark suites against `eval/baselines.json`), `compare` (a run against a
reference output), `manifest` (show or re-run a run), `devices` (list or revoke paired devices).
`pixi run brasscribe <command> --help` has the options.

On macOS on Apple silicon the model adapters use [uv](https://docs.astral.sh/uv/) by default
(`uv run --frozen --project ml/adapters/<name>`; the uv lock files are solved for that platform only).
Elsewhere, or with `BRASSCRIBE_ADAPTER_RUNNER=pixi`, they use the pixi environment of the same name
(`pixi install -e muscriptor`, …). Model weights are not in git: they go under `BRASSCRIBE_MODELS`, or
the adapter downloads them from where their makers publish them (licences in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).

A job option the engine refuses answers 422 with `{"code": …, "detail": …}`; the codes are in
`profiles.py`, and the apps word them themselves.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BRASSCRIBE_DATA` | `<repo>/data` | Cache, runs, uploads, datasets |
| `BRASSCRIBE_MODELS` | `<data>/models`, then `<repo>/models` | Model weights |
| `BRASSCRIBE_ADAPTERS` | `<repo>/ml/adapters` | Adapter directory |
| `BRASSCRIBE_ADAPTER_RUNNER` | `uv` on Apple silicon Macs, else `pixi` | `uv` or `pixi` |
| `BRASSCRIBE_TOKEN` | none | Static bearer token for scripts; the apps pair and get their own |
| `BRASSCRIBE_TRUST_LOCAL` | `1` | Clients on this computer use the API without a token |
| `BRASSCRIBE_ALLOWED_HOSTS` | none | Extra host names (comma-separated) clients on this computer may use, e.g. a local proxy's |
| `BRASSCRIBE_MAX_UPLOAD_BYTES` | 2 GiB | Largest upload (request body); larger ones get 413 |
| `BRASSCRIBE_GPU_LOCK` | `/tmp/brasscribe-gpu-<uid>.lock` | Lock for heavy models, shared by this user's runs |
| `BRASSCRIBE_BAND_SOUNDS_DIR` | none | Band SoundFont and part map Studio plays |

`src/brasscribe_engine/config.py` lists the rest (companion state, device expiry, display name, owner
credential, report folders).

## Tests

```sh
pixi run test-fast     # engine + music, without the slow tests
pixi run test          # everything, and checks that openapi.json is up to date
pixi run openapi       # rewrite openapi.json after an API change
```

`scripts/check.sh fast engine` and `full engine` are the same tiers
([docs/dev/verify.md](../docs/dev/verify.md)). Tests that need recordings or reference output under
`data/` skip when it is missing.

## Docker

```sh
docker build -f engine/Dockerfile --target cpu -t brasscribe:cpu .    # --target cuda for NVIDIA GPUs
docker run --rm -v "$PWD/data:/data" -p 8765:8765 brasscribe:cpu
```

The image has the engine and every adapter environment, and serves on the LAN without mDNS (a bridged
container would advertise its own address).

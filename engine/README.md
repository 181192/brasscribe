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
- **Tablature.** The `bass-tab` profile (`bass_tab.py`) writes a bass line as tab instead of a band score: the
  separated bass stem, or the recording itself when it is the bass alone (`recording: instrument`), then Basic
  Pitch, the shared beat grid and durations, and a string and fret for every note from the Rust crate
  [`target-fretted`](../core/target-fretted/README.md), which the engine calls through the core's command line
  (`brasscribe-core fret`). Its result is `tab.json` (`GET /v1/jobs/{id}/tab`, `Tab` in `schemas.py`): the
  fingered notes, the tunings ranked by fit, the recording's offset from A = 440, tempo, key and meter, and the
  octave shift when the line was heard an octave high. The tab itself is `tab.musicxml`, written by the same crate
  (`brasscribe-core tab`), and `tab.pdf` and `tab.mid` through MuseScore when it is installed; `/musicxml`, `/pdf`
  and `/midi` of the job serve them. It takes `instrument` (`bass-4`, `bass-5`, `bass-6`), `tuning`, `capo`,
  `style`, `octave` (`auto`, or the player's choice) and `layout` (`tab`, `tab-and-notation`, `notation`), and
  none of the band options. SwiftF0 listens to the same audio as a second opinion: a note it did not hear at that
  pitch gets a confidence below 0.4 and a "?" in the tab, a single note it heard an octave lower is written there,
  and overtones heard as notes are left out. `brasscribe bench bass-tab` measures all of it on Slakh bass lines and
  on synthesized lines at the bottom of the instrument ([`bass_tab_bench.py`](../eval/brasscribe_eval/bass_tab_bench.py));
  it runs where the data and the models are, not in CI.
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
pixi run brasscribe run song.wav --profile bass-tab --instrument bass-5 --out data/runs/my-tab
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
`profiles.py`, and the apps word them themselves. A `bass-tab` job on an engine without `brasscribe-core` is
refused the same way (`core_missing`), before any model runs. Bandroom for Mac and for Windows bundle
`brasscribe-core` and point the engine they install at it with `BRASSCRIBE_CORE_CLI`.

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
| `BRASSCRIBE_ADAPTER_TIMEOUT_S` | 3 h heavy, 1 h other models | How long one model run may take before it is stopped |
| `BRASSCRIBE_BAND_SOUNDS_DIR` | none | Band SoundFont and part map Studio plays |
| `BRASSCRIBE_CORE_CLI` | `<repo>/core/target/release/brasscribe-core`, then the `PATH` | The Rust core's command line, for the `bass-tab` profile. A checkout gets it from `scripts/worktree-setup.sh` (or `cargo build --release -p brasscribe-cli` in `core/`); the Docker image builds it and sets the variable |

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

The image has the engine, every adapter environment and the Rust core's command line (built from `core/`
in its own stage, for the `bass-tab` profile), and serves on the LAN without mDNS (a bridged
container would advertise its own address).

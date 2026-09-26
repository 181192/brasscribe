# Model conversions and parity tests

Per-model scripts that convert the pipeline's models to platform runtimes (ONNX, Core ML,
TFLite) and test the converted model against the reference framework on the eval sets.
A model is switched on in Play only once its parity gate passes (note F1 >= 0.98 against the
reference output, `docs/plan/apps-plan.md` §6).

This lives in `convert/`, not `models/convert/`: `models/` is ignored (repo `.gitignore` and
`.git/info/exclude`) and is a symlink in worktrees, so it cannot hold tracked files.
Converted models are written to `models/converted/<model>/` in the main checkout and are
never committed; only the small JSON reports under `convert/reports/` are.

## Layout

| Path | What it does |
|---|---|
| `common/parity.py` | Clip lists, note/event matching (mir_eval, 50 ms onsets, offsets ignored), pooled F1, SDR, isolated-process benchmarks (latency, peak RSS, CoreML EP node coverage), Core ML compute plans, report writing |
| `common/separation.py` | Separator parity: stem SDR, then SwiftF0 and Basic Pitch note F1 on converted vs reference stems |
| `common/coreml_ops.py` | coremltools torch-frontend fixes: op-name aliases (`greater_equal`, ...) and scalar casts of folded length-1 arrays |
| `swift-f0/` | Upstream ONNX -> static-shape ONNX (onnxsim) -> onnx2torch -> Core ML fp32/fp16 (30.3 s window and 2 s streaming window) |
| `basic-pitch/` | Parity of the upstream Core ML/TFLite/ONNX exports vs the TF SavedModel; batch-1 ONNX (explicit Conv pads, for the CoreML EP) and batch-1 Core ML fp32/fp16 |
| `beat-this/` | `small0` and `final0`: dynamic ONNX, fixed 1500-frame ONNX, Core ML fp32/fp16 (network only; log-mel on the host) |
| `demucs/` | HT-Demucs core (STFT/iSTFT on the host) -> ONNX, Core ML fp32/fp16 |
| `roformer/` | BS-RoFormer SW and Mega-53 core (STFT, complex mask, iSTFT on the host) -> ONNX fp32/fp16, Core ML fp16 |
| `muscriptor/` | MuScriptor transformer as ONNX prefill + decode-with-past graphs, greedy decode on the host |
| `summarize.py` | Markdown table from `reports/*.json` |
| `reports/*.json` | One machine-readable parity report per model |

Each model has its own uv env (`uv run` inside its folder). Torch is pinned to 2.7.0 in the
envs that use coremltools 9.0 (its newest tested torch). The adapter envs under `ml/adapters/`
are not touched.

## Method

- **Swap only the network.** Every backend replaces the model call inside the upstream
  package's own pipeline (SwiftF0 `session.run`, `basic_pitch.inference.predict`, Beat This
  `File2Beats`, `demucs.apply.apply_model`, MSST `demix`, MuScriptor `TranscriptionModel`),
  so resampling, chunking, overlap-add, peak picking and note creation are identical and any
  difference comes from the conversion.
- **Reference:** PyTorch CPU fp32 (Beat This, Demucs, RoFormers, MuScriptor); the TF SavedModel
  (Basic Pitch); the upstream ONNX on ONNX Runtime CPU (SwiftF0 ships no PyTorch weights).
- **Metric:** pooled note F1 over clips (reference output as ground truth); Beat This uses
  event F1 of beat and downbeat times at 50 ms (gate on the lower); separators report stem SDR
  and gate on SwiftF0 and Basic Pitch note F1 of the transcribed stems.
- **Clips:** 10 ChoraleBricks brass-quartet mixes and 8 URMP brass mixes, plus the 87
  isolated parts behind them for the monophonic/pitch models; separators use three 30 s eval
  excerpts plus Mikkel 60–90 s; Beat This adds full Mikkel.
- **Benchmarks:** fresh process per backend, one warm-up, median of N (N in the JSON),
  on the realistic path (including host pre/post-processing). `peak_rss_mb` is the process
  peak (macOS `ru_maxrss` bytes), `model_rss_mb` subtracts the post-import baseline.
  CoreML EP rows record how many graph nodes the EP took. Core ML compute units are
  requests; the `coreml_compute_plan` sections list the device Core ML actually plans per op.

## Results (M5 Pro, 48 GB, macOS)

Regenerate with `python3 convert/summarize.py`. Latency = wall time for the audio length given.

| Model | Format / runtime | Size | Parity vs reference | Latency | Peak RSS | Gate |
|---|---|---|---|---|---|---|
| SwiftF0 | ONNX static, ORT CoreML EP | 1.1 MB | 1.0000 | 14 ms / 30 s | 149 MB | pass |
| SwiftF0 | Core ML fp32 (ALL -> GPU) | 1.2 MB | 1.0000 | 9 ms / 30 s | 393 MB | pass |
| SwiftF0 | Core ML fp16 (ALL -> GPU) | 0.6 MB | 0.9899 | 6 ms / 30 s | 395 MB | pass |
| SwiftF0 | Core ML fp16 CPU_AND_NE | 0.6 MB | 0.3703 | 21 ms / 30 s | 496 MB | **fail** |
| SwiftF0 | streaming 2 s window, fp32 / fp16 | | 1.0000 / 0.9872 | | | pass |
| Basic Pitch | upstream TFLite (LiteRT CPU) | 0.2 MB | 1.0000 | 0.72 s / 30 s | 719 MB | pass |
| Basic Pitch | upstream / batch-1 ONNX, ORT CPU | 0.2 MB | 1.0000 | 0.15 s / 30 s | 585 MB | pass |
| Basic Pitch | batch-1 ONNX, ORT CoreML EP | 0.2 MB | 1.0000 | 0.17 s / 30 s | 617 MB | pass |
| Basic Pitch | upstream Core ML (ALL) | 0.3 MB | 1.0000 | 0.09 s / 30 s | 591 MB | pass |
| Basic Pitch | batch-1 Core ML fp32 (ALL) | 0.3 MB | 1.0000 | 0.09 s / 30 s | 589 MB | pass |
| Basic Pitch | batch-1 Core ML fp16 (any units) | 0.2 MB | 0.815–0.822 | 0.10 s / 30 s | 607 MB | **fail** |
| Beat This small0 | ONNX dynamic, ORT CPU | 78 MB | 1.0000 / 1.0000 | 0.63 s / 60 s | 2.1 GB | pass |
| Beat This small0 | Core ML fp32 (ALL -> GPU) | 78 MB | 0.9988 / 0.9946 | 0.08 s / 60 s | 501 MB | pass |
| Beat This small0 | Core ML fp16 (ALL -> GPU) | 39 MB | 0.9980 / 0.9941 | 0.05 s / 60 s | 497 MB | pass |
| Beat This small0 | Core ML fp16 CPU_AND_NE (all ops on ANE) | 39 MB | 0.9976 / 0.9941 | 0.33 s / 60 s | 465 MB | pass |
| Beat This final0 | Core ML fp16 (ALL) | 39 MB | 0.9979 / 0.9916 | 0.06 s / 60 s | 597 MB | pass |
| HT-Demucs | ONNX core, ORT CPU | 166 MB | 1.0000 / 0.9996, SDR >= 49 dB | 3.7 s / 30 s | 4.3 GB | pass |
| HT-Demucs | ONNX core, ORT CoreML EP (1434/1459 nodes) | 166 MB | 1.0000 / 1.0000, SDR >= 80 dB | 1.6 s / 30 s | 2.4 GB | pass |
| HT-Demucs | Core ML fp32 (ALL -> GPU) | 205 MB | 1.0000 / 1.0000, SDR >= 80 dB | 0.94 s / 30 s | 1.3 GB | pass |
| HT-Demucs | Core ML fp16 (ALL -> GPU) | 103 MB | 1.0000 / 0.9849, SDR >= 13 dB | 0.55 s / 30 s | 1.2 GB | pass |
| HT-Demucs | Core ML fp16 CPU_AND_NE | 103 MB | 0.9922 / 0.9518, SDR >= 4.7 dB | 15.3 s / 30 s | 6.7 GB | **fail** |
| BS-RoFormer SW | ONNX fp32 core, ORT CPU | 668 MB | 1.0000 / 1.0000, SDR >= 74 dB | 88 s / 30 s | 14.2 GB | pass |
| BS-RoFormer SW | ONNX fp16 core, ORT CPU | 336 MB | 0.9971 / 0.9922, SDR >= 6.7 dB | 162 s / 30 s | 22.5 GB | pass (see below) |
| BS-RoFormer SW | Core ML fp16 (ALL -> GPU) | 335 MB | 1.0000 / 0.9990, SDR >= 27 dB | 6.3 s / 30 s | 3.9 GB | pass |
| BS-RoFormer SW | ONNX fp32, ORT CoreML EP | 668 MB | — | — | — | **blocked** |
| Mega-53 | ONNX fp32 core, ORT CPU (low-memory session) | 2.6 GB | 1.0000 / 1.0000, SDR >= 73 dB | 143 s / 30 s | 25.2 GB | pass |
| Mega-53 | Core ML fp16 (ALL -> GPU) | 1.3 GB | 1.0000 / 0.9993, SDR >= 34 dB | 14.7 s / 30 s | 21.5 GB | pass |
| Mega-53 | ONNX fp16 core (exported, 1.3 GB) | 1.3 GB | — | — | — | not run |
| MuScriptor medium | ONNX prefill + decode-with-past, ORT CPU | 2 x 1.2 GB | 1.0000; 24/24 chunks token-identical | 51 s / 30 s (23 ms/token) | 4.1 GB | pass |
| MuScriptor medium | same, ORT CoreML EP | | — | — | — | **blocked** |

Separator F1 columns are SwiftF0 / Basic Pitch; Beat This columns are beat / downbeat.
PyTorch CPU reference timings: Beat This small0 0.75 s / 60 s, HT-Demucs 8.4 s / 30 s,
BS-RoFormer SW 63 s / 30 s, Mega-53 104 s / 30 s (14.7 GB), MuScriptor medium 34 s / 30 s
(16 ms/token, 2.6 GB). Mega-53 Core ML load takes 55 s (first compile).

## What fails and why

- **fp16 on the Neural Engine for SwiftF0 and HT-Demucs.** The ANE runs fp16 end to end; the
  SwiftF0 matmul-DFT spectrogram and the HT-Demucs normalisation lose too much precision
  (SwiftF0 voicing collapses; Demucs stems drop to single-digit dB SDR). The same fp16 models
  pass on the GPU (`ALL` plans every op on the GPU). Use fp32 or GPU for these; a mixed-precision
  build (fp32 spectrogram/normalisation ops) is the likely fix, untested.
- **Basic Pitch fp16 Core ML.** fp16 shifts onset/frame activations near the 0.5/0.3
  thresholds on every compute unit (F1 ~0.82). Use the upstream Core ML model (fp32) or the
  fp32 batch-1 build; both are exact.
- **Beat This fixed-length models on pieces under 30 s.** Upstream runs such pieces as one
  shorter chunk; the fixed 1500-frame Core ML model zero-pads, which changes attention context.
  The two such eval clips deviate (pooled F1 still >= 0.99). The dynamic ONNX is exact.
- **BS-RoFormer SW on the ORT CoreML EP.** The process was killed by the OS (out of memory)
  while the EP compiled/ran the 13.4 s chunk. Core ML directly (coremltools) runs it on the
  GPU at ~10x the PyTorch CPU speed.
- **Mega-53 ONNX fp16** was exported but not run: fp32 on ORT CPU already peaks at 25 GB
  on this 48 GB machine, and fp16 on CPU needs more (see next point).
- **MuScriptor on the CoreML EP.** The EP cannot build the dynamic-length prefill graph
  ("unbounded dimension", then error -7 building the execution plan). Needs static-shape graphs:
  a fixed-size KV cache with a length mask. On CPU the ONNX graphs are exact (identical tokens on
  every chunk) but 1.5x slower than PyTorch CPU.
- **MuScriptor on Core ML / MLX Swift: not attempted.** Core ML needs the same static KV-cache
  rewrite (or a coremltools stateful model). MLX Swift has no port of this model: the transformer,
  log-mel conditioner, MT3 detokeniser and prelude-forcing loop would have to be written in Swift
  and the safetensors weights mapped.
- **ONNX fp16 on CPU** is emulated by ORT: slower and larger in memory than fp32 on CPU, and its
  stems drift (SW SDR min 6.7 dB) although transcriptions still agree. fp16 ONNX is for GPU EPs
  (DirectML/CUDA/WebGPU), not verified here.

## Open questions

- Phone latency and memory: only macOS on M5 Pro was measured. iOS/Android numbers need a device.
- LiteRT beyond Basic Pitch's shipped `.tflite` was not produced; Android ORT Mobile can run
  the ONNX files, untested on device.
- Ported host code is still needed per platform: SwiftF0 needs none (spectrogram in-graph);
  Basic Pitch needs none (CQT in-graph); Beat This needs its log-mel; the separators need
  STFT/iSTFT and complex masking; MuScriptor needs its log-mel conditioning and the decode loop.

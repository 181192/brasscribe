# Research brief (shared by all research agents)

Project: "brasscribe" — local-first app: recorded audio (pop/rock/orchestral/brass etc.) → musical understanding (melody, bass, harmony, chords, rhythm, tempo, meter, key, sections, countermelodies) → brass-band arrangement → MusicXML. Personal use, accuracy >> speed, offline batch, not real-time. Target machine: Apple M5 Pro, 48 GB unified memory, macOS 26.6. Pipeline stages are replaceable adapters (likely Go orchestrator → per-model Python subprocess).

**Status (2026-09-29):** the brief reports 01–06 were written to on 2026-09-25. Kept for reference.

## Rules
- Your knowledge cutoff is ~June 2026; today is 2026-09-25. Actively SEARCH for releases/papers since then (ISMIR 2026 papers, arXiv Jul–Sep 2026, new HF models). Never fill a field from memory. If you can't verify something, write "not found".
- Primary sources only: arXiv, ISMIR/ICASSP/TASLP proceedings, official GitHub repos, Hugging Face model cards, challenge leaderboards (MDX/SDX, MIREX, etc.). No SEO listicles. Don't rely on Papers with Code (defunct/redirected).
- Give a URL for every factual claim.
- License: record CODE license and WEIGHTS license separately (MIT code + non-commercial weights is common). Personal use is fine, but note it.
- Repo activity: last commit date / last release from the repo itself (use `gh api repos/OWNER/REPO` or `gh api repos/OWNER/REPO/commits?per_page=1` via Bash, or WebFetch).
- Apple Silicon: label each model "claimed in docs", "reported working" (link issue/PR), or "unknown". Note MPS/CoreML/MLX/ONNX paths.
- Brass suitability: look for per-instrument results on datasets containing brass (Slakh, URMP, MusicNet, MedleyDB, MoisesDB, etc.). State whether brass is its own class or lumped into "other"/"wind", and whether the model can separate simultaneous brass voices (e.g. 3 cornets in close harmony). Note that brass-band ground-truth data is scarce.
- Benchmarks: record dataset, metric, number as reported; flag when numbers from different papers aren't comparable.
- Do NOT install/run large models — this is desk research. Small `gh`/`pip index`/WebFetch checks are fine.

## For each serious candidate, document
model · architecture · release/update date · code license · weights license · repository · pretrained weights (where) · training datasets · published benchmarks · hardware requirements · Apple Silicon support · inference speed · strengths · weaknesses · suitability for brass music

## Output
Write your findings to the markdown file named in your task (in /Users/k/private/brasscribe/docs/research/). Structure: short executive summary with a PRIMARY and BACKUP pick, a comparison table, per-candidate detail sections, open questions that only benchmarking can settle, and a references list. Then return a ≤300-word summary to the caller with your top picks and the biggest risks.

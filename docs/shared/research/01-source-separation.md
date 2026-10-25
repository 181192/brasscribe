# 01 — Music Source Separation

**Status (2026-09-29):** desk research, acted on. BS-RoFormer SW and Mega-53 run in the engine through `ml/adapters/separator` and `ml/adapters/mega53`; the decision is in [00-summary.md](00-summary.md) §0. Separation does not run on the phone.

Research date: 2026-09-25. Scope: separation as a front end for brasscribe (recorded audio → musical understanding → brass-band arrangement). Desk research only; nothing was installed or run.

---

## Executive summary

**PRIMARY: a two-stage RoFormer stack, run through ZFTurbo's MSST or python-audio-separator on PyTorch MPS, with the MLX port as the speed path.**
1. **Stage 1, the stems for "understanding": BS-RoFormer SW (6-stem).** It outputs vocals, bass, drums, guitar, piano and other. It has the best public open-weights multi-stem numbers found: on MVSEP's Multisong set, bass 14.62 / drums 14.11 / vocals 11.30 / guitar 9.05 / piano 7.83 / other 8.71 SDR ([mvsep 77](https://mvsep.com/algorithms/77)). It also drove the winning MSR-2025 system ([arXiv 2602.09042](https://arxiv.org/html/2602.09042v1)).
2. **Stage 2, brass-aware stems: MVSep Mega-53 v1 (BS-RoFormer, 53 stems).** This is the **only open-weights model found that was trained on real mixed-genre music and outputs brass sub-classes**: brass, trumpet, trombone, french-horn, tuba, saxophone, wind, woodwind. It was released on 2026-04-20 ([release v1.0.21](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21)). SynthSOD's X-UMX baseline also has horn/trumpet/trombone/tuba outputs, but it is synthetic-orchestral, AGPL, and fails on real recordings (§6). Banquet can be *queried* for brass, but it is weak (§5). Use Mega-53 to detect which brass or wind families are present, and to pull a "brass" stem out of stage 1's "other".

**BACKUP: HT-Demucs v4 (`htdemucs_ft`, plus `htdemucs_6s` for guitar/piano).** Code is MIT and actively maintained again (v4.1.0 on 2026-07-11). MPS is claimed in the docs, and an MLX port claims 2.6x the speed of MPS. The sound is weaker than the RoFormers, but it is the lowest-risk dependency. **Pair it with SAM-Audio (Meta, text-prompted, Dec 2025) as an experimental probe** for "trumpet", "tuba" and similar prompts. SAM-Audio is the only open model that can be *asked* for an arbitrary brass instrument. It is generative, mono, 48 kHz, and evaluated only by subjective scores. Its MUSDB evaluation covers only vocals, drums and bass, so **there is no published per-instrument evidence for brass**.

**The three findings that matter most for brasscribe:**
1. **No model separates simultaneous voices of the same instrument.** Three cornets in close harmony come out as one "trumpet"/"brass" stem at best. Cornet, flugelhorn-vs-cornet, tenor horn, baritone and euphonium are not classes in any model found. Same-timbre ("monotimbral") separation is a research topic with tiny datasets ([GuitarDuets, ISMIR 2024](https://arxiv.org/abs/2507.01172)). Voice splitting has to happen in transcription or symbolic post-processing, not in separation.
2. **What separation is good for depends on the input.** For pop/rock/orchestral input, separation gives cleaner melody, bass, harmony and drums for downstream models. For brass-band recordings the whole mix is brass, so brass-vs-other models add almost nothing. At most Mega-53 might peel off percussion, tuba or bass, and horn. Nothing in the literature measures this.
3. **Evidence that separation improves transcription is thin and mixed.** The clearest controlled number is from YourMT3+. Transcribing singing from a Spleeter-separated stem instead of the mixture takes a transcriber *not* trained on mixtures from 3.6 to 68.0 onset-F1. But for a transcriber trained with cross-stem mixture augmentation the gain is only about 1–6 points ([arXiv 2407.04822](https://arxiv.org/pdf/2407.04822), Table 2). The separator there was Spleeter; a RoFormer front end could change the gap in either direction. Separation artifacts cost accuracy. SDR-leading models can also distort attacks (BS-RoFormer distorted drum attacks about 2x more than SCNet-XL at equal SDR, [arXiv 2609.04224](https://arxiv.org/abs/2609.04224)). Plan to benchmark "mixture vs stem" per downstream task rather than assume separation helps.

---

## Comparison table

Metrics are **not comparable across rows** unless the dataset and metric match. "MUSDB" means the MUSDB18-HQ test set. "Multisong" is MVSEP's 100-track set ([quality checker](https://mvsep.com/quality_checker)). MVSEP "Wind" is a 35-track, 1-minute-per-track set. The BS-RoFormer paper reports *median* SDR.

| Model | Arch | Stems (is brass its own class?) | Headline numbers (dataset / metric) | Code lic. | Weights lic. | Apple Silicon | Last activity |
|---|---|---|---|---|---|---|---|
| **BS-RoFormer SW** (community, via jarredou) | BS-RoFormer | V/B/D/guitar/piano/other; brass is in **other** | Multisong: B 14.62, D 14.11, V 11.30, Gtr 9.05, Pno 7.83, Other 8.71 SDR ([mvsep 77](https://mvsep.com/algorithms/77)) | MIT (MSST/audio-separator) | **Undocumented provenance/licence** | Claimed in docs (audio-separator MPS; mlx-audio-separator documents SW explicitly) | Weights file 2025-09-27 ([audio-separator release](https://github.com/nomadkaraoke/python-audio-separator/releases/tag/model-configs)) |
| **MVSep Mega-53 v1** | BS-RoFormer (dim 256, depth 12, 53 stems) | **Yes**: brass, trumpet, trombone, french-horn, tuba, sax, wind, woodwind (+45 more) | Unspecified MVSEP validation set, open v1: brass 6.70, trumpet 4.97, trombone 2.69, horn 5.26, tuba 7.20, sax 8.89, wind 8.63 SDR ([mvsep 135](https://mvsep.com/algorithms/135)); wind 8.63 on the Wind leaderboard ([lb](https://mvsep.com/quality_checker/leaderboard/wind)) | MIT (MSST repo) | **Not stated** | Unknown (MSST selects MPS; STFT falls back to CPU; release says ≥16 GB VRAM) | 2026-04-20 |
| MVSep Wind / Brass / Woodwind (service) | BS-/Mel-RoFormer, SCNet | Wind; Brass; Woodwind as binary stems | Wind set: BS-RoFormer 9.82, Mel+SCNet ensemble 7.22 SDR ([mvsep 61](https://mvsep.com/algorithms/61)); Brass/Woodwind pages publish no metrics ([98](https://mvsep.com/algorithms/98), [100](https://mvsep.com/algorithms/100)) | — | **Weights not public** (web service) | n/a | Wind BS-RoFormer 2025-08 |
| **HT-Demucs v4** (`htdemucs`, `_ft`, `_6s`) | Hybrid wave/spec U-Net + cross-domain Transformer | 4 stems; 6s adds guitar and piano ("piano not working great"); brass is in **other** | MUSDB: 9.00 SDR; 9.20 with sparse attention + per-source fine-tuning ([README](https://github.com/adefossez/demucs)); Multisong htdemucs: B 11.76 D 10.88 V 8.24 O 5.74 ([MSST](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md)) | MIT | Hosted by Meta, no separate licence | **Claimed in docs** (MPS auto); MLX port [demucs-mlx](https://github.com/ssmall256/demucs-mlx) | Repo 2026-08-31; PyPI 4.1.0 on 2026-07-11 |
| BS-RoFormer (paper) | Band-split + RoPE Transformer | 4 stems | MUSDB median SDR: 9.80 (no extra data), 11.99 (+500 songs) ([arXiv 2309.02612](https://arxiv.org/pdf/2309.02612)); MSST re-train: MUSDB 9.65 avg | MIT (lucidrains reimpl.) | Official ByteDance weights not released; community checkpoints vary | Claimed in docs (via audio-separator / MSST / mlx) | lucidrains 2026-06-14 |
| Mel-Band RoFormer | Mel-band split + RoPE | Per checkpoint (mostly vocals/instrumental) | MUSDB, no extra data, L=6: V 11.21 B 9.64 D 9.91 O 7.81 ([arXiv 2310.01809](https://arxiv.org/pdf/2310.01809)) | MIT | Per checkpoint (Kim vocal: MIT on HF) | Claimed in docs; also [mlx-audio mel_roformer](https://github.com/Blaizzy/mlx-audio) | active |
| SCNet / SCNet-XL | Sparse-compression band network | 4 stems | Paper: MUSDB 9.0 SDR, CPU time 48% of HT-Demucs ([arXiv 2401.13276](https://arxiv.org/abs/2401.13276)); MSST SCNet XL IHF: MUSDB 10.08 avg (best 4-stem in that table) | MIT | Google Drive / MSST releases, not separately licensed | Probably via MSST MPS; unknown | official repo 2025-09-08 |
| Banquet (query-bandit) | Band-split + PaSST query embedding | Query by audio example; MoisesDB fine classes incl. brass, reeds | MoisesDB: close to htdemucs_6s on VDBO, better on guitar/piano; long-tail stems "all still very weak… no sample above 5 dB SNR" ([arXiv 2406.18747](https://arxiv.org/html/2406.18747v2)) | MIT | **CC BY-NC-SA 4.0** ([Zenodo](https://zenodo.org/records/13694558)) | Unknown (CUDA flag in CLI) | 2025-07-29 |
| **SAM-Audio** (small/base/large, +tv) | DiT flow matching over DAC-VAE latents; T5 text, PE-AV visual | Open vocabulary (text / visual / time-span prompts) | Subjective only. MUSDB "Instr(pro)", covering only vocals/drums/bass: OVR 4.45 vs AudioShake 4.28 vs Demucs 4.26; net win rate vs Demucs 17.6%. No per-instrument or brass results ([arXiv 2512.18099](https://arxiv.org/abs/2512.18099)) | SAM License | SAM License, gated on HF | **Reported working**: MPS workaround ([issue #73](https://github.com/facebookresearch/sam-audio/issues/73)), MLX port in [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2026-05-26 |
| AudioSep | Text-queried (CLAP) ResUNet | Open vocabulary | In SAM-Audio's MUSDB comparison: OVR 2.45 (vs Demucs 4.26) | MIT | per repo | Unknown | 2024-11-26 (stale) |
| SynthSOD baseline | X-UMX | Orchestral: trumpet, horn, trombone, tuba (separate brass model) | Synthetic test: >2 dB SDR for all brass except horn; "none… achieved strong separation results even in URMP" ([arXiv 2409.10995](https://arxiv.org/html/2409.10995v1)) | AGPL-3.0 ([repo](https://github.com/repertorium/SynthSOD-Baseline)) | same repo | Unknown | 2025-10-13 |

---

## Per-candidate details

### 1. BS-RoFormer SW (6-stem): stage-1 pick
- **Architecture:** BS-RoFormer, a band-split spectrogram model with RoPE Transformers over time and band axes ([arXiv 2309.02612](https://arxiv.org/pdf/2309.02612)). Community checkpoint.
- **Provenance:** MVSEP gives no training details or attribution ([mvsep 77](https://mvsep.com/algorithms/77)). The widely cited HF mirror `jarredou/BS-ROFO-SW-Fixed` now returns HTTP 401. python-audio-separator still ships `BS-Roformer-SW.ckpt` (699 MB) and its yaml in its `model-configs` release (uploaded 2025-09-27; [release](https://github.com/nomadkaraoke/python-audio-separator/releases/tag/model-configs)), and lists it as "BS Roformer SW by jarredou" (`audio_separator/models.json`). **The weights licence and origin are undocumented.** That is acceptable for personal use, but pin a local copy with its hash.
- **Benchmarks (MVSEP Multisong + guitar/piano leaderboards):** vocals 11.30, instrumental 17.50, bass 14.62, drums 14.11, guitar 9.05, piano 7.83, other 8.71 ([mvsep 77](https://mvsep.com/algorithms/77)). For comparison, htdemucs on the same Multisong set scores bass 11.76, drums 10.88, vocals 8.24, other 5.74 ([MSST table](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md)).
- **Used in SOTA pipelines:** The SJTU X-LANCE system took 1st place in the MSR Challenge 2025 on all metrics (MMSNR 4.46, FAD 0.199, MOS overall 3.47). It used a frozen BS-Rofo-SW, then four fine-tuned BS-RoFormers to split drums and "other" into 8 targets ([arXiv 2602.09042](https://arxiv.org/html/2602.09042v1)). This is the best public example of hierarchical separation working.
- **Apple Silicon:** claimed in docs. audio-separator runs RoFormer `.ckpt` on PyTorch MPS, keeping spectral ops on device, and requires PyTorch ≥ 2.13 on Apple Silicon ([README](https://github.com/nomadkaraoke/python-audio-separator)). mlx-audio-separator lists BS-/Mel-RoFormer support and reports 2.16x the speed of audio-separator on `model_bs_roformer_ep_317` (M4 mini, [README](https://github.com/ssmall256/mlx-audio-separator)). The MLX port documents `BS-Roformer-SW.ckpt` specifically, including a dedicated SW performance/optimisation section, so SW on MLX is **claimed in docs**. No absolute runtime is published.
- **Training data:** not found. **Inference speed:** not found (no published seconds-per-track). **Hardware:** not found. The file is 699 MB, so a similar or lighter footprint than Mega-53 (1.37 GB) is likely, but that is unverified.
- **Brass:** brass lands in "other". This is useful for pop/rock (cleaner bass, drums and vocals for harmony and melody). It does nothing for brass-band input.

### 2. MVSep Mega-53 v1: the only open model with brass sub-classes
- **Release:** 2026-04-20, ZFTurbo/MSST [v1.0.21](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21). The single checkpoint is 1.37 GB (about 2.7k downloads). There is a per-stem split mirror at [noblebarkrr/BS-Roformer-MVSep-Mega-53-stems](https://huggingface.co/noblebarkrr/BS-Roformer-MVSep-Mega-53-stems).
- **Config:** BS-RoFormer, dim 256, depth 12, 53 stems, stereo, 44.1 kHz, chunk 441000 samples = 10 s ([yaml](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems.yaml)).
- **Stems relevant to brass:** `brass, trumpet, trombone, french-horn, tuba, saxophone, wind, woodwind`, plus strings/violin/viola/cello/double-bass, timpani, percussion, piano, organ and others. There are **no cornet, flugelhorn, euphonium, baritone or tenor-horn classes**. MVSEP's own Brass model *training* list includes flugelhorn ([mvsep 98](https://mvsep.com/algorithms/98)), but that model is not public.
- **Author's caveats:** memory-heavy even at batch 1, "at least 16 GB of VRAM". Per-stem quality is below MVSEP's specialised models. **Stems do not sum to the mix**, because overlapping classes exist, e.g. brass vs trumpet. MVSEP recommends using it to *detect* the stem set, then extracting with narrower models ([release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21), [mvsep 135](https://mvsep.com/algorithms/135)).
- **Benchmarks:** the open v1 vs the improved MVSEP-hosted model, on an **unspecified** MVSEP validation set ([mvsep 135](https://mvsep.com/algorithms/135)):

  | stem | open v1 SDR | MVSEP-hosted SDR |
  |---|---|---|
  | brass | 6.70 | 6.85 |
  | trumpet | 4.97 | 5.87 |
  | trombone | 2.69 | 3.08 |
  | french-horn | 5.26 | 5.51 |
  | tuba | 7.20 | 7.52 |
  | saxophone | 8.89 | 9.50 |
  | wind | 8.63 | 8.66 |
  | woodwind | 3.31 | 3.32 |

  On the public Wind leaderboard (35 tracks), `bs_mega_53stem_wind` scores 8.63 wind SDR, 2nd behind MVSEP's non-public Wind BS-RoFormer at 9.82 ([leaderboard](https://mvsep.com/quality_checker/leaderboard/wind)).
- **Licence:** the MSST repo is MIT. **The weights licence is not stated** in the release notes; don't assume MIT.
- **Training data:** not found (MVSEP-internal). **Inference speed:** not found.
- **Apple Silicon:** unknown. MSST's `inference.py` selects `mps` when available ([source](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/inference.py)), and `bs_roformer.py` moves STFT/iSTFT to CPU on MPS. The model is not in python-audio-separator's catalog. With 48 GB unified memory the "16 GB VRAM" note is probably fine, but that needs checking.
- **Brass suitability:** good as a *presence detector* and a coarse brass/tuba/horn splitter on mixed-genre input. Trumpet and trombone SDR (about 3–5 dB) implies heavy bleed. It cannot split multiple instruments of the same class.

### 3. HT-Demucs v4: backup
- **Architecture:** hybrid waveform/spectrogram U-Net with a cross-domain Transformer ([README](https://github.com/adefossez/demucs), [paper arXiv 2211.08553](https://arxiv.org/abs/2211.08553)).
- **Maintenance:** Défossez's fork is "the officially maintained Demucs". The Meta repo is archived. Last push 2026-08-31, PyPI `demucs` 4.1.0 on 2026-07-11.
- **Models:**
  - `htdemucs`: MUSDB + 800 songs.
  - `htdemucs_ft`: per-source fine-tuned, 4x slower.
  - `htdemucs_6s`: adds guitar and piano; "the piano source is not working great".
- **Benchmarks:** MUSDB-HQ 9.00 SDR; 9.20 with sparse attention + fine-tuning. Multisong numbers are in the table above.
- **Hardware:** about 7 GB GPU memory at default settings; about 1.5x track duration on CPU ([README](https://github.com/adefossez/demucs)).
- **Apple Silicon:** claimed in docs. "On Apple Silicon, the GPU is used automatically through Metal (MPS)" ([docs/mac.md](https://github.com/adefossez/demucs/blob/main/docs/mac.md)). The MLX port demucs-mlx (MIT, v1.4.14, 2026-09-23) claims bit-exact parity within float tolerance. On an M4 Max, a 3:15 track takes 2.7 s vs 6.9 s on PyTorch MPS vs 52.3 s on CPU ([README](https://github.com/ssmall256/demucs-mlx)). CoreML conversions also exist (e.g. [Isolate](https://github.com/neokumar1/Isolate), [john-rocky/CoreML-Models](https://github.com/john-rocky/CoreML-Models)) but are not needed for batch use.
- **Brass:** brass is in "other" (Multisong "other" 5.74 SDR, the weakest stem). There is no brass class.

### 4. BS-RoFormer / Mel-Band RoFormer / SCNet families (4-stem and single-stem)
- **BS-RoFormer:** 1st in the SDX23 MSS track (SAMI-ByteDance, global SDR mean 9.97 on leaderboard C). Paper MUSDB median SDR 9.80 without extra data; 11.99 with 500 extra songs (L=12, 93.4M params, 4 weeks on 16 A100s) ([arXiv 2309.02612](https://arxiv.org/pdf/2309.02612)). ByteDance did not release weights. lucidrains' reimplementation is MIT (last push 2026-06-14). A US patent on band-split transformer separation exists ([USPTO 12542148](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12542148)); the assignee was not verified. That is irrelevant for personal use.
- **Mel-RoFormer:** mel-scale bands. Beats BS-RoFormer on vocals, drums and other without extra data (V 11.21 / O 7.81 at L=6) ([arXiv 2310.01809](https://arxiv.org/pdf/2310.01809)). It is the architecture of most community vocal/instrumental checkpoints on HF (becruily, pcunwa, GaboxR67, KimberleyJSN; licences vary per checkpoint).
- **SCNet:** ICASSP 2024, 9.0 dB on MUSDB, CPU time 48% of HT-Demucs ([arXiv 2401.13276](https://arxiv.org/abs/2401.13276)). In MSST's MUSDB-only table, SCNet XL IHF is best at 10.08 avg (BS-RoFormer 9.65) ([MSST](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md)). **Beyond-SDR finding (Jul 2026):** BS-RoFormer distorts drum attacks more than twice as much as SCNet-XL (|Δ attack-slope| 1.33 vs 0.64) even though SDR calls them equal. Onset F-measure still tracks SI-SDR (ρ = 0.62) ([arXiv 2609.04224](https://arxiv.org/abs/2609.04224)). **This matters for rhythm and onset extraction downstream.** SCNet on Apple Silicon: speed not found; MPS support is presumed via MSST but not verified.
- **Newer architectures (2026), no public brass-relevant weights:**
  - SFC, input-adaptive spectral compression replacing band-split (TASLP; [arXiv 2602.08671](https://arxiv.org/abs/2602.08671)).
  - BS PolarFormer, BS Mamba2, DTTNet (in MSST releases through v1.0.22, 2026-08-27).
  - MSST framework paper ([arXiv 2607.23395](https://arxiv.org/abs/2607.23395)).
  - None change the brass picture.
- **Datasets:** ACMID ([arXiv 2510.07840](https://arxiv.org/abs/2510.07840)) is a web-crawled, auto-cleaned dataset with a 7-stem setup including **"Wind-Brass"**. Its crawling/cleaning code and weights are said to be on GitHub. It is a possible source for future brass fine-tuning (not investigated further).
- **MVSEP services:** MVSEP runs Wind (MelRoFormer / SCNet Large / BS-RoFormer), **Brass** (trumpet, trombone, horn, tuba, flugelhorn, untagged brass) and Woodwind models as a web service ([61](https://mvsep.com/algorithms/61), [98](https://mvsep.com/algorithms/98), [100](https://mvsep.com/algorithms/100)). **The weights are not public**, and the Brass/Woodwind pages show no metrics. Not usable offline.

### 5. Query-based / text-conditioned separation
- **SAM-Audio (Meta, arXiv 2512.18099, HF release 2025-12-12)** ([repo](https://github.com/facebookresearch/sam-audio), [paper](https://arxiv.org/abs/2512.18099)):
  - **Architecture:** diffusion Transformer trained with flow matching on DAC-VAE latents (25 Hz × 128). Sizes: small 500M, base 1B, large 3B, excluding the T5/PE/codec encoders.
  - **Training data:** 10,610 multitrack songs (536 h) with instrument stems, plus about 20k h of music mixed with SFX.
  - **Prompts:** text in lowercase noun-phrase form, visual mask, or time span ("+"/"−" anchors).
  - **Evaluation is subjective/judge-based only:** on MUSDB "Instr(pro)", SAM-Audio OVR 4.45 vs AudioShake 4.28, Demucs 4.26, AudioSep 2.45. Net win rate vs Demucs 17.6%. The paper states this MUSDB benchmark "only include[s] vocals, drums and bass". The in-the-wild instrument benchmark (37 classes) does include trumpet, tuba, horn and saxophone items (paper Fig. 16). However, results are reported only in aggregate, so **there is no brass-specific number**. The paper's "text-based instrument separation significantly lags behind Demucs" sentence describes *prior* text-query systems, not SAM-Audio.
  - **Latency:** about 7.3 s per 10 s of input on one A100 (16-step midpoint ODE + reranking).
  - **Long form:** trained on ≤30 s. The paper recommends multi-diffusion windows (20 s, 5 s overlap) over one-shot or naive chunking.
  - **Format:** 48 kHz ([mlx config](https://huggingface.co/mlx-community/sam-audio-large)). The API takes `(B,1,T)` mono.
  - **Licence:** SAM License for code and weights; gated HF access ([LICENSE](https://github.com/facebookresearch/sam-audio/blob/main/LICENSE)).
  - **Apple Silicon:** reported working. There is a community MPS setup (xformers stub, eva-decord; [issue #73](https://github.com/facebookresearch/sam-audio/issues/73)) and an MLX port in mlx-audio with `separate_long()` chunking ([mlx-audio](https://github.com/Blaizzy/mlx-audio)). The official MPS issue is still open ([#29](https://github.com/facebookresearch/sam-audio/issues/29)).
  - **Brass suitability:** it is the only open model that can be prompted for "trumpet", "french horn", "tuba", "trombone" or "brass section". Risks:
    - (a) Generative: it can hallucinate content, which would become invented notes.
    - (b) Mono and subjective-only evaluation.
    - (c) Nothing shows it can split *same-instrument* voices, e.g. "first cornet". Treat it as an experiment.
- **Banquet** ([arXiv 2406.18747](https://arxiv.org/abs/2406.18747), ISMIR 2024): a single decoder conditioned on a PaSST embedding of a *query audio clip*. On MoisesDB it approaches htdemucs_6s on VDBO and beats it on guitar and piano. Long-tail stems (including brass and reeds) are "all still very weak… no sample performing above 5 dB SNR". The authors blame data scarcity: MoisesDB is pop/rock heavy and "wind" is rare ([arXiv 2307.15913](https://arxiv.org/html/2307.15913)). Weights are CC BY-NC-SA 4.0, 8.7 GB ([Zenodo](https://zenodo.org/records/13694558)). Apple Silicon: unknown; Mac speed not found (the README quotes only an RTX 4090 batch size). Not recommended for brass.
- **AudioSep / FlowSep / CLAPSep / SoloAudio:** all clearly below Demucs on music in SAM-Audio's comparison (OVR ≤ 2.56 on Instr(pro)). FlowSep 2 ([arXiv 2608.22111](https://arxiv.org/pdf/2608.22111)) and Hybrid-Sep ([arXiv 2506.16833](https://arxiv.org/pdf/2506.16833)) are recent language-queried systems. No music/brass benchmarks or public weights were verified for them ("not found").

### 6. Orchestral / classical and brass-specific research
- **SynthSOD** ([arXiv 2409.10995](https://arxiv.org/html/2409.10995v1)):
  - 47 h of synthesized orchestral music (Spitfire BBCSO) with an X-UMX baseline. The brass model (horn, trumpet, trombone, tuba) was trained separately.
  - On the synthetic test set, all brass except horn reach >2 dB SDR (frame-median museval).
  - On real recordings, "none of the models were able to achieve strong separation results even in URMP".
  - The per-instrument tables are images and could not be machine-verified here.
  - Code and pretrained models: [repertorium/SynthSOD-Baseline](https://github.com/repertorium/SynthSOD-Baseline) (AGPL-3.0, last push 2025-10-13).
- **Score-informed separation** ([arXiv 2503.07352](https://arxiv.org/abs/2503.07352), EUSIPCO 2025): score-only masking generalizes synthetic→real better. This is relevant only if brasscribe iterates, i.e. transcribe first, then separate with the score.
- **The Spheres dataset** ([arXiv 2511.21247](https://arxiv.org/abs/2511.21247), CC BY 4.0): about 1 h of real orchestral multitrack including brass, 23 mics, with an X-UMX family-level baseline. A candidate for evaluating orchestral input.
- **Small classical ensembles** ([arXiv 2505.17823](https://arxiv.org/abs/2505.17823)): a large gap between synthetic validation (6.2–6.9 dB) and real recordings.
- **Saxophone (wind analogue):** a Demucs v3 model fine-tuned on FiloSax, MIT ([HF](https://huggingface.co/xavriley/demucs_v3_saxophone_separation)). It reaches 14.22 dB SDR on 10 private jazz-quartet tracks vs 14.03 for LALAL.AI's "Wind" stem ([arXiv 2405.16687](https://arxiv.org/abs/2405.16687)). An instrument-specific model on a narrow genre works well; there is no brass equivalent.
- **Brass-band ground truth:** none found. No multitrack brass-band dataset appeared in any source.

---

## Hierarchical separation (song → 4/6 stems → "other" → brass/strings/…)

**Evidence for:**
- **MSR-2025 winner** ([arXiv 2602.09042](https://arxiv.org/html/2602.09042v1)): BS-Rofo-SW (6 stems), then fine-tuned BS-RoFormers decompose "other" and drums into 8 targets, then restoration. 1st on all metrics.
- **MVSEP "Ensemble All-In"** chains guitar, piano, wind and strings models on filtered sources. MVSEP states "Guitars, piano, drums, bass, etc., yield better results because they use filtered sources from other stems" ([mvsep 47](https://mvsep.com/algorithms/47)). This is the operator's claim, with no ablation published.
- The MVSEP Wind model offers an "extract from Instrumental" variant ([mvsep 61](https://mvsep.com/algorithms/61)), with no published metric.

**Evidence against / mixed:**
- **MVSEP Karaoke** ([mvsep 76](https://mvsep.com/algorithms/76)): extracting lead vocals *after* a vocals-first pass is *worse* for every RoFormer. Direct vs cascaded lead-vocal SDR: 9.45→9.22, 9.61→8.98, 9.67→9.36, 9.85→9.62. It helped only the older MDX-B (7.42→8.28). Errors compound when the first stage is already strong.
- Mega-53 stems don't sum to the mix. Overlapping classes (brass ⊃ trumpet) mean a hierarchy must choose one level per region, or reconcile them.
- Older work: Manilow et al., "Hierarchical Musical Instrument Separation" (ISMIR 2020, [pdf](https://www.jonathanleroux.org/pdf/Manilow2020ISMIR10.pdf)); an ensemble/hierarchical sub-stem study ([arXiv 2410.20773](https://arxiv.org/abs/2410.20773)) found sub-stem results "room for improvement".

**Recommendation:** a two-level stack. Stage 1 SW (or Demucs). Stage 2 Mega-53 on the **original mix** for brass/wind detection and extraction, plus Mega-53 or specialist models on stage-1 "other" as a comparison. Choose per stem by benchmark, not by default.

---

## Does separation improve downstream transcription?

Controlled studies are scarce. What exists:

| Study | Setup | Finding |
|---|---|---|
| YourMT3+ ([arXiv 2407.04822](https://arxiv.org/pdf/2407.04822), Table 2) | Singing transcription on MIR-ST500: Spleeter-separated vocals (SVS) vs full mixture | Base YMT3 (no mixture augmentation): **3.62 → 67.98** onset-F1 with SVS. With cross-stem augmentation, mixture 64–71 vs SVS 70–72, so **+1 to +6 pts**. Separation matters most when the transcriber wasn't trained on mixtures. |
| Jointist ([arXiv 2302.00286](https://arxiv.org/abs/2302.00286)) | Joint transcription + separation training (Slakh) | Joint training improves transcription by >1 pt and separation by about 5 dB SDR. |
| Charlie Parker Omnibook ([arXiv 2405.16687](https://arxiv.org/abs/2405.16687)) | Sax separation (Demucs v3 fine-tuned) → solo-sax transcriber | 96.2 onset-F1 on clean solo sax (FiloSax) vs **75.4 on separated sax from real records**. Separation makes the task feasible but leaves a large gap. No mixture baseline was reported. |
| Drum ADT via stem separation ([arXiv 2509.24853](https://arxiv.org/abs/2509.24853)) | Drum stem separation → ADT | +12%/+10% F vs an 8-class baseline on MDB/ENST, −2% on RBMA. The baseline is a different system, so not controlled. |
| Cocktail-fork ([arXiv 2212.07327](https://arxiv.org/abs/2212.07327)) | Separation before ASR / tagging on soundtracks | Separated input beats the mixture but is "sub-optimal due to artifacts". **Remixing the residual back at about 17.5 dB SNR** helped further. This is a speech result, but a useful trick to test for AMT. |
| TISMIR two-branch AMT ([tismir.300](https://transactions.ismir.net/articles/10.5334/tismir.300)) | Literature claim (citing Tamer et al. 2023b) | "Simply cascading source separation followed by transcription leads to suboptimal results due to error propagation." |
| Beyond SDR ([arXiv 2609.04224](https://arxiv.org/abs/2609.04224)) | Separator effect on rhythm features | Onsets are preserved (tracks SI-SDR). Attacks/envelopes are not, and the SDR ranking inverts. |
| 2025 AMT Challenge ([arXiv 2603.27528](https://arxiv.org/html/2603.27528v1)) | Multi-instrument AMT | No entrant used a separation front end. Winner F1 0.60 vs MT3 0.39. F dropped from about 0.72 (solo) to 0.44 (3 instruments). Polyphony, not separation, is the bottleneck. |

**Implication for brasscribe:** separation will probably help monophonic/bass/melody extractors on pop/rock input, and matters less for mixture-trained multi-instrument AMT (YourMT3+-style). Keep both paths (mixture and stem) as adapter options and pick per task by measurement. Try the "remix residual at +X dB" trick.

---

## Apple Silicon summary

| Path | What | Status |
|---|---|---|
| Demucs (PyTorch) | `uvx demucs` | Claimed in docs, auto MPS ([mac.md](https://github.com/adefossez/demucs/blob/main/docs/mac.md)) |
| demucs-mlx | MLX port, all Demucs v4 models incl. `_ft` and `_6s` | Claimed in docs: 2.7 s vs 6.9 s MPS for a 3:15 track on M4 Max ([repo](https://github.com/ssmall256/demucs-mlx)); MIT, active (2026-09-23) |
| python-audio-separator | Demucs/RoFormer/MDXC on MPS, MDX `.onnx` on CoreML EP | Claimed in docs; PyTorch ≥ 2.13 on Apple Silicon ([README](https://github.com/nomadkaraoke/python-audio-separator)); v0.47.0 on 2026-08-27 |
| mlx-audio-separator | MLX port of the audio-separator inference paths (Roformer, MDXC, MDX, VR, Demucs) | Claimed in docs: 163/163 catalog models passed the release gate on an M4 mini; 1.4–2.5x vs audio-separator ([repo](https://github.com/ssmall256/mlx-audio-separator)); 15 stars, single maintainer |
| MSST (ZFTurbo) | Any MSST model incl. Mega-53 | Selects `mps`; STFT/iSTFT fall back to CPU ([code](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/models/bs_roformer/bs_roformer.py)). Mega-53 on MPS: unknown |
| mlx-audio | SAM-Audio + Mel-RoFormer MLX | Reported working (SAM-Audio via [issue #73](https://github.com/facebookresearch/sam-audio/issues/73) comment); MIT, 7.9k stars, active |
| CoreML | Demucs conversions ([Isolate](https://github.com/neokumar1/Isolate), [CoreML-Models](https://github.com/john-rocky/CoreML-Models)) | Community; not needed for offline batch |

---

## Open questions only benchmarking can settle
1. Does a separated "brass" stem (Mega-53 brass/trumpet/tuba, or SAM-Audio "brass section") **improve or hurt** downstream brass transcription vs the raw mix, on real brass-band and big-band recordings? SDR 3–7 dB implies a lot of bleed.
2. Mega-53 memory and runtime on M5 Pro/48 GB via MSST MPS, and whether mlx-audio-separator can load it.
3. SW vs htdemucs_ft vs SCNet-XL: which stems give the best **bass line, melody and chord** extraction? This is a task metric, not SDR. Include attack/onset fidelity, given the Beyond-SDR result.
4. Stage-2 input: Mega-53 on the original mix vs on stage-1 "other". The Karaoke data suggests cascades can lose 0.2–0.6 dB.
5. SAM-Audio: does it hallucinate notes on brass prompts? Does mono output matter? Can span prompts isolate a soloist (e.g. a cornet solo) well enough for melody extraction?
6. On brass-band input, does separation help at all? Candidates: tuba/bass and percussion extraction, and horn vs trumpet family split via the Mega-53 classes.
7. Test-time tricks (overlap, TTA, ensembling SW + Mega-53 "other"), and whether remixing the residual at +15–20 dB helps AMT.
8. A small in-house evaluation set is needed. There is no brass-band multitrack ground truth. Options: synthesise from brass-band MIDI with good samples, or record stems.

---

## References
- Demucs (maintained fork): https://github.com/adefossez/demucs · mac docs: https://github.com/adefossez/demucs/blob/main/docs/mac.md · HT-Demucs paper: https://arxiv.org/abs/2211.08553
- demucs-mlx: https://github.com/ssmall256/demucs-mlx · mlx-audio-separator: https://github.com/ssmall256/mlx-audio-separator · mlx-audio: https://github.com/Blaizzy/mlx-audio
- python-audio-separator: https://github.com/nomadkaraoke/python-audio-separator · SW weights release: https://github.com/nomadkaraoke/python-audio-separator/releases/tag/model-configs
- ZFTurbo MSST: https://github.com/ZFTurbo/Music-Source-Separation-Training · pretrained table: https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md · Mega-53 release: https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21 · MSST paper: https://arxiv.org/abs/2607.23395
- Mega-53 HF mirror: https://huggingface.co/noblebarkrr/BS-Roformer-MVSep-Mega-53-stems
- MVSEP: quality checker https://mvsep.com/quality_checker · Wind leaderboard https://mvsep.com/quality_checker/leaderboard/wind · algorithms 47, 61, 76, 77, 98, 100, 135: https://mvsep.com/algorithms/{id}
- BS-RoFormer: https://arxiv.org/abs/2309.02612 · lucidrains impl.: https://github.com/lucidrains/BS-RoFormer · patent: https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12542148
- Mel-RoFormer: https://arxiv.org/abs/2310.01809 · Mel-RoFormer vocal melody: https://arxiv.org/abs/2409.04702
- SCNet: https://arxiv.org/abs/2401.13276 · https://github.com/starrytong/SCNet
- SFC: https://arxiv.org/abs/2602.08671 · Beyond SDR: https://arxiv.org/abs/2609.04224
- SAM-Audio: https://arxiv.org/abs/2512.18099 · https://github.com/facebookresearch/sam-audio · MLX weights: https://huggingface.co/mlx-community/sam-audio-large
- Banquet: https://arxiv.org/abs/2406.18747 · https://github.com/kwatcharasupat/query-bandit · weights: https://zenodo.org/records/13694558
- AudioSep: https://github.com/Audio-AGI/AudioSep · FlowSep 2: https://arxiv.org/abs/2608.22111 · Hybrid-Sep: https://arxiv.org/abs/2506.16833
- MoisesDB: https://arxiv.org/abs/2307.15913 · ACMID: https://arxiv.org/abs/2510.07840
- SynthSOD: https://arxiv.org/abs/2409.10995 · Score-informed MSS: https://arxiv.org/abs/2503.07352 · Spheres: https://arxiv.org/abs/2511.21247 · Small classical ensembles: https://arxiv.org/abs/2505.17823 · GuitarDuets: https://arxiv.org/abs/2507.01172
- MSR Challenge 2025 winner: https://arxiv.org/abs/2602.09042
- SDX23 music track: https://arxiv.org/abs/2308.06979
- YourMT3+: https://arxiv.org/abs/2407.04822 · Jointist: https://arxiv.org/abs/2302.00286 · Omnibook: https://arxiv.org/abs/2405.16687 · Sax model: https://huggingface.co/xavriley/demucs_v3_saxophone_separation · Drum ADT: https://arxiv.org/abs/2509.24853 · Cocktail fork: https://arxiv.org/abs/2212.07327 · TISMIR two-branch: https://transactions.ismir.net/articles/10.5334/tismir.300 · AMT Challenge 2025: https://arxiv.org/abs/2603.27528
- Hierarchical: https://www.jonathanleroux.org/pdf/Manilow2020ISMIR10.pdf · https://arxiv.org/abs/2410.20773

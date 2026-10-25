# 02 — Multi-instrument automatic music transcription (mixture → notes + instrument labels)

**Status (2026-09-29):** desk research, acted on. MuScriptor is the engine's multi-instrument transcriber (`ml/adapters/muscriptor`); the benchmarked decision is in [00-summary.md](00-summary.md) §0.

Research date: 2026-09-25. Desk research only; nothing was installed or run. Every number below is quoted from the cited source. Where two sources disagree, both are given.

---

## Executive summary

**PRIMARY: MuScriptor (Kyutai + Mirelo, ISMIR 2026; code v0.3.0, Sep 2026).** A decoder-only transformer (sizes from 103M to 1.4B) trained on 11k hours of *real* multi-instrument recordings with aligned notes, then post-trained with RL. It is the only open-weight model trained at scale on real mixes, and on its authors' held-out real-music set it scores roughly double YourMT3+ on multi-instrument F1 (47.8–48.2 vs 21.9). It is pip-installable PyTorch, supports Python 3.10–3.13, uses MPS automatically according to the README, and exports MusicXML through MuseScore. **Code is MIT; weights are CC BY-NC 4.0 and gated on Hugging Face.** That is fine for personal use. [paper](https://arxiv.org/abs/2607.08168) · [repo](https://github.com/muscriptor/muscriptor)

**BACKUP: YourMT3+ (YPTF.MoE+Multi).** A 45.8M-parameter PyTorch/Lightning model. It is the best published Slakh model (Brass onset F1 74.96, Multi F1 74.84) and the best URMP model (Multi F1 67.98). It came 2nd in the 2025 AMT Challenge, which included trombone. It is small and cheap to run as a second opinion. It is weak on real recordings of "non-main" instruments (below 10% on RWC-Pop for anything other than piano, bass, vocals and drums). The weights license is ambiguous: the GitHub LICENSE says GPL-3.0, the HF Space card says Apache-2.0, and the maintainer said "Apache 2.0" for the checkpoints. [paper](https://arxiv.org/abs/2407.04822) · [HF Space code+ckpts](https://huggingface.co/spaces/mimbres/YourMT3)

**Brass-specific conclusions (these apply to every candidate):**
1. **Vocabulary gap.** MuScriptor and YourMT3+ both use the MT3_FULL(_PLUS) taxonomy. Its only brass classes are Trumpet (GM 56, 59), Trombone (57), Tuba (58), French Horn (60) and Brass Section (61–63). There is no class for cornet, flugelhorn, tenor horn, baritone or euphonium. [vocabulary.py](https://huggingface.co/spaces/mimbres/YourMT3/raw/main/amt/src/config/vocabulary.py) Brass-band parts will get coarse or wrong labels. Treat the model's label as a "brass family" hint and assign parts by pitch range and voice-leading in a later pipeline stage.
2. **Same-timbre voices are not separated.** A MuScriptor maintainer confirmed that "multiple instances of the same 'instrument' … are not distinguished" ([#91](https://github.com/muscriptor/muscriptor/issues/91)). The MT3-style tokenization also cannot represent two notes of the same pitch on the same instrument at the same time. Keeping such notes in MuScriptor's test set drops onset F1 from 60.4 to 51.8 and Multi F1 from 48.2 to 42.0 ([paper §4.2.3](https://arxiv.org/pdf/2607.08168)). So three cornets in close harmony come out as **one polyphonic "Trumpet" stream with unisons merged**, whichever model is used. Voice separation has to be a downstream stage.
3. **No model has per-instrument results on real brass recordings.** Not found. Slakh's "Brass" class pools GM 56–63 on synthetic audio. URMP (which has trumpet, horn, trombone and tuba) is reported only in aggregate. BSED (Beethoven symphonies with horn, trumpet and trombone) is evaluated instrument-agnostically. MV2H is reported only by TUTTI, which has no brass test. Brass-band ground truth is essentially absent. The closest public evaluation resources are **ChoraleBricks** (real, isolated SATB chorales on trumpet, flugelhorn, baritone horn, French horn, trombone and tuba; CC-BY 4.0) and **CocoChorales** (350 h of synthetic brass quartets).
4. **The old baseline is weak and its weights license is unclear.** The released MT3 checkpoint reproduces only 25.8 Full-granularity multi F1 on Slakh, against the 55 reported in the MT3 paper ([MR-MT3 Table 1](https://arxiv.org/pdf/2403.10024)). The license for its checkpoint is undocumented ([open issue #177](https://github.com/magenta/mt3/issues/177)). It is not worth integrating.
5. **Audio-LLMs are not transcribers.** Frontier audio-LLMs "cannot be trusted to … transcribe" pitch ([PitchBench](https://arxiv.org/abs/2605.26176)). On the same tasks, Gemini and Qwen-Omni score 84–100% from MIDI input but 6–65% from audio ([Carone et al.](https://arxiv.org/html/2510.22455)). The MuScriptor ablation also shows a MERT foundation-model input doing worse than a plain mel spectrogram (Multi F1 36.8 vs 39.7).

---

## Comparison table

Metric key (numbers are **not comparable across rows** unless the metric and dataset match):
- **MT3-Multi** = onset + offset + program must all match (mir_eval multi-instrument).
- **Inst-Onset** = onset + pitch + program.
- **Agn-Onset** = instrument-agnostic onset F1.
- **MuS-Multi** = MuScriptor "Multi F1": offset F1 plus a correct instrument (drums onset-only), measured on its internal real-music D_Test of 372 tracks.
- **AMTC** = 2025 AMT Challenge Inst-Onset on FluidSynth-rendered audio.

| Model | Arch / stack | Latest activity | Code lic. | Weights lic. | Brass classes | Headline multi-instr. result | Brass-relevant result | Apple Silicon | Separate env needed? |
|---|---|---|---|---|---|---|---|---|---|
| **MuScriptor** (large 1.4B / medium 307M / small 103M) | Decoder-only transformer, mel input, instrument-conditioning prefix, CFG, GRPO-style RL; PyTorch | Repo last commit 2026-09-04, v0.3.0 | MIT | **CC BY-NC 4.0**, gated on HF | MT3_FULL_PLUS: Trumpet, Trombone, Tuba, French Horn, Brass Section | D_Test MuS-Multi 48.2 (CFG 1) / 47.8 (CFG 2); YourMT3+ 21.9 | PHENICX-Anechoic (includes horn and trumpet) MuS-Multi 25.7 vs YourMT3+ 12.2; no per-brass numbers | Claimed in docs ("runs on Metal (MPS) automatically") | Yes: torch ≥2.3, numpy ≥2, Py 3.10–3.13 |
| **YourMT3+** YPTF.MoE+Multi | Perceiver-TF encoder + MoE, multi-channel T5 decoder; PyTorch Lightning | GitHub 2024-11-29; HF Space 2025-01-31 | GPL-3.0 (GitHub) vs Apache-2.0 (Space card) | "Apache 2.0" per maintainer ([#12](https://github.com/mimbres/YourMT3/issues/12)) | Same MT3_FULL_PLUS | Slakh MT3-Multi 74.84; URMP MT3-Multi 67.98; AMTC 0.5938 (2nd) | Slakh Brass Inst-Onset 74.96 (MT3 colab: 28.67) | Unknown | Yes: pins numpy 1.26.4, transformers 4.45.1 |
| MIROS (MusicFM + YourMT3+ multi-decoder, ≈370M) | SSL conformer encoder, parallel T5 decoders | 2025 challenge entry | not found | not found | presumably MT3 vocab (not stated) | AMTC 0.5998 (1st); Slakh "multi-instrument F-measure 0.83" | Challenge set includes trombone; no per-instrument number | Unknown | n/a (no public release found) |
| **MT3** (T5-small, 93.7M) | T5X / Flax / JAX + TF | Repo 2026-09-15 (maintenance only) | Apache-2.0 | **Not stated** ([#177](https://github.com/magenta/mt3/issues/177) open) | MT3_FULL | Paper: Slakh MT3-Multi 0.55 (Full), URMP 0.50 (Full); released ckpt reproduces Slakh Full 25.8 | Slakh Brass Inst-Onset 43.3 (MT3†, PTF replication); 28.67 (YourMT3 colab run) | Unknown (no Mac reports; CPU issue [#141](https://github.com/magenta/mt3/issues/141)) | Yes: TF + JAX + t5x/flax/seqio from git HEAD |
| MR-MT3 | MT3 + memory retention, token shuffling; PyTorch port | 2024-07-12 | MIT | MIT (HF card) | Slakh MIDI classes | Slakh Inst-Onset (MIDI Class) 62.5 vs MT3 59.5 (from scratch); leakage φ 1.24 vs 1.65 | none | Unknown | Yes: Py 3.10, TF 2.11, protobuf 3.20, transformers 4.18 |
| Perceiver-TF (ByteDance) | Perceiver TF + onset/frame piano rolls; PyTorch | 2023 paper | code not found | not released | Slakh 12 classes incl. single "Brass", "Reed", "Pipe" | Slakh Multi-Onset .798 vs MT3† .743 | Slakh Brass Onset F1 .732 vs MT3† .433 | n/a | n/a |
| Jointist | Instrument recognition + O&F-style transcription + separation; PyTorch | 2023-07-26 | **no license file** | not stated | 39 classes: Trumpet, Trombone, Tuba, Horn, Brass | Slakh Inst-F1 (N&O) 24.8 | none | Unknown | Yes: Py 3.8.10, CUDA 10.2 image |
| Omnizart (music module) | CNN (aspp / attn), note-stream; TF/Keras | v0.6.3, 2026-05-31 | MIT | MIT (bundled) | 11 programs incl. **French Horn (60)** (MusicNet-derived) | no recent multi-instrument benchmark found | none | Unknown | Yes: TensorFlow, madmom |
| timbre-trap | Autoencoder, instrument-agnostic; PyTorch | 2024-05-05 | MIT | — | none (agnostic) | "comparable to SOTA instrument-agnostic" | n/a | Unknown | small |
| TUTTI (audio → ABC score) | Hierarchical patch/char transformer, 88.9M | Repo 2026-08-11; weights not found | no license file | not released | ensemble scores; no brass tests | Quartets MV2H 95.6; unseen sax 84.9–85.3 | none | n/a | Py 3.10 conda |

---

## Candidate details

### MuScriptor — PRIMARY
- **What:** "An open-weight multi-instrument music transcription model that works on real-world music recordings from across a diverse range of musical genres." Authors: Rouard, Krause, Roebel, Simon-Gabriel, Défossez (Kyutai, Mirelo AI, IRCAM). Proc. ISMIR 2026. arXiv v2 dated 2026-08-03. [arXiv 2607.08168](https://arxiv.org/abs/2607.08168)
- **Architecture:** Decoder-only transformer. Input is a 5 s mel spectrogram (16 kHz mono, nFFT 2048, hop 160, 512 mel bins), projected and concatenated with learned embeddings for the instruments present in the track. Output is the MT3 token scheme over 36 MT3_FULL_PLUS instrument groups. Uses classifier-free guidance (α=2) and argmax decoding. Released sizes: small 103M (14 layers, dim 768), medium 307M (24 layers, 1024, the default), large 1.4B (48 layers, 1536). [README](https://github.com/muscriptor/muscriptor)
- **Training data:** 1.45M MIDI files synthesized on the fly with more than 250 soundfonts, plus 170k real recordings (11k hours) aligned to scores by DTW (internal data, not released), plus 300 hand-verified tracks for RL. [paper §3.1](https://arxiv.org/pdf/2607.08168)
- **Benchmarks (all from the paper):**
  - D_Test, 372 real multi-instrument tracks, 1.3B model, with and without RL. Onset / Frame / Offset / Drums / Multi:
    - Synth + Real + RL, CFG 1: 60.4 / 73.3 / 49.0 / 50.2 / 48.2
    - YourMT3+ on the same set: 32.52 / 45.54 / 17.79 / 41.4 / 21.9 (Table 1)
    - Model trained on synthetic data only, CFG 2: Multi F1 16.2. **Real data is what makes it work.**
  - Out-of-domain, MuScriptor vs YourMT3+ (Table 2). Onset / Frame / Offset / Multi:
    - Bach10 (violin, clarinet, sax, bassoon): 43.1 / 85.0 / 36.0 / 34.7 vs 59.8 / 66.0 / 48.0 / 26.4
    - PHENICX-Anechoic (orchestral, including horn and trumpet per the [dataset page](https://www.upf.edu/web/mtg/phenicx-anechoic)): 56.1 / 74.6 / 32.6 / 25.7 vs 56.7 / 58.9 / 18.7 / 12.2
    - RWC-Classical: 67.7 / 70.5 / 36.9 / 36.0 vs **71.7 / 71.3 / 44.3 / 40.5**. YourMT3+ wins here.
    - RWC-Jazz: 59.4 / 62.7 / 33.9 / 31.8 vs 52.9 / 57.2 / 31.1 / 26.4
  - Instrument conditioning at inference (supplying the true instrument list) raises Multi F1 from 38.7 to 40.5 (Table 3). **This is relevant for us: the instrument list is usually known.**
  - Scaling, real-data-only models, Multi F1: 60M 35.2 → 100M 38.2 → 300M 39.7 → 1.3B 40.5 (Table 4).
  - Input representation (Table 5): mel 39.7, CQT 38.2, **MERT 36.8**, Encodec 28.9.
  - **No Slakh, URMP or MusicNet numbers are reported.** A direct comparison on brass datasets is therefore missing.
- **Output:** MIDI with 36 instrument groups. `--format sheets` produces quantized MIDI, MusicXML and per-part PDFs through MuseScore 4, and uses `beat-this` for tempo and downbeats. Quantization "works best if there is a steady tempo". **Velocity is constant** ([#103](https://github.com/muscriptor/muscriptor/issues/103); the model card says no dynamics are produced).
- **Known issues:**
  - Long files degrade. Random note clusters appear, "beyond the first 8 minutes … mostly unrecognizable", attributed to conditioning on prior predictions ([#84](https://github.com/muscriptor/muscriptor/issues/84)). **Mitigation: chunk the audio and pass the instrument list.**
  - Speed. On an RTX 4090, the large model at batch 1 took 1,139 s for a 272 s file (RTF 4.19), and the medium model took ≈92 s for a 140 s file, described as a host-side decode bottleneck ([#102](https://github.com/muscriptor/muscriptor/issues/102)). An open PR proposes speculative decoding ([#95](https://github.com/muscriptor/muscriptor/pull/95)). There are no M-series timings. Expect the large model to run at several times real time on M5 Pro. This is acceptable for offline batch.
  - A community Rust/candle port exists ([#14](https://github.com/muscriptor/muscriptor/issues/14)), an alternative path to Metal.
- **License:** Code MIT. Weights CC BY-NC 4.0, requiring a Hugging Face login and license acceptance ([README](https://github.com/muscriptor/muscriptor), [HF large](https://huggingface.co/MuScriptor/muscriptor-large)).
- **Apple Silicon:** Claimed in docs. No user reports found (a search of issues for "mps" and "mac" turned up nothing relevant).
- **Env:** `requires-python >=3.10`, classifiers up to 3.13, torch ≥2.3, numpy ≥2 ([pyproject](https://github.com/muscriptor/muscriptor/blob/main/pyproject.toml)). This conflicts with YourMT3's numpy 1.26 pin, so the two need separate uv envs.
- **Brass suitability:** Best available on real audio, but brass-band instruments fall outside the vocabulary (see summary). Same-instrument voices are merged. Pass the instrument condition (for example `Trumpet, Trombone, Tuba, Brass Section`) and expect cornets and flugelhorns to surface as Trumpet, and tenor horn, baritone and euphonium as French Horn, Trombone or Brass Section. That mapping is untested.

### YourMT3+ — BACKUP
- **What:** Sungkyun Chang, Emmanouil Benetos, Holger Kirchhoff, Simon Dixon. MLSP 2024. [arXiv 2407.04822](https://arxiv.org/abs/2407.04822)
- **Architecture:** Perceiver-TF hierarchical time-frequency encoder with a mixture of experts (2 of 8 experts active), plus a multi-channel T5 decoder that gives each instrument group its own token stream (so partially annotated datasets can be used). Trained with intra- and cross-dataset stem augmentation and pitch shifting. Uses 2.048 s segments. YPTF.MoE+Multi has 45.8M parameters.
- **Training data:** Slakh, URMP, EGMD, MIR-ST500, ENST, CMedia, MusicNet-EM, GuitarSet, MAESTRO, MAPS.
- **Benchmarks (paper Tables 2 and 14; noPS | PS):**
  - Slakh: Agn-Onset 84.14 | 84.56; MT3-Multi 73.98 | 74.84. MT3 colab 57.69; MT3 paper 62.
  - URMP: Agn-Onset 81.05 | 81.79; MT3-Multi 67.22 | 67.98. MT3 58.71.
  - MusicNet ext.: Strings 66.14; Winds 55.95. On the refined EM labels: Strings 91.32; Winds 83.46.
  - Slakh per class, Inst-Onset (YPTF.MoE+M / MT3 colab / MT3 per PTF authors / Perceiver-TF):
    - **Brass 74.96 / 28.67 / 43.3 / 73.2**
    - Reed 82.22 / 19.41 / 44.0 / 72.5
    - Pipe 74.72 / 40.60 / 28.2 / 66.6
    - Strings 75.44 / 47.02 / 55.1 / 74.4
  - Limitation stated in the paper: on RWC-Pop real recordings, instruments other than piano, bass, vocals and drums score **below 10%**. The paper also says: "except for the piano, all the pitched instruments showed a significant gap in the chroma-level metric, suggesting substantial octave errors" ([paper p.4–8](https://arxiv.org/pdf/2407.04822)).
  - 2025 AMT Challenge: F1 0.5938, 2nd place. By instrument count: 1 instrument 0.7594, 2 instruments 0.4316, 3 instruments 0.3918 ([2603.27528](https://arxiv.org/pdf/2603.27528)).
  - BSED (real Beethoven symphonies, instrument-agnostic onset F1): 42.3. On PHENICX: 57.0 ([BSED Table 5](https://transactions.ismir.net/articles/10.5334/tismir.343)).
- **Code and weights:** Complete code and checkpoints live in the HF Space `mimbres/YourMT3` (`amt/src/...`, `logs/`). The GitHub repo holds only the README and LICENSE. The Space card says `license: apache-2.0` ([API](https://huggingface.co/api/spaces/mimbres/YourMT3)). GitHub's LICENSE is GPL-3.0 ([repo](https://github.com/mimbres/YourMT3)). The maintainer answered "Apache 2.0!" when asked about the checkpoints ([#12](https://github.com/mimbres/YourMT3/issues/12)). **Unresolved; record all three.**
- **Env:** `transformers==4.45.1`, `numpy==1.26.4`, torch installed from a cu113 index URL in the Space requirements ([requirements.txt](https://huggingface.co/spaces/mimbres/YourMT3/raw/main/requirements.txt)). It needs its own env. MPS is unknown, and no issues mention Mac.
- **Speed:** Decode time scales with token count and therefore note density ([#17](https://github.com/mimbres/YourMT3/issues/17)). Dense brass tutti is the worst case. Challenge runtime column: 12.60 (units given as ms, hardware not stated).
- **Brass suitability:** Strongest published per-class brass number, but on synthetic Slakh. It is small enough to run as a cross-check or ensemble voter next to MuScriptor. Same vocabulary and same-timbre limitations.

### MIROS (2025 AMT Challenge winner)
- MusicFM self-supervised conformer encoder, a recurrent adapter conditioned on instrument-group embeddings, and parallel T5 decoders with RoPE and FlashAttention. About 370M parameters. Challenge F1 0.5998 (precision 0.6558, recall 0.5724). Solo 0.7193, 3 instruments 0.4367; precision falls from 0.9067 to 0.4643. Slakh "multi-instrument F-measure of 0.83" (metric definition not given). The paper notes: "Although it underperformed YourMT3+ on Slakh2100, it attained slightly better accuracy on the competition data … suggesting possible Slakh overfitting by YourMT3+." [2603.27528](https://arxiv.org/pdf/2603.27528)
- **Code and weights:** not found. The FlashAttention dependency suggests a CUDA-first design.
- **Challenge caveat:** The test set is 76 short pieces rendered with FluidSynth using FluidR3 GM. Eight instruments are allowed, including **trombone**; the only other winds are flute, bassoon and oboe. Tempo is 60–90 BPM with no ornaments. So this is synthetic evaluation. MT3 scored 0.3932 and Basic Pitch 0.0634.

### MT3 (Google Magenta)
- T5-small (93.7M) on T5X/Flax/JAX. ICLR 2022. [arXiv 2111.03017](https://arxiv.org/abs/2111.03017)
- **Reported results (mixture model):**
  - Onset+offset F1: Slakh 0.57, URMP 0.58, MusicNet 0.33.
  - Multi-instrument F1 at Full granularity: Slakh 0.55, URMP 0.50, MusicNet 0.34 (Tables 2–3).
  - Zero-shot (dataset held out of training), onset+offset+program: URMP 0.17, Slakh 0.02.
  - The paper itself notes that "multiple notes predicted from a monophonic instrument (such as clarinet or French horn) reflects an ensemble containing multiple players", so same-instrument voices are merged by design.
- **Reproducibility:** Using the released checkpoint, MR-MT3 obtained Slakh onset-offset multi F1 of 50.9 (Flat), 48.9 (MIDI Class) and 25.8 (Full), against the reported 48 / 62 / 55 ([MR-MT3 Table 1](https://arxiv.org/pdf/2403.10024)).
- **License:** Code Apache-2.0. The checkpoint at `gs://mt3/checkpoints/mt3/` has **no stated license**. Issue [#177](https://github.com/magenta/mt3/issues/177) (opened 2026-08-01) is unanswered.
- **Env:** `setup.py` installs `flax`, `t5x`, `seqio` and `note-seq` from git HEAD, plus tensorflow and tensorflow-datasets ([setup.py](https://github.com/magenta/mt3/blob/main/setup.py)). Not reproducible and heavy. A PyTorch port exists ([kunato/mt3-pytorch](https://github.com/kunato/mt3-pytorch), no license, last push 2023-06).
- **Verdict:** Reference baseline only.

### MR-MT3
- Adds memory retention (prior-segment tokens), prior-token sampling and token shuffling to reduce "instrument leakage". Introduces two metrics: the leakage ratio φ and instrument-detection F1. Tan, Cheuk, Cho, Liao, Mitsufuji (Sony), 2024. [arXiv 2403.10024](https://arxiv.org/abs/2403.10024)
- **Results:**
  - From scratch on Slakh: Inst-Onset MIDI Class 62.5 vs 59.5, Full 35.3 vs 33.5; φ 1.24 vs 1.65; instrument-detection F1 39.1 vs 34.2 (Table 2).
  - Continued from the MT3 checkpoint: MIDI Class 70.0, φ 1.18 (Table 3).
- Code MIT; weights at [HF gudgud1014/MR-MT3](https://huggingface.co/gudgud1014/MR-MT3) (card license MIT). Env: Python 3.10, TF 2.11, protobuf 3.20, transformers 4.18 ([README](https://github.com/gudgud96/MR-MT3)). Last commit 2024-07-12.
- **Relevance:** The leakage idea matters for us, since hallucinated instruments are the top failure mode in the challenge. MuScriptor's instrument conditioning addresses the same problem more directly.

### Perceiver-TF (ByteDance SAMI)
- Wei-Tsung Lu, Ju-Chiang Wang, Yun-Ning Hung. ICASSP 2023. Frame and onset piano-roll outputs for 12 Slakh classes plus vocals; PyTorch. [arXiv 2306.10785](https://arxiv.org/abs/2306.10785)
- **Slakh onset F1** (Table 2, checked against the PDF): All .798; **Brass .732** (MT3† .433); Reed .725 (.440); Pipe .666 (.282).
- Official code and weights: not found. Its encoder is reimplemented inside YourMT3 (the "YPTF" models).
- Piano-roll outputs can in principle represent overlapping notes. Brass is still a single class.

### Jointist
- Kin Wai Cheuk et al. (ByteDance), ISMIR 2023. An instrument-recognition module conditions a transcription module that outputs per-instrument piano rolls, with an optional separation module. 39 classes, including Trumpet, Trombone, Tuba, Horn and Brass. [arXiv 2302.00286](https://arxiv.org/abs/2302.00286)
- **Slakh:** Flat onset F1 58.4 (MT3 76.0). Instrument-wise note-with-offset F1 24.8. In a listening test (20 participants) it beat MT3 on subjective scores, for example "Inst. Integrity" 2.87 vs 2.66.
- The repo has **no license** ([repo](https://github.com/KinWaiCheuk/Jointist)), last commit 2023-07-26, Python 3.8.10 with a CUDA 10.2 image. Not a candidate. Useful as a design reference for instrument-conditioned transcription.

### Omnizart
- MIT. v0.6.3 released 2026-05-31; Python ≥3.8 and <3.15; TensorFlow, with tf-nightly on 3.14 ([pyproject](https://github.com/Music-and-Culture-Technology-Lab/omnizart/blob/master/pyproject.toml)).
- The music module predicts 11 programs `[0, 6, 40, 41, 42, 43, 60, 68, 70, 71, 73]`. That includes **60 = French Horn**, but no trumpet, trombone or tuba. It is trained on MusicNet among others ([docs](https://music-and-culture-technology-lab.github.io/omnizart-doc/music/api.html)).
- No recent multi-instrument benchmark found. It is legacy-tier for our purposes, although it is still maintained and its horn class makes it a cheap sanity check.

### timbre-trap
- Cwitkowitz et al. (Sony), ICASSP 2024. An instrument-agnostic autoencoder that shares one decoder between transcription and reconstruction; designed for low-resource settings. [arXiv 2309.15717](https://arxiv.org/abs/2309.15717) · [repo](https://github.com/sony/timbre-trap) (MIT, last commit 2024-05-05).
- No instrument labels, so it does not fit this stage. Listed for completeness.

### Other 2025–26 items found
- **Harmonica** (Ou, Martel, Hennessy-Priest, Cho; arXiv 2609.04640, 2026-09-04, submitted to ICASSP 2027). Instrument-agnostic harmonic-convolution models. The nano variant reaches frame F1 0.796 at 1,622× real time and "outperforms Basic Pitch by 14.6 pp". Code and weights not found. [arXiv](https://arxiv.org/abs/2609.04640)
- **Lightweight two-branch MIT via note-level contrastive clustering** (Li and Zhu; TISMIR 9(1), 2026). A timbre-agnostic backbone plus a timbre encoder that clusters notes into a given number of instruments. Conceptually interesting for separating same-family voices. Code, weights and numbers not verified. [TISMIR](https://transactions.ismir.net/articles/10.5334/tismir.300)
- **Music Transcription with (Almost) No Supervision** (Shin, …, Thickstun; arXiv 2605.24193, 2026-05-22). Cycle-consistent training with minimal paired data. The authors claim unlabeled audio of a new instrument improves transcription of that instrument. A possible route to brass-band fine-tuning without annotations. Code not found. [arXiv](https://arxiv.org/abs/2605.24193)
- **BSED / BSD** (Berendes, Saha, Maman, Arifi-Müller, Müller; TISMIR, 2026-07-24). 20 Beethoven-symphony excerpts, each with 4 real recordings and 1 synthetic rendition, covering horn, trumpet and trombone (trombone has only 23 notes). Instrument-agnostic onset F1: Basic Pitch 24.9, YourMT3+ 42.3, Onsets&Frames trained on MusicNet 60.6, O&F trained on BSD 71.1. The weights for these O&F models are not released. Dataset CC-BY-NC-SA 4.0 ([zenodo](https://zenodo.org/records/20344500)). [TISMIR](https://transactions.ismir.net/articles/10.5334/tismir.343) **Takeaway: fine-tuning on real, aligned orchestral data beats general models by a wide margin.**

### End-to-end audio → score (MusicXML / ABC / kern)
- **TUTTI** (arXiv 2609.00640, 2026-09-01). Audio to "interleaved reduced ABC", pretrained on 363,610 NotaGen-generated multi-instrument scores rendered with SFZ. Quartets MV2H 95.6 (previous best 84.9); unseen alto and tenor sax 84.9 and 85.3 (previous 59.9 and 60.3). Limited to segments of 14.8 s or less. The repo ([a-musiclover/TUTTI](https://github.com/a-musiclover/TUTTI), no license file) ships training code and the corpus; **pretrained weights not found**. No brass evaluation. [arXiv](https://arxiv.org/html/2609.00640)
- **SheetSage2Kern** (Cummins et al., arXiv 2608.06165). A frozen MuQ encoder feeding a transformer decoder that outputs **kern (melody plus Harte chords)**. Quartets SER 4.98%; pop lead-sheet SER 20.92%. Code MIT ([repo](https://github.com/Multimodal-Music-Research-Lab/SheetSage2Kern_model)). It targets melody and chords, not full scores. Relevant to other brasscribe stages. [arXiv](https://arxiv.org/html/2608.06165v1)
- **Rubato** (Tamer, Ebert, Yang, Smith; arXiv 2605.24291). Piano only; time-aligned notation in "InterMo". Best OMR-NED (72.30) in the [Dual Evaluation study](https://arxiv.org/html/2608.04511). Weights not found. Out of scope because it is piano only.
- **Audio-LLMs.** No model found that claims usable multi-instrument score output. Evidence against: [PitchBench](https://arxiv.org/abs/2605.26176) and [Carone et al. 2025](https://arxiv.org/html/2510.22455). [MuNo-SP](https://arxiv.org/html/2609.10351v1) is for understanding, not transcription.

---

## Instrument recognition / activity detection (short)

This is useful for building MuScriptor's instrument condition automatically and for flagging leakage.
- **MuScriptor instrument conditioning.** Not a detector: it consumes a track-level instrument list. The web UI can "auto-detect the instruments", but users report drift on long files ([#84](https://github.com/muscriptor/muscriptor/issues/84)). For brass-band input the list is known in advance, so supply it manually.
- **Essentia `mtg_jamendo_instrument`** (Discogs-EffNet embeddings, 16 kHz, TensorFlow). A 40-class clip or patch tagger whose classes include `brass`, `horn`, `trombone`, `trumpet`, `saxophone`, `orchestra` ([metadata JSON](https://essentia.upf.edu/models/classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.json)). Model license CC BY-NC-SA 4.0 ([Essentia models](https://essentia.upf.edu/models.html)). Coarse timing only.
- **PANNs (AudioSet)** sound-event detection, with frame-wise outputs from the decision-level models. AudioSet classes include brass instruments. Code MIT ([audioset_tagging_cnn](https://github.com/qiuqiangkong/audioset_tagging_cnn), [panns_inference](https://github.com/qiuqiangkong/panns_inference)); weights license not verified. Brass frame-level accuracy was not verified.
- **Jointist's instrument-recognition module** (39 classes). Per-class F1 is weak for rare classes ([paper](https://arxiv.org/abs/2302.00286)). Unlicensed.
- **Hierarchical minority-instrument detection** (Sechet et al., DAFx 2025, MedleyDB, Hornbostel–Sachs hierarchy). Reports "more reliable coarse-level instrument detection". Code not found. [arXiv 2506.21167](https://arxiv.org/abs/2506.21167)
- **Assessment:** No model found that gives validated frame-level activity for individual brass-band instruments. The practical approach is a user-supplied instrument list plus post-hoc cleanup of leaked instruments.

---

## Open questions that only benchmarking can settle

1. **Classical and ensemble brass: MuScriptor or YourMT3+?** YourMT3+ wins onset F1 on Bach10 and RWC-Classical, and wins RWC-C on Multi F1 (40.5 vs 36.0). MuScriptor wins frame F1 almost everywhere and PHENICX Multi F1 (25.7 vs 12.2). MuScriptor reports no URMP or Slakh results. **Run both on URMP brass pieces, ChoraleBricks brass mixes (real audio, CC-BY 4.0, SATB, with MusicXML) and CocoChorales brass-ensemble samples.** Score with Inst-Onset, Agn-Onset and offset F1, plus MV2H after quantization.
2. **What labels do brass-band instruments get?** Cornet, flugelhorn, tenor horn, baritone and euphonium have no class. Measure the confusion matrix on ChoraleBricks: its flugelhorn and baritone horn tracks are the closest real proxies.
3. **Close-harmony, same-timbre voice separation.** Once three cornets are merged into one stream, how well can a downstream voice separator recover the parts? Compare note F1 with and without the loss from same-pitch merging. The MuScriptor paper measured 8.6 points of onset F1 lost to overlapping same-pitch notes on general music; brass-band unisons may cost more.
4. **Octave errors on low brass.** YourMT3+ reports large chroma-vs-pitch gaps. Measure octave-error rate on tuba, euphonium and bass trombone lines.
5. **Long-form stability.** MuScriptor degrades beyond about 5–8 minutes ([#84](https://github.com/muscriptor/muscriptor/issues/84)). Test whether chunking plus instrument conditioning fixes this on 10-minute band pieces.
6. **M5 Pro throughput on MPS** for MuScriptor small, medium and large. There is no published Mac data. Is large at batch 1 tolerable (over 4× real time on a 4090 per [#102](https://github.com/muscriptor/muscriptor/issues/102))?
7. **Does the instrument condition help or hurt when the listed classes are only approximate** (for example, telling it "Trumpet" for cornets)?
8. **Fine-tuning feasibility.** BSED shows real orchestral fine-tuning taking O&F from 60.6 to 71.1. Could MuScriptor-small or YourMT3+ be fine-tuned on ChoraleBricks and CocoChorales brass on a 48 GB Mac? The MuScriptor weights license (NC) permits this for personal use; its repo is inference-focused, so training code availability was not verified.

---

## References

- MuScriptor paper: https://arxiv.org/abs/2607.08168 (PDF https://arxiv.org/pdf/2607.08168)
- MuScriptor repo: https://github.com/muscriptor/muscriptor ; pyproject: https://github.com/muscriptor/muscriptor/blob/main/pyproject.toml
- MuScriptor issues: #84 https://github.com/muscriptor/muscriptor/issues/84 · #91 https://github.com/muscriptor/muscriptor/issues/91 · #95 https://github.com/muscriptor/muscriptor/pull/95 · #102 https://github.com/muscriptor/muscriptor/issues/102 · #103 https://github.com/muscriptor/muscriptor/issues/103 · #14 https://github.com/muscriptor/muscriptor/issues/14
- MuScriptor weights: https://huggingface.co/MuScriptor/muscriptor-large · https://huggingface.co/MuScriptor/muscriptor-medium · https://huggingface.co/MuScriptor/muscriptor-small
- YourMT3+ paper: https://arxiv.org/abs/2407.04822 (PDF https://arxiv.org/pdf/2407.04822)
- YourMT3 GitHub: https://github.com/mimbres/YourMT3 ; HF Space (code + ckpts): https://huggingface.co/spaces/mimbres/YourMT3 ; vocabulary: https://huggingface.co/spaces/mimbres/YourMT3/raw/main/amt/src/config/vocabulary.py ; requirements: https://huggingface.co/spaces/mimbres/YourMT3/raw/main/requirements.txt ; license Q: https://github.com/mimbres/YourMT3/issues/12 ; speed Q: https://github.com/mimbres/YourMT3/issues/17
- 2025 AMT Challenge: https://arxiv.org/abs/2603.27528 (PDF https://arxiv.org/pdf/2603.27528)
- MT3 paper: https://arxiv.org/abs/2111.03017 ; repo: https://github.com/magenta/mt3 ; checkpoint license issue: https://github.com/magenta/mt3/issues/177 ; CPU issue: https://github.com/magenta/mt3/issues/141
- MT3 PyTorch port: https://github.com/kunato/mt3-pytorch
- MR-MT3: https://arxiv.org/abs/2403.10024 ; https://github.com/gudgud96/MR-MT3 ; https://huggingface.co/gudgud1014/MR-MT3
- Perceiver-TF: https://arxiv.org/abs/2306.10785
- Jointist: https://arxiv.org/abs/2302.00286 ; https://github.com/KinWaiCheuk/Jointist
- Omnizart: https://github.com/Music-and-Culture-Technology-Lab/omnizart ; https://music-and-culture-technology-lab.github.io/omnizart-doc/music/api.html
- timbre-trap: https://arxiv.org/abs/2309.15717 ; https://github.com/sony/timbre-trap
- Harmonica: https://arxiv.org/abs/2609.04640
- Two-branch contrastive MIT: https://transactions.ismir.net/articles/10.5334/tismir.300 ; https://arxiv.org/abs/2509.12712
- (Almost) No Supervision: https://arxiv.org/abs/2605.24193
- BSED: https://transactions.ismir.net/articles/10.5334/tismir.343 ; https://zenodo.org/records/20344500
- PHENICX-Anechoic: https://www.upf.edu/web/mtg/phenicx-anechoic
- ChoraleBricks: https://transactions.ismir.net/articles/10.5334/tismir.252 ; https://doi.org/10.5281/zenodo.15081741 ; https://github.com/stefan-balke/choralebricks ; newer Zenodo record: https://zenodo.org/records/20849469
- CocoChorales / Chamber Ensemble Generator: https://arxiv.org/abs/2209.14458 ; https://magenta.withgoogle.com/datasets/cocochorales
- TUTTI: https://arxiv.org/html/2609.00640 ; https://github.com/a-musiclover/TUTTI
- SheetSage-A2S / SheetSage2Kern: https://arxiv.org/html/2608.06165v1 ; https://github.com/Multimodal-Music-Research-Lab/SheetSage2Kern_model
- Rubato: https://arxiv.org/abs/2605.24291 ; Dual Evaluation: https://arxiv.org/html/2608.04511
- Audio-LLM evidence: PitchBench https://arxiv.org/abs/2605.26176 ; Carone et al. https://arxiv.org/html/2510.22455 ; MuNo-SP https://arxiv.org/html/2609.10351v1
- Essentia models: https://essentia.upf.edu/models.html ; instrument head metadata: https://essentia.upf.edu/models/classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.json
- PANNs: https://github.com/qiuqiangkong/audioset_tagging_cnn ; https://github.com/qiuqiangkong/panns_inference
- Minority instrument detection: https://arxiv.org/abs/2506.21167

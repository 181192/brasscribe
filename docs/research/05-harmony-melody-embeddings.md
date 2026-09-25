# 05 — Key, chords, melody, symbolic harmony, and audio embeddings for verification

Desk research, 2026-09-25. Follows `_brief.md`. Every claim links to a source. "Not found" means I could not verify it. Repo dates come from `gh api` on 2026-09-25.

---

## Executive summary

The recommended stack has two halves:

- **Audio side:** estimate key, chords and melody from the mix (or from separated stems).
- **Symbolic side:** re-derive harmony and spelling from the transcribed notes, then cross-check the two halves.

For the verification loop, timbre-invariant measures (chroma/CQT DTW, and running the same AMT model on both signals) are the best bet. A soundfont render will never sound like a real band, so timbre-heavy embeddings mostly measure the timbre mismatch.

| Area | PRIMARY (to confirm by benchmark) | BACKUP | Why |
|---|---|---|---|
| Global key (audio) | **S-KEY** (Deezer): MIT code, weights in the repo, MPS claimed | **madmom CNN key** (git master; weights CC BY-NC-SA) | S-KEY matches or beats madmom on 4 datasets, including classical SWD ([arXiv 2501.12907](https://arxiv.org/html/2501.12907)) |
| Local key / modulations | **Symbolic**: AugmentedNet / AnalysisGNN local-key output on the transcription | windowed S-KEY / madmom (DIY) | No maintained audio local-key model found. The ISMIR 2025 work evaluates local key; it does not ship a model ([poster 67](https://ismir2025program.ismir.net/poster_67.html)) |
| Chords (audio, large vocab + inversions) | **consonance-ACE** (conformer, decomposed root/bass/notes): MIT, checkpoint in the repo, reports inversion metrics | **music-x-lab ISMIR2019 Chord-CNN-LSTM**: MIT, weights in the repo, still near the top of MIREX 2025 | See the chord section below |
| Functional harmony / Roman numerals (symbolic) | **AnalysisGNN / RNHybrid** (MIT repo, 2025–26, trained on Dilemmadata-scale corpora) | **AugmentedNet** (MIT, TF 2.5, pretrained .hdf5) | Run on the transcribed MusicXML |
| Pitch spelling | **partitura `ps13s1`** (Apache-2.0) in concert pitch | **PKSpell** (MIT, 2021) | Deterministic, fast, and already sits in the symbolic toolkit |
| Melody f0 (audio) | **Deep Salience `melody2`** (MIT, weights in the repo, trained on MedleyDB including instrumental melodies) | **MSNet "melody" model** (MIT) | Most 2024–26 models are singing-voice-only (MIR-1K etc.) |
| Verification: localizing bad regions | **Chroma/CENS or DLNCO + MrMsDTW (synctoolbox)**, plus the **same AMT model run on source and render**, compared frame by frame | **MuQ early layers** (frame-level, CC-BY-NC weights) and/or **CLEWS** segment embeddings (MIT weights) as a coarse second opinion | CLEWS gave the best human correlation (ρ=0.971) for playback similarity, but that study is piano-only and CLEWS is at least partly transposition-invariant ([arXiv 2608.04511](https://arxiv.org/html/2608.04511)) |

**Biggest risks**
1. **Domain.** Every audio ACE and key model here is trained on pop/rock (Isophonics, Billboard, RWC, USPop) or catalogue audio. Brass-band and orchestral harmony, with dense voicings and chromatic inner parts, is out of domain. No per-instrument or brass results exist for any of these tasks.
2. **Melody definition.** "Predominant melody" is ill-defined in orchestral and brass textures. The average ORCHSET overall accuracy across methods is about 0.27 ([ISMIR 2016](https://archives.ismir.net/ismir2016/paper/000256.pdf)). No dedicated audio countermelody model was found.
3. **Weight licences.** MERT, MuQ, OMAR-RQ and the madmom models are all non-commercial. That is fine for personal use, but it should be recorded.
4. **Rotting installs.** madmom's PyPI release (0.16.1, 2018) does not work on Python ≥3.10. Sheet Sage needs Linux/amd64 plus CUDA. The Jukebox repo is archived.

---

## Comparison tables

### Key detection

| Model | Arch | Updated | Code lic | Weights lic | Scope | Apple Silicon |
|---|---|---|---|---|---|---|
| S-KEY ([repo](https://github.com/deezer/skey)) | Self-supervised ChromaNet (STONE extension) | last push 2025-06-09 | MIT | Ships in the repo (`skey/models/skey.pt`), so MIT by default. The arXiv *paper* is CC BY-NC-SA ([arXiv](https://arxiv.org/abs/2501.12907)): discrepancy noted | global, 24 keys | "claimed in docs" (`--device mps`) ([README](https://github.com/deezer/skey)) |
| madmom `CNNKeyRecognitionProcessor` ([repo](https://github.com/CPJKU/madmom)) | CNN (Korzeniowski & Widmer) | master: last commit 2024-08-25; PyPI 0.16.1 from 2018-11-14 | BSD-style | **CC BY-NC-SA 4.0** ([LICENSE](https://github.com/CPJKU/madmom/blob/main/LICENSE)) | global | unknown. The PyPI build is broken on Python ≥3.10 (issues [#527](https://github.com/CPJKU/madmom/issues/527)/[#535](https://github.com/CPJKU/madmom/issues/535) still open); master has NumPy/Python fixes ([commit #540](https://github.com/CPJKU/madmom/commits)) |
| Essentia `KeyExtractor` ([docs](https://essentia.upf.edu/reference/std_KeyExtractor.html)) | HPCP + key-profile correlation; profiles: diatonic, krumhansl, temperley, weichai, tonictriad, temperley2005, thpcp, shaath, gomez, noland, faraldo, pentatonic, edmm, edma, **bgate (default)**, braw | active (push 2026-09-21) | AGPL-3.0 | n/a (no NN) | global, or frame-wise via Key on HPCP | arm64 wheels on PyPI (latest dev build is cp314 only) ([PyPI](https://pypi.org/project/essentia/)) |
| KeyMyna ([arXiv 2604.10021](https://arxiv.org/html/2604.10021)) | Myna masked-contrastive ViT + MLP | paper 2026-04; repo [echo-cipher/keymyna](https://github.com/echo-cipher/keymyna) last push 2025-02 (may predate the paper) | **no licence** on the repo | not stated | global | unknown |
| partitura `estimate_key` ([docs](https://partitura.readthedocs.io/en/latest/modules/partitura.musicanalysis.html)) | Krumhansl–Schmuckler on symbolic notes | active | Apache-2.0 | n/a | global (symbolic) | pure Python |

Key benchmarks as reported (not comparable across rows unless the source is the same):

| Source | Dataset | Metric | Numbers |
|---|---|---|---|
| S-KEY paper, Table II ([arXiv](https://arxiv.org/html/2501.12907)) | FMAKv2 / GTZAN / GiantSteps / SWD (Schubert Winterreise, classical) | MIREX score % | S-KEY(1M): 73.2 / 74.4 / 72.1 / **90.4**; madmom: 73.1 / 67.9 / 71.0 / 87.7 |
| KeyMyna Table 1 ([arXiv](https://arxiv.org/html/2604.10021)) | GiantSteps / Billboard | weighted acc % | KeyMyna 75.91 / 84.35; MERT-95M 72.95 / 81.30; AllConv 74.60 / 85.10 |
| MuQ paper ([arXiv](https://arxiv.org/html/2501.01108)) | GiantSteps (MARBLE probe) | refined acc | MuQ 63.5; MERT 65.6 (quoted from the MERT paper); MusicFM 63.9 |
| PupuM2D ([arXiv 2606.25713](https://arxiv.org/html/2606.25713)) | GiantSteps (MARBLEv2 probe) | refined acc | PupuM2D-L 66.1 |

GiantSteps is EDM, so it says little about brass. SWD (classical art song) is the closest domain on the list, and S-KEY is best there.

### Chord recognition (audio)

| Model | Arch | Updated | Code lic | Weights | Vocab / inversions | Apple Silicon |
|---|---|---|---|---|---|---|
| **consonance-ACE** ([repo](https://github.com/andreamust/consonance-ACE), [arXiv 2509.01588](https://arxiv.org/html/2509.01588)) | Conformer with decomposed outputs (root/bass/pitch classes) + consonance-based label smoothing | push 2026-07-02 | MIT | `ACE/checkpoints/conformer_decomposed_smooth.ckpt` in the repo, so MIT by default (no separate statement) | large vocab; reports **inverted-chord** metrics; optional Beat This! beat-sync | unknown (PyTorch) |
| **ISMIR2019 Chord-CNN-LSTM** ([repo](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition)) | CNN-LSTM with chord structure decomposition + HMM decoding | push 2024-04-09 | MIT | in the repo (MIT); reweighted variants on Google Drive | large vocab with bass/inversions (editable `*_chord_list.txt`) | unknown (PyTorch + librosa) |
| BTC ([repo](https://github.com/jayg996/BTC-ISMIR19)) | Bi-directional Transformer | push 2020-05-23 | MIT | `btc_model.pt`, `btc_model_large_voca.pt` in the repo | 25 or 170 classes (no inversions in 170) | unknown |
| ChordMini student (2E1D / BTC) ([arXiv 2602.19778](https://arxiv.org/html/2602.19778), [ChordMiniApp](https://github.com/ptnghia-j/ChordMiniApp)) | BTC teacher → pseudo-labels on 1000+ h → student | push 2026-07-30 | MIT | in the app repo `python_backend/models/ChordMini` (Git LFS); weights licence not stated separately | 170 | unknown. The README recommends Python 3.10 |
| ChordFormer ([arXiv 2502.11840](https://arxiv.org/html/2502.11840)) | Conformer | paper 2025-02 | **no code released** | none | large vocab | n/a |
| ACR seq2seq ([arXiv 2604.24386](https://arxiv.org/html/2604.24386), [repo](https://github.com/KimLeekyung/ACR_seq2seq)) | Transformer encoder-decoder, segment-level events | push 2026-05-31 | **no licence** on the repo | not stated | 168 | unknown |
| BMACE ([arXiv 2601.02101](https://arxiv.org/html/2601.02101)) | Mamba | 2026-01 | not found | not found | 170 | unknown |
| Chordino / NNLS-Chroma ([c4dm/nnls-chroma](https://github.com/c4dm/nnls-chroma); Python wrapper [chord-extractor](https://github.com/ohollo/chord-extractor)) | NNLS chroma + HMM (Vamp) | nnls 2020; chord-extractor 2025-08 | GPL-2.0 | n/a | small dictionary, includes bass/inversions | wrapper is pure-Python; arm64 Vamp binary availability unknown |
| autochord ([repo](https://github.com/cjbayron/autochord)) | Bi-LSTM-CRF on NNLS chroma | 2023-04 | Apache-2.0 | bundled | 25 | unknown (TF) |

**MIREX 2025 ACE**: the only common test set across these systems ([results repo](https://github.com/ismir-mirex/ace-results/tree/main/2025), [wiki](https://music-ir.org/mirex/wiki/2025:Audio_Chord_Estimation_Results)). Scores are weighted chord symbol recall (WCSR) in %:

| System | BB2013 Root | BB2013 MajMin | BB2013 MajMinBass | BB2013 Sevenths | RWC Root | RWC MajMin | RWC MajMinBass | RWC Sevenths |
|---|---|---|---|---|---|---|---|---|
| MD1 (Doai, "degree-based, enharmonic distinction") | **81.35** | **79.15** | **77.91** | **66.40** | 83.98 | 81.18 | 79.42 | 66.53 |
| YK1 (Wu & Yoshida, semi-supervised generative) | 81.01 | 78.10 | 75.41 | 64.53 | **88.76** | **87.27** | **81.14** | **76.88** |
| ISMIR2019 baseline (music-x-lab) | 78.61 | 76.39 | 74.72 | 64.15 | — | — | — | — |
| wu-single (Ding & Weiß) | 75.77 | 73.14 | 71.74 | 55.41 | 82.48 | 81.35 | 78.48 | 62.86 |
| Chordino baseline | 71.06 | 67.18 | 65.09 | 48.88 | 78.97 | 77.78 | 74.13 | 63.15 |
| BMACE | 55.72 | 8.88 | 8.70 | 2.52 | 56.48 | 11.97 | 11.78 | 2.41 |

Comparability flags:
- BMACE's own paper reports MajMin of about 0.77 on uspop2002 ([arXiv](https://arxiv.org/html/2601.02101)). The 2–12% here points to a label-format failure, not to model quality.
- YK1's RWC lead may reflect overlap with its training data. That is unknown and not asserted.
- No code was found for MD1 or YK1.
- The 2019 music-x-lab model sits within about 2–3 points of the 2025 winner on Billboard2013.

**Per-paper numbers are not comparable.** BTC's reported WCSR ranges from about 54 (Root; ChordFormer's own "BTC+CNN" re-implementation, [arXiv](https://arxiv.org/html/2502.11840)) to about 82 (Root; [2602.19778](https://arxiv.org/html/2602.19778), [2601.02101](https://arxiv.org/html/2601.02101)), depending on split, vocabulary and re-implementation. Selected self-reported numbers:
- ChordFormer, Humphrey–Bello 1217 songs, 5-fold: Root 84.69, MajMin 84.09, Sevenths 72.28, Tetrads 65.32, MIREX 83.62; class-wise acc up to 0.447.
- consonance-ACE, train Isophonics+Billboard, test RWC+USPop: Root 84.0, MajMin 77.8, Tetrads 60.8, MIREX 79.8. Inverted: MajMin-inv 75.6 vs BTC 72.4.
- ChordMini BTC student: MIREX 80.16, Tetrads 67.00 vs supervised BTC 77.79 / 63.44.
- ACR seq2seq, 471 songs: MIREX 85.7 vs BTC 80.8.

### Symbolic harmony, spelling and toolkits

| Tool | Task | Updated | Licence | Notes |
|---|---|---|---|---|
| AugmentedNet ([repo](https://github.com/napulen/AugmentedNet), [ISMIR 2021](https://archives.ismir.net/ismir2021/paper/000050.pdf)) | Roman numerals, local key, tonicization, quality, inversion | 2024-02 | MIT (weights `.hdf5` in the repo) | TF 2.5. MusicXML in, annotated MusicXML + CSV out. Reported: key 83.7, degree 66.0, quality 77.6, inversion 77.2 |
| AnalysisGNN ([repo](https://github.com/manoskary/analysisgnn), [arXiv 2509.06654](https://arxiv.org/html/2509.06654)) | 20+ note-level tasks: RN, cadence, phrase, non-chord tones, harmonic rhythm | 2026-04-30 | MIT (repo) | RN CSR 0.530 (RNBert 0.574, ChordGNN 0.518) on the AugmentedNet test set |
| RNHybrid ([arXiv 2607.13587](https://arxiv.org/html/2607.13587)) | Interactive RN analysis (MusicBERT + GNN; partial-label completion) | 2026-07 | code in the analysisgnn repo (MIT) | RN acc 0.576 (AugNet) / 0.578 (DLC) on Dilemmadata |
| RNBert ([repo](https://github.com/malcolmsailor/rnbert)) | RN via fine-tuned MusicBERT | ISMIR 2024 | not stated | fairseq, two Python envs; hard to deploy |
| BACHI ([arXiv 2510.06528](https://arxiv.org/abs/2510.06528)) | Symbolic chord recognition (boundary → root → quality → bass) | ICASSP 2026 | code not found | Claims SOTA on classical + pop |
| Dilemmadata ([arXiv 2606.31595](https://arxiv.org/abs/2606.31595), [Zenodo](https://zenodo.org/records/19661299)) | Dataset: 1,621 pieces, 2.8M note-wise RN labels | 2026-06 | see Zenodo | Largest RN corpus; training data for any future fine-tune |
| partitura ([repo](https://github.com/CPJKU/partitura)) | ps13s1 spelling, Krumhansl key, VoSA voice separation, tonal tension, MusicXML/MEI/MIDI I/O | push 2026-08-25; PyPI 1.9.0 | Apache-2.0 | pure Python |
| music21 ([repo](https://github.com/cuthbertLab/music21)) | `roman.romanNumeralFromChord`, `chordify`, `analyze('key')`, MusicXML writing, transposition | push 2026-09-24; PyPI 10.5.0 | BSD-3 | Rule-based RN per chord; no learned end-to-end analysis ([docs](https://www.music21.org/music21docs/moduleReference/moduleRoman.html)) |
| PKSpell ([repo](https://github.com/fosfrancesco/pkspell), [arXiv 2107.14009](https://arxiv.org/pdf/2107.14009)) | Pitch spelling + key signature from MIDI (RNN) | 2022-07 | MIT | SOTA on the MuseData benchmark at release |
| Bouquillard & Jacquemard 2026 ([arXiv 2606.20198](https://arxiv.org/abs/2606.20198)) | Two-stage modal→tonal pitch spelling (jazz, classical, monophonic) | 2026-06 | code not found | Useful for jazz-inflected pop arrangements |

### Melody

| Model | Target | Updated | Code lic | Weights | Training domain | Apple Silicon |
|---|---|---|---|---|---|---|
| **Deep Salience** ([repo](https://github.com/rabitt/ismir2017-deepsalience)) | melody1/2/3, bass, multif0, vocal, pitch | 2019-11 | MIT | `.h5` in the repo (melody1–3, bass, multif0, vocal, pitch) | MedleyDB (instrumental + vocal melody) | unknown (old Keras) |
| **MSNet** (melodic SegNet) ([repo](https://github.com/bill317996/Melody-extraction-with-melodic-segnet), [arXiv 1810.12947](https://arxiv.org/pdf/1810.12947)) | `-t vocal` or `-t melody` | 2020-02 | MIT | in the repo | vocal: MIR-1K etc.; melody: MedleyDB | unknown (PyTorch 0.4.1-era) |
| FTANet ([repo](https://github.com/yushuai/FTANet-melodic)) | singing melody | 2022-09 | **no licence** | in the repo | vocal-only | unknown (Keras 2 + a PyTorch port) |
| SpectMamba ([arXiv 2505.08681](https://arxiv.org/html/2505.08681), [repo](https://github.com/Tinkle01/SpectMamba)) | singing melody, note-then-f0 decoder | 2025-09 | **no licence** | not stated | vocal | unknown (Mamba kernels are CUDA-oriented) |
| MELODIA ([page](https://www.justinsalamon.com/melody-extraction.html)); also `PredominantPitchMelodia` in Essentia | salience + contour heuristics | v1.0 (2012-era) | Vamp binary: non-commercial; Essentia: AGPL | n/a | genre-agnostic heuristics | Essentia arm64 wheels exist |
| Sheet Sage ([repo](https://github.com/chrisdonahue/sheetsage), [arXiv 2212.01884](https://arxiv.org/pdf/2212.01884)) | note-level melody + chords → lead sheet | 2025-05 | MIT code; models **CC BY-NC-SA 3.0** | Docker | HookTheory (pop) | **effectively unsupported**: Linux/amd64 Docker; the Jukebox path needs CUDA and ≥12 GB VRAM |

Benchmarks: SpectMamba OA on ADC2004 / MIREX05 / MedleyDB is 80.67 / 84.64 / 72.62 ([arXiv](https://arxiv.org/html/2505.08681)). ORCHSET (symphonic, with per-excerpt labels for whether the melody is in strings, brass or woodwinds, [MTG](https://www.upf.edu/web/mtg/orchset)): mean OA across methods about 0.27; the best ML method about 0.53 ([ISMIR 2016](https://archives.ismir.net/ismir2016/paper/000256.pdf), [Zenodo thesis](https://zenodo.org/records/1120334)). No 2025–26 model reports ORCHSET: not found.

### Embeddings for the verification loop

| Model | Type | Rate | Code lic | Weights lic | Frame-level? | Notes |
|---|---|---|---|---|---|---|
| MuQ ([repo](https://github.com/tencent-ailab/MuQ), [HF](https://huggingface.co/OpenMuQ/MuQ-large-msd-iter)) | SSL, Mel-RVQ targets, ~300M | 24 kHz in | MIT | **CC-BY-NC 4.0** | yes | fp32 recommended (NaN risk); the MSD release may underperform the paper |
| MuQ-MuLan ([HF](https://huggingface.co/OpenMuQ/MuQ-MuLan-large)) | music–text contrastive, ~700M | 24 kHz | MIT | CC-BY-NC 4.0 | clip | text-query tagging, not verification |
| MERT-v1-330M ([HF](https://huggingface.co/m-a-p/MERT-v1-330M)) | SSL MLM with RVQ + CQT teachers | 24 kHz, 75 Hz frames, 25 layers × 1024 | Apache-2.0 ([repo](https://github.com/yizhilll/MERT)) | **CC-BY-NC-4.0** | yes | 5 s context; `trust_remote_code` |
| MusicFM ([repo](https://github.com/minzwon/musicfm)) | BEST-RQ SSL, 330M | 24 kHz, 25 Hz | MIT | **Apache-2.0** (repo README) | yes | the most permissive large SSL model |
| OMAR-RQ ([repo](https://github.com/MTG/omar-rq)) | multi-feature masked token prediction | 16/24 kHz; 15.6–25 Hz | AGPL-3.0 | CC BY-NC-SA 4.0 | yes | multifeature-25hz-fsq: pitch .940, chord .749 (its own probes) |
| PupuM2D ([arXiv 2606.25713](https://arxiv.org/html/2606.25713)) | 2D-patch M2D SSL, 5M–632M | 24 kHz, 25 Hz | project site (yichenggu.com/PupuM2D) | not found | yes | MARBLEv2 key 66.1, beat F1 91.0 (self-reported) |
| LAION-CLAP ([repo](https://github.com/LAION-AI/CLAP)) | audio–text contrastive (HTSAT) | 48 kHz | CC0-1.0 | not stated separately (HF [lukewys/laion_clap](https://huggingface.co/lukewys/laion_clap)) | clip | music checkpoints exist; timbre/semantic, not pitch-precise |
| CLEWS ([repo](https://github.com/sony/clews), [arXiv 2502.16936](https://arxiv.org/html/2502.16936v3)) | version-matching embeddings on CQT | 20 s segments, 5 s hop | MIT | **MIT** ([Zenodo](https://zenodo.org/records/15045900), 8.7 GB) | segment | trained with ±12-semitone pitch-roll augmentation, so it is likely blind to transposition or key errors |
| CLaMP 3 ([repo](https://github.com/sanderwood/clamp3)) | cross-modal (audio / score / text) | — | MIT | not checked | segment | ρ=0.884 in the Dual-Eval study |
| EnCodec ([repo](https://github.com/facebookresearch/encodec)) / DAC ([repo](https://github.com/descriptinc/descript-audio-codec)) | codec latents | 24/48 kHz; DAC 16/24/44.1 kHz | MIT / MIT | EnCodec: **not confirmed** (README states only the code licence); DAC: MIT | yes | acoustic reconstruction latents, dominated by timbre, so poor for "right notes?" checks |
| Jukebox / JukeMIR ([openai/jukebox](https://github.com/openai/jukebox) **archived**; [p-lambda/jukemir](https://github.com/p-lambda/jukemir)) | 5B LM features | — | non-standard / MIT | non-standard | yes | impractical on the M5 (CUDA-era, huge) |

---

## Per-candidate details

### S-KEY (key): PRIMARY
- **Architecture:** extends STONE (ISMIR 2024, [deezer/stone](https://github.com/deezer/stone)) with a chroma-based pseudo-label pretext task so relative major and minor keys can be told apart. Self-supervised on 60k and 1M Deezer tracks ([arXiv](https://arxiv.org/html/2501.12907)). ICASSP 2025.
- **Licence:** code MIT ([repo](https://github.com/deezer/skey)); weights `skey.pt` ship inside the MIT repo. The paper page says CC BY-NC-SA, which is the paper licence. Personal use is fine either way.
- **Benchmarks:** see the key table. Best on SWD (classical), 90.4.
- **Apple Silicon:** MPS "claimed in docs". Input: anything torchaudio can read.
- **Weaknesses:** one global key per file, 24-key taxonomy. The authors note it is inadequate for blues-type harmony. Local key and modulation output: not found.
- **Brass suitability:** untested. Brass bands modulate often (marches: trio in the subdominant; hymn arrangements), so global key alone is not enough. Use it for the piece's home key and derive local keys symbolically.

### madmom CNN key: BACKUP
- **Model:** the Korzeniowski & Widmer CNN, and the supervised SOTA S-KEY compares against.
- **Licences:** code BSD-style; **models CC BY-NC-SA 4.0** ([LICENSE](https://github.com/CPJKU/madmom/blob/main/LICENSE)).
- **Maintenance:** PyPI 0.16.1 (2018) fails on Python ≥3.10 ([#535](https://github.com/CPJKU/madmom/issues/535) `collections.MutableSequence`); install from git master (2024-08 fixes).
- **Apple Silicon:** unknown. Cython build, CPU only.

### Essentia key profiles
- **Method:** classic HPCP + profile correlation. The profile set is listed in the table; the default is `bgate` ([docs](https://essentia.upf.edu/reference/std_KeyExtractor.html)). The docs do not say which profile suits which genre.
- **Role:** a cheap third opinion, and frame-wise key-strength curves for detecting modulations. AGPL-3.0 is fine for a local personal app.

### consonance-ACE (chords): PRIMARY
- **Paper and architecture:** "From Discord to Harmony" (Poltronieri, Serra, Rocamora, 2025-09, [arXiv](https://arxiv.org/html/2509.01588)). A conformer with a decomposed output (root, bass, chord notes), trained with consonance-aware soft labels.
- **Data:** trained on Isophonics + Billboard; tested on RWC-Pop + USPop.
- **Why it's primary:**
  - It reports **inversion accuracy** explicitly (MajMin-inv 75.6 vs BTC 72.4). Inversions matter for bass-line writing in brass-band arrangement.
  - Its decomposed output maps directly onto voicing (root / bass / note set) rather than onto a fixed 170-class list, so unusual brass voicings degrade gracefully.
  - MIT, checkpoint in the repo, inference CLI, optional beat-synchronous smoothing via Beat This! ([README](https://github.com/andreamust/consonance-ACE)).
- **Weaknesses:** it did not enter MIREX 2025. It is a pop-trained research repo with 36 stars. Apple Silicon: unknown.

### music-x-lab ISMIR2019 Chord-CNN-LSTM: BACKUP
- **Why:** it ran as a baseline at MIREX 2025 and scored Billboard2013 MajMinBass 74.72 / SeventhsBass about 62, within about 3 points of the best 2025 entry ([MIREX results](https://github.com/ismir-mirex/ace-results/tree/main/2025)). MIT, weights in the repo, editable chord dictionary, HMM decoding ([repo](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition)).
- **Adoption:** used as one of the chord backends in ChordMiniApp ([repo](https://github.com/ptnghia-j/ChordMiniApp)).

### Other chord notes
- **BTC** is the de-facto baseline and teacher, with MIT code and weights. It has no bass or inversion output in the 170-class vocabulary.
- **ChordFormer** has the best self-reported large-vocabulary numbers, but **no code or weights**.
- **MD1** (MIREX 2025 winner on Billboard) does "enharmonic distinction", which is relevant to spelling, but no code was found.
- **Synthetic training audio works for ACE** ([arXiv 2508.05878](https://arxiv.org/abs/2508.05878)). This is a route to fine-tuning on rendered brass-band audio generated from symbolic arrangements with known chords. It needs benchmarking.
- **ISMIR 2026** (Abu Dhabi, 8–12 Nov 2026, [CFP](https://ismir2026.ismir.net/authors/call-for-papers)): accepted-paper list not public as of today, so not found.

### Symbolic functional harmony: cross-check on the transcription
- **Pipeline option:** transcription → MusicXML (concert pitch) → AnalysisGNN / AugmentedNet → Roman numerals + local key. Then compare the implied chord roots and bass against audio ACE per beat. Disagreement flags either a transcription error or an ACE error, which is useful signal for the verification loop.
- **AnalysisGNN / RNHybrid** (MIT, 2025–26) are the most current and actively maintained, and are trained on a corpus of about 1.7k pieces. RNHybrid adds partial-label completion, so user-fixed chords can constrain the rest.
- **AugmentedNet** is simpler to deploy (a single `.hdf5`, CLI), but it is 2021-vintage TF 2.5.
- **music21** is the glue layer: chordify, `romanNumeralFromChord`, key analysis and MusicXML output (BSD-3).
- **Classical-harmony bias:** all of these are trained on classical and chorale corpora. Brass-band hymn arrangements fit well; pop-derived material fits less well.

### Pitch spelling
- **When:** run in **concert pitch before** transposing to B♭/E♭ parts. Otherwise transposition compounds spelling errors.
- **partitura `ps13s1`** ([docs](https://partitura.readthedocs.io/en/latest/modules/partitura.musicanalysis.html)) implements Meredith's ps13; Apache-2.0, pure Python.
- **PKSpell** (MIT) adds key-signature estimation. Beyond those two, music21 can respell given a key.
- **Bouquillard & Jacquemard 2026** is a newer option aimed at jazz and lead-sheet material; no code was found.

### Melody: Deep Salience `melody2` (PRIMARY) / MSNet `melody` (BACKUP)
- **Selection rule:** use models trained on *general* melody (MedleyDB, where the melody is often an instrument), not singing-only models.
  - Deep Salience ships melody1/2/3 and bass weights under MIT ([repo](https://github.com/rabitt/ismir2017-deepsalience)).
  - MSNet has an explicit `melody` model type ([README](https://github.com/bill317996/Melody-extraction-with-melodic-segnet)).
  - FTANet, SpectMamba and most 2024–26 papers (SpectMamba, DUDA, HKDSME) are **singing-voice-only**.
- **Old frameworks:** both picks are 2019–2020 Keras / PyTorch code. Expect a port and a re-save of the weights. Apple Silicon: unknown for both. CPU inference of small CNNs is fine.
- **Practical alternative:** separate stems first (see the separation research), then run a monophonic f0 tracker per stem. Melody becomes "which stem carries the tune", a selection problem that the symbolic side can answer. This is often more robust for instrumental music than predominant-f0 on the mix.
- **Note level:** Sheet Sage gives melody notes plus chords, but it is Linux/CUDA only and non-commercial. Use it only as a reference idea.

### Melody vs countermelody
- **Audio:** no dedicated audio countermelody model found. MIREX-style "predominant melody" assumes one line per frame. ORCHSET shows how ambiguous this gets in symphonic textures ([MTG](https://www.upf.edu/web/mtg/orchset)).
- **Symbolic (recommended):** after multi-voice transcription, apply melody-line identification ([arXiv 1906.10547](https://arxiv.org/pdf/1906.10547); [ISMIR 2022 paper 91](https://archives.ismir.net/ismir2022/paper/000091.pdf)) plus heuristics: register, rhythmic independence, salience from the audio melody curve, and contrary motion to the melody. Tag the top-ranked line as melody and the next independent line as countermelody.
- **Voice separation:** partitura's VoSA gives monophonic voice streams to rank.
- This is a design proposal; benchmark data for brass is nonexistent.

### Verification loop: render → compare → localize

**Constraint first.**
- The render (soundfont or sample library) will never match the source's timbre, room or mix. Brass-band parts are also transposing instruments.
- So **render the transcription in concert pitch**, verify the *transcription* rather than the brass-band arrangement, and pick **timbre-invariant, pitch-sensitive** measures.
- Timbre-dominated spaces (EnCodec/DAC latents, CLAP, late MERT/MuQ layers) will mostly measure the timbre gap.

Candidate measures, in order of expected usefulness:

1. **Chroma/CENS or DLNCO + MrMsDTW (synctoolbox)** ([repo](https://github.com/meinardmueller/synctoolbox); PyPI 1.4.2, 2026-05; licence field NOASSERTION, README says MIT for code).
   - Align render to source.
   - Use the **local path cost per frame** as an "explained-poorly" curve.
   - Peaks in cost after alignment mark wrong harmony or missing notes; warping-path slope anomalies mark tempo or structure errors (missing or extra bars).
   - DTW with Chroma CENS reached ρ=0.891 against human judgments of playback similarity ([arXiv 2608.04511](https://arxiv.org/html/2608.04511)).
2. **Same AMT model on both signals.**
   - Transcribe source and render with the *same* multi-instrument AMT model, align via the DTW path from step 1, and compute frame- and note-level differences (mir_eval: [repo](https://github.com/mir-evaluation/mir_eval), MIT).
   - This cancels timbre and the AMT model's own biases, and it localizes to pitch and time. It is my inference and is not published as a verification method; the 2025 AMT Challenge uses a similar symbolic→audio→symbolic pipeline for evaluation ([arXiv 2603.27528](https://arxiv.org/pdf/2603.27528)).
3. **Score-informed NMF resynthesis.**
   - Initialize NMF activations from the transcription on the *source* spectrogram. The residual energy that the score-constrained model cannot explain marks missing notes or voices, localized in time and pitch.
   - Toolkits: [libnmfd](https://github.com/groupmm/libnmfd), [libfmp](https://github.com/meinardmueller/libfmp) (Müller group).
   - Strong fit for "which regions does the transcription explain poorly", because it works on the source audio itself and needs no render timbre.
4. **Early-layer SSL features** (MuQ layers ≈1–5, MusicFM ≈1–3).
   - A layer-wise study shows pitch and key information peaks in early layers (pitch layer 1: MuQ 91.5%, MusicFM 89.5%; key: MuQ layer 5, MusicFM layer 3) ([arXiv 2505.16306](https://arxiv.org/html/2505.16306)).
   - Frame-level cosine distance along the DTW path gives a second localized curve. MusicFM has Apache-2.0 weights; MuQ is CC-BY-NC.
   - Unknown: how much timbre leaks into these layers. This needs benchmarking.
5. **CLEWS** segment embeddings (MIT weights).
   - Best human correlation for playback similarity (ρ=0.971 vs Gemini 3.1 Pro 0.970, TWED-MFCC 0.924, CLaMP 3 0.884) ([arXiv 2608.04511](https://arxiv.org/html/2608.04511)).
   - Caveats:
     - That study rendered MusicXML via MuseScore → FluidSynth with a General MIDI soundfont, **piano only**.
     - 20 s segments give coarse localization.
     - Pitch-roll augmentation during training suggests weak sensitivity to transposition or key errors.
     - The study's code repo ([pingw220/AMT-Dual-Eval](https://github.com/pingw220/AMT-Dual-Eval)) returns 404 today; the paper claims MIT.
   - Use it as a global "is this the same piece?" sanity score.
6. **FAD per-song** (fadtk, MIT; supports MERT, CLAP, EnCodec, DAC, [repo](https://github.com/microsoft/fadtk)). Distributional and not localized; low value here.

---

## Open questions only benchmarking can settle

1. ACE on brass-band audio: consonance-ACE vs ISMIR2019 vs ChordMini on a handful of hand-annotated brass-band and orchestral recordings. Are inversions recovered with a tuba/euphonium bass?
2. Does running ACE on separated stems (e.g. bass stem + mix) beat the mix alone?
3. S-KEY vs madmom vs Essentia `bgate`/`temperley` on brass-band repertoire (march trios, hymn tunes). Is windowed S-KEY usable for local key?
4. Audio ACE vs symbolic RN (AnalysisGNN) agreement rate. Is disagreement a good error detector?
5. Deep Salience `melody2` vs MSNet `melody` vs stem + monophonic f0 on brass-led material (ORCHSET brass-labelled excerpts are a small public proxy).
6. Verification-loop sensitivity: inject known errors (wrong chord, dropped inner voice, octave error, transposition, missing bar) into ground-truth scores. Measure which signal (CENS-DTW cost, AMT-diff, NMF residual, MuQ/MusicFM early layers, CLEWS) detects and localizes each. Also measure the false-alarm rate from pure timbre mismatch (a perfect score rendered with a bad soundfont).
7. Does rendering with a brass sample library instead of a GM soundfont materially change 4–6?
8. Apple Silicon: MPS correctness for consonance-ACE, MuQ (NaN risk in fp16), CLEWS. madmom build on Python 3.12 from git.

---

## References

Key
- S-KEY paper: https://arxiv.org/abs/2501.12907 · https://arxiv.org/html/2501.12907 · code https://github.com/deezer/skey
- STONE: https://github.com/deezer/stone
- madmom: https://github.com/CPJKU/madmom · licence https://github.com/CPJKU/madmom/blob/main/LICENSE · issues https://github.com/CPJKU/madmom/issues/535, https://github.com/CPJKU/madmom/issues/527 · models https://github.com/CPJKU/madmom_models
- Essentia KeyExtractor: https://essentia.upf.edu/reference/std_KeyExtractor.html · https://github.com/MTG/essentia · https://pypi.org/project/essentia/
- KeyMyna: https://arxiv.org/abs/2604.10021 · https://arxiv.org/html/2604.10021 · https://github.com/echo-cipher/keymyna
- Local key cross-version consistency (ISMIR 2025): https://ismir2025program.ismir.net/poster_67.html

Chords
- ChordFormer: https://arxiv.org/abs/2502.11840 · https://arxiv.org/html/2502.11840
- consonance-ACE: https://arxiv.org/html/2509.01588 · https://github.com/andreamust/consonance-ACE
- Pseudo-labelling / ChordMini: https://arxiv.org/html/2602.19778 · https://github.com/ptnghia-j/ChordMiniApp
- BMACE (Mamba): https://arxiv.org/html/2601.02101
- Event-based seq2seq ACR: https://arxiv.org/html/2604.24386 · https://github.com/KimLeekyung/ACR_seq2seq
- Chord recognition thesis (2025): https://arxiv.org/pdf/2512.22621 · https://github.com/PierreRL/AutomaticChordRecognition
- Synthetic training audio: https://arxiv.org/abs/2508.05878
- BTC: https://github.com/jayg996/BTC-ISMIR19
- ISMIR2019 large-vocab: https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition
- NNLS/Chordino: https://github.com/c4dm/nnls-chroma · https://github.com/ohollo/chord-extractor
- autochord: https://github.com/cjbayron/autochord
- MIREX 2025 ACE: https://github.com/ismir-mirex/ace-results/tree/main/2025 · https://music-ir.org/mirex/wiki/2025:Audio_Chord_Estimation_Results
- ISMIR 2026 CFP: https://ismir2026.ismir.net/authors/call-for-papers

Symbolic
- AugmentedNet: https://github.com/napulen/AugmentedNet · https://archives.ismir.net/ismir2021/paper/000050.pdf
- AnalysisGNN: https://arxiv.org/html/2509.06654 · https://github.com/manoskary/analysisgnn
- RNHybrid: https://arxiv.org/html/2607.13587
- RNBert: https://github.com/malcolmsailor/rnbert
- BACHI: https://arxiv.org/abs/2510.06528
- Dilemmadata: https://arxiv.org/abs/2606.31595 · https://zenodo.org/records/19661299
- ChordGNN: https://github.com/manoskary/ChordGNN
- partitura: https://github.com/CPJKU/partitura · https://partitura.readthedocs.io/en/latest/modules/partitura.musicanalysis.html
- music21: https://github.com/cuthbertLab/music21 · https://www.music21.org/music21docs/moduleReference/moduleRoman.html
- PKSpell: https://arxiv.org/pdf/2107.14009 · https://github.com/fosfrancesco/pkspell
- Jazz/classical pitch spelling 2026: https://arxiv.org/abs/2606.20198
- Melody-line identification: https://arxiv.org/pdf/1906.10547 · https://archives.ismir.net/ismir2022/paper/000091.pdf

Melody
- Deep Salience: https://github.com/rabitt/ismir2017-deepsalience
- MSNet: https://github.com/bill317996/Melody-extraction-with-melodic-segnet · https://arxiv.org/pdf/1810.12947
- FTANet: https://github.com/yushuai/FTANet-melodic
- SpectMamba: https://arxiv.org/html/2505.08681 · https://github.com/Tinkle01/SpectMamba
- MELODIA: https://www.justinsalamon.com/melody-extraction.html
- Sheet Sage: https://github.com/chrisdonahue/sheetsage · https://arxiv.org/pdf/2212.01884
- ORCHSET: https://www.upf.edu/web/mtg/orchset · https://archives.ismir.net/ismir2016/paper/000256.pdf · https://zenodo.org/records/1120334
- Melody extraction review: https://arxiv.org/abs/2202.01078

Embeddings and verification
- MuQ: https://github.com/tencent-ailab/MuQ · https://huggingface.co/OpenMuQ/MuQ-large-msd-iter · https://arxiv.org/html/2501.01108
- MERT: https://huggingface.co/m-a-p/MERT-v1-330M · https://github.com/yizhilll/MERT · https://arxiv.org/abs/2306.00107
- MusicFM: https://github.com/minzwon/musicfm
- OMAR-RQ: https://github.com/MTG/omar-rq
- PupuM2D: https://arxiv.org/html/2606.25713
- Layer-wise SSL study: https://arxiv.org/html/2505.16306
- Random-quantizer SSL (2026): https://arxiv.org/html/2601.09603v1
- LAION-CLAP: https://github.com/LAION-AI/CLAP · https://huggingface.co/lukewys/laion_clap
- CLEWS: https://github.com/sony/clews · https://arxiv.org/html/2502.16936v3 · https://zenodo.org/records/15045900
- CLaMP 3: https://github.com/sanderwood/clamp3
- EnCodec: https://github.com/facebookresearch/encodec · https://huggingface.co/facebook/encodec_24khz
- DAC: https://github.com/descriptinc/descript-audio-codec
- Jukebox (archived): https://github.com/openai/jukebox · JukeMIR https://github.com/p-lambda/jukemir
- Dual Evaluation for Music Transcription (2026): https://arxiv.org/html/2608.04511
- Perceptual measure for AMT resynthesis: https://arxiv.org/abs/2202.12257
- 2025 AMT Challenge: https://arxiv.org/pdf/2603.27528
- synctoolbox: https://github.com/meinardmueller/synctoolbox
- libnmfd: https://github.com/groupmm/libnmfd · libfmp: https://github.com/meinardmueller/libfmp
- fadtk: https://github.com/microsoft/fadtk
- mir_eval: https://github.com/mir-evaluation/mir_eval
- MARBLE: https://arxiv.org/abs/2306.10548 · https://marble-bm.shef.ac.uk/

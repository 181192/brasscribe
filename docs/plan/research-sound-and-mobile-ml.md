# Realistic playback, room sound and on-device ML

Researched 2026-09-25. Every claim links to a primary source (project repo, licence text, vendor docs, paper). "Not found" means I searched and found no primary source. It does not mean the thing doesn't exist.

## TL;DR

- **Samples:** no free, redistributable library covers cornet, tenor horn, baritone or euphonium. The libraries that are clean to bundle (VSCO 2 CE, Iowa MIS, MS Basic) have trumpet, horn, trombone and tuba only. The rest either forbid shipping the samples as an instrument or allow it only non-commercially.
- **Neural synthesis:** no open-weight model covers brass-band instruments. DDSP (Apache-2.0, runs in real time on CPU) is the only neural route that works offline, and it would need training on our own recordings.
- **Room sound is solved:** convolution with CC BY OpenAIR IRs, plus HRTF or ambisonic placement, works both natively and in the browser using Apache/MIT libraries.
- **Mobile ML:** Basic Pitch, SwiftF0, Beat This! small and HTDemucs are small and licence-clean. BS-RoFormer SW fp16 is 336 MB and exports to ONNX. MuScriptor medium is 1.23 GB fp32. For these specific models, I found no published latency or memory numbers on iPhone or Android flagships.
- **Licence is the binding constraint, not hardware:** MuScriptor is non-commercial, and the BS-RoFormer SW and Mega-53 weights have no stated licence.

---

## 1. Sample-based playback beyond General MIDI

### Sample libraries

| Library | Brass content | Licence | Can we ship it inside an app? |
|---|---|---|---|
| VSCO 2 Community Edition | F horn, tenor trombone, old trombone, trumpet, tuba ([repo `Brass/`](https://github.com/sgossner/VSCO-2-CE)) | CC0 ([repo](https://github.com/sgossner/VSCO-2-CE), [Versilian](https://versilian-studios.com/vsco-community/)) | **Yes**, with no conditions. SFZ format. |
| Univ. of Iowa MIS | Horn, Bb trumpet, tenor and bass trombone, tuba. No euphonium, cornet or flugel ([MIS](https://theremin.music.uiowa.edu/MIS.html)) | "may be downloaded and used for any projects, without restrictions" ([MIS](https://theremin.music.uiowa.edu/MIS.html)) | **Yes**, but these are raw note recordings (pp/mf/ff), so we would build the SFZ mapping ourselves. |
| MuseScore MS Basic (SF3) | GM set only: no cornet, flugel, euphonium or tenor horn ([forum](https://musescore.org/en/node/325468)) | MIT, provided the notice is kept ([licence file](https://github.com/musescore/MuseScore/blob/master/share/sound/MS%20Basic_License.md)). The file still uses the old "MuseScore_General" naming ([issue #19446](https://github.com/musescore/MuseScore/issues/19446)). | **Yes**. Good as a baseline or fallback. |
| Virtual Playing Orchestra | Trumpet, horn, trombone, tuba (solo and section). No euphonium, cornet or flugel ([VPO](https://virtualplaying.com/virtual-playing-orchestra/)) | Redistribution allowed with credit. The author objects to "repackag[ing] and sell[ing] this library in part or in whole for profit" ([VPO](https://virtualplaying.com/virtual-playing-orchestra/)). | **Grey area** for a paid app, fine for a free one. VPO also bundles samples from sources with their own licences. |
| Sonatina Symphonic Orchestra | Trumpet, horns, trombone, tuba ([repo](https://github.com/peastman/sso)) | CC Sampling Plus 1.0 ([repo](https://github.com/peastman/sso)). Commercial transformation is allowed; distributing the whole work is non-commercial only. CC retired this licence in 2011 ([CC](https://creativecommons.org/licenses/sampling+/1.0/)). | **No** for a commercial app bundle. Rendered audio is OK. |
| Philharmonia samples | Trumpet, trombone, tuba, French horn and more ([mirror list](https://github.com/skratchdot/philharmonia-samples/)). The site says the tuba family includes the euphonium ([Philharmonia](https://philharmonia.co.uk/resources/instruments/tuba/)). Whether euphonium samples are actually in the download: not verified. | Free for commercial works, but "must not be sold or made available 'as is' (i.e. as samples or as a sampler instrument)" ([Philharmonia](https://philharmonia.co.uk/resources/sound-samples/)) | **No**: a playback app is effectively a sampler instrument. Rendered audio is OK. |
| Pianobook (e.g. Dusty Flugelhorn, Solo Brass Untamed with euphonium and flugel) ([Dusty Flugelhorn](https://www.pianobook.co.uk/packs/dusty-flugelhorn/), [Solo Brass Untamed](https://www.pianobook.co.uk/packs/solo-brass-untamed-demo/)) | Flugelhorn, euphonium, tuba (Kontakt/SFZ/DS) | Personal licence; "may not copy, modify, distribute" outside Pianobook ([T&C](https://www.pianobook.co.uk/terms-conditions/)) | **No**, unless we get per-author permission. |
| Muse Sounds (MuseHub) | Full brass set | "Individual samples may not be redistributed"; only works inside MuseScore Studio ([FAQ](https://support.musehub.com/en/articles/15070610-musesounds-pro-frequently-asked-questions)) | **No** |
| Free SFZ/SF2 set covering the whole brass band (cornet, tenor horn, baritone, euphonium) | Not found. A forum thread notes GM has no cornet, flugel, euphonium or tenor horn ([forum](https://musescore.org/en/node/325468)). Musical Artifacts has brass SF2 files, but the listing returned 403 and licences are per item ([listing](https://musical-artifacts.com/artifacts?formats=sf2&tags=brass)). | — | — |

**Physical modelling (commercial):** Audio Modeling SWAM ships Euphonium, Eb Tuba, Bass Tuba, Flugelhorn and Eb Flugelhorn ([Horns & Tubas](https://audiomodeling.com/swam-engine/solo-brass/horns-e-tubas/), [Trumpets](https://audiomodeling.com/swam-engine/solo-brass/trumpets/)). These are also sold as iOS apps with AUv3 ([SWAM Euphonium](https://apps.apple.com/us/app/swam-euphonium/id1470391512), [SWAM Flugelhorn](https://apps.apple.com/us/app/swam-flugelhorn/id1470367052)). SDK or OEM licence for embedding: not found. On iOS and macOS, our app could **host AUv3 instruments the user has installed themselves**, which avoids redistribution entirely.

**Options for the brass-band gap:**
- (a) Map parts to the nearest instrument: cornet→trumpet, flugel/tenor horn→horn, baritone/euphonium→trombone/tuba. Also shift the filters, since cornet is darker than trumpet.
- (b) Record our own SFZ with a band. At 3 dynamics × chromatic range, this is roughly a day per instrument. We then own the licence.
- (c) Host AUv3/SWAM instruments on Apple platforms.

### Sample players

| Player | Formats | Licence | Platforms | Notes |
|---|---|---|---|---|
| sfizz | SFZ | BSD-2-Clause ([repo](https://github.com/sfztools/sfizz)) | Win/mac/Linux; C/C++ API. Web demo via its emscripten branch ([sfizz-webaudio](https://github.com/sfztools/sfizz-webaudio)). | No official iOS or Android build found. Would need our own port (plain C++, feasible). |
| FluidSynth | SF2/SF3 | LGPL ([repo](https://github.com/FluidSynth/fluidsynth)) | Desktop, iOS, Android, WASM | The LGPL FAQ says App Store distribution "might be incompatible", and relinking must stay possible ([FAQ](https://www.fluidsynth.org/wiki/LicensingFAQ/)). **Avoid on iOS.** Fine on Android as a dynamically linked `.so`. |
| TinySoundFont | SF2 | MIT ([repo](https://github.com/schellingb/TinySoundFont)) | Single-header C, runs anywhere | Permissive alternative to FluidSynth for mobile. |
| alphaTab / alphaSynth | SF2 (+MusicXML import, notation rendering) | MPL-2.0 ([repo](https://github.com/CoderLine/alphaTab)) | Web, .NET, Android (Kotlin) | Renders the score and plays it back with a cursor. Strong fit for the play-along UI. |
| SpessaSynth | SF2/SF3/DLS, reverb and chorus | Apache-2.0 ([repo](https://github.com/spessasus/spessasynth_lib)) | Web (AudioWorklet) | Best pure-web SF2 engine found. |
| JUCE (host/engine) | — | AGPLv3, or commercial: Starter free up to $20k revenue, Indie up to $300k, Pro unlimited ([get-juce](https://juce.com/get-juce/)) | Desktop, iOS, Android | Worth it if we want one C++ audio core across all targets. |

**Recommended stack:** SFZ as the content format, played by sfizz on desktop and native, and by the sfizz-wasm build or SpessaSynth (SF2) on web. alphaTab is an option for notation plus cursor sync.

---

## 2. Neural and expressive synthesis from scores

| Work | What it does | Brass? | Weights / licence | Offline viability |
|---|---|---|---|---|
| DDSP ([repo](https://github.com/magenta/ddsp)) | Differentiable DSP: harmonic plus noise synthesis driven by f0 and loudness | Train your own | Apache-2.0, still maintained | **High.** DDSP-VST ran in real time as a CPU plugin ([repo](https://github.com/magenta/ddsp-vst), archived Oct 2024, [blog](https://magenta.tensorflow.org/ddsp-vst-blog)). |
| MIDI-DDSP ([repo](https://github.com/magenta/midi-ddsp)) | MIDI → expression → DDSP, in a hierarchy | Trumpet, horn, trombone, tuba (URMP, 13 instruments) ([site](https://midi-ddsp.github.io/)) | Apache-2.0; repo archived 2022, TF1-era | Medium. Old stack, no cornet, euphonium or tenor horn. Useful as a design reference. |
| RAVE ([repo](https://github.com/acids-ircam/RAVE)) | Real-time timbre transfer VAE | Train your own | **CC BY-NC 4.0** ([LICENSE](https://github.com/acids-ircam/RAVE/blob/master/LICENSE)) | Runs in real time, but the NC licence rules it out commercially. |
| Spectrogram diffusion ([repo](https://github.com/magenta/music-spectrogram-diffusion)) | Multi-instrument MIDI → audio | Includes GM brass | Apache-2.0; archived | Low: diffusion, GPU, offline render only. |
| Multi-aspect conditioning diffusion ([site](https://benadar293.github.io/multi-aspect-conditioning/)) | Diffusion with performance, instrument and room conditioning | Orchestral examples; no explicit brass | CC BY-NC-SA 4.0 | Low (GPU), and NC. |
| CoSaRef ([arXiv 2410.16785](https://arxiv.org/abs/2410.16785)) | Concatenative synthesis + diffusion refinement | Unspecified | No code or weights found | — |
| AnySynth ([arXiv 2607.11143](https://arxiv.org/abs/2607.11143)) | Zero-shot instrument cloning (flow-matching DiT) from reference audio + MIDI | Any, from reference audio | No code or weights found | — |
| P-MUSE ([arXiv 2608.01920](https://arxiv.org/abs/2608.01920)) | Prompt/MIDI synthesis and editing | Piano, guitar, bass, drums only | Not found | — |
| RenderBox ([arXiv 2502.07711](https://arxiv.org/abs/2502.07711)) | Text-controlled expressive score→audio rendering (timing, dynamics) | "Multiple instruments", unspecified | No code or weights found | — |

**Humanisation (timing and dynamics from a score):** published models target piano: ScorePerformer, Pianist Transformer ([arXiv 2512.02652](https://arxiv.org/pdf/2512.02652)), MIDI-VALLE. I found no open model for brass ensembles.

A practical alternative is rule-based rendering driven by MusicXML markings:
- dynamics to CC11/velocity curves
- articulation to sample layer and length
- phrase-end breaths
- small per-section onset jitter
- section-level tempo drift

The strongest option for realism: we already transcribe real recordings, so we have per-note onset, offset and dynamic data from real brass bands. The **transcription itself can drive humanisation**, which gives true timing and dynamics without a model.

**Verdict:** neural synthesis for brass-band timbres is not ready off the shelf. If we want it, train DDSP per instrument on isolated stems from our own recordings (Apache-2.0 stack, runs in real time on CPU). Otherwise, SFZ samples plus rule-based or transcription-driven expression is the realistic target.

---

## 3. Room simulation and spatial placement

### Impulse responses

| Source | Licence | Notes |
|---|---|---|
| OpenAIR (Univ. of York) | Licence is per entry. For example, Central Hall York is **CC BY 4.0**, credited to named authors and www.openairlib.net (verified via a [Wayback snapshot, 2026-06-10](https://web.archive.org/web/20260610183752/https://www.openair.hosted.york.ac.uk/?page_id=435)) | On 2026-09-25 both live hosts returned "account suspended" ([york host](https://www.openair.hosted.york.ac.uk/?page_id=435), [openairlib.net](https://openairlib.net/?page_id=770)). Mirror the IRs we pick and record each licence. B-format IRs exist for many spaces. |
| Théâtre Acoustique RIR library | CC BY-NC 4.0; commercial use goes through BabelScores ([download](https://www.lieuxperdus.com/convolver/download/)) | Stereo, binaural and HOA versions. Non-commercial only. |
| Our own | Ours | Record a sine sweep in a band room or concert hall. Cheap to do, and it gives the most authentic brass-band space. |

### Engines

| Library | Licence | Native | Web | Use |
|---|---|---|---|---|
| Web Audio `ConvolverNode` + `PannerNode` (HRTF) ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Web_audio_spatialization_basics)) | Browser built-in | — | Yes | Zero-dependency web reverb and binaural placement. |
| Omnitone ([repo](https://github.com/GoogleChrome/omnitone)) | Apache-2.0, active | — | Yes | Ambisonic → binaural decoding in the browser. |
| Resonance Audio (C++, web SDK) ([repo](https://github.com/resonance-audio/resonance-audio), [web](https://github.com/resonance-audio/resonance-audio-web-sdk)) | Apache-2.0; **archived** | Yes | Yes | Room model plus HRTF; works, but unmaintained. |
| Steam Audio ([repo](https://github.com/ValveSoftware/steam-audio)) | Apache-2.0, active | Win, Linux, macOS, Android, iOS | No | HRTF, reflections, convolution reverb. Game-oriented C API. |
| libspatialaudio ([repo](https://github.com/videolabs/libspatialaudio)) | Licence not stated in GitHub metadata | Yes | — | Ambisonic encode/decode and binaural. Check the licence before use. |
| Apple PHASE / AVAudioEngine ([PHASE](https://developer.apple.com/documentation/phase/), [AVAudioUnitReverbPreset](https://developer.apple.com/documentation/avfaudio/avaudiounitreverbpreset)) | OS | iOS/macOS | — | PHASE gives direct, early-reflection and late-reverb layers with HRTF ([WWDC21](https://developer.apple.com/videos/play/wwdc2021/10079/)). AVAudioUnitReverb has factory presets. |
| Airwindows ([repo](https://github.com/airwindows/airwindows)) | MIT | Yes | via WASM | Algorithmic reverbs we can lift as C++. |
| Dragonfly Reverb ([repo](https://github.com/michaelwillis/dragonfly-reverb)) | GPL-3.0 | Yes | — | High quality, but GPL. Avoid in closed-source apps. |

**Placement design:** position each section on a virtual stage in the standard brass-band horseshoe. Each part gets azimuth and distance, then a shared convolution tail (OpenAIR hall or our own IR). Output is binaural for headphone play-along and stereo for speakers.

**Recommended engines:**
- Web: Web Audio HRTF panner + ConvolverNode.
- Native: Steam Audio, or our own partitioned convolution + HRTF in the audio core.

---

## 4. On-device ML for mobile

### Runtimes

| Runtime | Notes |
|---|---|
| Core ML (coremltools) | Best path on iOS/macOS (ANE/GPU). Complex STFT has to move outside the graph: the HTDemucs ports split preprocessing, Core ML core and post-processing ([HF port](https://huggingface.co/reiscook/pocket-voice-cleanup-demucs-htdemucs-coreml), [CoreML-Models convert script](https://github.com/john-rocky/CoreML-Models/blob/master/conversion_scripts/convert_htdemucs.py)). |
| ExecuTorch | Reached 1.0 GA ([release](https://github.com/pytorch/executorch/releases/tag/v1.0.0), [Arm](https://newsroom.arm.com/news/executorch-1-0-ga-release-edge-ai)). Now at 1.5 with Core ML, MLX and Qualcomm delegates ([v1.5.0](https://github.com/pytorch/executorch/releases/tag/v1.5.0)). The natural route for our PyTorch models on both OSes. |
| ONNX Runtime Mobile | EPs: CoreML and XNNPACK on iOS; NNAPI and XNNPACK on Android. Operator-reduced builds cut the AAR from ~24 MB to ~7.5 MB ([docs](https://onnxruntime.ai/docs/tutorials/mobile/)). The same models also run in `onnxruntime-web`/WebGPU. |
| LiteRT (formerly TFLite) | Android/iOS/web; GPU and NPU (Tensor, Qualcomm, MediaTek, Samsung); PyTorch→.tflite conversion ([docs](https://developers.google.com/edge/litert)). |

### Our models: size, existing ports, verdict

| Model | Size | Existing mobile/web port | Licence | Phone-offline verdict |
|---|---|---|---|---|
| Basic Pitch | Small | Official CoreML, TFLite and ONNX shipped in the repo ([repo](https://github.com/spotify/basic-pitch)); TS/browser port ([basic-pitch-ts](https://github.com/spotify/basic-pitch-ts)); CoreML in a model zoo ([CoreML-Models](https://github.com/john-rocky/CoreML-Models)) | Apache-2.0 | **Yes** |
| SwiftF0 | 14,386 params, 135 KB ONNX with STFT in-graph (opset 18) ([repo](https://github.com/lars76/swift-f0)) | ONNX native | MIT | **Yes.** Real-time pitch tracking for play-along scoring. |
| Beat This! | `small` 8.1 MB, `final` 78 MB ([repo](https://github.com/CPJKU/beat_this)) | None found; PyTorch → ExecuTorch/ONNX needed | MIT, code and weights ([repo](https://github.com/CPJKU/beat_this)) | **Yes** (small) |
| HTDemucs | ONNX ~181 MB ([HF](https://huggingface.co/timcsy/demucs-web-onnx)) | CoreML ([HF](https://huggingface.co/reiscook/pocket-voice-cleanup-demucs-htdemucs-coreml), [convert script](https://github.com/john-rocky/CoreML-Models/blob/master/conversion_scripts/convert_htdemucs.py)); many ONNX/web ports | MIT ([repo](https://github.com/facebookresearch/demucs), archived) | Likely yes (4-stem). Weak on brass-internal separation. |
| BS-RoFormer SW (6-stem) | fp16 ONNX 336 MB, fp32 669 MB; fixed 4 s chunks (T=345), STFT outside the graph ([HF](https://huggingface.co/elicwhite/bs-roformer-sw-6stem-onnx)) | ONNX + WebGPU browser demo ([repo](https://github.com/elicwhite/bs-roformer-web)). Needed WebGPU graph rewrites (62-way split exceeds storage-buffer limits). | Code MIT. **Weights: no stated licence and no provenance** (rehost owner "not involved in training") ([HF card](https://huggingface.co/elicwhite/bs-roformer-sw-6stem-onnx)). | Technically plausible on flagships. Latency and memory not published. |
| Mega-53 (BS-RoFormer, 53 stems) | 1.37 GB ckpt | None found | Released as an asset of the MIT MSST repo ([release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21)); no separate weight licence | **Desktop/server.** Too big for a phone bundle. |
| MuScriptor medium (307M) | 1.23 GB fp32 safetensors ([HF](https://huggingface.co/MuScriptor/muscriptor-medium)); large is 5.47 GB ([HF](https://huggingface.co/MuScriptor/muscriptor-large)) | Community GGUF/llama.cpp port of *large* (2.78 GB fp16) ([HF](https://huggingface.co/byzp/muscriptor-large-gguf)). No mobile port found. | CC BY-NC 4.0 + gated conditions | Size-wise, medium at fp16 (~0.6 GB) is comparable to on-device Whisper. WhisperKit ships Whisper up to large-v3 (626 MB compressed) on iOS ([WhisperKit](https://github.com/argmaxinc/WhisperKit)). **The licence blocks commercial use regardless.** |

**Published phone latency and memory for these specific models (Demucs, BS-RoFormer, Basic Pitch, MuScriptor) on recent iPhones or Android flagships: not found.** The only reference point I found: Apple's own Logic Pro Stem Splitter runs on-device and requires an M1 or later iPad ([Apple support](https://support.apple.com/guide/logicpro-ipad/extract-vocal-instrumental-stems-stem-lpip1b60ada3/ipados)). That suggests high-quality separation targets M-class silicon rather than older A-series phones.

**Realistic split:**

| On the phone, fully offline | Desktop or companion server |
|---|---|
| Score playback (SFZ/SF2 + convolution + HRTF) | Mega-53 separation, BS-RoFormer on long files |
| SwiftF0 live pitch and Basic Pitch for play-along feedback | MuScriptor transcription (licence aside, ~1.2 GB and autoregressive) |
| Beat This! small for tempo following | Full recording → MusicXML pipeline |
| HTDemucs (4-stem) on recent devices, if needed | |

Recommendation: the mobile app consumes MusicXML produced on desktop or server and does playback plus live assessment on-device. Transcribing on the phone is a later option that depends on licence-clean models.

### Store size limits and model download

| Store | Limit | Model-delivery mechanism |
|---|---|---|
| App Store | 4 GB uncompressed app, 80 MB executable (iOS 9+) ([Apple](https://developer.apple.com/help/app-store-connect/reference/app-uploads/maximum-build-file-sizes)) | **Apple-hosted Background Assets:** 200 packs, 200 GB total across platforms ([Apple](https://developer.apple.com/help/app-store-connect/reference/app-uploads/apple-hosted-asset-pack-size-limits/)). On-Demand Resources is deprecated as of iOS 27 ([Apple](https://developer.apple.com/help/app-store-connect/reference/app-uploads/on-demand-resources-size-limits)). |
| App Review | Guideline 4.2.3(ii): if a download is needed on first launch, disclose its size and prompt the user. Guideline 2.5.2 forbids downloading *code* that changes functionality ([guidelines](https://developer.apple.com/app-store/review/guidelines/)). Model weights are data, but keep the inference code in the binary. | |
| Google Play | Base module 500 MB; asset pack 1.5 GB each; install-time total 4 GB; on-demand/fast-follow 30 GB; 34 GB max (compressed; help page as of 2026-09-25) ([Play help](https://support.google.com/googleplay/android-developer/answer/9859372?hl=en)) | **Play for On-device AI (beta):** AI packs up to 1.5 GB; install-time, fast-follow or on-demand delivery; targeting by SoC, device model and RAM ([docs](https://developer.android.com/google/play/on-device-ai)). |

Sample libraries (hundreds of MB to GB for SFZ) should use the same mechanisms. For example, ship MS Basic (small) in the bundle and deliver the full SFZ set as downloadable asset packs.

---

## 5. Licence implications of shipping weights

| Model | Weight licence | Can it ship in a commercial app? | Notes |
|---|---|---|---|
| MuScriptor | CC BY-NC 4.0 + gated "specific conditions" ([HF](https://huggingface.co/MuScriptor/muscriptor-medium)) | **No** | NonCommercial means "not primarily intended for or directed towards commercial advantage or monetary compensation" ([CC legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en)). Running it on a server behind a paid product is still commercial use. Bundling weights in a *free, non-commercial* app bypasses the HF gate, so the app must reproduce the attribution and the extra conditions: the user warrants they have rights to the input audio, and indemnifies Mirelo/Kyutai ([HF gate text](https://huggingface.co/MuScriptor/muscriptor-large)). A commercial path needs a licence from Mirelo/Kyutai. |
| BS-RoFormer SW | None stated; no provenance ([HF card](https://huggingface.co/elicwhite/bs-roformer-sw-6stem-onnx)) | **Not safely** | The MIT code (lucidrains, ZFTurbo) does not license the weights. |
| Mega-53 | No weight-specific licence; attached to a release of the MIT-licensed MSST repo ([release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21)) | **Unclear** | The MIT repo licence arguably covers it, but that is untested. Get written permission from ZFTurbo/MVSep before commercial use. |
| HTDemucs | MIT ([repo](https://github.com/facebookresearch/demucs)) | Yes | Fallback separator, weaker on brass. |
| Basic Pitch | Apache-2.0 ([repo](https://github.com/spotify/basic-pitch)) | Yes | Keep the NOTICE. |
| SwiftF0 | MIT ([repo](https://github.com/lars76/swift-f0)) | Yes | |
| Beat This! | MIT, code and weights ([repo](https://github.com/CPJKU/beat_this)) | Yes | The README warns that some training data is copyrighted or CC-limited; the user must assess. |
| RAVE (if used for synthesis) | CC BY-NC 4.0 ([LICENSE](https://github.com/acids-ircam/RAVE/blob/master/LICENSE)) | No | |

**Licence-clean mobile ML set today:** Basic Pitch, SwiftF0, Beat This!, HTDemucs. For any commercial release, replace MuScriptor and the RoFormer separators, license them, or train our own. Until then, keep them in a desktop tool the user runs locally (personal, non-commercial use).

# App stack research: workbench (A) and musician app (B)

**Status (2026-09-29): research, acted on.** The shell recommendation (Tauri 2) was superseded by native apps per platform (`docs/plan/apps-plan.md`); pixi and the notation findings were adopted.

As of 2026-09-25. Versions checked via `gh api` on that date. Where no primary source was found, the text says "not found" or labels the evidence.

**Apps.** (A) is the technical workbench: pipeline stages, scores, benchmarks, GPU. (B) is the musician app: source to MusicXML, score, play-along, a11y, desktop plus mobile if possible.

## TL;DR

| Decision | Recommendation | Why |
|---|---|---|
| Shell for (A) and (B) desktop | **Tauri 2** (2.11.6 stable; 3.0 in alpha) with a web UI | The notation library is web-first (alphaTab). The UI gets browser a11y via the system webview. The shell is small, and one codebase covers the desktop apps and mobile. |
| Engine packaging for (A) | **pixi** workspace (one lockfile, per-adapter environments), shipped as a first-run download via pixi-pack or constructor | The engine is already 8 separate uv projects, and basic-pitch pins Python 3.10 while the rest use 3.12. pixi gives each adapter its own environment, with a different Python if needed, under one multi-platform lock, CUDA on linux/win and MPS on osx-arm64. |
| Notation plus play-along | **alphaTab** 1.8.4 (MPL-2.0) | Built-in synth, cursor, speed, loop range, per-track mute/solo/volume and `renderTracks` (part selection). Reads MusicXML `<transpose>` as display-only, so written pitch shows while playback stays at concert pitch. It can also sync the cursor to the original recording. |
| Mobile (B) | Thin client (Tauri mobile) talking to a desktop or server engine | Tauri's shell plugin cannot spawn processes on iOS/Android. The models (Mega-53 1.4 GB, BS-RoFormer ~700 MB) plus PyTorch don't fit on-device without a port (ExecuTorch or Core ML). |
| Accessible score | A parallel structured "talking score" view plus BRF braille (music21.braille or MuseScore), not the rendered SVG | alphaTab, OSMD and Verovio SVG output is not screen-reader navigable. Verovio's a11y proof of concept was closed without merge. |

---

## 1. Cross-platform shells

| Shell | Desktop | iOS / Android | Python engine | Screen-reader support | Fit |
|---|---|---|---|---|---|
| **Tauri 2** (Apache-2.0, [2.11.6, 2026-09-19](https://github.com/tauri-apps/tauri/releases/tag/tauri-v2.11.6); 3.0.0-alpha.2 out) | Win (WebView2), macOS (WKWebView), Linux (WebKitGTK) ([webview versions](https://v2.tauri.app/reference/webview-versions/)) | Yes, using the system Android WebView and WKWebView ([same page](https://v2.tauri.app/reference/webview-versions/)) | Desktop: sidecar via `bundle.externalBin`, which must be single binaries with a target-triple suffix ([sidecar docs](https://v2.tauri.app/develop/sidecar/)). A pixi or conda env is a directory, so ship it in `bundle.resources` or install it on first run. **Mobile: the shell plugin "only allows to open URLs" on android/ios** ([shell plugin](https://v2.tauri.app/plugin/shell/)), so there is no child process | Inherited from the webview: WebView2 is Chromium (Narrator, NVDA, JAWS); WKWebView (VoiceOver). Linux WebKitGTK/Orca: *indirect evidence only, not re-verified*: an old [Ubuntu regression](https://bugs.launchpad.net/ubuntu/+source/orca/+bug/1971076) and a [Wails report](https://github.com/wailsapp/wails/discussions/4535). Open Tauri issues: [a11y tracking #207](https://github.com/tauri-apps/tauri/issues/207), [NVDA silent in frameless windows #12901](https://github.com/tauri-apps/tauri/issues/12901) (keep native decorations) | **(A) and (B)** |
| **Electron** | Win/mac/Linux, bundles Chromium | No | Spawn any process (`child_process`) | Chromium a11y tree on all 3 OSes ([Electron a11y](https://www.electronjs.org/docs/latest/tutorial/accessibility)) | (A) fallback if WebKitGTK a11y or rendering is a blocker on Linux. Larger installer |
| **Flutter** | Win/mac/Linux | Yes | FFI or process; no web notation libraries (a webview would be needed for alphaTab) | TalkBack, VoiceOver, Narrator/NVDA, Orca listed ([Flutter a11y](https://docs.flutter.dev/ui/accessibility/assistive-technologies)) | Strong mobile, weak fit for web notation |
| **Compose Multiplatform** | Win/mac/Linux (JVM) | iOS stable since [1.8.0 (2025-05)](https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/); Android | JVM process spawning | Desktop: macOS supported; Windows via Java Access Bridge (off by default); **Linux not supported** ([docs](https://kotlinlang.org/docs/multiplatform/compose-desktop-accessibility.html)) | Fails the Linux a11y requirement |
| **React Native** | Windows and macOS only through Microsoft out-of-tree forks; no official Linux ([out-of-tree platforms](https://reactnative.dev/docs/out-of-tree-platforms)) | Yes | Native modules | Native a11y on iOS/Android | No Linux desktop |

**Verdict.** Use Tauri 2 for both apps. The notation layer (alphaTab, OSMD, Verovio) is JS/WASM, so a webview shell reuses it as-is. Keep Electron as the Linux escape hatch.

## 2. Packaging Python + PyTorch + GPU

The current repo state: `music/`, `eval/` and 7 `ml/adapters/*` are separate uv projects. `basic-pitch` requires `>=3.10,<3.11`; everything else requires `>=3.12,<3.13`.

| Tool | Multi-OS lock | GPU handling | Output | Notes |
|---|---|---|---|---|
| **pixi** (BSD-3, [v0.81.0](https://github.com/prefix-dev/pixi/releases)) | One `pixi.lock` across platforms, with multiple environments (features) per workspace | Platforms carry virtual packages, e.g. `{ platform = "linux-64", cuda = "12" }` ([system requirements](https://pixi.prefix.dev/latest/workspace/system_requirements/)). The PyTorch guide shows `pytorch-gpu` on linux/win-cuda and `pytorch-cpu` on osx-arm64 in one manifest ([pixi PyTorch](https://pixi.prefix.dev/latest/python/pytorch/)). Don't mix conda and PyPI in one dependency chain ([same page](https://pixi.prefix.dev/latest/python/pytorch/)) | An environment directory; ship it with [pixi-pack](https://github.com/Quantco/pixi-pack) (v0.7.11) or [conda constructor](https://github.com/conda/constructor) (3.17.3) | Also manages non-Python deps (e.g. ffmpeg from conda-forge) |
| **uv** (Apache-2.0, [0.12.19](https://github.com/astral-sh/uv/releases)) | `uv.lock` universal; torch variants via explicit indexes plus `sys_platform` markers ([uv PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/)) | `--torch-backend=auto` works only in the `uv pip` interface ([same](https://docs.astral.sh/uv/guides/integration/pytorch/)). Torch CUDA wheels bundle the CUDA runtime, so only the NVIDIA driver is needed (maintainer answer on the [PyTorch forum](https://discuss.pytorch.org/t/is-it-required-to-set-up-cuda-on-pc-before-installing-cuda-enabled-pytorch/60181)) | venv; relocation is not a goal | A uv workspace shares one `requires-python`, so the 3.10 basic-pitch adapter can't join. Keeping the status quo means 8 locks |
| **conda-pack** (BSD-3, [0.9.2](https://github.com/conda/conda-pack)) | No lock, packs an existing env | Whatever the env has | Relocatable tarball | Superseded by pixi-pack for pixi |
| **PyInstaller** ([6.22.3](https://github.com/pyinstaller/pyinstaller/releases); GPL-2 with bootloader exception, commercial OK ([licence](https://pyinstaller.org/en/stable/license.html))) | Per-OS build | Bundles torch/CUDA libs, which are multi-GB and fragile | One-dir or one-file exe | Fits a Tauri `externalBin`, but the size is a problem with CUDA |
| **Nuitka** (AGPL-3.0 plus runtime exception for compiled output; [README](https://github.com/Nuitka/Nuitka/blob/develop/README.rst)) | Per-OS build | Same as above | Compiled exe | Slow builds on the torch dependency tree |
| **Docker** | Linux images | Linux Docker Engine with the NVIDIA Container Toolkit works. **Docker Desktop GPU is Windows/WSL2 only** ([Docker docs](https://docs.docker.com/desktop/features/gpu/)), so no Metal on macOS | Image | Good for CI and Linux benchmark runners, not for a desktop app |
| **Briefcase** (BSD-3, [v0.4.5](https://github.com/beeware/briefcase/releases)) | Per-OS | Nothing GPU-specific | Native installers for macOS, Windows, Linux, iOS, Android and web ([platforms](https://briefcase.beeware.org/en/stable/reference/platforms/index.html)) | PyTorch on mobile via Briefcase: not found |

MPS needs macOS 14+ and an MPS-enabled build ([PyTorch MPS](https://docs.pytorch.org/docs/2.14/notes/mps.html)).

**Recommendation for (A).**
1. Migrate the adapters into one **pixi workspace**, one environment per adapter, including a py310 environment for basic-pitch. Use platforms `linux-64-cuda`, `win-64-cuda` and `osx-arm64` (MPS), plus CPU fallbacks.
2. The Tauri app ships a small launcher. On first run it installs the env (pixi-pack or constructor) and downloads model weights into a cache directory. Don't embed GBs in the installer. Windows MSI/NSIS size limits were not verified.
3. Run the engine as a local HTTP/stdio service that the UI calls. Run benchmarks headless in Docker on Linux/CUDA CI.

## 3. Notation rendering and playback

| | **alphaTab** 1.8.4 (2026-07-05) | **OpenSheetMusicDisplay** 2.1.3 (2026-09-19) | **Verovio** 6.3.0 (2026-08-19) | **MuseScore** 4.7.5 |
|---|---|---|---|---|
| Licence | MPL-2.0 ([LICENSE](https://github.com/CoderLine/alphaTab/blob/develop/LICENSE)) | BSD-3 ([repo](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay)) | LGPL-3.0 ([repo](https://github.com/rism-digital/verovio)). Static WASM or App Store bundling needs relinkability/LGPL compliance care | GPL-3.0 ([LICENSE.txt](https://github.com/musescore/MuseScore/blob/master/LICENSE.txt)). Shipping the CLI inside (B) brings GPL obligations for that component |
| MusicXML | Yes (plus GP, alphaTex) ([intro](https://www.alphatab.net/docs/introduction)) | Native focus | Yes (MEI-first) | Yes |
| Built-in synth | Yes, SoundFont2 (TinySoundFont) ([intro](https://www.alphatab.net/docs/introduction)) | **Sponsor-only** audio player ([blog](https://opensheetmusicdisplay.org/blog/blog-audio-player-upgraded/), [sponsors](https://github.com/sponsors/opensheetmusicdisplay)) | None: `renderToMIDI` plus `getElementsAtTime`, and you bring the player ([Verovio book](https://book.verovio.org/interactive-notation/playing-midi.html)) | Desktop app only |
| Cursor sync | Built in, plus `scrollToCursor` ([API](https://www.alphatab.net/docs/reference/api/)) | Cursor API; playback sync is in the sponsor player | DIY via the timemap | n/a |
| Speed / loop | `playbackSpeed`, `isLooping`, `playbackRange` ([API](https://www.alphatab.net/docs/reference/api/)) | Sponsor player | DIY | n/a |
| Part selection | `renderTracks` (show/hide) plus `changeTrackMute/Solo/Volume` ([API](https://www.alphatab.net/docs/reference/api/)) | Show/hide instruments | DIY | n/a |
| Transposing brass | MusicXML `<transpose>` at part start becomes `staff.displayTranspositionPitch` (display only, playback stays concert) ([importer L1715](https://github.com/CoderLine/alphaTab/blob/develop/packages/alphatab/src/importer/MusicXmlImporter.ts#L1715-L1741)). **Mid-piece transpose changes are not supported.** Settings exist for `transpositionPitches` / `displayTranspositionPitches` ([docs](https://alphatab.net/docs/reference/settings/notation/displaytranspositionpitches/)) | `TransposeCalculator` for whole-sheet transposition ([wiki](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay/wiki/Transposing)) | `transposeToSoundingPitch`, `transpose` options ([toolkit options](https://book.verovio.org/toolkit-reference/toolkit-options.html)) | Full |
| Play along with the original audio | **Yes**: external media sync (since 1.6; synth *or* external audio, not both) ([guide](https://www.alphatab.net/docs/guides/audio-video-sync)) | No | DIY | No |
| Native mobile | Android (Kotlin) native plus .NET; the web build works in webviews ([README](https://github.com/CoderLine/alphaTab)) | Web | Web/WASM, C++ | No |
| Accessibility | No a11y features found | None found | [PoC #4273](https://github.com/rism-digital/verovio/issues/4273) closed without merge (2026-02) | Best of the notation apps (below) |

**MuseScore embedding.** Only the CLI is available (`mscore -o` for PDF/SVG/MIDI/BRF). The WASM port [webmscore](https://github.com/LibreScore/webmscore) was last pushed 2023-01, so treat it as stale. Use MuseScore for engraving exports and QA, not as an interactive widget.

**Verdict.** alphaTab is the best fit for play-along: cursor, part selection, speed, loop, and sync to the source recording. Spike this next: load real brasscribe band MusicXML (cornets in B♭, horns in E♭, percussion) into alphaTab and check import completeness. alphaTab is guitar-first, so check layout of 10+ staves, written vs concert pitch, and rehearsal marks. Fallback: Verovio render plus our own synth/timemap.

## 4. Audio capture limits

| Platform | Other apps' audio? | Mechanism | Limits |
|---|---|---|---|
| **iOS** | Only via a **ReplayKit broadcast upload extension** (screen broadcast); buffers typed `audioApp` ([RPBroadcastSampleHandler](https://developer.apple.com/documentation/replaykit/rpbroadcastsamplehandler), [audioApp](https://developer.apple.com/documentation/replaykit/rpsamplebuffertype/audioapp)) | User starts the broadcast from Control Center; the extension has tight memory limits | "ReplayKit is incompatible with AVPlayer content" ([ReplayKit](https://developer.apple.com/documentation/replaykit)), so DRM/AVPlayer streams are excluded. No general loopback API found |
| **Android** 10+ | `AudioPlaybackCapture` with MediaProjection consent plus `RECORD_AUDIO` ([docs](https://developer.android.com/media/platform/av-capture)) | Only usages MEDIA/GAME/UNKNOWN; apps targeting API 29+ are capturable by default, and `allowAudioPlaybackCapture="false"` opts out; the most restrictive policy wins ([same](https://developer.android.com/media/platform/av-capture)) | Spotify opt-out: **primary source not found**. User reports say Spotify records silent ([Pixel community thread](https://support.google.com/pixelphone/thread/70413620/)) |
| **Windows** | Yes | WASAPI loopback (`AUDCLNT_STREAMFLAGS_LOOPBACK`, shared mode) ([docs](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)). Per-process loopback needs Win10 build 20348+ ([params](https://learn.microsoft.com/en-us/windows/win32/api/audioclientactivationparams/ns-audioclientactivationparams-audioclient_process_loopback_params)) | Trusted drivers block protected (DRM) content ([docs](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)) |
| **Linux** | Yes | PipeWire capture stream with `PW_KEY_STREAM_CAPTURE_SINK="true"` records sink monitor ports ([audio-capture.c](https://docs.pipewire.org/audio-capture_8c-example.html)) | No consent prompt |
| **macOS** | Yes (already implemented) | Core Audio process taps plus aggregate device; the sample says macOS 14.2+ and `NSAudioCaptureUsageDescription` ([Apple sample](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)) | TCC prompt on first use |

**Video file audio.** Mobile: AVFoundation `AVAssetReader` ([Apple](https://developer.apple.com/documentation/avfoundation/avassetreader)) and Android `MediaExtractor` plus `MediaCodec` ([Android](https://developer.android.com/reference/android/media/MediaExtractor)). Desktop: bundle ffmpeg (conda-forge via pixi). Note that **ffmpeg-kit is archived** ([repo](https://github.com/arthenica/ffmpeg-kit)), so don't build mobile on it.

## 5. Accessibility

**Norway, in force now** (Lovdata consolidated text, amended by FOR-2021-12-21 (in effect 2022-02-01) and later by FOR-2023-01-17-87 ([FOR-2013-06-21-732](https://lovdata.no/dokument/SF/forskrift/2013-06-21-732))):
- **§4, private sector:** WCAG 2.0 A+AA, except 1.2.3, 1.2.4 and 1.2.5.
- **§4b, public sector:** EN 301 549 V3.2.1, which means WCAG 2.1.

Apps must meet the same minimum as websites ([uutilsynet](https://www.uutilsynet.no/regelverk/regelverk-og-krav/746)). The duty covers solutions aimed at the public.

**WCAG 2.2** "er ikke en del av regelverket nå" (uutilsynet page dated 2023-11-08 ([status](https://www.uutilsynet.no/fremtidig-regelverk/status-nyere-versjoner-av-wcag/1868))).

**EAA** (EU in force 2025-06-28): Norwegian implementation is delayed ([uutilsynet](https://www.uutilsynet.no/regelverk/fremtidige-regelverk-og-krav/747)). Whether brasscribe falls within EAA product/service scope was not assessed.

**EN 301 549 V4.1.1 (2026-09)** adopts WCAG 2.2 ([ETSI PDF](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/04.01.01_60/en_301549v040101p.pdf)). It is not yet cited in the OJEU, so V3.2.1 remains the legal reference ([AccessibleEU](https://accessible-eu-centre.ec.europa.eu/content-corner/news/european-accessibility-standard-en-301-549-has-been-updated-2026-09-07_en)).

**Target WCAG 2.2 AA** ([What's new in 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)). This is future-proof and a superset of the legal floor. These criteria bite a score player:

| SC | Where it bites |
|---|---|
| 2.1.1 Keyboard | Transport, part toggles, bar navigation, loop set, all without a mouse |
| 2.2.2 Pause, Stop, Hide | Auto-scrolling cursor/score during playback |
| 1.4.1 Use of Color / 1.4.11 Non-text Contrast | Cursor and active-part highlight need shape or outline plus contrast, not only colour |
| 2.5.7 Dragging | Loop-range selection needs a non-drag alternative (bar number inputs) |
| 2.5.8 Target Size (24 px) | Transport buttons, part chips on mobile |
| 2.4.11 Focus Not Obscured | Sticky player bar over the focused score element |
| 4.1.3 Status Messages | Transcription progress, playback position announcements (live region) |
| 1.2.x | Media alternatives for any tutorial video |

**Accessible notation approaches.** Rendered SVG from alphaTab, OSMD or Verovio is not navigable (see §3), so provide parallel views generated from the same MusicXML:
- **Structured, talking-score view.** HTML with a heading per part and section, a list per bar, and "play bars n–m". Prior art: [Talking Scores](https://www.talkingscores.org/) (open source, MusicXML to text plus MIDI; [repo](https://github.com/dbuik1/talkingscores)).
- **Braille music (BRF):**
  - [music21.braille](https://www.music21.org/music21docs/moduleReference/moduleBrailleTranslate.html) (`objectToBraille`) is already an engine dependency, so it's the lowest-cost option.
  - MuseScore 4 BRF export plus braille panel ([handbook](https://musescore.org/en/handbook/4/braille)).
  - [FreeDots](https://github.com/mlang/freedots) (GPL-3.0, last push 2020, stale).
  - Commercial: GOODFEEL, BrailleMUSE ([overview](https://tobyrush.com/braillemusic/)).
- **Hand-off to MuseScore Studio.** It supports NVDA, VoiceOver and Orca; JAWS is not supported ([handbook](https://handbook.musescore.org/navigation/accessibility)). "Open in MuseScore" is a legitimate accessible path for score editing.

**Local check.** `mscore -o out.brf` on `data/mikkel/mikkel-leadsheet-v4.musicxml` aborted in a sandboxed shell (`mutex lock failed`), and MIDI export failed the same way. This is an environment issue, not a BRF verdict. Re-test from a normal terminal.

## Open spikes
1. alphaTab with a real brass-band MusicXML: import completeness, transposing display, 10+ staves, performance in WKWebView, WebView2 and WebKitGTK.
2. Tauri on Linux with Orca: is the alphaTab page plus structured view readable?
3. Migrate the adapters to pixi: confirm conda-forge availability for the adapters' deps, especially basic-pitch, onnxruntime and torchaudio versions.
4. Mobile: pick thin client first. Evaluate [ExecuTorch](https://github.com/pytorch/executorch) (v1.5.1) or Core ML only for the small models (SwiftF0, Beat This!).

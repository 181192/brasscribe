# Third-party notices

Brasscribe's own code is licensed under MIT OR Apache-2.0 ([LICENSE](LICENSE)). It uses the software,
fonts, sounds and models below, which keep their own licences. This file lists what the apps ship
(bundled), what they download on the user's computer (not bundled), and what only the development
tools use.

## Notation and playback libraries

| Component | Licence | Where | How it is used |
|---|---|---|---|
| [Verovio](https://github.com/rism-digital/verovio) 6.3.0 | LGPL-3.0-or-later | Play for Mac, iPhone and iPad | Built from the unmodified upstream source as a separate dynamic framework (`apps/apple/scripts/build-verovio.sh`), so it can be replaced. The LGPL text (`COPYING`, `COPYING.LESSER`) ships in the app next to Verovio's resources. |
| Leipzig and Bravura SMuFL fonts (from Verovio's `data/`) | SIL OFL 1.1 | Play for Mac, iPhone and iPad | Music glyphs for Verovio. |
| [alphaTab](https://alphatab.net) 1.8.4 | MPL-2.0 | Play for Android and Windows, Studio | Unmodified package (npm `@coderline/alphatab`, Maven `net.alphatab:alphaTab`, NuGet `AlphaTab`). Its source is at https://github.com/CoderLine/alphaTab. |
| Bravura font (shipped with alphaTab) | SIL OFL 1.1 | Play for Android and Windows, Studio | Music glyphs for alphaTab. |
| Sonivox SoundFont (shipped with alphaTab) | Apache-2.0, Copyright (c) 2004-2006 Sonic Network Inc. | Studio, Play for Android | alphaTab's default General MIDI sounds, used when the band sounds are missing. |
| [alphaSkia](https://github.com/CoderLine/alphaSkia) 3.4.135 | BSD-3-Clause (Skia: BSD-3-Clause) | Play for Android and Windows | Drawing backend for alphaTab. |
| [UniFFI](https://github.com/mozilla/uniffi-rs) runtime | MPL-2.0 | Every app that links the Rust core | Unmodified crate, linked into `brasscribe_ffi`. |

## Band sounds

The band SoundFonts every app bundles are built from the sources below. [sounds/LICENSES.md](sounds/LICENSES.md)
has the details, the files are pinned in [sounds/manifest.json](sounds/manifest.json), and
[sounds/band-notice.txt](sounds/band-notice.txt) is the notice the apps ship next to the SoundFont.

| Source | Licence |
|---|---|
| [VSCO 2 Community Edition](https://github.com/sgossner/VSCO-2-CE), Versilian Studios LLC | CC0 1.0 |
| [University of Iowa Musical Instrument Samples](https://theremin.music.uiowa.edu/MIS.html), Electronic Music Studios, Lawrence Fritts | "may be downloaded and used for any projects, without restrictions" |
| [MuseScore MS Basic](https://github.com/musescore/MuseScore/tree/master/share/sound) SoundFont | MIT (FluidR3 by Frank Wen; FluidR3Mono by Michael Cowgill; MuseScore_General adaptation by S. Christian Collins; notice in `sounds/LICENSES.md`) |
| [OpenAIR](https://www.openair.hosted.york.ac.uk/) impulse responses, University of York | CC BY 4.0 (offline renderer only, not in the apps) |

**MuseScore General** (`MuseScore_General.sf2`, MIT, same notice as MS Basic) is the fallback of Play
for Mac, iPhone and iPad when the band SoundFont is missing. It is not committed; `make soundfont` in
`apps/apple` downloads it for a local build.

## Fonts

| Font | Licence | Where |
|---|---|---|
| [Instrument Serif](https://github.com/Instrument/instrument-serif), Copyright 2022 The Instrument Serif Project Authors | SIL OFL 1.1 | Display face of every app and the site; `OFL.txt` ships beside the font (`design/brand/fonts/`, `design/dist/*/`). |

## Machine-learning models

### Bundled

| Model | Licence | Where |
|---|---|---|
| [SwiftF0](https://github.com/lars76/swift-f0) (ONNX) | MIT | Play for Android and Windows |
| [Basic Pitch](https://github.com/spotify/basic-pitch) (ONNX) | Apache-2.0 | Play for Android |
| [Beat This!](https://github.com/CPJKU/beat_this) small (ONNX) | MIT (code and published weights) | Play for Android |

Play for Mac, iPhone and iPad uses Core ML conversions of the same three models. They are not bundled:
the app copies them from the paired computer on first use.

### Downloaded by the user, not bundled

Bandroom (the engine for Mac and Windows) and a developer checkout download these on the user's
computer, from where their makers publish them. Brasscribe does not re-host or redistribute them.

| Model | Licence | Notes |
|---|---|---|
| [MuScriptor](https://huggingface.co/MuScriptor/muscriptor-medium) medium (the band writer) | **CC BY-NC 4.0, non-commercial use only** | Gated on Hugging Face: each user accepts the licence with their own Hugging Face account, and Bandroom downloads it with that user's key. Full-band scores therefore may only be used non-commercially. The model card adds conditions of use: don't input and write down music without all the necessary rights to it, including intellectual property rights; the model and what it writes down come as is, without warranty; and the user indemnifies its makers, Kyutai and Mirelo, against claims that come from breaking these conditions. Bandroom states this before it downloads the model, and the user ticks a box to accept it. |
| BS-RoFormer SW (soloist separation), via [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | No licence stated for the weights (the separator code is MIT) | Downloaded from the upstream release URL. |
| Mega-53 (instrument separation), via [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training) | No licence stated for the weights (the inference code, which Bandroom ships at a pinned revision, is MIT) | Downloaded from the upstream release URL. |
| Beat This! final checkpoint | MIT | Engine beat tracking; fetched by the adapter on first use. |
| Basic Pitch, SwiftF0 | Apache-2.0, MIT | Engine adapters, installed from their Python packages. |

## Other dependencies

- **Engine (Python):** installed by `pixi install` from conda-forge and PyPI (versions pinned in
  `pixi.lock`); Bandroom runs the same install on the user's computer on first launch. Notable:
  music21 (BSD-3-Clause), FastAPI (MIT), PyTorch (BSD-3-Clause).
- **Bandroom** (Mac and Windows) ships the [pixi](https://github.com/prefix-dev/pixi) binary (BSD-3-Clause),
  and the project's own `brasscribe-core` command-line tool, built from the Rust core below.
- **Rust core:** crates under MIT, Apache-2.0, BSD-style or Unicode-3.0 licences, plus UniFFI (MPL-2.0,
  above). `cargo metadata` in `core/` lists them.
- **Android:** AndroidX and Jetpack Compose (Apache-2.0), Kotlin coroutines and serialization
  (Apache-2.0), Ktor (Apache-2.0), Oboe (Apache-2.0), ONNX Runtime (MIT), JNA (Apache-2.0 option of
  LGPL-2.1/Apache-2.0), and the Google Play services code scanner (Android SDK licence; not bundled
  code, it calls the system scanner).
- **Windows:** Windows App SDK (Microsoft software licence), ONNX Runtime with DirectML (MIT),
  NAudio (MIT), CommunityToolkit.Mvvm (MIT).
- **Studio:** alphaTab (above); build and test tools only in development.

## Not distributed

The evaluation datasets (ChoraleBricks CC BY 4.0, URMP, Slakh) and the PANNs tagger used for
research are downloaded on request by the development tools and never bundled. The repository keeps
small derived test data only:

- `eval/fixtures/`: MIDI, beats and pitch contours computed from the ChoraleBricks v1.1.0 recordings
  (CC BY 4.0, Zenodo 10.5281/zenodo.20849469; see `eval/README.md`). Bandroom's bundled workspace
  includes this folder.
- `apps/android/pitch/src/test/resources/`: Basic Pitch notes and Beat This! beats of 30 s of one URMP
  track (URMP, University of Rochester; B. Li et al., IEEE Trans. Multimedia 2019).

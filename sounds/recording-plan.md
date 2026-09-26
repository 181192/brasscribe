# Recording plan: our own brass-band samples

**Why:** no free library we can redistribute has a cornet, flugelhorn, tenor horn, baritone, euphonium or brass-band basses (docs/plan/research-sound-and-mobile-ml.md §1). The realistic tier maps these to trumpet, horn, trombone and tuba with EQ. Recording the real instruments removes that approximation, and we own the licence.

**Instruments (one player each):**

| Instrument | Sounding range to record (MIDI, from `music/src/brasscribe_music/instruments.py` pro range) | Notes |
|---|---|---|
| B♭ cornet | E3–A♭5 (52–80); also 81–82 if the player is comfortable | Also covers soprano cornet up to E♭6 (87) if a soprano player is available: second priority |
| Flugelhorn | E3–A♭5 (52–80) | |
| E♭ tenor horn | A2–E♭5 (45–75) | |
| Baritone | E2–B♭4 (40–70) | |
| Euphonium | B♭1–D5 (34–74) | 4-valve compensating instrument; include pedal B♭1 |
| E♭ bass | C1–C5 (24–72) as far as the player's range goes; the core is C1–G3 | |
| B♭ bass | B♭0–C5 (22–72) as far as the player's range goes; the core is B♭0–D3 | |

## Takes per note

Every **semitone**, not every third or fourth like VSCO. Transposing brass samples more than about 2 semitones changes the formants audibly.

| Articulation | Dynamics | Length | Round robins |
|---|---|---|---|
| Sustain, no vibrato | pp, mf, ff | 4 s (basses 5 s), natural release | 1 |
| Staccato | pp, mf, ff | natural | 3 |
| Sustain with vibrato (cornet, flugel, euphonium only; second priority) | mf | 4 s | 1 |

- Keep 2 s of silence between notes. This keeps the release tail and room decay, and makes automatic slicing trivial (the same silence-gap segmenter as `sounds/analyse.py`).
- Play ascending chromatic runs within one octave per take (e.g. "cornet sus mf C4–B4"), so the file name says which pitches it holds. Retake single cracked notes at the end of the run.
- Tune to A = 440 Hz. Record the tuner reading once per take in the session log. `analyse.py` measures the cents offset anyway and writes it into the instrument.

**Per instrument:** about 30 semitones × (3 sustain + 9 staccato) ≈ 360 notes. At about 7 s each, including gaps, that is about 45 minutes of playing time. Add retakes, breaks and embouchure recovery (ff staccato in the low and high registers is tiring), and plan **one day per instrument**.

## Room and microphones

- **Room:** a dry band room or a studio live room with an RT60 of 0.3 s or less. The tier adds the hall convolution itself, so the room must not be baked into the samples. Hang heavy curtains, and keep the player at least 2 m from walls.
- **Main pair:** 2 small-diaphragm omni or cardioid condensers, spaced 40 cm (ORTF or AB), at 2 m, 1.5 m high. They should point at the bell for cornet and flugel, and at the bell's upper rim from the audience side for the upright instruments (horn, baritone, euphonium, basses). This is how the band is heard from the hall.
- **Close mic:** 1 large-diaphragm condenser or ribbon at 50 cm, off the bell axis by 30°. It gives an optional drier layer and a backup.
- **Room mic (optional):** 1 omni at 5 m. It is used only to judge the room, never mixed into the samples.
- Keep the same microphones, positions (mark the floor) and preamp gain for every instrument, so levels and colour are consistent across the band. That is the main flaw of mixing VSCO and Iowa samples today.
- Use the loudest ff note for the preamp gain check: peaks at about −6 dBFS.

## File format and naming

- **Format:** 48 kHz / 24-bit WAV, one file per microphone per take (multichannel poly-WAV is fine). No processing, normalisation or fades on the originals.
- **Take file:** `<instrument>_<articulation>_<dynamic>_<lowNote><highNote>_<mic>_t<take>.wav`, e.g. `cornet_sus_mf_C4B4_main_t1.wav`. Notes are in scientific pitch at **sounding** pitch (C4 = MIDI 60), sharps written `s` (e.g. `Fs3`).
- **Sliced notes** (made by the builder): `<instrument>_<articulation>_<midi>_<dynamic>_rr<n>.wav`, the same scheme as `data/sounds/built/*/samples/`.
- **Session log** (CSV, one row per take): date, player, instrument make and model, mouthpiece, take file, tuner cents, retakes, comments.

## Session schedule (one instrument per day)

| Time | Block |
|---|---|
| 09:00–09:45 | Setup, mic positions marked, gain check, 2-minute room tone per mic |
| 09:45–10:00 | Player warm-up (not recorded) |
| 10:00–11:15 | Sustain mf, all octaves; then sustain pp |
| 11:15–11:30 | Break |
| 11:30–12:30 | Sustain ff (low to high, rests between octaves) |
| 12:30–13:15 | Lunch |
| 13:15–14:45 | Staccato pp, mf, ff, 3 round robins |
| 14:45–15:00 | Break |
| 15:00–15:45 | Vibrato sustains (if applicable), retakes of cracked notes |
| 15:45–16:30 | Listen-back on the close mic, spot-check tuning, backup to two disks |

Order across days: euphonium and B♭ cornet first (largest gap versus the current mapping, and the solo instruments in Mikkel), then tenor horn, flugelhorn, baritone, E♭ bass, B♭ bass.

## Release licence

- Samples released as **CC0 1.0** (like VSCO 2 CE), so they can be bundled in every app and store without attribution conditions. The players are credited in the README anyway.
- Each player signs a short release before recording. It covers: the recordings are made for brasscribe; they are published under CC0; the player waives performer and neighbouring rights to the extent the law allows (the performer provisions of the Norwegian *åndsverkloven*, or the local equivalent; the exact sections still need checking); and the player agrees to be credited by name, or chooses to stay anonymous.
- Record the instrument make and model and the mouthpiece in the release too (useful metadata, no rights involved).
- Keep signed releases outside the repository. Put only the player name (or "anonymous") and the licence in `sounds/manifest.json` when the samples are published.

## Integration

1. Add the recordings as a new source (`"library": "brasscribe"`) in `sounds/manifest.json` and `sounds/fetch.py`, hosted on the project's release assets.
2. Map the parts in `sounds/mapping.json` directly: cornet to cornet, with no timbre EQ.
3. `analyse.py` → `build.py` → `render.py`, then rerun `sounds/descriptors.py` and the A/B protocol against the current realistic tier.

## Open questions

- Which band and players, and which dates? Instruments should be of the same make across the section where possible.
- Should we also measure an impulse response in the band's own rehearsal room on the same day? A sine sweep takes 30 minutes and gives an authentic band-room IR that we own (CC0).

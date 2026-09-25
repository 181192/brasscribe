# Mikkel (Antonsen / Halstensen), end-to-end target

**Sources:**
- Spotify track `3GAzmxoUSl9xyQch08ykWj`, captured to `data/mikkel/mikkel.wav` (246 s).
- Live video: https://www.youtube.com/watch?v=R3rmh4Qp4kU (255 s, the same performance as the album track).

**Credits (from the video description).**
- Recorded live in Grieghallen, Bergen, 10 August 2006, for *Landscapes* (OEA Records).
- Ole Edvard Antonsen: solo.
- Bergen Philharmonic Orchestra, conducted by Torodd Wigum.
- Atle Halstensen: keyboards. Tom Erik Antonsen: bass. Rune Arnesen: drums.

**Setup seen in the video (frames every 8 s, plus full-resolution stills):**
- **Soloist:** standing front centre on a silver valved instrument. In the close-up at 0:10 it has a wrapped leadpipe loop and cornet-like proportions, not a standard trumpet. Some later shots show a wider bell, so he may switch instruments; confirm by ear.
- **Strings:** a full section is dominant in most shots — violins, violas, a large cello section, double basses.
- **Orchestral brass:** at the back, including trumpets and trombones (visible around 1:50) and a tuba (bell visible at 1:14).
- **Keyboards:** a synth/keyboard rig at the back of the orchestra.
- **Rhythm section:** a drum kit behind a plexiglass screen, with hanging shell or bead chimes and cymbals; the drummer wears headphones, so they play to a click. Electric bass.
- Woodwinds and harp were not clearly identified in the sampled frames.

**What this means for the pipeline:**
- The intro is the solo line alone, which matches the transcription.
- MuScriptor's "distorted electric guitar" label was the soloist, as PANNs and the separator indicated.
- The texture is **soloist + string orchestra + orchestral brass + keys + rhythm section**. A three-role model (melody / bass / chords) throws most of it away: string countermelodies, brass hits, keyboard figures and percussion colour.
- The natural brass-band target is a **cornet (or flugel) solo with band accompaniment**. That is a standard brass-band genre, and published brass-band arrangements of Antonsen's music exist (e.g. *Vidda*, De Haske).

## Layered arrangement: solo cornet with brass band

**Pipeline:**
1. `layers.py`: Mega-53 on the full mix. Mega-53's strings stems are near-silent for this recording, even though the strings are prominent in the video, so the orchestra is taken as a **residual**: mix minus the Mega-53 trumpet, bass and drums stems.
2. Transcribe each layer.
   - Solo: MuScriptor, confirmed by Basic Pitch. This stem comes straight from the full mix, and MuScriptor behaves there.
   - In the quiet intro MuScriptor hears nothing before 43 s. Basic Pitch notes there are kept and flagged red.
   - Orchestra, bass and drums: MuScriptor.
3. `arrange_layers_song.py`: split the orchestra by behaviour, not timbre. Short notes attacked with at least two others are chordal hits (the brass choir); everything else is lines and pads.
4. `arranger.arrange_layers`: full contest-band lineup plus percussion.

| Layer | Band parts |
|---|---|
| Solo | Solo Cornet |
| Orchestra lines (top moving line) | Euphonium countermelody; each note placed in the octave nearest the previous one |
| Orchestra lines + pads | Flugelhorn, Solo/1st/2nd Horn, 1st/2nd Baritone, in close position |
| Orchestra hits | Repiano, 2nd/3rd Cornet, 1st/2nd Trombone |
| Bass | E♭ Bass; B♭ Bass an octave below where comfortable; Bass Trombone while the choir plays |
| Drums | Percussion (kit, unpitched notation) |
| — | Soprano Cornet tacet |

**Output:** `data/mikkel/arranged-band/brass-band.{musicxml,pdf,mp3}`.
- MuseScore round trip: all 17 pitched parts match, with correct brass sounds; the drum kit is recognised.

**Known limits:**
- Many solo notes are red: MuScriptor-only or Basic Pitch-only.
- The key estimate is C major. The bass has an F pedal and B naturals are frequent, so this could be F lydian; confirm by ear.
- Pads are one chord per beat. There's no articulation, dynamics or phrasing yet.
- Unison doubling of the paired parts (1st/2nd Baritone, 1st/2nd Horn) appears where the chord has fewer tones than players.

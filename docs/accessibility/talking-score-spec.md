# Talking score: specification

The talking score is the text form of a score. A screen-reader user navigates it by part, bar, beat and note, and each stop produces one announcement string. The Rust core generates the strings (`announce()`), so every app speaks the same words. The apps provide navigation, focus and speech through the platform screen reader; they never self-voice.

Conformance vectors: [talking-score-vectors.json](talking-score-vectors.json). Every example in this document is one of those cases. Where the text and the vectors disagree, the vectors win and the text gets fixed.

## 1. Data it reads

The input is the Composition plus the arrangement: parts, bars, events. §6 gives the JSON shape. The fields come from the Composition schema:

| Field | Source | Notes |
|---|---|---|
| pitch | `notes[].pitch` (MIDI, concert) plus the spelled written pitch from the arranged part | Always announce the **spelled** pitch (step, alter, octave), never the MIDI number |
| onset, duration | `start`, `dur` in ticks (`ticks_per_beat` = 24), spelled into type + dots + ties + tuplets by the MusicXML writer | The announcer uses the spelled values, so it matches the printed page |
| confidence | `notes[].confidence`, float 0–1 | Below 0.7 the engine colours the note red today |
| sources | `notes[].sources[]` | Model names, e.g. `swiftf0`, `muscriptor`, `basic-pitch` |
| free-time region | `Composition.free_regions[]` = `{start, end` (ticks)`, start_s, end_s, tempo_bpm, notation: "proportional"\|"tempo", label: "ad lib."}` | Inside a region, beat positions are synthetic (evenly spaced), so the announcer uses performed seconds instead (§4.8) |
| performed time | `onset_s`, `offset_s`, `performed_dur` (ticks) | Seconds from the start of the recording |
| articulations | `articulations[]`: `staccato`, `fermata` (more later) | |

## 2. Settings

| Setting | Values | Default |
|---|---|---|
| `lang` | `en`, `nb` | UI language |
| `pitch_mode` | `written`, `concert` | `written` for a single part; `concert` for the full score |
| `verbosity` | `brief`, `standard`, `full` | `standard` |
| `octave_style` | `scientific` (C4 = middle C), `helmholtz` (nb only, §3.3) | `scientific` |
| `announce_confident` | bool; in `full`, say "confident" for notes ≥ 0.7 | false |

## 3. Pitch names

### 3.1 English

`<Letter>[-<accidental>] <octave>`

- Accidentals: `sharp`, `flat`, `double-sharp`, `double-flat`.
- Say `natural` only when the key signature would otherwise alter that letter. For example, C in written D major is "C-natural 5", but C in C major is "C 5".
- Examples: "B-flat 4", "F-sharp 4", "C-natural 5", "F-double-sharp 3", "B 4".

### 3.2 Norwegian bokmål

Norwegian musicians use German-derived names. Writing "B-flat" style names in Norwegian would be wrong.

| Written | nb | | Written | nb |
|---|---|---|---|---|
| C | C | | C♯ / C♭ | Ciss / Cess |
| D | D | | D♯ / D♭ | Diss / Dess |
| E | E | | E♯ / E♭ | Eiss / **Ess** |
| F | F | | F♯ / F♭ | Fiss / Fess |
| G | G | | G♯ / G♭ | Giss / Gess |
| A | A | | A♯ / A♭ | Aiss / **Ass** |
| **B♮** | **H** | | B♯ / **B♭** | Hiss / **B** |

- Double accidentals: `<name of the natural letter> dobbeltkryss` / `<…> dobbelt-b`, e.g. F𝄪 = "F dobbeltkryss", B𝄫 = "H dobbelt-b". This is a fallback. **Open question:** whether players expect "Fississ"/"Bess"-style names; ask brass-band players.
- No "natural" word is needed in nb, because the name already says the alteration: C♮ = "C", C♯ = "Ciss".
- Instrument keys follow the same names: "kornett i B", "althorn i Ess", "Ess-bass", "B-bass".

### 3.3 Octaves

- `scientific` (both languages): the number follows the name, with C4 = middle C. The octave changes at C, so B3 is one semitone below C4. "Ess 5", "E-flat 5".
- `helmholtz` (nb, optional): C2 = "store C", C3 = "lille c", C4 = "enstrøken c", C5 = "tostrøken c", C6 = "trestrøken c". Example: E♭5 = "tostrøken ess". **Open question:** whether band players use this at all. Scientific stays the default.

### 3.4 Written versus concert pitch

- Default: a single part is shown and spoken in **written** pitch. That is what the player reads (brass-band parts are transposing, except the bass trombone and percussion).
- The mode is announced **when it changes**, not on every note:
  - en: "Concert pitch" / "Written pitch, Cornet in B-flat"
  - nb: "Klingende tone" / "Skrevet tone, kornett i B"
- `full` verbosity gives both: "written B-flat 4, sounds A-flat 4" / "skrevet B 4, klinger Ass 4".
- The written pitch comes from the part's `<transpose>` (chromatic, diatonic, octave-change). Concert = written + chromatic semitones, and the core must keep the diatonic spelling.

## 4. Announcement grammar

```
announcement := [region_change ". "] [part_change ". "] location ": " body {", " modifier}
location     := [bar_part ", "] position          (standard, full)
              | beat_short                         (brief)
bar_part     := "bar" N [" of " TOTAL (full)] {", " bar_change}
position     := beat_position | time_position      (time_position inside ad lib)
body         := note | held | rest | bar_rest | chord | unpitched
modifier     := tie | tuplet | articulation | dynamic | performed | confidence   (in this order)
```

- Separators are `", "` and `". "`, so the screen reader pauses between parts.
- Numbers are digits. The decimal separator follows the locale (nb "2,5").
- Casing: the apps pass the string as is. Only region and part changes start with a capital letter.
- `bar_part` appears when the bar differs from the context (the previous announcement), and always when navigating by bar.
- `bar_change` lists what changes at this bar, in this order:
  - key: en "key 3 sharps" / nb "3 kryss"; "key 1 flat" / "1 b"; "no sharps or flats" / "ingen faste fortegn"
  - time: en "3 4 time" / nb "3 fjerdedels takt"; en "6 8 time" / nb "6 åttendedels takt"
  - tempo: "tempo 136" / "tempo 136"
  - rehearsal mark: "rehearsal A" / "øvingsbokstav A"

### 4.1 Positions (beats)

Beat unit:
- the time-signature denominator
- in compound time (6/8, 9/8, 12/8), a dotted quarter, with numerator ÷ 3 beats per bar

The offset inside a beat is `num/den` of a beat.

| Offset | en | nb |
|---|---|---|
| 0 | `beat 2` | `slag 2` |
| 1/2 | `beat 2 and` | `slag 2-og` |
| 1/4 | `beat 2 e` | `slag 2, 2. av 4` |
| 3/4 | `beat 2 a` | `slag 2, 4. av 4` |
| 1/3, 2/3 | `beat 2, triplet 2` / `triplet 3` | `slag 2, triol 2` / `triol 3` |
| other | `beat 2 plus 1/6` | `slag 2 pluss 1/6` |

- `brief` drops the word: "2:", "2 and:".
- **Open question:** Norwegian counting for sixteenths. Band teachers may say "en-e-og-a" in Norwegian too; ask players.

### 4.2 Durations

| type | en standard | en brief | nb standard | nb brief |
|---|---|---|---|---|
| breve | double whole note | double whole | brevis | brevis |
| whole | whole note | whole | helnote | hel |
| half | half note | half | halvnote | halv |
| quarter | quarter note | quarter | fjerdedelsnote | fjerdedel |
| eighth | eighth note | eighth | åttendedelsnote | åttendedel |
| 16th | sixteenth note | sixteenth | sekstendedelsnote | sekstendedel |
| 32nd | thirty-second note | thirty-second | trettitodelsnote | trettitodel |
| 64th | sixty-fourth note | sixty-fourth | sekstifiredelsnote | sekstifiredel |

- Dots go before the type: en `dotted`, `double-dotted`; nb `punktert`, `dobbeltpunktert`.
- Rests: en "`<type>` rest" ("quarter rest"); nb "`<type>`spause" ("fjerdedelspause", "helpause", "halvpause", "åttendedelspause").
- A bar of rest: "rest, whole bar" / "pause hele takten".
- Consecutive rest bars (when the part view collapses them): "bars 82 to 88: rest, 7 bars" / "takt 82 til 88: pause, 7 takter".

### 4.3 Ties

- **Note navigation skips tie continuations.** The note that starts a tie announces what follows:
  - one continuation: en "tied to `<dur>`[ in bar N]" / nb "bundet til `<dur>`[ i takt N]". Add "in bar N" only when the continuation is in another bar.
  - a chain of more than two notes: en "tied, `<beats>` beats in all" / nb "bundet, `<beats>` slag i alt". Halves are spoken as "3 and a half" / "3 og et halvt".
- **Beat navigation** can land where a tied note is still sounding. It then announces kind `held`: en "`<pitch>` held, from bar N beat B" / nb "`<pitch>` holdes, fra takt N slag B". Drop "bar N" when it's the same bar.

### 4.4 Tuplets

- Position uses the tuplet grid (§4.1).
- Modifier:
  - triplet: en "triplet, i of 3" / nb "triol, i av 3"
  - duplet, quintuplet, sextuplet: say `actual`/`normal` in words. en "5 in the time of 4, 1 of 5"; nb "5 på 4, 1 av 5"
- The duration spoken is the printed type ("eighth note, triplet, 2 of 3").

### 4.5 Chords, divisi, percussion

- Chord: en "chord, 3 notes: C 5, E 5, G 5, quarter note" / nb "akkord, 3 toner: C 5, E 5, G 5, fjerdedelsnote". Pitches go from low to high.
- Unpitched percussion: instrument names joined with "and" / "og", then the duration. "bass drum and hi-hat, eighth note" / "stortromme og hi-hat, åttendedelsnote".

### 4.6 Articulations and dynamics

- Articulations: staccato / staccato, accent / aksent, tenuto / tenuto, marcato / marcato, fermata / fermat.
- Dynamics are announced on the note where they take effect, always in full words (screen readers mangle "mf"). The words are the same in both languages: pianissimo, piano, mezzo-piano, mezzo-forte, forte, fortissimo.
- Hairpins: "crescendo" / "crescendo", "diminuendo" / "diminuendo" at the start note; "end crescendo" / "slutt crescendo" at the end note.

### 4.7 Confidence

| confidence | en | nb |
|---|---|---|
| ≥ 0.7 | (nothing; `full` + `announce_confident`: "confident") | (nothing / "sikker") |
| 0.4 – < 0.7 | uncertain | usikker |
| < 0.4 | very uncertain | svært usikker |

- `full` adds "confidence 55 percent, source SwiftF0" / "sikkerhet 55 prosent, kilde SwiftF0". With several sources, they are joined with "and" / "og".
- The 0.7 threshold matches the engine's red colouring today.
- **Open question:** the 0.4 threshold for the second level is a proposal. It should be calibrated against the measured precision per confidence bin (`10-benchmark-results.md`).
- A note the user has reviewed and accepted ("Mark as checked") no longer announces uncertainty.

### 4.8 Free time (*ad lib*)

In a region from `Composition.free_regions[]`:

- **Entering**, before the first announcement inside:
  - en "Ad lib, free time, bars A to B, about S seconds." / nb "Ad lib, fritt tempo, takt A til B, omtrent S sekunder."
  - S = `end_s − start_s`, rounded to whole seconds.
- **Position** uses the performed time from the start of the recording, not the synthetic beat. That position matches "Listen to this bar" and the original audio.
  - Under 60 s: "at 22 seconds" / "ved 22 sekunder".
  - Otherwise: "at 1 minute 5 seconds" / "ved 1 minutt 5 sekunder".
- **Performed length:** when the performed duration is ≥ 1.0 s, add "held about X seconds" / "holdes omtrent X sekunder" after the articulations. X is rounded to 0.5 s. Shorter notes get no length.
- **Leaving:** en "A tempo, 136 beats per minute." / nb "A tempo, 136 slag per minutt."
- `notation: "tempo"` regions (the user entered a tempo instead): announce "Ad lib" on entry, but keep beat positions.

### 4.9 Part change

- When the part differs from the context, the part name comes first as its own sentence: "Solo Horn." / "Solo althorn."
- nb part names use the table in §7.

## 5. Navigation

The same commands on every platform. The apps map them to native gestures.

| Command | Result | Apple (VoiceOver) | Android (TalkBack) | Windows (Narrator/NVDA) and Studio (keyboard) |
|---|---|---|---|---|
| Next / previous note | next event in the part (skips tie continuations) | rotor "Notes", swipe down/up | swipe right/left on the score list (one item per event) | → / ← |
| Next / previous beat | event or `held` at the next beat | rotor "Beats" | custom action "Next beat" | Ctrl+→ / Ctrl+← |
| Next / previous bar | first event of the bar, with `bar_part` | rotor "Bars" | custom action "Next bar" | Ctrl+↓ / Ctrl+↑ (Studio: Alt+↓/↑) |
| Next / previous part | same time position in the next part, with `part_change` | rotor "Parts" | custom action "Next part" | Ctrl+Shift+↓ / ↑ |
| Next / previous uncertain note | next event with confidence < 0.7 | rotor "Uncertain notes" | custom action | U / Shift+U (while the score has focus) |
| Go to bar | "Go to bar" field, then that bar | custom action "Go to bar" | custom action | Ctrl+G |
| Read bar | every event in the bar, in `brief` form, joined with ", " | custom action "Read bar" | custom action | R |
| Play this bar / play from here | plays with audio; focus stays | custom actions | custom actions | P / Shift+P |
| Where am I | full-verbosity announcement of the current event | custom action | custom action | W |

- The score view exposes the current event as its **value**:
  - A: `.accessibilityValue`
  - K: `stateDescription`
  - W: `IValueProvider`
  - S: `aria-valuetext` on a focusable `role="application"` region used only inside the score, or better, a roving-tabindex list
- Moving sends the new announcement.

## 6. JSON shape

`core` exports this with `talking_score(composition, arrangement) -> TalkingScore`. Apps call `announce(ts, cursor, context, settings) -> String` and never build strings themselves.

```json
{
  "version": 1,
  "title": "Mikkel — solo cornet & brass band (draft)",
  "total_bars": 128,
  "free_regions": [
    {"start_bar": 1, "end_bar": 4, "start_s": 0.0, "end_s": 31.5, "tempo_bpm": 60, "notation": "proportional", "label": "ad lib."}
  ],
  "parts": [
    {
      "id": "solo-cornet",
      "name": "Solo Cornet",
      "name_nb": "Solokornett",
      "instrument": "Cornet in B♭",
      "instrument_nb": "kornett i B",
      "transpose": {"chromatic": -2, "diatonic": -1, "octave": 0},
      "bars": [
        {
          "number": 2,
          "key_fifths": 2,
          "time": {"beats": 4, "beat_type": 4},
          "tempo_bpm": null,
          "rehearsal": null,
          "events": [
            {
              "kind": "note",
              "tick": 0,
              "pos": {"beat": 1, "num": 0, "den": 1},
              "type": "eighth", "dots": 0,
              "tuplet": null,
              "tie": null,
              "written": {"step": "B", "alter": -1, "octave": 4},
              "concert": {"step": "A", "alter": -1, "octave": 4},
              "articulations": [],
              "dynamic": null,
              "confidence": 0.55,
              "sources": ["swiftf0"],
              "checked": false,
              "time_s": 2.9,
              "performed_s": 0.4
            }
          ]
        }
      ]
    }
  ]
}
```

- `kind`: `note`, `rest`, `bar-rest`, `chord` (with `pitches: [...]`), `unpitched` (with `instruments`), and `held`. `held` is generated by the navigator, never stored.
- `tie`: `{"start": bool, "stop": bool, "next": {"bar", "type", "dots"}, "chain_beats": number|null}`.
- `tuplet`: `{"actual": 3, "normal": 2, "index": 2}`.
- `pos` is exact (rational), never a float.
- The text export ("talking-score text", one of Play's export formats) renders this structure as:
  - one heading per part
  - a sub-heading per bar
  - one line per event, in `standard` verbosity
  - HTML with `<h2>`/`<h3>`/`<ul>`, and plain text as a fallback

## 7. Norwegian part names (proposal)

| en | nb |
|---|---|
| Soprano Cornet | Sopran-kornett (Ess-kornett) |
| Solo Cornet | Solokornett |
| Repiano Cornet | Repiano-kornett |
| 2nd / 3rd Cornet | 2. / 3. kornett |
| Flugelhorn | Flygelhorn |
| Solo / 1st / 2nd Horn | Solo / 1. / 2. althorn |
| 1st / 2nd Baritone | 1. / 2. baryton |
| 1st / 2nd Trombone | 1. / 2. trombone |
| Bass Trombone | Basstrombone |
| Euphonium | Eufonium |
| E♭ Bass / B♭ Bass | Ess-bass / B-bass |
| Percussion | Slagverk |

**Open question:** whether Norwegian bands say "althorn" or "tenorhorn". Ask players.

## 8. Examples (from the vectors)

| id | en | nb |
|---|---|---|
| note-new-bar-uncertain | bar 2, beat 1: B-flat 4, eighth note, uncertain | takt 2, slag 1: B 4, åttendedelsnote, usikker |
| concert-pitch-mode | bar 2, beat 1: A-flat 4, eighth note, uncertain | takt 2, slag 1: Ass 4, åttendedelsnote, usikker |
| note-sixteenth-position-natural-in-key | beat 3 a: C-natural 5, sixteenth note | slag 3, 4. av 4: C 5, sekstendedelsnote |
| dotted-and-tie-start-across-bar | beat 4 and: G 5, eighth note, tied to dotted eighth note in bar 12 | slag 4-og: G 5, åttendedelsnote, bundet til punktert åttendedelsnote i takt 12 |
| held-from-tie-beat-navigation | beat 1: G 5 held, from bar 11 beat 4 and | slag 1: G 5 holdes, fra takt 11 slag 4-og |
| multi-bar-rest | bars 82 to 88: rest, 7 bars | takt 82 til 88: pause, 7 takter |
| triplet | beat 3, triplet 2: F-sharp 4, eighth note, triplet, 2 of 3 | slag 3, triol 2: Fiss 4, åttendedelsnote, triol, 2 av 3 |
| very-uncertain-and-dynamic-and-articulation | beat 4: A 5, quarter note, accent, fortissimo, very uncertain | slag 4: A 5, fjerdedelsnote, aksent, fortissimo, svært usikker |
| adlib-region-entry | Ad lib, free time, bars 1 to 4, about 32 seconds. bar 1, at 0 seconds: D 4, eighth note | Ad lib, fritt tempo, takt 1 til 4, omtrent 32 sekunder. takt 1, ved 0 sekunder: D 4, åttendedelsnote |
| adlib-inside-fermata | at 22 seconds: D 5, half note, fermata, held about 2.5 seconds | ved 22 sekunder: D 5, halvnote, fermat, holdes omtrent 2,5 sekunder |
| adlib-exit-a-tempo | A tempo, 136 beats per minute. bar 5, beat 1 and: D 4, sixteenth note | A tempo, 136 slag per minutt. takt 5, slag 1-og: D 4, sekstendedelsnote |
| part-change-and-key | Solo Horn. bar 12, key 3 sharps, beat 1: C-sharp 5, quarter note | Solo althorn. takt 12, 3 kryss, slag 1: Ciss 5, fjerdedelsnote |
| full-verbosity-both-pitches | bar 2 of 128, beat 1: written B-flat 4, sounds A-flat 4, eighth note, uncertain, confidence 55 percent, source SwiftF0 | takt 2 av 128, slag 1: skrevet B 4, klinger Ass 4, åttendedelsnote, usikker, sikkerhet 55 prosent, kilde SwiftF0 |

The ad lib examples assume the free-time fix has landed. In today's golden output, bars 1–4 still sit on a fixed 136 bpm grid, with beat gaps of 1–6 s.

## Open questions

1. Norwegian double-accidental names and sixteenth counting (§3.2, §4.1).
2. Helmholtz octave names: offer or drop (§3.3).
3. The second confidence threshold, 0.4 (§4.7).
4. "althorn" or "tenorhorn" (§7).
5. Whether TTS engines read "Ess 5" and "Ass 4" correctly in nb voices (Apple, Google, Microsoft). This is untested; a pronunciation-dictionary entry may be needed. Check in each screen-reader script.

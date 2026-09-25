# Blind A/B listening test: realistic tier vs baseline

**Question:** do listeners prefer the realistic sound tier over the baseline (MuseScore with MS Basic)?
**Acceptance bar** (docs/plan/apps-plan.md §6): the realistic tier is preferred in at least 80% of judgements. With 5 listeners × 5 excerpts that is **20 of 25**. Under chance, 20/25 has a one-sided binomial p of 0.002.

## What is compared

| | Baseline | Realistic |
|---|---|---|
| Source | `data/golden/mikkel-arranged-band/brass-band.mp3`, MuseScore 4.7's own render with MS Basic | `sounds/render.py` output: VSCO 2 CE and Iowa samples adapted per part, seating, early reflections, OpenAIR Central Hall IR |
| Score | `brass-band.musicxml` | the same score, as MIDI exported by the MuseScore CLI |
| Percussion | MS Basic | MS Basic, rendered by FluidSynth. The drums are kept equal so the test isolates the brass. |

## Preparing the material

```sh
uv run --project sounds python sounds/render.py data/runs/sound/mikkel.mid -o data/runs/sound/realistic
uv run --project sounds python sounds/ab-test/generate.py \
  --baseline data/golden/mikkel-arranged-band/brass-band.mp3 \
  --realistic data/runs/sound/realistic/mikkel.realistic.wav \
  --midi data/runs/sound/mikkel.mid -o data/runs/sound/ab-test
```

The generator:
- aligns the two tiers by onset-envelope cross-correlation;
- picks 5 non-overlapping 12 s excerpts, one per fifth of the piece, each at the busiest window of its zone;
- encodes the realistic render to 128 kb/s MP3 like the baseline, and decodes both;
- applies identical cut points, a 50 ms fade-in and a 500 ms fade-out to both tiers;
- matches both to −20 LUFS with a shared peak ceiling of −1 dBFS;
- writes one folder per listener. Excerpt order is shuffled per listener. For each excerpt, the realistic clip is "A" for half the listeners (with 5 listeners, one of the two tiers gets the extra slot at random).

`excerpts.json` records the cut times, the pre-normalisation loudness and a chroma-similarity sanity check per pair; a value near 1 means the two clips contain the same music. `key.json` maps the letters to tiers. **Keep `key.json` away from listeners and out of git.** The test leader should not be the person running the listening session, or should not open the key until all answers are in.

## Running a session

1. Use closed headphones (the same model for every listener if possible) in a quiet room. Set a comfortable level on the first pair, then leave the volume alone.
2. Give the listener their own `listener-N/` folder and `answers.csv`. Say only this: *"Each pair is the same music played two ways. For each pair, pick the version that sounds more like a real brass band. You can replay as often as you like. There is no 'same' option."*
3. The listener may switch between A and B freely. Plan about 10 minutes per listener.
4. Record the answer (A or B), a confidence from 1 to 3, and an optional comment.
5. Do not discuss the tiers until every listener is done.

**Listeners:** 5 people, ideally at least 2 brass-band players and at least 1 non-musician. Note their background in a separate sheet, not in the answer file.

## Scoring

```sh
uv run --project sounds python sounds/ab-test/score.py data/runs/sound/ab-test
```

This prints per-listener and per-excerpt counts, the overall share, the binomial p-value and PASS/FAIL against the 80% bar. Report the measured numbers together with the render settings (`realistic/mikkel.realistic.json`) and the commit.

## Known confounds (open questions)

- The baseline is MuseScore's own mix. Which panning and reverb MuseScore applied to this export has not been checked. The realistic tier adds a measured room, so a preference could come from the room alone. **Follow-up test:** baseline plus the same room convolution against the realistic tier.
- The two tiers differ in loudness balance between sections. Loudness is matched only per excerpt overall.
- The score has no dynamics (every note is mf in the MIDI), so both tiers play with flat dynamics.

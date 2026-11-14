# 19 — Printed music from a picture: which recogniser

Date: 2026-11-13. The question: a player has a screenshot of a score, a photo of a page on a stand, or a PDF,
and wants it in the app as a score or a tab, the way a recording becomes one. Which optical music recogniser
should the engine run for that? The answer is measured on pages whose notes are known.

## Short answer

**homr**, run as a separate program by an adapter. On the benchmark's pages it reads a screenshot almost
without error. On the simulated phone photo it still finds nearly every pitch, but gets one note length in
thirteen wrong, so about one bar in five has an error in it. The other two tried are not as good on the
screenshot and do not read the photo at all.

| Recogniser | Screenshot: pitch | note | bars right | Photo: pitch | note | bars right | Time a page | Install |
|---|---|---|---|---|---|---|---|---|
| homr 0.7.1 | **0.997** | **0.997** | **0.994** | **0.986** | **0.925** | **0.782** | 3 to 5 s | 475 MB, and 139 MB of weights |
| Audiveris 5.11.0 (page enlarged to 300 dpi first) | 0.970 | 0.957 | 0.874 | 0.311 | 0.203 | 0.028 | 5 to 10 s | 162 MB |
| oemer 0.1.5 (on the older NumPy and OpenCV it needs) | 0.662 | 0.594 | 0.240 | 0.624 | 0.488 | 0.018 | 2.5 to 4 min | 0.4 GB, and 209 MB of weights |

- *pitch* is the F1 of notes found at the right pitch, in order; *note* asks for the right length too; *bars
  right* is the share of bars with every note right in pitch, place and length. All are over the whole set
  (1,025 notes in 325 bars a set), staff by staff in score order.
- Times are on an Apple M5 Pro with other work running, the recogniser already installed and its weights
  in place, on the CPU.
- `scribe bench sheet-image` holds homr's row as a gate, on readings kept in the repository: CI does not run
  homr. `python -m scribe_eval.sheet_image_bench prepare --recogniser <adapter>` and `report --recogniser
  <adapter>` make a row for another adapter.

## The pages

Nine pieces are written in [`sheet_image_bench.py`](../../../eval/scribe_eval/sheet_image_bench.py) and engraved
by MuseScore 4.7.5 (the fixtures record the version; another may lay a page out differently), so every note on
a page is known: *Old Hundredth* (Louis Bourgeois, 1551, public domain) as one line and as a hymn on two staves
with chords, and invented pieces: a march in 2/4 with sixteenths and dotted rhythms, a waltz in the bass clef, a
jig in 6/8, four parts in score (two pages), a line of 96 bars (two pages), a guitar line with a tab staff under
it, and a tune that starts on a pickup and changes key and time twice. The invented lines have key signatures
of up to three flats and sharps, accidentals, rests and ties over the bar line. Each page is kept twice:

- **screenshot**: the page as a notation program shows it, an A4 page 1,075 pixels wide (130 dpi), which is what
  a phone's screenshot of a score is.
- **photo**: the same page as a phone would photograph it, 1,000 pixels across with the desk around it, so the
  page is narrower than the screenshot's and a staff is about seven pixels from line to line: turned up to
  three degrees, seen at an angle from below and from one side, half as bright in one corner as in the other,
  with a shadow across it, blurred, with noise, saved as a JPEG at quality 55.

**What the set is, and is not.** It is small, synthetic, and of one kind:

- The photo is a flat page put through a formula. A real photo has a curled page, glare, a finger, a stand's
  ledge across the bottom system, motion blur and a lens. The first photo set made for this note was sharper
  than the screenshot (1,400 pixels wide, a soft shadow), and homr read it as well as the screenshot, which
  said more about the set than about homr; the numbers above are on the harder one. A set of real photographs
  is the measurement still missing.
- All but one piece are single lines with one voice. The hymn has chords on two staves; nothing has more than
  one voice on a staff.
- One piece has a pickup and changes of key and time; none has slurs, articulations, dynamics, lyrics, repeats
  and voltas, grace notes, tuplets, multi-bar rests, a C clef or a transposing part's key.
- One engraver, one font, one house style. No handwriting, no old engraving, no scan of a printed part.
- With nine pieces, one misread time signature moves a set's numbers by a point.

It shows whether the notes come through at all, and it cannot rank two recognisers that are close.

## What each one did

**homr** ([liebharc/homr](https://github.com/liebharc/homr), AGPL-3.0). A segmentation network finds the staves,
and a transformer reads each staff into notes. It takes several pictures or a PDF in one call and joins them into
one score, finds the page's title with an OCR model, and writes MusicXML.

- Of the 1,025 notes of the screenshots it found 1,024 at the right pitch and length, and read five notes that
  are not there, on the guitar page, where it takes the tab staff for a staff of notes.
- Of the photos' it found 1,011 at the right pitch and 948 with the right length too: at seven pixels a staff
  space, dots and flags are what goes first. It lost two bars of 325.
- It misreads time signatures: the 4/4 beside the pickup as 3/4 in the screenshot of the changing tune, and the
  hymn's 4/4 as 3/4 in its photo. The notes in those bars are right.
- A system of two staves (the hymn) comes out as one part with two staves, the four-part score as four parts.
- It does not read a tab staff, and it does not read the small 8 under a guitar's clef: a guitar's line comes out
  an octave above where it sounds. The engine knows the instrument and takes it down (`sheet-tab`), and the
  benchmark compares what the staff shows.
- It gives no confidence for what it reads.
- It writes notes, rests, ties, chords, clefs, keys and time signatures. It writes no part names (every part is
  "Voice" or "Piano"), no dynamics, lyrics or tempo.
- It turns a photo the way its EXIF orientation says. A page on its side without that tag is not read.
- It decodes whatever it is handed: a 33 KB PNG of 12,000 by 12,000 pixels took it to 4 GB of memory. The
  engine reads a picture's size from its header and refuses one over 50 million pixels before homr sees it.
- The engine runs it on the CPU with its 32-bit weights on every computer (on a Mac homr would otherwise use a
  16-bit segmentation model through Core ML), so a page reads the same everywhere; the numbers above are that
  configuration.

**Audiveris** ([Audiveris/audiveris](https://github.com/Audiveris/audiveris), AGPL-3.0, a Java program with its
own runtime). The classic rule-based recogniser, with a page editor of its own.

- It refuses a page at screenshot resolution outright ("interline value of 9 pixels … try 300 DPI"). The numbers
  above are with every page enlarged to 2,480 pixels wide first; without that it reads nothing.
- On the enlarged screenshots it is close on pitch, drops whole bars and gets rhythm wrong more often (bars
  right 0.87).
- On the photos it falls apart: it finds a little over half the bars and three notes in ten. It is made for flat
  scans.

**oemer** ([BreezeWhite/oemer](https://github.com/BreezeWhite/oemer), MIT; homr began from its segmentation).
The last release is from 2025 and it no longer runs on what `pip install oemer` gives today: it uses NumPy
names that were removed, and with those restored it fails on a current OpenCV. The numbers above are with
NumPy 1.23, OpenCV 4.6 and ONNX Runtime 1.16 on Python 3.10.

- It takes two to four minutes a page on the CPU, where the others take seconds.
- On the screenshots it gave nothing for one piece of nine and found 84 % of the bars of the rest; pitches are
  wrong in runs (a clef or key read wrong carries through a line).
- On the photos it finds the notes about as often and a quarter of the bars.

**Not measured.** The end-to-end research models (Sheet Music Transformer and its successors, Legato) write
\*\*kern or ABC, not MusicXML, and are published as research code rather than as a program to run on a page; a
fair run needs a converter of its own per model. homr's transformer is trained on public sets those models are trained on too (GrandStaff, PrIMuS).
They are worth a row here when one of them ships as something an adapter can call.

## Licence, and what is installed where

homr's code and weights are AGPL-3.0. The engine runs `homr` as a program of its own, in its own environment,
through the same adapter contract as the models: nothing of Brasscribe imports it or links to it, and it is in no
app (the phone sends the picture to the computer). homr's own licence FAQ names a separate process as the clear
separation. Its transformer was trained on, among others, Camera-PrIMuS, whose copy on Hugging Face is
CC BY-NC 4.0; Brasscribe is non-commercial, and [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md) says so
for what it reads. Audiveris has the same licence and the same answer. Neither could be put inside a phone app
distributed through an app store without the app taking the AGPL.

Nothing of homr is redistributed by Brasscribe. Where its environment is installed, the package (475 MB with
what it depends on) comes from PyPI onto the user's computer, and its weights (139 MB) from homr's own release
on GitHub, fetched by the adapter runner and checked against pinned SHA-256s. No installation gets it unasked:
the engine offers the two profiles only where the environment is there. Bandroom does not install it yet, so in
Bandroom the profiles do not show until it does, with a notice of what is being installed and under which
licence.

## Doubt

homr says nothing about how sure it is. Two signs of a misreading were tried:

- **The bar does not add up.** A bar whose notes and rests on a staff are not what the time signature says is
  misread somewhere. Each staff is counted by itself. When the bars around a bar agree on another amount, the
  time signature is what was misread (homr does that, above), and one doubt at the first such bar stands for
  all of them.
- **A second reading differs.** The page enlarged 1.4 times and read again, bar against bar. On the first sets
  made for this note it found one wrong bar that the first sign did not, of nine, for twice the time; the
  photos' errors were the same at both sizes. It is not used.

On the sets above (bars compared where a staff's bar count came out right):

| Set | Bars read wrong | of which marked | Bars read right that are marked |
|---|---|---|---|
| screenshot | 2 | 1 | 1 (the bar with the misread time signature) |
| photo | 36 | 30 | 10 |

A wrong pitch in a bar that adds up is not marked: that is what a player checking the score against the page
has to look for. The suite reports the shares as `doubt_found` and `doubt_false`.

## What the engine does with it

Two profiles, one for each target ([engine/README.md](../../../engine/README.md)): `sheet` keeps the page as a
score (parts, PDF, MIDI, MP3, braille, talking score) and `sheet-tab` writes its first staff as tab through the
fingering a recording's notes get. Not done yet, and worth doing next:

- arranging a read lead sheet or piano page for a band lineup, and transposing a read part for a seat;
- reading a tab staff (fret numbers), which no recogniser tried here does;
- choosing which staff of several becomes the tab;
- taking MusicXML itself as an upload, which needs no recogniser at all.

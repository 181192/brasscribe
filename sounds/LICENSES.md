# Band sounds: sources and licences

Every sample in the band SoundFonts (`brasscribe-band-16bit.sf2`, `brasscribe-band-mobile.sf2`, the sound pack in
`band-sounds.json`) and in the offline renderer comes from the sources below. Each file is pinned by URL, size and
sha256 in [manifest.json](manifest.json). No commercial library, no copyrighted recording and no recording of a
brasscribe user is used. `band-notice.txt` is the plain-text notice the apps ship next to the SoundFont.

| Source | Licence | What the band uses it for |
|---|---|---|
| [VSCO 2 Community Edition](https://github.com/sgossner/VSCO-2-CE), Versilian Studios LLC | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | Brass: trumpet (the cornet desks, soprano cornet), trumpet vibrato sustains (the solo cornet), F horn (tenor horns), tenor trombone (baritones, euphonium, trombones), tuba (E♭ and B♭ bass). Percussion (VSCO 1 Percussion): the muted concert bass drum, concert snare and clash cymbals of the band kit. |
| [University of Iowa Musical Instrument Samples](https://theremin.music.uiowa.edu/MIS.html), Electronic Music Studios, Lawrence Fritts | "may be downloaded and used for any projects, without restrictions" | Trumpet (the trumpet, one cornet desk, the flugelhorn's top), horn (flugelhorn, tenor-horn fill), tenor trombone (range fill), bass trombone, tuba (pedal notes and layer fill). |
| [MuseScore MS Basic](https://github.com/musescore/MuseScore/tree/master/share/sound) SoundFont | MIT (notice below) | The band kit's hi-hats, toms, side stick, ride, tambourine and hand percussion; the pop kit (MS Basic Standard, unchanged). |
| [OpenAIR](https://www.openair.hosted.york.ac.uk/) Central Hall, University of York: Alexander Vilkaitis, Ilias Antonopoulos, Joska De Langen, Xuan Liu | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | The concert-hall impulse response of the offline renderer (`sounds/render.py`). Not in the apps. |

Candidates that were checked and not used:

- **Philharmonia Orchestra samples**: free to use in music, but the terms forbid redistributing the samples themselves, which a SoundFont in an app does.
- **Sonatina Symphonic Orchestra**: Creative Commons Sampling Plus 1.0, a retired licence that restricts redistribution of the whole work.
- **University of Iowa trumpet vibrato runs**: usable, but the VSCO vibrato sustains are closer in tone to the cornet desks; not bundled.
- **VSCO suspended cymbal and timpani**: no part the arranger writes plays them.

The offline renderer's other OpenAIR rooms (Jack Lyons Concert Hall, Dixon Studio Theatre, St Margaret's Church)
are CC BY 4.0 with the attributions in `manifest.json`. The Usina del Arte hall is not used until its licence is
confirmed.

## MS Basic notice

MS Basic is a scaled-down MuseScore_General.sf2. The notice it carries, which must be kept in derivative works:

> FluidR3 (original version) by Frank Wen Copyright (c) 2000-02
>
> Mono conversion (FluidR3Mono) by Michael Cowgill Copyright (c) 2014-17
>
> Adaptation for MuseScore_General.sf2 by S. Christian Collins Copyright (c) 2018-19
>
> Temple Blocks instrument provided by Ethan Winer Copyright (c) 2002
>
> Drumline Cymbals provided by Michael Schorsch Copyright (c) 2016
>
> MuseScore_General.sf2 is shared under the MIT license as described in COPYING, as was FluidR3Mono and FluidR3 before it.

COPYING:

> Mono version: Copyright (c) 2014-16 Michael Cowgill
> Copyright (c) 2000-2002, 2008 Frank Wen <getfrank@gmail.com>
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
> documentation files (the "Software"), to deal in the Software without restriction, including without limitation
> the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of
> the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
> THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
> TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

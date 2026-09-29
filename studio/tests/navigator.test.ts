import { describe, expect, it } from "vitest";
import { Navigator } from "../src/lib/navigator";
import { buildTalkingScore, concertFifths, transposePitch } from "../src/lib/talkingxml";

const n = (step: string, oct: number, dur: number, type: string, extra = "", alter = 0) =>
  `<note><pitch><step>${step}</step>${alter ? `<alter>${alter}</alter>` : ""}<octave>${oct}</octave></pitch><duration>${dur}</duration>${extra}<type>${type}</type></note>`;

// Solo Cornet (B-flat, written D major), 4/4, divisions 6.
const XML = `<?xml version="1.0"?>
<score-partwise version="4.0">
  <work><work-title>Fixture</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Solo Cornet</part-name></score-part>
    <score-part id="P2"><part-name>Solo Horn</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>6</divisions><key><fifths>2</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
      <direction><direction-type><dynamics><mf/></dynamics></direction-type></direction>
      <note color="#D0021B"><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>3</duration><type>eighth</type></note>
      ${n("G", 4, 3, "eighth")}
      ${n("C", 5, 6, "quarter", "<notations><articulations><staccato/></articulations></notations>")}
      <note><rest/><duration>6</duration><type>quarter</type></note>
      ${n("G", 5, 6, "quarter", '<tie type="start"/>')}
    </measure>
    <measure number="2">
      ${n("G", 5, 12, "half", '<tie type="stop"/>')}
      <note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>2</duration><time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification><type>eighth</type><notations><tuplet type="start"/></notations></note>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>2</duration><time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification><type>eighth</type></note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification><type>eighth</type><notations><tuplet type="stop"/></notations></note>
      ${n("D", 5, 6, "quarter")}
      <note><chord/><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>6</duration><type>quarter</type></note>
    </measure>
    <measure number="3"><note><rest measure="yes"/><duration>24</duration></note></measure>
    <measure number="4"><note><rest measure="yes"/><duration>24</duration></note></measure>
    <measure number="5">${n("E", 5, 24, "whole")}</measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes><divisions>6</divisions><key><fifths>3</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>
        <transpose><diatonic>-5</diatonic><chromatic>-9</chromatic></transpose></attributes>
      ${n("C", 5, 24, "whole", "", 1)}
    </measure>
    <measure number="2">${n("E", 5, 24, "whole")}</measure>
    <measure number="3"><note><rest measure="yes"/><duration>24</duration></note></measure>
    <measure number="4"><note><rest measure="yes"/><duration>24</duration></note></measure>
    <measure number="5"><note><rest measure="yes"/><duration>24</duration></note></measure>
  </part>
</score-partwise>`;

describe("talking score from MusicXML", () => {
  const ts = buildTalkingScore(XML);

  it("reads parts, bars, positions, ties, tuplets, chords and bar rests", () => {
    expect(ts.title).toBe("Fixture");
    expect(ts.total_bars).toBe(5);
    const [cornet, horn] = ts.parts;
    expect(cornet.name_nb).toBe("Solokornett");
    expect(horn.name_nb).toBe("Solo althorn");
    const b1 = cornet.bars[0].events;
    expect(b1.map((e) => e.kind)).toEqual(["note", "note", "note", "rest", "note"]);
    expect(b1[0]).toMatchObject({ pos: { beat: 1, num: 0, den: 1 }, uncertain: true, dynamic: "mf", concert: { step: "A", alter: -1, octave: 4 } });
    expect(b1[1].pos).toEqual({ beat: 1, num: 1, den: 2 });
    expect(b1[2].articulations).toEqual(["staccato"]);
    expect(b1[4].tie).toMatchObject({ start: true, next: { bar: 2, type: "half", dots: 0 } });
    const b2 = cornet.bars[1].events;
    expect(b2[0].skip).toBe(true);
    expect(b2[1]).toMatchObject({ pos: { beat: 3, num: 0, den: 1 }, tuplet: { actual: 3, normal: 2, index: 1 } });
    expect(b2[2]).toMatchObject({ pos: { beat: 3, num: 1, den: 3 }, tuplet: { index: 2 } });
    expect(b2[4].kind).toBe("chord");
    expect(b2[4].pitches?.map((p) => p.written.step)).toEqual(["D", "F"]);
    expect(cornet.bars[2].events[0]).toMatchObject({ kind: "bar-rest", bars: 2 });
    expect(cornet.bars[3].events[0].skip).toBe(true);
    expect(cornet.bars[1].startTick).toBe(3840);
  });

  it("transposes with the diatonic spelling kept", () => {
    expect(transposePitch({ step: "C", alter: 1, octave: 5 }, { chromatic: -9, diatonic: -5, octave: 0 })).toEqual({ step: "E", alter: 0, octave: 4 });
    expect(transposePitch({ step: "B", alter: -1, octave: 4 }, { chromatic: -2, diatonic: -1, octave: 0 })).toEqual({ step: "A", alter: -1, octave: 4 });
    // Written D major on B-flat and E-flat instruments sounds in C; C major on E-flat soprano sounds in E-flat.
    expect([concertFifths(2, -2), concertFifths(3, -9), concertFifths(2, -14), concertFifths(0, 3)]).toEqual([0, 0, 0, -3]);
  });

  it("navigates by note, bar, beat, part and uncertain note, in both languages", () => {
    const nav = new Navigator(ts);
    expect(nav.goBar(0).text).toBe("bar 1, beat 1: B-flat 4, eighth note, mezzo-forte, uncertain");
    expect(nav.nextNote()!.text).toBe("beat 1 and: G 4, eighth note");
    expect(nav.nextNote()!.text).toBe("beat 2: C-natural 5, quarter note, staccato");
    expect(nav.nextNote()!.text).toBe("beat 3: quarter rest");
    expect(nav.nextNote()!.text).toBe("beat 4: G 5, quarter note, tied to half note in bar 2");
    // The tie continuation is skipped.
    expect(nav.nextNote()!.text).toBe("bar 2, beat 3: F-sharp 4, eighth note, triplet, 1 of 3");
    expect(nav.nextNote()!.text).toBe("beat 3, triplet 2: A 4, eighth note, triplet, 2 of 3");
    nav.nextNote();
    expect(nav.nextNote()!.text).toBe("beat 4: chord, 2 notes: D 5, F-sharp 5, quarter note");
    expect(nav.nextNote()!.text).toBe("bars 3 to 4: rest, 2 bars");
    expect(nav.nextNote()!.text).toBe("bar 5, beat 1: E 5, whole note");
    expect(nav.nextNote()).toBeNull();

    // Beat navigation lands on the held tie.
    nav.goBar(0);
    for (let i = 0; i < 3; i++) nav.nextBeat();
    expect(nav.nextBeat()!.text).toBe("bar 2, beat 1: G 5 held, from bar 1 beat 4");

    // Part change keeps the time position and gives the new key.
    expect(nav.nextPart()!.text).toBe("Solo Horn. bar 2, key 3 sharps, beat 1: E 5, whole note");
    expect(nav.goBar(3).text).toBe("bar 4: rest, whole bar");

    nav.setPart(0);
    nav.goBar(1);
    expect(nav.nextUncertain(-1)!.text).toBe("bar 1, beat 1: B-flat 4, eighth note, mezzo-forte, uncertain");
    expect(nav.readBar()).toBe("bar 1, 1: B-flat 4 eighth, mezzo-forte, uncertain, 1 and: G 4 eighth, 2: C-natural 5 quarter, staccato, 3: quarter rest, 4: G 5 quarter, tied to half note in bar 2");
    expect(nav.whereAmI()).toBe("bar 1 of 5, beat 1: written B-flat 4, sounds A-flat 4, eighth note, mezzo-forte, uncertain");
    expect(nav.setPitchMode("concert")).toBe("Concert pitch");
    expect(nav.setPitchMode("written")).toBe("Written pitch, Cornet in B-flat");

    const nb = new Navigator(ts, undefined, "nb");
    expect(nb.goBar(0).text).toBe("takt 1, slag 1: B 4, åttendedelsnote, mezzo-forte, usikker");
    expect(nb.nextNote()!.text).toBe("slag 1-og: G 4, åttendedelsnote");
    expect(nb.setPitchMode("concert")).toBe("Klingende tone");
  });

  it("names a Trumpet part a trumpet, not by its transposition", () => {
    const tpt = new Navigator(buildTalkingScore(XML.replace("<part-name>Solo Cornet</part-name>", "<part-name>Trumpet</part-name>")));
    tpt.goBar(0);
    tpt.setPitchMode("concert");
    expect(tpt.setPitchMode("written")).toBe("Written pitch, Trumpet in B-flat");
  });
});

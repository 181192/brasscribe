import Foundation
import Testing
@testable import ScoreKit

/// apps/fixtures/ties-and-trills.musicxml (make-ties-and-trills.py), at 60 bpm, a quarter a second: the notes
/// Apple plays are the ones alphaTab plays on Android and Windows (AlphaTabMusicXml tests there).
private func fixture() -> Score? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let f = dir.appending(path: "apps/fixtures/ties-and-trills.musicxml")
        if FileManager.default.fileExists(atPath: f.path) { return try? MusicXMLParser.parse(url: f) }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

private struct Played: Equatable { var start: Double, end: Double, key: Int }

private func played(_ s: Score, _ part: Int) -> [Played] {
    s.parts[part].playbackNotes.map {
        Played(start: s.seconds(atTick: $0.startTick), end: s.seconds(atTick: $0.startTick + $0.durTicks), key: $0.pitch)
    }
}

@Test func tiesSoundOnceInEveryPart() throws {
    let s = try #require(fixture())
    let want = [Played(start: 0, end: 3, key: 72), Played(start: 3, end: 4, key: 74), Played(start: 4, end: 5, key: 70),
                Played(start: 5, end: 6, key: 65), Played(start: 6, end: 11, key: 67)]
    #expect(Array(played(s, 0).prefix(5)) == want)
    #expect(played(s, 1).first == Played(start: 0, end: 4, key: 70))
    #expect(Array(played(s, 2).prefix(5)) == want.map { Played(start: $0.start, end: $0.end, key: $0.key - 22) })
}

@Test(arguments: [
    // part, start, end, main key, auxiliary key (sounding)
    (0, 12.0, 16.0, 74, 75), (0, 16.0, 20.0, 72, 74), (0, 20.0, 24.0, 74, 76), (0, 24.0, 28.0, 67, 68), (0, 28.0, 34.0, 65, 67),
    (1, 12.0, 16.0, 67, 68),
    (2, 12.0, 16.0, 52, 53), (2, 16.0, 20.0, 50, 52), (2, 20.0, 24.0, 52, 54), (2, 24.0, 28.0, 45, 46), (2, 28.0, 34.0, 43, 45),
])
func trillsAlternateWithTheWrittenAuxiliary(part: Int, start: Double, end: Double, main: Int, aux: Int) throws {
    let s = try #require(fixture())
    let t = played(s, part).filter { $0.start >= start - 1e-6 && $0.start < end }
    #expect(Set(t.map(\.key)) == [main, aux])
    #expect(t.first?.key == main)
    #expect(abs((t.last?.end ?? 0) - end) < 1e-3)
    #expect(abs(t[1].start - t[0].start - 0.125) < 1e-3)  // alphaTab's 32nds
}

@Test func trillAuxiliaryFollowsTheMarkThenTheKey() {
    let e5 = SpelledPitch(step: "E", alter: 0, octave: 5)
    #expect(MusicXMLParser.trillSemitones(e5, accidentalMark: nil, fifths: 0) == 1)
    #expect(MusicXMLParser.trillSemitones(e5, accidentalMark: "sharp", fifths: 0) == 2)
    #expect(MusicXMLParser.trillSemitones(e5, accidentalMark: nil, fifths: 1) == 2)  // F♯ from G major
    let a4 = SpelledPitch(step: "A", alter: 0, octave: 4)
    #expect(MusicXMLParser.trillSemitones(a4, accidentalMark: nil, fifths: -1) == 1)  // B♭ from F major
    #expect(MusicXMLParser.trillSemitones(SpelledPitch(step: "B", alter: 0, octave: 4), accidentalMark: nil, fifths: 0) == 1)
}

@Test func staccatoSoundsHalfItsValue() throws {
    let xml = """
    <?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration><type>quarter</type><notations><articulations><staccato/></articulations></notations></note>
    <note><pitch><step>D</step><octave>5</octave></pitch><duration>6</duration><type>half</type><dot/></note>
    </measure></part></score-partwise>
    """
    let n = try MusicXMLParser.parse(Data(xml.utf8)).parts[0].playbackNotes
    #expect(n.map(\.durTicks) == [Score.ticksPerQuarter / 2, 3 * Score.ticksPerQuarter])
}

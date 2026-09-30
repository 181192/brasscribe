import Foundation
import Testing
@testable import ScoreKit

/// A one-part score with `attributes` and `notes` in its first bar.
private func score(attributes: String = "<divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>",
                   notes: String = "<note><rest/><duration>4</duration></note>", sound: String = "") -> Data {
    Data("""
    <score-partwise><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes>\(attributes)</attributes>\(sound)\(notes)</measure></part></score-partwise>
    """.utf8)
}

private func pitched(alter: String = "0", octave: String = "4", duration: String = "4") -> String {
    "<note><pitch><step>C</step><alter>\(alter)</alter><octave>\(octave)</octave></pitch><duration>\(duration)</duration></note>"
}

private func isMalformed(_ data: Data) -> Bool {
    do { _ = try MusicXMLParser.parse(data); return false } catch let e as MusicXMLError {
        if case .malformed = e { return true }
        return false
    } catch { return false }
}

@Suite struct MalformedScoreTests {
    @Test(arguments: ["1e30", "-1e30", "nan", "inf", "3", "-2.5"])
    func refusesAnAlterationOutsideTwoSemitones(alter: String) {
        #expect(isMalformed(score(notes: pitched(alter: alter))))
    }

    @Test func keepsDoubleSharpsAndFlats() throws {
        let s = try MusicXMLParser.parse(score(notes: pitched(alter: "2", duration: "2") + pitched(alter: "-2", duration: "2")))
        #expect(s.parts[0].notes.map(\.midiPitch) == [62, 58])
    }

    @Test(arguments: ["0", "-4", "3", "6", "2048", "99999999999999999999"])
    func refusesABeatTypeThatIsNotAPowerOfTwo(beatType: String) {
        // an unreadable number keeps the default quarter, like before
        if Int(beatType) == nil { #expect(!isMalformed(score(attributes: "<time><beats>4</beats><beat-type>\(beatType)</beat-type></time>"))); return }
        #expect(isMalformed(score(attributes: "<time><beats>4</beats><beat-type>\(beatType)</beat-type></time>")))
    }

    @Test(arguments: [1, 2, 4, 8, 16, 32])
    func acceptsEveryUsualBeatType(beatType: Int) throws {
        let s = try MusicXMLParser.parse(score(attributes: "<divisions>8</divisions><time><beats>3</beats><beat-type>\(beatType)</beat-type></time>",
                                               notes: "<note><rest/><duration>\(3 * 32 / beatType)</duration></note>"))
        #expect(s.measures[0].beatType == beatType)
        #expect(s.position(atTick: 0).beat == 1)
    }

    @Test(arguments: ["256", "200+100", "-1", "9223372036854775807+1"])
    func refusesMoreThan255Beats(beats: String) {
        #expect(isMalformed(score(attributes: "<time><beats>\(beats)</beats><beat-type>4</beat-type></time>")))
    }

    @Test func aBarOf255BeatsWritesAMIDIFile() throws {
        let s = try MusicXMLParser.parse(score(attributes: "<divisions>1</divisions><time><beats>255</beats><beat-type>64</beat-type></time>"))
        #expect(!MIDIWriter.data(for: s).isEmpty)
    }

    @Test func refusesHugeDivisions() {
        #expect(isMalformed(score(attributes: "<divisions>9223372036854775807</divisions>")))
        #expect(isMalformed(score(attributes: "<divisions>1000001</divisions>")))
    }

    @Test(arguments: ["-1", "4097", "9223372036854775807"])
    func refusesANegativeOrHugeDuration(duration: String) {
        #expect(isMalformed(score(notes: pitched(duration: duration))))
        #expect(isMalformed(score(notes: "<forward><duration>\(duration)</duration></forward>")))
        #expect(isMalformed(score(notes: pitched() + "<backup><duration>\(duration)</duration></backup>")))
    }

    @Test func refusesAPartLongerThanTheLimit() {
        let bar = "<note><rest/><duration>1024</duration></note>"
        let notes = String(repeating: bar, count: MusicXMLParser.maxScoreQuarters / 1024 + 1)
        #expect(isMalformed(score(notes: notes)))
    }

    @Test(arguments: ["10", "-1", "99999999999999999999999"])
    func refusesAnOctaveOutsideTheStaff(octave: String) {
        if Int(octave) == nil { #expect(!isMalformed(score(notes: pitched(octave: octave)))); return }
        #expect(isMalformed(score(notes: pitched(octave: octave))))
    }

    @Test func refusesAHugeTransposition() {
        #expect(isMalformed(score(attributes: "<transpose><chromatic>9223372036854775807</chromatic></transpose>")))
        #expect(isMalformed(score(attributes: "<transpose><chromatic>-2</chromatic><octave-change>100</octave-change></transpose>")))
    }

    @Test(arguments: ["1e400", "inf", "nan", "0", "-120", "0.001", "100000"])
    func ignoresATempoOutsideTheRange(tempo: String) throws {
        let s = try MusicXMLParser.parse(score(sound: "<sound tempo=\"\(tempo)\"/>"))
        #expect(s.tempos.map(\.bpm) == [120])
        #expect(s.tempoBPM.isFinite)
        _ = TalkingScore(score: s, language: .english).text()
        #expect(!MIDIWriter.data(for: s).isEmpty)
    }

    @Test func keepsATempoInTheRange() throws {
        let s = try MusicXMLParser.parse(score(sound: "<sound tempo=\"96.5\"/>"))
        #expect(s.tempos.map(\.bpm) == [96.5])
    }

    @Test func ignoresAnOutOfRangeMIDIProgram() throws {
        let data = Data("""
        <score-partwise><part-list><score-part id="P1"><part-name>Cornet</part-name>
        <midi-instrument id="I1"><midi-program>-9223372036854775808</midi-program></midi-instrument></score-part></part-list>
        <part id="P1"><measure number="1"><note><rest/><duration>4</duration></note></measure></part></score-partwise>
        """.utf8)
        let s = try MusicXMLParser.parse(data)
        #expect(s.parts[0].midiProgram == nil)
        #expect(!MIDIWriter.data(for: s).isEmpty)
    }

    @Test func refusesAPartWithNoBars() {
        let data = Data("""
        <score-partwise><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
        <part id="P1"></part></score-partwise>
        """.utf8)
        #expect(throws: MusicXMLError.malformed("no bars")) { try MusicXMLParser.parse(data) }
    }

    @Test func refusesAScoreWithNoParts() {
        #expect(throws: MusicXMLError.malformed("no parts")) { try MusicXMLParser.parse(Data("<score-partwise></score-partwise>".utf8)) }
    }
}

@Suite struct CueNoteTests {
    /// Bar 1 holds a played half note and a half-note cue; bar 2 must still start after a whole bar.
    let xml = """
    <score-partwise><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1">
    <measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration><type>half</type></note>
    <note><cue/><pitch><step>E</step><octave>5</octave></pitch><duration>2</duration><type>half</type></note>
    </measure>
    <measure number="2"><note><pitch><step>G</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure>
    </part></score-partwise>
    """

    @Test func cueNotesTakeTheirTimeButAreNotPlayed() throws {
        let s = try MusicXMLParser.parse(Data(xml.utf8))
        #expect(s.measures.map(\.startTick) == [0, 4 * Score.ticksPerQuarter])
        #expect(s.parts[0].notes.map(\.midiPitch) == [72, 79])
        #expect(s.parts[0].notes.map(\.startTick) == [0, 4 * Score.ticksPerQuarter])
    }
}

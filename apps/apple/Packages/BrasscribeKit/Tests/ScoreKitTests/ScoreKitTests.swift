import Foundation
import Testing
@testable import ScoreKit

/// The golden Mikkel output, found via BRASSCRIBE_FIXTURES or by walking up to the repo's data/ link.
func goldenDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] {
        let u = URL(fileURLWithPath: env)
        if FileManager.default.fileExists(atPath: u.appending(path: "brass-band.musicxml").path) { return u }
    }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

struct Reference: Decodable {
    struct PartRef: Decodable { let name: String; let count: Int; let first: [[Double]]; let last: [[Double]] }
    let parts: [PartRef]
}

@Suite(.enabled(if: goldenDir() != nil, "golden Mikkel fixture not found")) struct MikkelScoreTests {
    let score: Score
    let composition: Composition

    init() throws {
        let dir = try #require(goldenDir())
        score = try MusicXMLParser.parse(url: dir.appending(path: "brass-band.musicxml"))
        composition = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    }


    @Test func structure() {
        #expect(score.parts.count == 18)
        #expect(score.measures.count == 128)
        #expect(score.tempoBPM == 136)
        #expect(score.parts.first?.name == "Soprano Cornet")
        #expect(score.parts.last?.isPercussion == true)
        #expect(score.measures.allSatisfy { $0.lengthTicks == 4 * Score.ticksPerQuarter })
        #expect(score.title.hasPrefix("Mikkel"))
    }

    @Test func transpositions() {
        let t = Dictionary(uniqueKeysWithValues: score.parts.map { ($0.name, $0.transposeSemitones) })
        #expect(t["Soprano Cornet"] == 3)
        #expect(t["Solo Cornet"] == -2)
        #expect(t["Solo Horn"] == -9)
        #expect(t["1st Baritone"] == -14)
        #expect(t["Euphonium"] == -14)
        #expect(t["1st Trombone"] == -14)   // brass-band tenor trombone reads in B-flat treble
        #expect(t["Bass Trombone"] == 0)
        #expect(t["B♭ Bass"] == -26)
        #expect(score.parts.first { $0.name == "Solo Cornet" }?.concertFifths == 0)
    }

    /// Concert pitches, onsets and durations agree with music21 on every pitched part.
    @Test func matchesMusic21Reference() throws {
        let url = try #require(Bundle.module.url(forResource: "mikkel-reference", withExtension: "json"))
        let ref = try JSONDecoder().decode(Reference.self, from: Data(contentsOf: url))
        for pr in ref.parts {
            let part = try #require(score.parts.first { $0.name == pr.name })
            if part.isPercussion { continue }
            let ours = part.playbackNotes.map { [Double($0.startTick) / 960, Double($0.pitch), Double($0.durTicks) / 960] }
                .sorted { ($0[0], $0[1]) < ($1[0], $1[1]) }
            #expect(ours.count == pr.count, "\(pr.name) count")
            for (a, b) in zip(ours.prefix(pr.first.count), pr.first) {
                #expect(abs(a[0] - b[0]) < 0.01 && a[1] == b[1] && abs(a[2] - b[2]) < 0.01, "\(pr.name) \(a) vs \(b)")
            }
            for (a, b) in zip(ours.suffix(pr.last.count), pr.last) {
                #expect(abs(a[0] - b[0]) < 0.01 && a[1] == b[1] && abs(a[2] - b[2]) < 0.01, "\(pr.name) \(a) vs \(b)")
            }
        }
    }

    @Test func percussionMapsToDrumKeys() throws {
        let perc = try #require(score.parts.last)
        let keys = Set(perc.playbackNotes.map(\.pitch))
        #expect(keys.isSuperset(of: [36, 38, 42]))
        #expect(perc.playbackNotes.count > 800)
    }

    @Test func compositionDecodes() {
        #expect(composition.voices.count == 5)
        #expect(composition.ticksPerBeat == 24)
        #expect(composition.firstDownbeat == -4)
        #expect(composition.voices[0].notes[0].start == 84)
        #expect(composition.voices[0].role == .melody)
    }

    /// Bar 1 of the score is tick 0 of the Composition: the solo cornet's first note sits
    /// at beat 3.5 in both.
    @Test func scoreAndCompositionShareTickZero() throws {
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let firstScore = try #require(solo.playbackNotes.first)
        let firstComp = composition.voices[0].notes[0]
        #expect(Double(firstScore.startTick) / 960 == Double(firstComp.start) / 24)
        #expect(firstScore.pitch % 12 == firstComp.pitch % 12)   // the arranger may move the solo by octaves
    }

    @Test func tempoMapRoundTrips() {
        let tm = composition.tempoMap
        // beat 4 (tick 96) is the first detected beat
        #expect(abs(tm.seconds(atBeat: 4) - composition.beatTimes[0]) < 1e-9)
        #expect(abs(tm.seconds(atBeat: 5) - composition.beatTimes[1]) < 1e-9)
        for b in stride(from: -2.0, through: 520, by: 7.3) {
            #expect(abs(tm.beat(atSeconds: tm.seconds(atBeat: b)) - b) < 1e-6)
        }
    }

    @Test func uncertaintyReachesTheSoloPart() throws {
        let idx = UncertaintyIndex(composition: composition)
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let uncertain = solo.notes.filter(idx.isUncertain)
        #expect(uncertain.count > 20)
        let bass = try #require(score.parts.first { $0.name == "B♭ Bass" })
        #expect(bass.notes.filter(idx.isUncertain).count < uncertain.count)
    }

    @Test func talkingScoreEnglishAndNorwegian() throws {
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let en = TalkingScore(score: score, language: .english, pitchMode: .written)
        let d = en.describe(part: solo, measureIndex: 0)
        #expect(d.hasPrefix("Bar 1, Solo Cornet. "))
        #expect(d.contains("beat 1: rest"))
        #expect(d.contains("beat 4 and: D 4, eighth note"))       // concert C4 written a tone up
        let concert = TalkingScore(score: score, language: .english, pitchMode: .concert)
        #expect(concert.describe(part: solo, measureIndex: 0).contains("beat 4 and: C 4"))
        let nb = TalkingScore(score: score, language: .norwegian, pitchMode: .written)
        let n = nb.describe(part: solo, measureIndex: 0)
        #expect(n.hasPrefix("Takt 1, Solo Cornet. "))
        #expect(n.contains("slag 4 og: D 4, åttendedelsnote"))
        let full = en.text()
        #expect(full.contains("## Percussion"))
        #expect(full.components(separatedBy: "\n").count > 18 * 128)
    }

    @Test func midiExport() throws {
        let data = MIDIWriter.data(for: score, options: .init(includeMetronome: true))
        #expect(data.prefix(4) == Data("MThd".utf8))
        let tracks = Int(data[10]) << 8 | Int(data[11])
        #expect(tracks == 1 + 18 + 1)
        let ch = MIDIWriter.channels(for: score)
        #expect(Set(ch.values).count <= 16)
        #expect(ch[score.parts.last!.id] == 9)
    }

    @Test func filterKeepsOnePart() throws {
        let dir = try #require(goldenDir())
        let xml = try String(contentsOf: dir.appending(path: "brass-band.musicxml"), encoding: .utf8)
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let one = MusicXMLFilter.keepingParts([solo.id], in: xml)
        let s = try MusicXMLParser.parse(Data(one.utf8))
        #expect(s.parts.map(\.name) == ["Solo Cornet"])
        #expect(s.measures.count == 128)
        #expect(s.parts[0].playbackNotes == solo.playbackNotes)
    }
}

@Test func noteNames() {
    let en = TalkingScore(score: Score(title: "", parts: [], measures: [], tempoBPM: 120), language: .english)
    let nb = TalkingScore(score: Score(title: "", parts: [], measures: [], tempoBPM: 120), language: .norwegian)
    #expect(en.noteName(.init(step: "E", alter: -1, octave: 5)) == "E-flat 5")
    #expect(nb.noteName(.init(step: "E", alter: -1, octave: 5)) == "Ess 5")
    #expect(nb.noteName(.init(step: "B", alter: -1, octave: 4)) == "B 4")
    #expect(nb.noteName(.init(step: "B", alter: 0, octave: 4)) == "H 4")
    #expect(nb.noteName(.init(step: "F", alter: 1, octave: 4)) == "Fiss 4")
    #expect(nb.noteName(.init(step: "A", alter: -1, octave: 3)) == "Ass 3")
    #expect(SpelledPitch.spelling(midi: 63, fifths: -3) == .init(step: "E", alter: -1, octave: 4))
    #expect(SpelledPitch.spelling(midi: 66, fifths: 2) == .init(step: "F", alter: 1, octave: 4))
}

@Test func tiesMergeAndChordsShareOnset() throws {
    let xml = """
    <?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>2</beats><beat-type>4</beat-type></time>
    <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
    <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><tie type="start"/><type>quarter</type></note>
    <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><tie type="stop"/><type>quarter</type></note>
    <note><chord/><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>2</duration><type>quarter</type></note>
    </measure><measure number="2"><note><rest/><duration>2</duration></note><backup><duration>2</duration></backup>
    <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><type>eighth</type></note></measure></part></score-partwise>
    """
    let s = try MusicXMLParser.parse(Data(xml.utf8))
    let n = s.parts[0].playbackNotes
    #expect(n.count == 3)
    #expect(n[0] == PlaybackNote(pitch: 72, startTick: 0, durTicks: 1920, velocity: 80))
    #expect(n[1].startTick == 960 && n[1].pitch == 76)
    #expect(n[2].startTick == 1920 && n[2].pitch == 74)
    #expect(s.measures[1].startTick == 1920)
    #expect(s.position(atTick: 2400).bar == 2)
    #expect(s.position(atTick: 2400).beat == 1.5)
}

@Test func timewiseIsRejected() {
    #expect(throws: MusicXMLError.notPartwise) {
        try MusicXMLParser.parse(Data("<score-timewise></score-timewise>".utf8))
    }
}

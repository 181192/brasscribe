import CryptoKit
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
    let sourceSHA256: String?
    let parts: [PartRef]
    enum CodingKeys: String, CodingKey { case parts; case sourceSHA256 = "source_sha256" }
}

/// Checks against the golden Mikkel output. The golden files are re-saved when the engine
/// improves, so these tests check structure and agreement with the Python reference
/// rather than frozen numbers.
@Suite(.enabled(if: goldenDir() != nil, "golden Mikkel fixture not found")) struct MikkelScoreTests {
    let score: Score
    let composition: Composition
    let xml: String

    init() throws {
        let dir = try #require(goldenDir())
        xml = try String(contentsOf: dir.appending(path: "brass-band.musicxml"), encoding: .utf8)
        score = try MusicXMLParser.parse(Data(xml.utf8))
        composition = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    }

    var firstPartMeasureCount: Int {
        let first = xml.range(of: "<part ")!
        let end = xml.range(of: "</part>", range: first.upperBound..<xml.endIndex)!
        return xml[first.lowerBound..<end.upperBound].components(separatedBy: "<measure ").count - 1
    }

    var soundTempos: [Double] {
        xml.components(separatedBy: "<sound tempo=\"").dropFirst().compactMap { Double($0.prefix { $0 != "\"" }) }
    }

    @Test func structure() {
        #expect(score.parts.count == 18)
        #expect(score.measures.count == firstPartMeasureCount)
        #expect(Set(score.tempos.map(\.bpm)) == Set(soundTempos))
        #expect(score.parts.first?.name == "Soprano Cornet")
        #expect(score.parts.last?.isPercussion == true)
        #expect(score.measures.allSatisfy { $0.lengthTicks == $0.beats * $0.beatTicks })
        #expect(score.title.hasPrefix("Mikkel"))
        #expect(score.durationSeconds > 0)
    }

    @Test func tempoChangesShapeTime() throws {
        guard score.tempos.count > 1 else { return }
        let t = score.tempos[1]
        let q = Double(Score.ticksPerQuarter)
        let expected = Double(t.tick) / q * 60 / score.tempos[0].bpm
        #expect(abs(score.seconds(atTick: t.tick) - expected) < 1e-6)
        #expect(abs(score.seconds(atTick: t.tick + 960) - expected - 60 / t.bpm) < 1e-6)
        // one Set Tempo meta event (FF 51 03) per tempo
        let bytes = [UInt8](MIDIWriter.data(for: score))
        var n = 0
        for i in 0..<(bytes.count - 2) where bytes[i] == 0xFF && bytes[i + 1] == 0x51 && bytes[i + 2] == 0x03 { n += 1 }
        #expect(n == score.tempos.count)
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
    }

    /// Concert pitches, onsets and durations agree with music21 on every pitched part.
    /// The reference is regenerated with scripts/make-parser-reference.py whenever the
    /// golden score is re-saved; a stale reference skips the comparison.
    @Test func matchesMusic21Reference() throws {
        let url = try #require(Bundle.module.url(forResource: "mikkel-reference", withExtension: "json"))
        let ref = try JSONDecoder().decode(Reference.self, from: Data(contentsOf: url))
        let sha = SHA256.hash(data: Data(xml.utf8)).map { String(format: "%02x", $0) }.joined()
        guard ref.sourceSHA256 == sha else {
            print("mikkel-reference.json is stale; run scripts/make-parser-reference.py")
            return
        }
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
        #expect(perc.playbackNotes.count > 100)
    }

    @Test func compositionDecodes() {
        #expect(!composition.voices.isEmpty)
        #expect(composition.ticksPerBeat > 0)
        #expect(composition.voices.contains { $0.role == .melody })
        #expect(composition.freeRegions.allSatisfy { $0.end > $0.start && $0.endS > $0.startS })
    }

    /// Bar 1 of the score is tick 0 of the Composition: the solo cornet's first note sits
    /// at the same beat in both (the arranger may move it by octaves).
    @Test func scoreAndCompositionShareTickZero() throws {
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let firstScore = try #require(solo.playbackNotes.first)
        let melody = try #require(composition.voices.first { $0.role == .melody })
        let firstComp = try #require(melody.notes.min { $0.start < $1.start })
        #expect(Double(firstScore.startTick) / 960 == Double(firstComp.start) / Double(composition.ticksPerBeat))
        #expect(firstScore.pitch % 12 == firstComp.pitch % 12)
    }

    @Test func tempoMapRoundTrips() {
        let tm = composition.tempoMap
        let b0 = Double(-composition.firstDownbeat)
        #expect(abs(tm.seconds(atBeat: b0) - composition.beatTimes[0]) < 1e-9)
        #expect(abs(tm.seconds(atBeat: b0 + 1) - composition.beatTimes[1]) < 1e-9)
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
        let note = try #require(solo.notes.first { if case .pitched = $0.kind { return true } else { return false } })
        guard case .pitched(let written) = note.kind else { return }
        let bar = note.measureIndex
        let en = TalkingScore(score: score, language: .english, pitchMode: .written)
        let d = en.describe(part: solo, measureIndex: bar)
        #expect(d.hasPrefix("Bar \(score.measures[bar].number)"))
        #expect(d.contains("Solo Cornet. "))
        #expect(d.contains(en.noteName(written)))
        let concert = TalkingScore(score: score, language: .english, pitchMode: .concert)
        let sounding = SpelledPitch.spelling(midi: note.midiPitch!, fifths: solo.concertFifths(inMeasure: bar))
        #expect(concert.describe(part: solo, measureIndex: bar).contains(concert.noteName(sounding)))
        #expect(sounding.midi == written.midi - 2)
        let nb = TalkingScore(score: score, language: .norwegian, pitchMode: .written)
        let n = nb.describe(part: solo, measureIndex: bar)
        #expect(n.hasPrefix("Takt "))
        #expect(n.contains("slag "))
        let full = en.text()
        #expect(full.contains("## Percussion"))
        #expect(full.components(separatedBy: "\n").count > 18 * score.measures.count)
    }

    @Test func dynamicsAndDirectionsAreSpoken() throws {
        let en = TalkingScore(score: score, language: .english)
        if let part = score.parts.first(where: { !$0.dynamics.isEmpty }),
           let first = part.dynamics.min(by: { $0.key < $1.key }) {
            let bar = score.measureIndex(atTick: first.key)
            #expect(en.describe(part: part, measureIndex: bar).contains(en.dynamicName(first.value)))
        }
        if let d = score.directions.first {
            let bar = score.measureIndex(atTick: d.tick)
            #expect(en.describe(part: score.parts[0], measureIndex: bar).contains(d.text))
        }
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
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let one = MusicXMLFilter.keepingParts([solo.id], in: xml)
        let s = try MusicXMLParser.parse(Data(one.utf8))
        #expect(s.parts.map(\.name) == ["Solo Cornet"])
        #expect(s.measures.count == score.measures.count)
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

@Test func tiesMergeChordsShareOnsetAndDirectionsParse() throws {
    let xml = """
    <?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>2</beats><beat-type>4</beat-type></time>
    <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
    <direction><direction-type><words>ad lib.</words></direction-type><sound tempo="60"/></direction>
    <direction><direction-type><dynamics><mf/></dynamics></direction-type></direction>
    <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><tie type="start"/><type>quarter</type></note>
    <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><tie type="stop"/><type>quarter</type></note>
    <note><chord/><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>2</duration><type>quarter</type></note>
    </measure><measure number="2"><direction><direction-type><rehearsal>A</rehearsal></direction-type><sound tempo="120"/></direction>
    <note><rest/><duration>2</duration></note><backup><duration>2</duration></backup>
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
    #expect(s.tempos == [.init(tick: 0, bpm: 60), .init(tick: 1920, bpm: 120)])
    #expect(abs(s.seconds(atTick: 2880) - 2.5) < 1e-9)
    #expect(s.parts[0].dynamics[0] == "mf")
    #expect(s.directions.map(\.text) == ["ad lib.", "A"])
    let t = TalkingScore(score: s, language: .english)
    #expect(t.describe(part: s.parts[0], measureIndex: 0).contains("mezzo-forte"))
    #expect(t.describe(part: s.parts[0], measureIndex: 1).hasPrefix("Bar 2, rehearsal A, Cornet."))
}

@Test func timewiseIsRejected() {
    #expect(throws: MusicXMLError.notPartwise) {
        try MusicXMLParser.parse(Data("<score-timewise></score-timewise>".utf8))
    }
}

/// Below 0.4 a note is "very uncertain" (boxed "?"), 0.4–0.7 "uncertain" ("?"), and the
/// talking score says which.
@Test func uncertaintyHasTwoLevels() throws {
    let comp = try Composition.decode(Data("""
    {"title":"t","voices":[{"id":"solo","name":"solo","role":"melody","notes":[
      {"pitch":60,"start":0,"dur":24,"confidence":0.3},
      {"pitch":62,"start":24,"dur":24,"confidence":0.6},
      {"pitch":64,"start":48,"dur":48,"confidence":0.9}]}],
     "meters":[{"tick":0,"beats":4,"beat_unit":4}],"keys":[{"tick":0,"fifths":0,"mode":"major"}],
     "beat_times":[0,1,2,3],"first_downbeat":0,"ticks_per_beat":24}
    """.utf8))
    let xml = """
    <score-partwise><part-list><score-part id="P1"><part-name>Solo</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration><type>half</type></note>
    </measure></part></score-partwise>
    """
    let score = try MusicXMLParser.parse(Data(xml.utf8))
    let idx = UncertaintyIndex(composition: comp)
    let notes = score.parts[0].notes
    #expect(notes.map(idx.level) == [.veryUncertain, .uncertain, nil])
    let en = TalkingScore(score: score, language: .english, pitchMode: .written, uncertainty: idx)
        .events(part: score.parts[0], measureIndex: 0)
    #expect(en[0].hasSuffix("very uncertain"))
    #expect(en[1].hasSuffix(", uncertain"))
    #expect(!en[2].contains("uncertain"))
    let nb = TalkingScore(score: score, language: .norwegian, pitchMode: .written, uncertainty: idx)
        .events(part: score.parts[0], measureIndex: 0)
    #expect(nb[0].hasSuffix("svært usikker"))
}

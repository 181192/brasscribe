import XCTest
@testable import BrasscribeCore

final class BrasscribeCoreTests: XCTestCase {
    /// Two quarter notes and a bass note: enough to exercise arranging and MusicXML.
    let composition = """
    {"title": "Test", "voices": [
      {"id": "melody", "role": "melody", "notes": [
        {"pitch": 72, "start": 0, "dur": 24}, {"pitch": 74, "start": 24, "dur": 24}]},
      {"id": "bass", "role": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 48}]}],
     "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}]}
    """

    func testVersion() {
        XCTAssertFalse(coreVersion().isEmpty)
    }

    func testArrangeProducesTransposedMusicXML() throws {
        let xml = try arrangeMusicxml(compositionJson: composition, arranger: "auto")
        XCTAssertTrue(xml.contains("<part-name>Solo Cornet</part-name>"))
        // concert C5 on a B-flat cornet is written D5
        XCTAssertTrue(xml.contains("<step>D</step>"))
    }

    func testInvalidInputThrows() {
        XCTAssertThrowsError(try normalizeComposition(json: "{"))
    }

    func testSpellingAndKey() {
        let s = spellPitches(onsetsBeats: [0, 1, 2], pitches: [66, 69, 74])
        XCTAssertEqual(s.map(\.step), ["F", "A", "D"])
        XCTAssertEqual(estimateKey(durationsBeats: [1, 1, 1], pitches: [62, 66, 69]).fifths, 2)
    }

    func testHumanizePrngVector() {
        XCTAssertEqual(humanizeUniform(key: ""), 0.7636945250957473)
        XCTAssertEqual(humanizeUniform(key: "a"), 0.3717309634354091)
    }

    func testHumanizeKeepsNotesInOrder() throws {
        let notes = [ScoreNote(tick: 24, durTick: 24, startS: 0.5, endS: 1.0, pitch: 74, velocity: 80),
                     ScoreNote(tick: 0, durTick: 24, startS: 0.0, endS: 0.5, pitch: 72, velocity: 80)]
        let perf = try Performance(compositionJson: composition)
        let h = try humanizePart(notes: notes, part: "Solo Cornet", player: 0, seed: "brasscribe",
                                 performance: perf, performedTiming: false)
        XCTAssertEqual(h.notes.map(\.pitch), [72, 74])
        XCTAssertEqual(h.stats.voice, "melody")
    }

    func testTalkingScoreVector() throws {
        // talking-score-vectors.json: note-new-bar-uncertain
        let request = """
        {"part": {"name": "Solo Cornet", "instrument": "Cornet in B♭", "transpose": {"chromatic": -2, "diatonic": -1}},
         "bar": {"number": 2, "key_fifths": 2, "total_bars": 128},
         "event": {"kind": "note", "pos": {"beat": 1, "num": 0, "den": 1}, "type": "eighth", "dots": 0,
                   "written": {"step": "B", "alter": -1, "octave": 4}, "concert": {"step": "A", "alter": -1, "octave": 4},
                   "confidence": 0.55, "sources": ["swiftf0"]},
         "context": {"part": "Solo Cornet", "bar": 1}, "settings": {"lang": "nb"}}
        """
        XCTAssertEqual(try talkingAnnounceJson(request: request), "takt 2, slag 1: B 4, åttendedelsnote, usikker")
    }

    func testTalkingScoreNavigation() throws {
        let xml = try arrangeMusicxml(compositionJson: composition, arranger: "auto")
        let ts = try TalkingScore(musicxml: xml, compositionJson: composition)
        let solo = UInt32(ts.partNames().firstIndex(of: "Solo Cornet")!)
        let start = TalkingCursor(part: solo, bar: 0, event: 0)
        let first = try ts.announce(cursor: start, context: TalkingContext(), settings: talkingSettingsDefault(), byBar: false)
        XCTAssertTrue(first.hasPrefix("bar 1, "), first)
        XCTAssertNotNil(ts.navigate(cursor: start, unit: .note, forward: true))
        XCTAssertTrue(ts.toText(settings: talkingSettingsDefault(), parts: [solo]).contains("Solo Cornet"))
    }
}

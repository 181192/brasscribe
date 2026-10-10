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

    func testSpellingAndKey() throws {
        let s = try spellPitches(onsetsBeats: [0, 1, 2], pitches: [66, 69, 74])
        XCTAssertEqual(s.map(\.step), ["F", "A", "D"])
        XCTAssertEqual(estimateKey(durationsBeats: [1, 1, 1], pitches: [62, 66, 69]).fifths, 2)
        XCTAssertThrowsError(try spellPitches(onsetsBeats: [0], pitches: [66, 69]))
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

    /// A bass line down to D1, which a 4-string bass in standard tuning cannot play.
    func bassLine(pinString: Int) -> String {
        """
        {"instrument": {"preset": "bass-4-standard"},
         "notes": [{"pitch": 26, "start": 0, "dur": 24}, {"pitch": 33, "start": 24, "dur": 24},
                   {"pitch": 38, "start": 48, "dur": 12}, {"pitch": 40, "start": 60, "dur": 36, "techniques": ["hammer-on"]}],
         "options": {"style": "open-position", "pins": [{"note": 2, "string": \(pinString)}]}}
        """
    }

    func object(_ json: String) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
    }

    func testFrettedFingeringAndTab() throws {
        let answer = try object(frettedFingeringJson(request: bassLine(pinString: 3)))
        let notes = try XCTUnwrap((answer["fingering"] as? [String: Any])?["notes"] as? [[String: Any]])
        XCTAssertEqual(notes.count, 4)
        XCTAssertEqual(notes[0]["out_of_range"] as? Bool, true)
        // With D2 pinned at the fifth fret, A1 is played beside it and not on the open string.
        XCTAssertEqual(notes[1]["string"] as? Int, 4)
        XCTAssertEqual(notes[1]["fret"] as? Int, 5)
        // The pin puts D2 on the third string, and the hammer-on follows it there.
        XCTAssertEqual(notes[2]["string"] as? Int, 3)
        XCTAssertEqual(notes[2]["fret"] as? Int, 5)
        XCTAssertEqual(notes[3]["string"] as? Int, 3)
        XCTAssertEqual((answer["violations"] as? [Any])?.count, 0)
        XCTAssertEqual((answer["tuning_suggestions"] as? [[String: Any]])?.first?["preset"] as? String, "bass-4-drop-d")

        let tab = try object(frettedTabJson(request: bassLine(pinString: 3)))
        XCTAssertEqual(tab["adjusted_notes"] as? Int, 0)
        let xml = try XCTUnwrap(tab["musicxml"] as? String)
        XCTAssertTrue(xml.contains("<sign>TAB</sign>") && xml.contains("<staff-lines>4</staff-lines>"))
    }

    func testFrettedTextTabAndPlayingInstructions() throws {
        let text = try frettedTabTextJson(request: bassLine(pinString: 3))
        XCTAssertTrue(text.hasPrefix("Bass\nTuning: Standard (E A D G), bottom line to top\n"), text)
        // D1 has no string; the hammer-on is an h before the fret it leads to.
        XCTAssertTrue(text.contains("\n   !\nG|----------------||\nD|----------------||\nA|---------5h7----||\nE|-----5----------||\n"), text)

        let en = try frettedPlayingInstructionsJson(request: bassLine(pinString: 3))
        XCTAssertTrue(en.contains("\nBar 1\n  Beat 1. D 1, no string to play it on. Quarter note.\n  Beat 2. String 4, fret 5. Quarter note.\n"), en)
        let inNorwegian = bassLine(pinString: 3).replacingOccurrences(of: "\"options\":", with: "\"text\": {\"lang\": \"nb\"}, \"options\":")
        let nb = try frettedPlayingInstructionsJson(request: inNorwegian)
        XCTAssertTrue(nb.contains("\nTakt 1\n  Slag 1. D 1, ingen streng å spille den på. Fjerdedelsnote.\n  Slag 2. Streng 4, bånd 5. Fjerdedelsnote.\n"), nb)
        XCTAssertEqual(en.split(separator: "\n", omittingEmptySubsequences: false).count, nb.split(separator: "\n", omittingEmptySubsequences: false).count)

        XCTAssertThrowsError(try frettedTabTextJson(request: "{"))
        let german = bassLine(pinString: 3).replacingOccurrences(of: "\"options\":", with: "\"text\": {\"lang\": \"de\"}, \"options\":")
        XCTAssertThrowsError(try frettedPlayingInstructionsJson(request: german)) { error in
            guard case CoreError.Invalid(let reason) = error else { return XCTFail("\(error)") }
            XCTAssertTrue(reason.contains("en or nb"), reason)
        }
    }

    func testFrettedInvalidInputThrows() throws {
        XCTAssertThrowsError(try frettedFingeringJson(request: "{")) { error in
            guard case CoreError.Invalid = error else { return XCTFail("\(error)") }
        }
        XCTAssertThrowsError(try frettedTabJson(request: "{"))
        // A pin on a string the instrument does not have is refused; one the string cannot sound is reported.
        XCTAssertThrowsError(try frettedFingeringJson(request: bassLine(pinString: 9))) { error in
            guard case CoreError.Invalid(let reason) = error else { return XCTFail("\(error)") }
            XCTAssertEqual(reason, "a pin names string 9 of 4")
        }
        let reported = try object(frettedFingeringJson(request: bassLine(pinString: 1)))
        XCTAssertEqual((reported["violations"] as? [[String: Any]])?.first?["kind"] as? String, "pin-not-honoured")
    }
}

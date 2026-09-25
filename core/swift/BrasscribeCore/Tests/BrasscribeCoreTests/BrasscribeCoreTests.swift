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
}

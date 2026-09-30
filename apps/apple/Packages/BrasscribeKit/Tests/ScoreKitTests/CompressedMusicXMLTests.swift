import Foundation
import Testing
@testable import ScoreKit

/// Resources/compressed.mxl: a container naming music/score.musicxml (deflated), next to a decoy .xml.
@Suite struct CompressedMusicXMLTests {
    let mxl: Data

    init() throws {
        mxl = try Data(contentsOf: URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "Resources/compressed.mxl"))
    }

    @Test func readsTheScoreTheContainerNames() throws {
        #expect(CompressedMusicXML.isZip(mxl))
        let score = try MusicXMLParser.parse(try CompressedMusicXML.musicXML(from: mxl))
        #expect(score.title == "Compressed")
        #expect(score.parts[0].notes.map(\.midiPitch) == [72])
    }

    @Test func refusesAScoreLargerThanTheLimit() {
        #expect(throws: MusicXMLError.self) { try CompressedMusicXML.musicXML(from: mxl, maxBytes: 100) }
    }

    @Test func refusesWhatIsNotAnArchive() {
        #expect(!CompressedMusicXML.isZip(Data("<score-partwise/>".utf8)))
        #expect(throws: MusicXMLError.self) { try CompressedMusicXML.musicXML(from: Data("PK\u{3}\u{4}not really".utf8)) }
        #expect(throws: MusicXMLError.self) { try CompressedMusicXML.musicXML(from: Data()) }
    }

    @Test func refusesATruncatedArchive() {
        #expect(throws: MusicXMLError.self) { try CompressedMusicXML.musicXML(from: mxl.prefix(mxl.count - 30)) }
        // the entries' data cut away, the directory kept
        var cut = mxl
        cut.replaceSubrange(40..<200, with: Data(repeating: 0, count: 160))
        #expect(throws: MusicXMLError.self) { try MusicXMLParser.parse(try CompressedMusicXML.musicXML(from: cut)) }
    }
}

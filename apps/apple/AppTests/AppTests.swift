import Testing
import Foundation
import ScoreKit
import TranscriptionKit
@testable import BrasscribePlay

func fixtureDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return URL(fileURLWithPath: env) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<6 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

@Test func keyNamesInBothLanguages() {
    #expect(KeyNames.name(fifths: 0).hasPrefix("C"))
    #expect(KeyNames.name(fifths: -3).contains("E♭") || KeyNames.name(fifths: -3).contains("Ess"))
}

@Test func freeTimeIsDetectedFromIrregularBeats() throws {
    let json = """
    {"title":"t","voices":[],"meters":[{"tick":0,"beats":4,"beat_unit":4}],"keys":[{"tick":0,"fifths":0,"mode":"major"}],
     "beat_times":[0,4,5,11,11.5,12,12.5,13,13.5,14,14.5,15],"first_downbeat":0,"ticks_per_beat":24}
    """
    let c = try Composition.decode(Data(json.utf8))
    let free = c.freeTimeBeats
    #expect(free.count == 1)
    #expect(free.first?.lowerBound == 0)
}

@Test(.enabled(if: fixtureDir() != nil)) @MainActor func pieceRoundTripsAndPracticeModelLoads() throws {
    let dir = try #require(fixtureDir())
    let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
    let comp = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    let r = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: [.musicXML, .pdf])
    let p = try Piece.create(title: "Test", profile: .orchestraWithSoloist, result: r, original: nil, video: nil, fixtureDirectory: dir)
    defer { p.delete() }
    #expect(Piece.loadAll().contains { $0.id == p.id })
    let m = try PracticeModel(piece: p)
    #expect(m.score.parts.count == 18)
    #expect(m.describe(partID: m.score.parts[1].id, bar: 0).contains("Solo Cornet"))
    #expect(m.uncertainCount(bar: 1) > 0)
    #expect(m.myPart == m.score.parts[1].id)
}

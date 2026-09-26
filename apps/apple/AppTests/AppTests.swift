import Testing
import AVFoundation
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

/// A short clip made with ffmpeg from the golden mp3 (data/runs/apple/mikkel-20s.mp4).
func testVideo() -> URL? {
    guard let d = fixtureDir() else { return nil }
    let v = d.deletingLastPathComponent().deletingLastPathComponent().appending(path: "runs/apple/mikkel-20s.mp4")
    return FileManager.default.fileExists(atPath: v.path) ? v : nil
}

/// Importing a video keeps the picture for the synced view and hands its audio to transcription.
@Test(.enabled(if: testVideo() != nil)) @MainActor func videoImportExtractsAudio() async throws {
    let app = AppModel()
    await app.accept(url: try #require(testVideo()))
    let src = try #require(app.pending, "\(String(describing: app.alert))")
    #expect(src.videoURL != nil)
    #expect(src.audioURL.pathExtension == "m4a")
    let f = try AVAudioFile(forReading: src.audioURL)
    #expect(abs(Double(f.length) / f.processingFormat.sampleRate - 20) < 0.5)
}

@Test(.enabled(if: fixtureDir() != nil)) func rustCoreArrangesTheGoldenCompositionOnDevice() throws {
    let bridge = RustCoreBridge()
    #expect(!bridge.version.isEmpty)
    let data = try Data(contentsOf: fixtureDir()!.appending(path: "composition.json"))
    let comp = try bridge.composition(fromJSON: data)
    let t0 = Date()
    let xml = try #require(try bridge.arrange(comp, lineup: .fullBand, difficulty: .faithful, keyFifths: nil))
    let seconds = Date().timeIntervalSince(t0)
    let score = try bridge.score(fromMusicXML: xml)
    print("CORE arrange on device \(Int(seconds * 1000)) ms, \(score.parts.count) parts, \(score.measures.count) bars")
    #expect(score.parts.count == 18)
    #expect(score.parts.contains { $0.name == "Solo Cornet" && !$0.playbackNotes.isEmpty })
    let minimal = try #require(try bridge.arrange(comp, lineup: .minimalBand, difficulty: .faithful, keyFifths: nil))
    #expect(try bridge.score(fromMusicXML: minimal).parts.count > 0)
}

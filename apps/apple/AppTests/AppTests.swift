import Testing
import AVFoundation
import Foundation
import ScoreKit
import SwiftUI
import TranscriptionKit
@testable import BrasscribePlay

/// The Old Hundredth fixture (apps/fixtures/old-hundredth), or BRASSCRIBE_FIXTURES.
func fixtureDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return URL(fileURLWithPath: env) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<6 {
        let c = dir.appending(path: "apps/fixtures/old-hundredth")
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
    let m = PracticeModel(piece: p, score: try p.loadScore(), composition: p.loadComposition(), seat: .notSet)
    #expect(m.score.parts.count == 18)
    #expect(m.describe(partID: m.score.parts[1].id, bar: 0).contains("Solo Cornet"))
    #expect(m.uncertainCount(bar: 1) > 0)
    #expect(m.myPart == m.score.parts[1].id)
}

/// A 20 s test pattern with a tone, made with ffmpeg (see PlayUITests): data/runs/apple/test-pattern-20s.mp4.
func testVideo() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<8 {
        let v = dir.appending(path: "data/runs/apple/test-pattern-20s.mp4")
        if FileManager.default.fileExists(atPath: v.path) { return v }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// Importing a video keeps the picture for the synced view and hands its audio to transcription.
@Test(.enabled(if: testVideo() != nil)) @MainActor func videoImportExtractsAudio() async throws {
    let app = AppModel()
    await app.accept(url: try #require(testVideo()))
    let pending = app.path.compactMap { route -> PendingSource? in
        guard case .source(let source) = route else { return nil }
        return source
    }.last
    let src = try #require(pending, "\(String(describing: app.path.last))")
    #expect(src.videoURL != nil)
    #expect(src.audioURL.pathExtension == "m4a")
    let f = try AVAudioFile(forReading: src.audioURL)
    #expect(abs(Double(f.length) / f.processingFormat.sampleRate - 20) < 0.5)
}

@Test(.enabled(if: fixtureDir() != nil)) func rustCoreArrangesTheFixtureCompositionOnDevice() throws {
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

/// Re-arranging for the quartet on device keeps the quartet: four parts, one per player.
@Test(.enabled(if: fixtureDir() != nil)) func rustCoreArrangesAQuartetOnDevice() throws {
    let bridge = RustCoreBridge()
    let comp = try bridge.composition(fromJSON: Data(contentsOf: fixtureDir()!.appending(path: "composition.json")))
    for difficulty in Difficulty.allCases {
        let xml = try #require(try bridge.arrange(comp, lineup: .quartet, difficulty: difficulty, keyFifths: nil))
        let names = try bridge.score(fromMusicXML: xml).parts.map(\.name)
        #expect(names == ["1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"], "\(difficulty)")
    }
}

/// Every lineup maps to its own engine and core value; the quartet never becomes the band.
@Test func lineupValuesAreExhaustive() {
    let engine = Dictionary(uniqueKeysWithValues: Lineup.allCases.map { ($0, $0.engineValue) })
    let core = Dictionary(uniqueKeysWithValues: Lineup.allCases.map { ($0, $0.coreValue) })
    #expect(engine == [.fullBand: "full", .minimalBand: "minimal", .quartet: "quartet"])
    #expect(core == [.fullBand: "band", .minimalBand: "minimal", .quartet: "quartet"])
    for l in Lineup.allCases { #expect(Lineup(recorded: l.coreValue) == l && Lineup(recorded: l.engineValue) == l) }
    #expect(Lineup.quartet.lead == "1st Cornet" && Lineup.fullBand.lead == "Solo Cornet")
}

@Test func quartetPartsHaveNorwegianNames() {
    #expect(PartNames.display("1st Cornet", language: .norwegian) == "1. kornett")
    #expect(PartNames.display("Tenor Horn", language: .norwegian) == "Althorn")
}

/// A solo take has nothing for the other three parts: no quartet.
@Test(.enabled(if: fixtureDir() != nil)) func quartetNeedsTheWholeGroup() throws {
    let comp = try Composition.decode(Data(contentsOf: fixtureDir()!.appending(path: "composition.json")))
    var solo = comp
    solo.voices = comp.voices.filter { $0.layer == "solo" }
    let result = TranscriptionResult(jobID: "t", composition: comp, musicXML: Data(), available: [])
    var p = try Piece.create(title: "Quartet check", profile: .orchestraWithSoloist, result: result, original: nil, video: nil,
                             fixtureDirectory: nil)
    defer { p.delete() }
    #expect(p.canArrangeQuartet(comp))
    #expect(!p.canArrangeQuartet(solo))
    p.profile = .solo
    #expect(!p.canArrangeQuartet(comp))
}


/// The engine groups neighbouring uncertain notes (Composition.review): Review has one item
/// per group, the Solo Cornet carries every solo group, and the level follows `very`.
@Test(.enabled(if: fixtureDir() != nil)) func reviewFollowsTheEnginesGroups() throws {
    let dir = try #require(fixtureDir())
    let comp = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    try #require(!comp.review.isEmpty, "the fixture Composition has review groups")
    let score = try MusicXMLParser.parse(url: dir.appending(path: "brass-band.musicxml"))
    let items = ReviewList.items(score: score, composition: comp, uncertainty: UncertaintyIndex(composition: comp))
    let solo = items.filter { $0.partName == PartNames.display("Solo Cornet") }
    let soloGroups = comp.review.filter { $0.voice == "solo" }
    #expect(solo.count == soloGroups.count)
    // only the parts the arranger marked: Home's count and Review's are the same places
    #expect(items.count == solo.count)
    #expect(score.parts.filter(\.hasMarks).map(\.name) == ["Solo Cornet"])
    #expect(solo.filter { $0.level == .veryUncertain }.count == soloGroups.filter(\.very).count)
    // groups are short (the engine aims at two bars; a group may reach into a third)
    #expect(solo.allSatisfy { ($0.lastBar ?? $0.bar) >= $0.bar && ($0.lastBar ?? $0.bar) - $0.bar <= 2 })
    // without groups, every uncertain onset is its own item
    var plain = comp
    plain.review = []
    #expect(ReviewList.items(score: score, composition: plain, uncertainty: UncertaintyIndex(composition: plain)).count > items.count)
}

/// Review edits go to the Composition: Change note is arranged again by the Rust core, and a kept
/// group is certain, so it leaves Review after arranging again.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func reviewEditsGoThroughTheCore() throws {
    let dir = try #require(fixtureDir())
    let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
    let comp = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    let r = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: [.musicXML, .composition])
    let piece = try Piece.create(title: "Edit", profile: .orchestraWithSoloist, result: r, original: nil, video: nil, fixtureDirectory: nil)
    defer { piece.delete() }
    let app = AppModel()
    let score = try MusicXMLParser.parse(xml)
    let items = ReviewList.items(score: score, composition: comp, uncertainty: UncertaintyIndex(composition: comp))
    let first = try #require(items.first)
    let lead = score.parts[first.partIndex].notes[first.noteIndex]
    let pitch = try #require(lead.midiPitch)

    var edited = comp
    let change = try #require(CompositionEdit.change(&edited, scoreTick: lead.startTick, concertPitch: pitch, by: 2))
    #expect(change.to == change.from + 2)
    let arranged = try app.rearrange(piece, composition: edited, output: OutputChoice(), open: false)
    let again = try arranged.loadScore()
    let part = try #require(again.part(id: first.partID))
    #expect(part.notes.contains { $0.startTick == lead.startTick && $0.midiPitch == pitch + 2 })

    CompositionEdit.keep(&edited, item: first, lead: lead)
    let after = ReviewList.items(score: again, composition: edited, uncertainty: UncertaintyIndex(composition: edited))
    #expect(!after.contains { $0.id == first.id })
    #expect(after.count == items.count - 1)
}

/// Mac windows stay whole on their screen's visible frame (AppKit coordinates, y up).
@Test func windowFitKeepsAWindowOnItsScreen() {
    // a laptop's visible frame: the Dock takes the bottom 70 pt, the menu bar the top 33
    let laptop = CGRect(x: 0, y: 70, width: 1512, height: 879)
    // fits: stays exactly where it is
    let small = CGRect(x: 100, y: 200, width: 900, height: 600)
    #expect(WindowFit.clamp(small, into: laptop) == small)
    // hangs under the Dock: moves up just enough, same size
    #expect(WindowFit.clamp(CGRect(x: 100, y: 20, width: 900, height: 600), into: laptop) == CGRect(x: 100, y: 70, width: 900, height: 600))
    // restored from a big external display: shrinks to the visible frame
    #expect(WindowFit.clamp(CGRect(x: 2000, y: 100, width: 2400, height: 1100), into: laptop) == laptop)
    // off the right edge: moves left only as far as needed
    #expect(WindowFit.clamp(CGRect(x: 1000, y: 200, width: 900, height: 600), into: laptop).maxX == laptop.maxX)
    // a screen smaller than the minimum: the minimum wins and the top-left is pinned to the visible top-left
    let tiny = CGRect(x: 0, y: 50, width: 500, height: 600)
    let pinned = WindowFit.clamp(CGRect(x: 40, y: 60, width: 800, height: 800), into: tiny, minSize: CGSize(width: 520, height: 640))
    #expect(pinned.size == CGSize(width: 520, height: 640))
    #expect(pinned.minX == tiny.minX && pinned.maxY == tiny.maxY)
    // the default size: 1280 × 900, or 90 % of a smaller screen
    #expect(WindowFit.defaultSize(visible: CGRect(x: 0, y: 0, width: 3840, height: 1175)) == CGSize(width: 1280, height: 900))
    #expect(WindowFit.defaultSize(visible: laptop) == CGSize(width: 1280, height: 791))
}

/// Settings → Appearance: Match system (the default and anything unknown) leaves the scheme to the
/// system; Light and Dark force it.
@Test @MainActor func appearanceSettingMapsToAColorScheme() {
    guard LaunchOptions.colorScheme == nil else { return }  // a test run with -appearance overrides the setting
    #expect(AppearanceSetting.scheme(stored: "system") == nil)
    #expect(AppearanceSetting.scheme(stored: "light") == .light)
    #expect(AppearanceSetting.scheme(stored: "dark") == .dark)
    #expect(AppearanceSetting.scheme(stored: "something else") == nil)
    #expect(AppearanceSetting.allCases.map(\.rawValue) == ["system", "light", "dark"])
    #expect(AppearanceSetting.allCases.map(\.title).allSatisfy { !$0.isEmpty })
}

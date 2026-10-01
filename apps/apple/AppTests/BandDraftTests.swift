import Foundation
import OnDeviceKit
import ScoreKit
import Testing
import TranscriptionKit
@testable import BrasscribePlay

// MARK: routing

@Test func aBrassBandIsADraftOnTheDeviceOnlyWithoutTheComputer() {
    func maker(_ p: SourceProfile, solo: Bool = true, draft: Bool = false, there: Bool, ready: Bool = true) -> AppModel.Maker {
        AppModel.maker(for: p, soloOnDevice: solo, bandDraftOnDevice: draft, computerThere: there, modelsReady: ready)
    }
    // the computer is there: bands go to it, as before
    #expect(maker(.brassBand, there: true) == .computer)
    // no computer, or one that is offline: a draft on the device
    #expect(maker(.brassBand, there: false) == .bandDraft)
    // the player asked for drafts: on the device even with the computer there
    #expect(maker(.brassBand, draft: true, there: true) == .bandDraft)
    // without the listening files nothing runs on the device
    #expect(maker(.brassBand, there: false, ready: false) == .computer)
    // solos as before
    #expect(maker(.solo, there: true) == .soloOnDevice)
    #expect(maker(.solo, solo: false, there: false) == .computer)
    // the other band recordings always need the computer
    for p in [SourceProfile.popRock, .orchestraWithSoloist] {
        #expect(maker(p, draft: true, there: false) == .computer)
    }
}

@Test @MainActor func theComputerIsThereWhenConnectedOrReconnecting() {
    let app = AppModel()
    let rec = EngineRecord(serverID: "s", serverName: "Band room", token: "t", lastAddress: "http://192.0.2.1:8765")
    app.connection.stage(.connected(serverName: "Band room"), record: rec)
    #expect(app.computerThere)
    app.connection.stage(.reconnecting(serverName: "Band room"), record: rec)
    #expect(app.computerThere)
    app.connection.stage(.offline, record: rec)
    #expect(!app.computerThere)
    app.connection.stage(.needsPairing(serverName: "Band room"), record: rec)
    #expect(!app.computerThere)
    // nothing paired
    app.connection.stage(.connected(serverName: ""), record: nil)
    app.connection.localAddress = nil
    #expect(!app.computerThere)
}

@Test @MainActor func theServiceFollowsTheRoute() {
    let app = AppModel()
    let saved = app.modelDownloadURL
    defer { app.modelDownloadURL = saved }
    // a download address counts as the listening files being there
    app.modelDownloadURL = "http://192.0.2.1:8765/models/"
    app.connection.stage(.offline, record: nil)
    app.connection.localAddress = nil
    #expect(app.service(for: .brassBand) is OnDeviceBandDraftService)
    #expect(app.service(for: .popRock) is CompanionService)
    #expect(app.whereItRuns(for: .brassBand) == String(localized: "A quick draft on this device. Your computer makes a better score."))
    let rec = EngineRecord(serverID: "s", serverName: "Band room", token: "t", lastAddress: "http://192.0.2.1:8765")
    app.connection.stage(.connected(serverName: "Band room"), record: rec)
    #expect(app.service(for: .brassBand) is CompanionService)
    let draft = app.bandDraftOnDevice
    defer { app.bandDraftOnDevice = draft }
    app.bandDraftOnDevice = true
    #expect(app.service(for: .brassBand) is OnDeviceBandDraftService)
}

/// "Try again" asks where the player asked: a full score asked of the computer does not become another draft
/// when bands are drafts on this device, and a too-long draft can be moved to the computer.
@Test @MainActor func tryAgainKeepsTheComputerThePlayerChose() {
    let app = AppModel()
    let saved = (app.modelDownloadURL, app.bandDraftOnDevice)
    defer { (app.modelDownloadURL, app.bandDraftOnDevice) = saved; app.jobs.values.forEach { $0.cancel() } }
    app.modelDownloadURL = "http://192.0.2.1:8765/models/"
    app.bandDraftOnDevice = true
    let src = PendingSource(audioURL: URL(fileURLWithPath: "/nonexistent/band.wav"), title: "Band")

    app.startTranscription(src, profile: .brassBand, output: OutputChoice(), onComputer: true)
    let full = try! #require(app.jobs.values.first)
    #expect(full.onComputer && full.service is CompanionService)
    app.retry(full)
    let again = try! #require(app.jobs.values.first { $0.id != full.id })
    #expect(again.onComputer && again.service is CompanionService)

    // the player's own choice of a draft stays a draft, until they move it to the computer
    app.jobs.values.forEach { $0.cancel() }
    app.jobs = [:]
    app.path = []
    app.startTranscription(src, profile: .brassBand, output: OutputChoice())
    let draft = try! #require(app.jobs.values.first)
    #expect(!draft.onComputer && draft.service is OnDeviceBandDraftService)
    app.retry(draft)
    #expect(app.jobs.values.allSatisfy { $0.service is OnDeviceBandDraftService })
    app.retry(draft, onComputer: true)
    #expect(app.jobs.values.contains { $0.onComputer && $0.service is CompanionService })

    // back from the too-long screen: What is this?, with the same recording
    app.path = [.transcribe(draft.id)]
    app.backToSource(draft)
    #expect(app.path == [.source(src)])
}

// MARK: words

@Test func theDraftSaysWhatItIs() {
    let there = DraftNotice.words(computerThere: true)
    #expect(there.text.contains("draft"))
    #expect(there.text.contains("differ slightly"))
    #expect(there.action == "Make the full score")
    #expect(there.hint == nil)
    let away = DraftNotice.words(computerThere: false)
    #expect(away.action == nil)
    #expect(away.hint == "Open Brasscribe on your computer to make the full score from the same recording.")
    #expect(ErrorWords.title(DraftTooLong(seconds: 900, maxSeconds: 600)) == "Too long for a draft on this device")
    // too long: the computer is the way forward when it is there; otherwise the words say to open it
    #expect(ErrorWords.draftTooLong(computerThere: true) == "Your computer can make the score from this recording.")
    #expect(ErrorWords.draftTooLong(computerThere: false) == "Open Brasscribe on your computer to make the score from this recording, or choose a shorter one.")
    #expect(ErrorWords.specific(DraftTooLong(seconds: 900, maxSeconds: 600)) == ErrorWords.draftTooLong(computerThere: false))
    #if os(iOS)
    #expect(TranscribeView.leaveLine(draft: true) == "Keep Brasscribe open until the draft is ready.")
    #endif
    #expect(TranscribeView.leaveLine(draft: false).hasPrefix("You can leave this screen."))
}

@Test func aDraftIsMarkedInYourScores() throws {
    let result = TranscriptionResult(jobID: "on-device", composition: nil, musicXML: Data(), available: [.musicXML])
    let p = try Piece.create(title: "Band", profile: .brassBand, result: result, original: nil, video: nil,
                             fixtureDirectory: nil, draft: true)
    defer { p.delete() }
    #expect(p.isDraft)
    #expect(p.summary.contains("Draft"))
    #expect(Piece.load(from: p.metaURL)?.isDraft == true)
    let full = try Piece.create(title: "Band", profile: .brassBand, result: result, original: nil, video: nil, fixtureDirectory: nil)
    defer { full.delete() }
    #expect(!full.isDraft && !full.summary.contains("Draft"))
}

@Test func theBandIsArrangedTheWayTheEngineMakesIt() {
    #expect(OnDeviceBandDraftService.options(.init(lineup: .fullBand)).lineup == "minimal")
    #expect(OnDeviceBandDraftService.options(.init(lineup: .minimalBand)).lineup == "minimal")
    #expect(OnDeviceBandDraftService.options(.init(lineup: .quartet)).lineup == "quartet")
    let seat = OnDeviceBandDraftService.options(.init(seat: "euphonium", reads: "bass", lead: "seat"))
    #expect(seat.seat == "euphonium" && seat.reads == "bass" && seat.lead == "seat")
    #expect(OnDeviceBandDraftService.options(.init(reads: "bass", lead: "seat")).lead == nil)
}

@Test func aRecordingLongerThanTheFreeMemoryIsRefusedBeforeListening() async throws {
    let clip = try #require(draftMixes().first).appending(path: "mix.wav")
    let svc = OnDeviceBandDraftService(store: ModelStore(cache: FileManager.default.temporaryDirectory.appending(path: "bc-models-none")),
                                       available: { OnDeviceBudget.fixedBytes + 1_000_000 })
    await #expect(throws: DraftTooLong.self) {
        for try await _ in svc.transcribe(.init(audioURL: clip, profile: .brassBand, title: "Chorale")) {}
    }
}

// MARK: parity with the engine's draft

/// The ChoraleBricks mixes under data/eval (not in git), with their reference draft from
/// apps/apple/scripts/make-band-draft-reference.sh under data/runs/apple.
func draftMixes() -> [URL] {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<8 {
        let c = dir.appending(path: "data/eval/choralebricks-brass4")
        if let names = try? FileManager.default.contentsOfDirectory(atPath: c.path) {
            return names.sorted().map { c.appending(path: $0) }.filter { FileManager.default.fileExists(atPath: $0.appending(path: "mix.wav").path) }
        }
        dir = dir.deletingLastPathComponent()
    }
    return []
}

func draftReference(_ mix: URL, lineup: String) -> URL? {
    let r = mix.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "runs/apple/\(mix.lastPathComponent)-band-draft-ref/\(lineup)/composition.json")
    return FileManager.default.fileExists(atPath: r.path) ? r : nil
}

/// Note F1 of one voice on pitch and performed onset (within 50 ms): the notes Basic Pitch heard.
func onsetF1(_ a: Composition, _ b: Composition, _ id: String) -> Double {
    let x = a.voices.first { $0.id == id }?.notes ?? []
    var y = b.voices.first { $0.id == id }?.notes ?? []
    var tp = 0
    for n in x {
        if let j = y.firstIndex(where: { $0.pitch == n.pitch && abs(($0.onsetS ?? -9) - (n.onsetS ?? 9)) <= 0.05 }) { y.remove(at: j); tp += 1 }
    }
    let total = x.count + (b.voices.first { $0.id == id }?.notes.count ?? 0)
    return total == 0 ? 1 : 2 * Double(tp) / Double(total)
}

/// Share of the reference's beats the device also found (within 70 ms).
func beatAgreement(_ a: Composition, _ b: Composition) -> Double {
    guard !b.beatTimes.isEmpty else { return 1 }
    let hits = b.beatTimes.filter { t in a.beatTimes.contains { abs($0 - t) <= 0.07 } }.count
    return Double(hits) / Double(max(a.beatTimes.count, b.beatTimes.count))
}

/// Note F1 of one voice on pitch and start tick (the written position: needs the same beat grid).
func voiceF1(_ a: Composition, _ b: Composition, _ id: String) -> Double {
    let x = a.voices.first { $0.id == id }?.notes.map { [$0.pitch, $0.start] } ?? []
    var y = b.voices.first { $0.id == id }?.notes.map { [$0.pitch, $0.start] } ?? []
    var tp = 0
    for n in x { if let j = y.firstIndex(of: n) { y.remove(at: j); tp += 1 } }
    let total = x.count + (b.voices.first { $0.id == id }?.notes.count ?? 0)
    return total == 0 ? 1 : 2 * Double(tp) / Double(total)
}

/// Every chorale mix → a band draft on this device (Core ML models and the Rust core), against the
/// engine's brass-band profile with muscriptor=false on the same mix: every part present and as long
/// as the others, and the melody and bass notes the same. The device's compositions are written to a
/// temporary folder for scoring against the chorales (`bench quartet-audio` rows).
@Test(.enabled(if: !draftMixes().isEmpty && convertedModels != nil))
func theDraftOnTheDeviceMatchesTheEngineDraft() async throws {
    let store = ModelStore(cache: FileManager.default.temporaryDirectory.appending(path: "bc-models"), localSource: convertedModels)
    let svc = OnDeviceBandDraftService(store: store)
    let out = FileManager.default.temporaryDirectory.appending(path: "band-drafts", directoryHint: .isDirectory)
    try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
    var melody: [Double] = [], bass: [Double] = [], written: [Double] = [], grid: [Double] = []
    for dir in draftMixes() {
        for (lineup, parts) in [(Lineup.minimalBand, 8), (.quartet, 4)] {
            let key = lineup == .quartet ? "quartet" : "minimal"
            let t0 = Date()
            var result: TranscriptionResult?
            for try await ev in svc.transcribe(.init(audioURL: dir.appending(path: "mix.wav"), profile: .brassBand, title: "Reference",
                                                     output: .init(lineup: lineup))) {
                if case .finished(let r) = ev { result = r }
            }
            let r = try #require(result)
            let score = try MusicXMLParser.parse(r.musicXML)
            let comp = try #require(r.composition)
            #expect(score.parts.count == parts, "\(dir.lastPathComponent) \(key)")
            // bars per part, from the MusicXML itself: every part as long as the others
            let xml = String(decoding: r.musicXML, as: UTF8.self)
            let bars = Set(xml.components(separatedBy: "<part id=").dropFirst().map { $0.components(separatedBy: "<measure ").count - 1 })
            #expect(bars.count == 1 && (bars.first ?? 0) >= 4, "\(dir.lastPathComponent) \(key): bars per part \(bars)")
            try JSONEncoder().encode(comp).write(to: out.appending(path: "\(dir.lastPathComponent)-\(key).json"))
            var line = "BAND DRAFT \(dir.lastPathComponent) \(key): \(Int(Date().timeIntervalSince(t0) * 1000)) ms, \(score.parts.count) parts, \(bars.first ?? 0) bars"
            if let refURL = draftReference(dir, lineup: key), let ref = try? Composition.decode(Data(contentsOf: refURL)) {
                let m = onsetF1(comp, ref, "melody"), b = onsetF1(comp, ref, "bass")
                let w = voiceF1(comp, ref, "melody"), g = beatAgreement(comp, ref)
                melody.append(m); bass.append(b); written.append(w); grid.append(g)
                line += String(format: "; vs engine draft: melody F1 %.3f, bass F1 %.3f (onset+pitch), beats agree %.3f (%d vs %d), melody F1 on written position %.3f, beats per bar %d vs %d",
                               m, b, g, comp.beatTimes.count, ref.beatTimes.count, w, comp.meters.first?.beats ?? 0, ref.meters.first?.beats ?? 0)
            }
            print(line)
        }
    }
    print("BAND DRAFT compositions in \(out.path)")
    if !melody.isEmpty {
        let mean = { (v: [Double]) in v.reduce(0, +) / Double(v.count) }
        print(String(format: "BAND DRAFT vs engine draft over %d runs: melody F1 %.3f, bass F1 %.3f (onset+pitch); beats agree %.3f; melody F1 on written position %.3f",
                     melody.count, mean(melody), mean(bass), mean(grid), mean(written)))
        // The notes are Basic Pitch's on both sides. The beat grid can differ where Beat This! on the device
        // and in PyTorch disagree, which moves written positions: reported, not gated.
        #expect(mean(melody) >= 0.9)
        #expect(mean(bass) >= 0.9)
    }
}

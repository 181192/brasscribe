import AVFoundation
import Foundation
import OnDeviceKit
import ScoreKit
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// The app's own Models folder has compiled models in it (scripts/stage-models.sh found the converted
/// packages when the project was generated).
let appCarriesModels: Bool = {
    guard let dir = ModelStore.appModels,
          let names = try? FileManager.default.contentsOfDirectory(atPath: dir.path) else { return false }
    return names.contains { $0.hasSuffix(".mlmodelc") }
}()

/// These tests run when the app carries models, and also when the converted packages are in the checkout
/// (as in CI, which fetches them): an app built without them there is a staging failure, and fails here
/// instead of skipping. Only a checkout with no models at all skips.
let modelsExpectedInApp: Bool = appCarriesModels || OnDeviceModel.needed.allSatisfy { m in
    convertedModels.map { FileManager.default.fileExists(atPath: $0.appending(path: "\(m.directory)/\(m.fileName)").path) } ?? false
}

/// A store that has only what the app carries: no development folder, and a cache that does not exist.
private func appOnlyStore() -> (store: ModelStore, cache: URL) {
    let nowhere = FileManager.default.temporaryDirectory.appending(path: "bc-no-models-\(UUID().uuidString)", directoryHint: .isDirectory)
    return (ModelStore(cache: nowhere.appending(path: "cache"), localSource: nowhere.appending(path: "converted")), nowhere)
}

/// Old Hundredth's first two phrases (public domain) as plain tones with a soft attack, a note a beat
/// at 90 a minute: enough for the pitch models to hear notes and the beat model a pulse.
private func writeTune(to url: URL) throws {
    let rate = 44_100.0, beat = 60.0 / 90
    let tune = [67, 67, 66, 64, 62, 67, 69, 71, 71, 71, 71, 69, 67, 72, 71, 69]
    let format = try #require(AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1))
    let frames = Int(rate * beat) * tune.count
    let buffer = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)))
    buffer.frameLength = buffer.frameCapacity
    let out = try #require(buffer.floatChannelData?[0])
    let perNote = Int(rate * beat)
    for (i, pitch) in tune.enumerated() {
        let hz = 440 * pow(2, Double(pitch - 69) / 12)
        for k in 0..<perNote {
            let t = Double(k) / rate
            let env = min(1, t / 0.01) * exp(-3 * t / beat) * (k > perNote - 800 ? Double(perNote - k) / 800 : 1)
            let wave = sin(2 * .pi * hz * t) + 0.4 * sin(4 * .pi * hz * t) + 0.2 * sin(6 * .pi * hz * t)
            out[i * perNote + k] = Float(0.4 * env * wave)
        }
    }
    try AVAudioFile(forWriting: url, settings: format.settings).write(from: buffer)
}

/// Every model this device needs is in the app, loads as it is, and nothing is compiled or stored.
@Test(.enabled(if: modelsExpectedInApp, "no on-device models in this checkout or in the app"))
func theAppCarriesEveryModelItNeeds() async throws {
    let (store, nowhere) = appOnlyStore()
    try #require(store.missing.isEmpty, "the converted models are in the checkout, but missing from the app: \(store.missing.map(\.compiledName))")
    for m in OnDeviceModel.needed { _ = try await store.model(m) }
    #expect(!FileManager.default.fileExists(atPath: nowhere.path))
    // with them, a solo is written down here whatever the computer does
    #expect(AppModel.maker(for: .solo, soloOnDevice: true, bandDraftOnDevice: false, computerThere: false,
                           modelsReady: store.missing.isEmpty) == .soloOnDevice)
}

/// A recording becomes a score with the app's own models and the core, and no other source of models.
@Test(.enabled(if: modelsExpectedInApp, "no on-device models in this checkout or in the app"))
func aSoloIsWrittenDownWithTheAppsOwnModels() async throws {
    let clip = FileManager.default.temporaryDirectory.appending(path: "bc-tune-\(UUID().uuidString).wav")
    defer { try? FileManager.default.removeItem(at: clip) }
    try writeTune(to: clip)
    let (store, nowhere) = appOnlyStore()
    var result: TranscriptionResult?
    for try await ev in OnDeviceSoloService(store: store).transcribe(.init(audioURL: clip, profile: .solo, title: "Old Hundredth",
                                                                           output: .init(lineup: .minimalBand))) {
        if case .finished(let r) = ev { result = r }
    }
    let score = try MusicXMLParser.parse(try #require(result).musicXML)
    let heard = Set(score.parts.flatMap(\.playbackNotes).map { $0.pitch % 12 })
    // the tune's notes are in the score: G, F sharp, E, D, A, B, C
    #expect(heard.isSuperset(of: [7, 6, 4, 2, 9, 11, 0]), "pitch classes written: \(heard.sorted())")
    #expect(!FileManager.default.fileExists(atPath: nowhere.path))
}

/// A solo take longer than the free memory allows is refused before anything is loaded, with words of its own.
@Test func aSoloLongerThanTheFreeMemoryIsRefusedBeforeListening() async throws {
    let clip = FileManager.default.temporaryDirectory.appending(path: "bc-solo-too-long-\(UUID().uuidString).wav")
    defer { try? FileManager.default.removeItem(at: clip) }
    let format = try #require(AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1))
    let buffer = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 44_100 * 60))
    buffer.frameLength = buffer.frameCapacity
    try AVAudioFile(forWriting: clip, settings: format.settings).write(from: buffer)
    let (store, _) = appOnlyStore()
    let svc = OnDeviceSoloService(store: store, available: { OnDeviceBudget.fixedBytes + 1_000_000 })
    do {
        for try await _ in svc.transcribe(.init(audioURL: clip, profile: .solo, title: "Solo")) {}
        Issue.record("a minute was let through with room for a second")
    } catch let e as DraftTooLong {
        #expect(e.solo)
        #expect(ErrorWords.title(e) == String(localized: "Too long to write down on this device"))
    }
}

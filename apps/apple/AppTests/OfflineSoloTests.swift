import Foundation
import OnDeviceKit
import ScoreKit
import Testing
import TranscriptionKit
@testable import BrasscribePlay

func onDeviceRef() -> URL? {
    guard let d = fixtureDir() else { return nil }
    let r = d.deletingLastPathComponent().deletingLastPathComponent().appending(path: "runs/apple/entertainer-ref")
    return FileManager.default.fileExists(atPath: r.appending(path: "solo/brass-band.musicxml").path) ? r : nil
}

let convertedModels = URL(fileURLWithPath: "/Users/k/private/brasscribe/models/converted")

@Test(.enabled(if: onDeviceRef() != nil && FileManager.default.fileExists(atPath: convertedModels.path)))
func beatThisOnThisPlatform() async throws {
    let clip = try #require(onDeviceRef()).deletingLastPathComponent().appending(path: "entertainer-tpt1-30s.wav")
    let store = ModelStore(cache: FileManager.default.temporaryDirectory.appending(path: "bc-models"), localSource: convertedModels)
    let m = try await store.model(.beatThis)
    let a = try MonoAudio.load(clip, sampleRate: BeatThis.sampleRate)
    let (spect, frames) = try BeatThis.logMel(a)
    let (b, d) = try BeatThis.logits(spect, frames: frames, model: m)
    print("BEATDBG frames \(frames) spect max \(spect.max() ?? 0) beat logit max \(b.max() ?? 0) min \(b.min() ?? 0) down max \(d.max() ?? 0)")
    #expect(BeatThis.decode(beat: b, downbeat: d).beats.count > 20)
}

/// Note F1 on concert pitch and onset (within a sixteenth).
func soloF1(_ a: [PlaybackNote], _ b: [PlaybackNote]) -> Double {
    var used = Set<Int>(); var tp = 0
    for n in a {
        if let j = b.indices.first(where: { !used.contains($0) && b[$0].pitch == n.pitch && abs(b[$0].startTick - n.startTick) <= 240 }) {
            used.insert(j); tp += 1
        }
    }
    let p = Double(tp) / Double(max(1, a.count)), r = Double(tp) / Double(max(1, b.count))
    return p + r > 0 ? 2 * p * r / (p + r) : 0
}

/// Recorded solo (30 s URMP trumpet part) → readable part, fully on the device: Core ML
/// models plus the Rust core. Compared with the Python pipeline (SwiftF0 + Basic Pitch +
/// Beat This small0 → brasscribe_eval.arrange_solo) on the same clip.
@Test(.enabled(if: onDeviceRef() != nil && FileManager.default.fileExists(atPath: convertedModels.path)))
func offlineSoloMatchesThePythonPipeline() async throws {
    let ref = try #require(onDeviceRef())
    let clip = ref.deletingLastPathComponent().appending(path: "entertainer-tpt1-30s.wav")
    let store = ModelStore(cache: FileManager.default.temporaryDirectory.appending(path: "bc-models"), localSource: convertedModels)
    let svc = OnDeviceSoloService(store: store)
    let t0 = Date()
    var result: TranscriptionResult?
    var stages: [StageKind] = []
    for try await ev in svc.transcribe(.init(audioURL: clip, profile: .solo, title: "Entertainer", output: .init(lineup: .minimalBand))) {
        switch ev {
        case .progress(let p): stages.append(p.stage)
        case .finished(let r): result = r
        }
    }
    let seconds = Date().timeIntervalSince(t0)
    let r = try #require(result)
    let ours = try MusicXMLParser.parse(r.musicXML)
    // Same models in Python, then the layered solo path the core ports.
    let layered = try MusicXMLParser.parse(Data(contentsOf: ref.appending(path: "layered/brass-band.musicxml")))
    // Same models in Python, then the older arrange_solo script the engine's solo profile calls.
    let script = try MusicXMLParser.parse(Data(contentsOf: ref.appending(path: "solo/brass-band.musicxml")))
    func solo(_ s: Score) -> [PlaybackNote] { s.parts.first { $0.name == "Solo Cornet" }?.playbackNotes ?? [] }
    let a = solo(ours)
    let fLayered = soloF1(a, solo(layered)), fScript = soloF1(a, solo(script))
    print("OFFLINE solo \(Int(seconds * 1000)) ms: \(a.count) notes, \(ours.parts.count) parts, \(ours.measures.count) bars. "
          + "vs Python layered path: \(solo(layered).count) notes, \(layered.measures.count) bars, F1 \(fLayered). "
          + "vs arrange_solo script: \(solo(script).count) notes, \(script.measures.count) bars, F1 \(fScript)")
    #expect(!a.isEmpty)
    #expect(stages.contains(.arranging))
    #expect(ours.measures.count == layered.measures.count)
    #expect(fLayered >= 0.95)
}

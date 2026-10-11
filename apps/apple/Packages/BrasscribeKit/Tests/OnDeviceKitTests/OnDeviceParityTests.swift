import CoreML
import Foundation
import Testing
@testable import OnDeviceKit

/// Reference outputs from the Python tools (scripts/make-ondevice-reference.sh) on a 30 s
/// URMP trumpet part, and the converted models from models/converted/.
func refDir() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let c = dir.appending(path: "data/runs/apple/entertainer-ref")
        if FileManager.default.fileExists(atPath: c.appending(path: "sw.mid").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

func modelsDir() -> URL? {
    if let e = ProcessInfo.processInfo.environment["BRASSCRIBE_MODELS"] { return URL(fileURLWithPath: e) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let m = dir.appending(path: "models/converted")
        if FileManager.default.fileExists(atPath: m.appending(path: "swift-f0").path) { return m }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

var clip: URL { refDir()!.deletingLastPathComponent().appending(path: "entertainer-tpt1-30s.wav") }

/// Minimal SMF reader: note on/off pairs in seconds, following tempo changes.
func readMIDI(_ url: URL) throws -> [DetectedNote] {
    let b = [UInt8](try Data(contentsOf: url))
    func be(_ i: Int, _ n: Int) -> Int { (0..<n).reduce(0) { $0 << 8 | Int(b[i + $1]) } }
    let division = be(12, 2), ntrk = be(10, 2)
    var raw: [(tick: Int, kind: Int, a: Int, bb: Int)] = []   // kind 0 off,1 on, 2 tempo
    var i = 14
    for _ in 0..<ntrk {
        let len = be(i + 4, 4); var p = i + 8; let end = p + len
        var tick = 0, status = 0
        func vlq() -> Int { var v = 0; while true { let c = Int(b[p]); p += 1; v = v << 7 | (c & 0x7F); if c < 0x80 { return v } } }
        while p < end {
            tick += vlq()
            var st = Int(b[p])
            if st < 0x80 { st = status } else { p += 1 }
            if st == 0xFF {
                let type = Int(b[p]); p += 1; let l = vlq()
                if type == 0x51 { raw.append((tick, 2, be(p, 3), 0)) }
                p += l
            } else if st == 0xF0 || st == 0xF7 { p += vlq() } else {
                status = st
                let hi = st & 0xF0
                let d1 = Int(b[p]); let d2 = (hi == 0xC0 || hi == 0xD0) ? 0 : Int(b[p + 1])
                p += (hi == 0xC0 || hi == 0xD0) ? 1 : 2
                if hi == 0x90 && d2 > 0 { raw.append((tick, 1, d1, d2)) } else if hi == 0x80 || (hi == 0x90 && d2 == 0) { raw.append((tick, 0, d1, 0)) }
            }
        }
        i = end
    }
    raw.sort { ($0.tick, $0.kind == 2 ? -1 : $0.kind) < ($1.tick, $1.kind == 2 ? -1 : $1.kind) }
    var usPerBeat = 500_000.0, lastTick = 0, secs = 0.0
    var open: [Int: (Double, Int)] = [:]
    var out: [DetectedNote] = []
    for e in raw {
        secs += Double(e.tick - lastTick) / Double(division) * usPerBeat / 1e6; lastTick = e.tick
        switch e.kind {
        case 2: usPerBeat = Double(e.a)
        case 1: open[e.a] = (secs, e.bb)
        default: if let (s, v) = open.removeValue(forKey: e.a) { out.append(DetectedNote(onset: s, offset: secs, pitch: e.a, velocity: v)) }
        }
    }
    return out.sorted { ($0.onset, $0.pitch) < ($1.onset, $1.pitch) }
}

/// Note F1 with 50 ms onset tolerance, same pitch, offsets ignored (convert/common/parity.py).
func noteF1(_ est: [DetectedNote], _ ref: [DetectedNote]) -> Double {
    var used = Set<Int>(); var tp = 0
    for e in est {
        if let j = ref.indices.first(where: { !used.contains($0) && ref[$0].pitch == e.pitch && abs(ref[$0].onset - e.onset) <= 0.05 }) {
            used.insert(j); tp += 1
        }
    }
    guard !est.isEmpty, !ref.isEmpty else { return est.isEmpty && ref.isEmpty ? 1 : 0 }
    let p = Double(tp) / Double(est.count), r = Double(tp) / Double(ref.count)
    return p + r == 0 ? 0 : 2 * p * r / (p + r)
}

func eventF1(_ est: [Double], _ ref: [Double]) -> Double {
    var used = Set<Int>(); var tp = 0
    for e in est { if let j = ref.indices.first(where: { !used.contains($0) && abs(ref[$0] - e) <= 0.05 }) { used.insert(j); tp += 1 } }
    guard !est.isEmpty, !ref.isEmpty else { return 0 }
    let p = Double(tp) / Double(est.count), r = Double(tp) / Double(ref.count)
    return 2 * p * r / (p + r)
}

@Suite(.serialized, .enabled(if: refDir() != nil && modelsDir() != nil)) struct OnDeviceParity {
    let store = ModelStore(cache: FileManager.default.temporaryDirectory.appending(path: "bc-models-test"), localSource: modelsDir())

    @Test func logMelMatchesTorchaudio() throws {
        let ref = try Data(contentsOf: refDir()!.appending(path: "logmel.f32"))
        let r = ref.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        let a = try MonoAudio.load(clip, sampleRate: BeatThis.sampleRate)
        let (ours, frames) = try BeatThis.logMel(a)
        #expect(frames == r.count / 128)
        var maxErr: Float = 0, sumErr: Float = 0
        for i in 0..<min(ours.count, r.count) { let d = abs(ours[i] - r[i]); maxErr = max(maxErr, d); sumErr += d }
        let mean = sumErr / Float(min(ours.count, r.count))
        print("PARITY logmel frames \(frames) vs \(r.count / 128), mean abs err \(mean), max \(maxErr)")
        #expect(mean < 0.05)
    }

    @Test func swiftF0MatchesPython() async throws {
        let m = try await store.model(.swiftF0)
        let a = try MonoAudio.load(clip, sampleRate: SwiftF0.sampleRate)
        let t0 = Date()
        let notes = SwiftF0.segmentNotes(try SwiftF0.detect(a, model: m))
        let ref = try readMIDI(refDir()!.appending(path: "sw.mid"))
        let f1 = noteF1(notes, ref)
        print("PARITY swiftf0 \(notes.count) notes vs \(ref.count), F1 \(f1), \(Int(Date().timeIntervalSince(t0) * 1000)) ms")
        #expect(f1 >= 0.95)
    }

    @Test func basicPitchMatchesPython() async throws {
        let m = try await store.model(.basicPitch)
        let a = try MonoAudio.load(clip, sampleRate: BasicPitch.sampleRate)
        let t0 = Date()
        let notes = BasicPitch.notes(try BasicPitch.infer(a, model: m))
        let ref = try readMIDI(refDir()!.appending(path: "bp.mid"))
        let f1 = noteF1(notes, ref)
        print("PARITY basicpitch \(notes.count) notes vs \(ref.count), F1 \(f1), \(Int(Date().timeIntervalSince(t0) * 1000)) ms")
        print("PARITY bp ours", notes.prefix(6).map { "\($0.pitch)@\(String(format: "%.3f", $0.onset))" })
        print("PARITY bp ref ", ref.prefix(6).map { "\($0.pitch)@\(String(format: "%.3f", $0.onset))" })
        #expect(f1 >= 0.95)
    }

    @Test func beatThisMatchesPython() async throws {
        let m = try await store.model(.beatThis)
        let a = try MonoAudio.load(clip, sampleRate: BeatThis.sampleRate)
        let t0 = Date()
        let b = try BeatThis.track(a, model: m)
        let refLines = try String(contentsOf: refDir()!.appending(path: "beats-small0.beats"), encoding: .utf8)
            .split(separator: "\n").map { $0.split(separator: "\t") }
        let refBeats = refLines.compactMap { Double($0[0]) }
        let refDowns = refLines.filter { $0.count > 1 && $0[1] == "1" }.compactMap { Double($0[0]) }
        let fb = eventF1(b.beats, refBeats), fd = eventF1(b.downbeats, refDowns)
        print("PARITY beatthis \(b.beats.count)/\(refBeats.count) beats F1 \(fb), downbeats \(b.downbeats.count)/\(refDowns.count) F1 \(fd), \(Int(Date().timeIntervalSince(t0) * 1000)) ms")
        #expect(fb >= 0.95 && fd >= 0.9)
    }
}

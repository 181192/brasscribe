import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

private let renderEnv = ProcessInfo.processInfo.environment

private func dB(_ x: Float) -> Double { 20 * log10(Double(max(x, 1e-9))) }

/// Offline renders of whole scores for listening and level analysis, written as WAV files.
///
/// - `BRASSCRIBE_RENDER_OUT`: output directory (the suite runs only when it is set)
/// - `BRASSCRIBE_RENDER_SCORES`: colon-separated brass-band.musicxml paths; a composition.json
///   next to a score supplies its tempo map
/// - `BRASSCRIBE_SOUNDS`: repository root holding the band SoundFont (and the room IR)
/// - `BRASSCRIBE_RENDER_PARTS=1`: also render every part of the first score solo, room off
/// - `BRASSCRIBE_RENDER_IR=1`: also render the convolution hall (`-irhall`)
///
/// Renders run without a room IR, as the shipped app does: hall is the environment node's reverb,
/// room is dry. Each is written as `<name>-apple-<hall|room>.wav` at the default output gain, and
/// as `…-m12.wav` 12 dB below it, where the limiter barely acts.
@Suite(.serialized, .enabled(if: renderEnv["BRASSCRIBE_RENDER_OUT"] != nil)) struct RenderHarnessTests {
    let out = URL(fileURLWithPath: renderEnv["BRASSCRIBE_RENDER_OUT"] ?? "")
    let scores = (renderEnv["BRASSCRIBE_RENDER_SCORES"] ?? "").split(separator: ":").map { URL(fileURLWithPath: String($0)) }

    func load(_ url: URL) throws -> (Score, TempoMap?) {
        let score = try MusicXMLParser.parse(url: url)
        let comp = url.deletingLastPathComponent().appending(path: "composition.json")
        let tempo = FileManager.default.fileExists(atPath: comp.path)
            ? try Composition.decode(Data(contentsOf: comp)).tempoMap : nil
        return (score, tempo)
    }

    func engine(_ score: Score, _ tempo: TempoMap?, ir: Bool = false) throws -> PlaybackEngine {
        try PlaybackEngine(score: score, tempoMap: tempo, soundBank: .locate(bundle: .main), roomIR: ir ? RoomIR.locate() : nil,
                           offlineFormat: PlaybackEngine.offlineFormat())
    }

    func render(_ e: PlaybackEngine, _ score: Score, gainDB: Double, to name: String) throws {
        e.outputGainDB = gainDB
        let t0 = Date()
        let buf = try e.renderScore(fromBeat: 0, beats: Double(score.endTick) / Double(Score.ticksPerQuarter))
        let secs = Date().timeIntervalSince(t0)
        let url = out.appending(path: name)
        try? FileManager.default.removeItem(at: url)
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: buf.format.sampleRate,
            AVNumberOfChannelsKey: buf.format.channelCount, AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true, AVLinearPCMIsNonInterleaved: false,
        ], commonFormat: .pcmFormatFloat32, interleaved: false)
        try file.write(from: buf)
        var hot = 0
        let d = buf.floatChannelData!, n = Int(buf.frameLength), ch = Int(buf.format.channelCount)
        for c in 0..<ch { for i in 0..<n where abs(d[c][i]) > 0.8 { hot += 1 } }
        print(String(format: "RENDER %@: %.2f LUFS, peak %.2f dBFS, |x|>0.8 %.5f, %.1f s audio in %.1f s",
                     name, LoudnessMeter.integrated(buf), dB(buf.peak), Double(hot) / Double(max(1, n * ch)),
                     Double(n) / buf.format.sampleRate, secs))
    }

    func sources() {
        let bank = SoundBank.locate(bundle: .main)
        print("RENDER sounds root: \(renderEnv["BRASSCRIBE_SOUNDS"] ?? "(unset)")")
        print("RENDER band: \(bank.bandStatus)")
        print("RENDER room IR: \(RoomIR.locate()?.path ?? "none"), used only for -irhall")
    }

    @Test func renderScores() throws {
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        sources()
        for url in scores {
            let name = url.deletingLastPathComponent().lastPathComponent
            let (score, tempo) = try load(url)
            print("RENDER \(name): \(score.parts.count) parts, tempo map \(tempo == nil ? "none" : "composition.json")")
            var variants = [(true, false, "hall"), (false, false, "room")]
            if renderEnv["BRASSCRIBE_RENDER_IR"] == "1" { variants.append((true, true, "irhall")) }
            for (roomOn, ir, suffix) in variants {
                let e = try engine(score, tempo, ir: ir)
                e.roomOn = roomOn
                print("RENDER \(name) roomOn=\(roomOn) usesRoomIR=\(e.usesRoomIR)")
                let base = "\(name)-apple-\(suffix)"
                try render(e, score, gainDB: PlaybackEngine.defaultOutputGainDB, to: "\(base).wav")
                try render(e, score, gainDB: PlaybackEngine.defaultOutputGainDB - 12, to: "\(base)-m12.wav")
            }
        }
    }

    @Test(.enabled(if: renderEnv["BRASSCRIBE_RENDER_PARTS"] == "1")) func renderPartsSolo() throws {
        let url = try #require(scores.first)
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        let name = url.deletingLastPathComponent().lastPathComponent
        let (score, tempo) = try load(url)
        var used: Set<String> = []
        for part in score.parts {
            var slug = part.name.lowercased().replacingOccurrences(of: " ", with: "-").replacingOccurrences(of: "♭", with: "b")
            if used.contains(slug) { slug += "-\(part.id.lowercased())" }
            used.insert(slug)
            let e = try engine(score, tempo)
            e.roomOn = false
            e.setSoloed(part.id, true)
            try render(e, score, gainDB: PlaybackEngine.defaultOutputGainDB - 12, to: "\(name)-apple-part-\(slug).wav")
        }
    }
}

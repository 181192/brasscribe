import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

/// The full-band test phrase of sounds/phrases.py (`phrases.json` "band"): every part holds a
/// chord tone for 4 s at mf, three times, while the cornets play 16ths on top and the drums
/// keep time.
func bandPhrase() -> URL? {
    guard let r = repoRoot() else { return nil }
    let f = r.appending(path: "data/sounds/phrases/phrases.json")
    return FileManager.default.fileExists(atPath: f.path) ? f : nil
}

struct Phrase {
    /// Part name → (start s, end s, key, velocity)
    let notes: [String: [(Double, Double, UInt8, UInt8)]]
    let names: [String]

    init(_ url: URL) throws {
        let doc = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let band = try #require(doc["band"] as? [String: [String: Any]])
        var out: [String: [(Double, Double, UInt8, UInt8)]] = [:]
        for (name, v) in band {
            let raw = try #require(v["notes"] as? [[NSNumber]])
            out[name] = raw.map { ($0[0].doubleValue, $0[1].doubleValue, UInt8($0[2].intValue), UInt8($0[3].intValue)) }
        }
        notes = out
        names = out.keys.sorted()
    }

    /// One part per phrase part, by name, so each gets its own band preset and seat.
    func score() throws -> Score {
        var list = "", parts = ""
        for (i, name) in names.enumerated() {
            let perc = name == "Percussion"
            list += """
            <score-part id="P\(i)"><part-name>\(name)</part-name><score-instrument id="P\(i)-I1"><instrument-name>\(name)</instrument-name>
            <instrument-sound>\(perc ? "drum.group.set" : "brass.cornet")</instrument-sound></score-instrument></score-part>
            """
            parts += """
            <part id="P\(i)"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
            <clef><sign>\(perc ? "percussion" : "G")</sign>\(perc ? "" : "<line>2</line>")</clef></attributes>
            <note><rest/><duration>4</duration></note></measure></part>
            """
        }
        let xml = "<?xml version=\"1.0\"?><score-partwise version=\"4.0\"><part-list>\(list)</part-list>\(parts)</score-partwise>"
        return try MusicXMLParser.parse(Data(xml.utf8))
    }

    /// Play the phrase straight into the part samplers (only the parts in `only`, when given),
    /// rendering the engine offline in 10 ms steps.
    func render(_ e: PlaybackEngine, score: Score, only: Set<String>? = nil, seconds: Double = 13.5) throws -> AVAudioPCMBuffer {
        let fmt = e.engine.manualRenderingFormat
        let step = AVAudioFrameCount(fmt.sampleRate / 100)
        let total = AVAudioFrameCount(seconds * fmt.sampleRate)
        let out = try #require(AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: total))
        let chunk = try #require(AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: step))
        var events: [(t: Double, on: Bool, sampler: AVAudioUnitSampler, key: UInt8, vel: UInt8, ch: UInt8)] = []
        for part in score.parts where only?.contains(part.name) ?? true {
            let s = try #require(e.sampler(for: part))
            let ch: UInt8 = part.isPercussion ? 9 : 0
            for n in notes[part.name] ?? [] {
                events.append((n.0, true, s, n.2, n.3, ch))
                events.append((n.1, false, s, n.2, 0, ch))
            }
        }
        events.sort { $0.t != $1.t ? $0.t < $1.t : (!$0.on && $1.on) }
        var next = 0
        while out.frameLength < total {
            let now = Double(out.frameLength) / fmt.sampleRate
            while next < events.count, events[next].t <= now {
                let ev = events[next]
                if ev.on { ev.sampler.startNote(ev.key, withVelocity: ev.vel, onChannel: ev.ch) } else { ev.sampler.stopNote(ev.key, onChannel: ev.ch) }
                next += 1
            }
            let n = min(step, total - out.frameLength)
            #expect(try e.engine.renderOffline(n, to: chunk) == .success)
            for c in 0..<Int(fmt.channelCount) {
                memcpy(out.floatChannelData![c] + Int(out.frameLength), chunk.floatChannelData![c], Int(chunk.frameLength) * 4)
            }
            out.frameLength += chunk.frameLength
        }
        return out
    }
}

/// Below the threshold the stage is a plain gain, so Mute my part and Only this keep the
/// balance between the parts, and with no memory it cannot pump when the Stop fade runs.
@Test func limiterIsLinearBelowTheThresholdAndNeverClips() throws {
    for x: Float in [0, 0.1, -0.5, 0.79] { #expect(OutputStageKernel.limit(x) == x) }
    #expect(OutputStageKernel.limit(0.9) < 0.9 && OutputStageKernel.limit(0.9) > 0.8)
    #expect(OutputStageKernel.limit(50) <= OutputStageKernel.ceiling)
    #expect(OutputStageKernel.limit(-50) >= -OutputStageKernel.ceiling)
    // the curve is monotonic, so it never pumps or inverts
    var last: Float = 0
    for i in 0...400 { let y = OutputStageKernel.limit(Float(i) / 100); #expect(y >= last); last = y }
}

// A hot buffer (12 dB over full scale) through the kernel stays under the ceiling.
@Test func limiterKeepsAHotBufferUnderFullScale() {
    let k = OutputStageKernel()
    k.gain = 4
    var x = (0..<4410).map { Float(sin(Double($0) * 2 * .pi * 440 / 44100)) }
    x.withUnsafeMutableBufferPointer { k.process($0.baseAddress!, count: $0.count) }
    #expect(x.map(abs).max()! <= OutputStageKernel.ceiling)
    #expect(x.map(abs).max()! > OutputStageKernel.threshold)
}

private func dB(_ x: Float) -> Double { 20 * log10(Double(max(x, 1e-9))) }

@Suite(.serialized, .enabled(if: bandPhrase() != nil && bandSoundFont() != nil)) struct OutputStageTests {
    let phrase: Phrase
    let score: Score

    init() throws {
        phrase = try Phrase(try #require(bandPhrase()))
        score = try phrase.score()
    }

    func engine() throws -> PlaybackEngine {
        // the room the app ships with: the environment node's hall (no IR file in the bundle)
        let e = try PlaybackEngine(score: score, soundBank: .locate(bundle: .main), roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
        #expect(e.loadedInstruments == score.parts.count)
        return e
    }

    /// The full band peaks just under full scale and never clips.
    @Test func fullBandPeaksNearMinusOneWithoutClipping() throws {
        let e = try engine()
        let buf = try phrase.render(e, score: score)
        let peak = buf.peak
        print("OUTPUT full band peak \(dB(peak)) dBFS at \(e.outputGainDB) dB")
        #expect(peak < 1, "clipped")
        #expect(peak <= OutputStageKernel.ceiling)
        #expect(dB(peak) > -3 && dB(peak) < -0.5, "full band peak \(dB(peak)) dBFS")
    }

    /// A solo part is louder than before the level-matched presets (−5.5 dB then), and the stage
    /// does not squash it.
    @Test func soloCornetIsNotQuieterThanBefore() throws {
        let e = try engine()
        let loud = try phrase.render(e, score: score, only: ["Solo Cornet"])
        e.outputGainDB = 0
        let unity = try phrase.render(e, score: score, only: ["Solo Cornet"])
        let lift = dB(loud.peak) - dB(unity.peak)
        print("OUTPUT solo cornet \(dB(loud.peak)) dBFS, \(dB(unity.peak)) dBFS at unity")
        #expect(lift >= 5.5)
        #expect(abs(lift - PlaybackEngine.defaultOutputGainDB) < 0.5, "a solo part stays below the limiter")
    }

    /// The metronome bypasses the stage: its click is loud enough beside the band and never clips.
    @Test func metronomeStaysUnderTheCeiling() throws {
        let e = try engine()
        let fmt = e.engine.manualRenderingFormat
        let buf = try #require(AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: 4096))
        e.metronome.startNote(UInt8(MIDIWriter.metronomeHigh), withVelocity: 110, onChannel: 9)
        var peak: Float = 0
        for _ in 0..<10 {
            #expect(try e.engine.renderOffline(4096, to: buf) == .success)
            peak = max(peak, buf.peak)
        }
        print("OUTPUT metronome \(dB(peak)) dBFS")
        #expect(peak < 1)
        #expect(dB(peak) > -30, "the click is audible")
    }
}

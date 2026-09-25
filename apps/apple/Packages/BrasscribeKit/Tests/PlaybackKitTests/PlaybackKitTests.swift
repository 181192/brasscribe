import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

func goldenDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return URL(fileURLWithPath: env) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// Offline-rendered playback of the golden Mikkel score. Bars 2–3 (beats 4–12) contain
/// the solo cornet and the basses.
@Suite(.serialized, .enabled(if: goldenDir() != nil)) struct PlaybackTests {
    let score: Score
    let composition: Composition

    init() throws {
        let dir = try #require(goldenDir())
        score = try MusicXMLParser.parse(url: dir.appending(path: "brass-band.musicxml"))
        composition = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    }

    func engine(original: URL? = nil) throws -> PlaybackEngine {
        try PlaybackEngine(score: score, tempoMap: composition.tempoMap, originalURL: original,
                           soundBank: .locate(bundle: .main), offlineFormat: PlaybackEngine.offlineFormat())
    }

    @Test func playsABar() throws {
        let e = try engine()
        let buf = try e.renderScore(fromBeat: 4, beats: 8)
        #expect(buf.frameLength > 0)
        #expect(buf.peak > 0.01, "bars 2-3 should sound (sound bank: \(e.soundBank.description))")
    }

    @Test func muteAllIsSilentAndSoloWorks() throws {
        let e = try engine()
        for p in score.parts { e.setMuted(p.id, true) }
        let silent = try e.renderScore(fromBeat: 4, beats: 8)
        #expect(silent.peak < 0.001)
        for p in score.parts { e.setMuted(p.id, false) }
        let bass = try #require(score.parts.first { $0.name == "B♭ Bass" })
        e.setSoloed(bass.id, true)
        #expect(!e.isAudible(score.parts[1].id))
        #expect(e.isAudible(bass.id))
        #expect(try e.renderScore(fromBeat: 4, beats: 8).peak > 0.005)
    }

    @Test func rateStretchesTime() throws {
        let e = try engine()
        e.rate = 0.5
        let slow = try e.renderScore(fromBeat: 4, beats: 2)
        e.rate = 1
        let normal = try e.renderScore(fromBeat: 4, beats: 2)
        #expect(Double(slow.frameLength) / Double(normal.frameLength) > 1.95)
        e.rate = 5
        #expect(e.rate == 1.5)
        e.rate = 0.1
        #expect(e.rate == 0.25)
    }

    @Test func loopClampsAndSeeks() throws {
        let e = try engine()
        e.setLoop(3...4)
        #expect(e.loop == 3...4)
        #expect(e.position == 12)
        e.setLoop(200...300)
        let last = score.measures.count - 1
        #expect(e.loop == last...last)
        e.setLoop(nil)
        #expect(e.loop == nil)
    }

    @Test func metronomeSoundsWhenScoreIsMuted() throws {
        let e = try engine()
        for p in score.parts { e.setMuted(p.id, true) }
        e.metronomeOn = true
        #expect(try e.renderScore(fromBeat: 0, beats: 4).peak > 0.001)
    }

    @Test func originalAndScoreShareTheBeat() throws {
        let tm = composition.tempoMap
        let e = try engine()
        e.seek(toBar: 9)
        #expect(e.position == 36)
        e.setSource(.original)
        #expect(abs(e.originalSeconds - tm.seconds(atBeat: 36)) < 1e-6)
        #expect(abs(e.position - 36) < 1e-6)
        e.setSource(.score)
        #expect(abs(e.position - 36) < 1e-6)
    }

    @Test func transposeRetunesPitchedSamplers() throws {
        let e = try engine()
        e.transposeSemitones = -2
        let perc = e.samplers[.percussion]
        #expect(perc?.globalTuning == 0)
        #expect(e.samplers[.cornets]?.globalTuning == -200)
    }
}

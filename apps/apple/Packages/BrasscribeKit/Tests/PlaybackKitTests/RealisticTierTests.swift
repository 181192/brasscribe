import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

/// Repository root: the worktree holding `sounds/` and the `data/` link.
func repoRoot() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        // sounds/band.py: apps/apple/Sounds/mapping.json (staged bundle copy) matches "sounds/" on a case-insensitive volume
        if FileManager.default.fileExists(atPath: dir.appending(path: "sounds/band.py").path) { return dir }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

func builtSounds() -> URL? {
    guard let r = repoRoot() else { return nil }
    let b = r.appending(path: "data/sounds/built")
    // A set built before Solo Cornet had its own target lacks the lead part.
    return FileManager.default.fileExists(atPath: b.appending(path: "solo-cornet/solo-cornet.sf2").path) ? b : nil
}

func bandSoundFont() -> URL? {
    guard let r = repoRoot() else { return nil }
    let f = r.appending(path: "data/sounds/band/brasscribe-band-16bit.sf2")
    return FileManager.default.fileExists(atPath: f.path) ? f : nil
}

/// The band SoundFont: one preset per part (bank MSB 0x79 + LSB bank), drums on 0x78/0,
/// channel_gain_db as the part's gain.
@Test(.enabled(if: bandSoundFont() != nil && goldenDir() != nil)) func bandSoundFontLoadsEveryPart() throws {
    let root = try #require(repoRoot())
    let parts = try BandSounds.loadBand(mapping: root.appending(path: "sounds/mapping.json"),
                                        seating: root.appending(path: "sounds/seating.json"), soundFont: try #require(bandSoundFont()))
    let score = try MusicXMLParser.parse(url: try #require(goldenDir()).appending(path: "brass-band.musicxml"))
    #expect(score.parts.allSatisfy { parts[$0.name] != nil }, "every golden part has a band preset")
    #expect(parts["Percussion"]?.bankMSB == 0x78)
    #expect(parts["Repiano Cornet"]?.bankLSB == 2)
    let t0 = Date()
    let e = try PlaybackEngine(score: score, soundBank: SoundBank(general: nil, perPart: parts), offlineFormat: PlaybackEngine.offlineFormat())
    let load = Date().timeIntervalSince(t0)
    #expect(e.loadedInstruments == score.parts.count)
    // each part alone makes sound where it plays
    var silent: [String] = []
    for p in score.parts {
        guard let first = p.playbackNotes.first else { continue }
        for q in score.parts { e.setSoloed(q.id, q.id == p.id) }
        let beat = Double(first.startTick) / Double(Score.ticksPerQuarter)
        if try e.renderScore(fromBeat: beat, beats: 4).peak < 0.001 { silent.append(p.name) }
    }
    print("BANDSF2 load \(Int(load * 1000)) ms, \(e.loadedInstruments) presets; silent parts \(silent)")
    #expect(silent.isEmpty)
}

/// The brass-band sample instruments from sounds/, when they have been built.
@Test(.enabled(if: builtSounds() != nil && goldenDir() != nil)) func realisticTierLoadsAndSounds() throws {
    let root = try #require(repoRoot())
    let parts = try BandSounds.load(mapping: root.appending(path: "sounds/mapping.json"),
                                    seating: root.appending(path: "sounds/seating.json"), built: try #require(builtSounds()))
    #expect(parts["Solo Cornet"]?.target == "solo-cornet")
    #expect(parts["Solo Cornet"]?.azimuth != nil)
    let score = try MusicXMLParser.parse(url: try #require(goldenDir()).appending(path: "brass-band.musicxml"))
    let bank = SoundBank(general: nil, perPart: parts)
    let t0 = Date()
    let e = try PlaybackEngine(score: score, soundBank: bank, offlineFormat: PlaybackEngine.offlineFormat())
    print("REALISTIC load \(Int(Date().timeIntervalSince(t0) * 1000)) ms, \(e.loadedInstruments) samplers loaded, \(bank.description)")
    let brass = score.parts.filter { parts[$0.name] != nil }
    #expect(e.loadedInstruments >= brass.count)
    let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
    #expect(e.sampler(for: solo) !== e.sampler(for: score.parts.first { $0.name == "Repiano Cornet" }!))
    let buf = try e.renderScore(fromBeat: 32, beats: 8)
    #expect(buf.peak > 0.005)
}

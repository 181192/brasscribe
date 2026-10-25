import AVFoundation
import Foundation
import Testing
@testable import TabKit

/// The player on a short tone of its own: it reads the file, keeps the pitch at another speed and says when it ends.
@MainActor
struct RecordingPlayerTests {
    final class Heard: RecordingPlayerListener {
        var playing: [Bool] = []
        var ended = 0
        var failed = 0
        func recordingPlaying(_ playing: Bool) { self.playing.append(playing) }
        func recordingEnded() { ended += 1 }
        func recordingFailed() { failed += 1 }
    }

    let dir = TempDir()

    /// Half a second of a quiet tone, as a WAV file.
    func tone() throws -> URL {
        let url = dir.file("tone.wav")
        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
        let file = try AVAudioFile(forWriting: url, settings: format.settings)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 22_050)!
        buffer.frameLength = 22_050
        for i in 0..<Int(buffer.frameLength) { buffer.floatChannelData![0][i] = 0.1 * sin(Float(i) * 2 * .pi * 440 / 44_100) }
        try file.write(from: buffer)
        return url
    }

    func until(_ seconds: Double, _ done: () -> Bool) async {
        let end = Date().addingTimeInterval(seconds)
        while !done() && Date() < end { try? await Task.sleep(for: .milliseconds(20)) }
    }

    @Test(.timeLimit(.minutes(1))) func aToneIsReadPlayedFasterWithItsPitchAndEnds() async throws {
        let heard = Heard()
        let player = AVRecordingPlayer(file: try tone(), listener: heard, silent: true)
        defer { player.release() }
        await until(5) { player.duration > 0 }
        #expect(abs(player.duration - 0.5) < 0.05)
        #expect(player.pitchAlgorithm == .spectral)
        player.speed = 1.5
        #expect(player.appliedRate == 1.5)
        player.play()
        #expect(player.asked)
        await until(10) { heard.ended > 0 }
        #expect(heard.ended == 1)
        #expect(!player.playing && !player.asked)
        #expect(heard.playing.last == false)
        #expect(heard.failed == 0)
    }

    @Test(.timeLimit(.minutes(1))) func aFileThatIsNoSoundFails() async throws {
        let heard = Heard()
        let url = dir.file("noise.wav")
        try Data("not a sound".utf8).write(to: url)
        let player = AVRecordingPlayer(file: url, listener: heard, silent: true)
        defer { player.release() }
        await until(5) { heard.failed > 0 }
        // the iPhone's player may read the file only once it is asked to play it
        if heard.failed == 0 { player.play(); await until(5) { heard.failed > 0 } }
        #expect(heard.failed == 1)
        #expect(!player.playing)
    }
}

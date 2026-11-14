import AVFoundation
import Foundation
import os

/// The tab's own sound as the model plays it: a recording's player that can also leave its notes out, tick the
/// beats and count a bar in.
@MainActor
public protocol TabSoundPlaying: RecordingPlayer {
    /// The notes sound; without them only the count-in and the metronome do.
    var notes: Bool { get set }
    /// The beats tick.
    var metronome: Bool { get set }
    /// A little faster or slower than `speed` (1: as it is), to come back beside a recording it plays along with
    /// without a jump: the notes come a little sooner or later, at their own pitch.
    var trim: Double { get set }
    /// A count-in is still heard: the song has not started to move.
    var countingIn: Bool { get }
    /// The next `play` counts in first: `beats` clicks, `beatSeconds` apart at the recording's own speed.
    func countIn(beats: Int, beatSeconds: Double)
}

/// What the sound's own thread and the main thread share: the synth, behind a lock that the sound's thread never
/// waits for (a block it cannot take the lock for is silent).
final class TabSoundCore: @unchecked Sendable {
    private let lock = OSAllocatedUnfairLock()
    private let synth: TabSynth
    private var running = false
    private var reachedEnd = false

    init(synth: TabSynth) { self.synth = synth }

    /// On the main thread: reads or changes the synth.
    func with<T>(_ work: (TabSynth) -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return work(synth)
    }

    func run(_ on: Bool) {
        lock.lock()
        running = on
        if on { reachedEnd = false }
        lock.unlock()
    }

    /// The tab's end was reached while it ran.
    var ended: Bool {
        lock.lock()
        defer { lock.unlock() }
        return reachedEnd
    }

    /// On the sound's thread: the next `frames` frames. The buffers come in silent.
    func render(frames: Int, left: UnsafeMutablePointer<Float>, right: UnsafeMutablePointer<Float>) {
        guard lock.lockIfAvailable() else { return }
        defer { lock.unlock() }
        guard running else { return }
        if !synth.render(frames: frames, left: left, right: right) {
            running = false
            reachedEnd = true
        }
    }
}

/// The instrument on an `AVAudioUnitSampler`: notes are handed to it for the frame they start at.
final class SamplerVoices: TabVoices, @unchecked Sendable {
    private let send: AUScheduleMIDIEventBlock?
    private static let velocity: UInt8 = 100

    init(_ sampler: AVAudioUnitSampler) { send = sampler.auAudioUnit.scheduleMIDIEventBlock }

    private func midi(_ status: UInt8, _ a: UInt8, _ b: UInt8, at frame: Int) {
        guard let send else { return }
        withUnsafeTemporaryAllocation(of: UInt8.self, capacity: 3) { bytes in
            bytes[0] = status; bytes[1] = a; bytes[2] = b
            send(AUEventSampleTimeImmediate + AUEventSampleTime(frame), 0, 3, bytes.baseAddress!)
        }
    }

    func on(_ pitch: Int, at frame: Int) { midi(0x90, UInt8(pitch), Self.velocity, at: frame) }
    func off(_ pitch: Int, at frame: Int) { midi(0x80, UInt8(pitch), 0, at: frame) }
    /// All sound off.
    func silence() { midi(0xB0, 120, 0, at: 0) }
}

/// The tab's own sound on this device: the notes on one program of a SoundFont (an `AVAudioUnitSampler`), the
/// clicks from `TabSynth`, on the recording's time, so it is played, slowed down, moved and repeated as the
/// recording is (`RecordingPlayer`).
///
/// Setting up the audio session is the app's job, as for the recording. Used from the main actor only.
@MainActor
public final class EngineTabSoundPlayer: TabSoundPlaying {
    /// General MIDI: a bass played with the fingers, a nylon-string guitar (the nearest to a ukulele), a steel-string guitar.
    public static let bass: UInt8 = 33
    public static let nylon: UInt8 = 24
    public static let steel: UInt8 = 25

    /// The small SoundFont alphaTab comes with (scripts/fetch-alphatab.sh), when the build carries it.
    public static var soundFont: URL? {
        Bundle.module.url(forResource: "sonivox", withExtension: "sf2", subdirectory: "page/alphatab/soundfont")
    }

    /// The program an instrument sounds on, by the engine's instrument family ("bass-4", "guitar-6", "ukulele");
    /// without one, a bass when the page goes below a guitar's lowest string.
    public static func program(family: String?, lowest: Int?) -> UInt8 {
        if let family {
            if family.hasPrefix("bass") { return bass }
            if family.hasPrefix("ukulele") { return nylon }
            return steel
        }
        if let lowest, lowest < 40 { return bass }
        return steel
    }

    private let engine = AVAudioEngine()
    private let sampler = AVAudioUnitSampler()
    private let core: TabSoundCore
    private let end: Double
    private weak var listener: (any RecordingPlayerListener)?
    private var watch: Task<Void, Never>?
    private var at = 0.0

    public private(set) var asked = false

    /// Throws when the SoundFont cannot be read or has no such program.
    public init(score: TabSoundScore, program: UInt8, soundFont: URL, listener: any RecordingPlayerListener, silent: Bool = false,
                offline: Bool = false) throws {
        self.listener = listener
        end = score.end
        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
        if offline { try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096) }
        let core = TabSoundCore(synth: TabSynth(score: score, voices: SamplerVoices(sampler), sampleRate: format.sampleRate))
        self.core = core
        let clicks = AVAudioSourceNode(format: format) { _, _, frames, buffers -> OSStatus in
            let out = UnsafeMutableAudioBufferListPointer(buffers)
            guard out.count >= 2, let left = out[0].mData?.assumingMemoryBound(to: Float.self),
                  let right = out[1].mData?.assumingMemoryBound(to: Float.self) else { return noErr }
            left.update(repeating: 0, count: Int(frames))
            right.update(repeating: 0, count: Int(frames))
            core.render(frames: Int(frames), left: left, right: right)
            return noErr
        }
        engine.attach(sampler)
        engine.attach(clicks)
        engine.connect(sampler, to: engine.mainMixerNode, format: format)
        engine.connect(clicks, to: engine.mainMixerNode, format: format)
        // The notes go out 6 dB down (the clicks are made at their level): a full chord with a click over it, and the
        // recording beside it in the device's mixer, have room.
        sampler.overallGain = -6
        if silent { engine.mainMixerNode.outputVolume = 0 }
        try sampler.loadSoundBankInstrument(at: soundFont, program: program, bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB),
                                            bankLSB: UInt8(kAUSampler_DefaultBankLSB))
        engine.prepare()
    }

    public var playing: Bool { asked && engine.isRunning }

    public var countingIn: Bool { asked && core.with { $0.countingIn } }

    /// Times the stretch being repeated has turned back to its start.
    public var turns: Int { core.with { $0.turns } }

    public var position: Double {
        guard asked else { return at }
        // What is heard now was rendered a moment ago.
        let behind = engine.isInManualRenderingMode ? 0 : engine.outputNode.presentationLatency
        let (rendered, counting, turned) = core.with { ($0.position - behind * $0.speed, $0.countingIn, $0.turns > $0.turnsAtJump) }
        if counting { return at }
        var heard = rendered
        // Rendered past a turn of the stretch that has not been heard yet: the song is still before its end.
        if let again = repeatSpan, heard < again.lowerBound, turned { heard += again.upperBound - again.lowerBound }
        return min(max(heard, min(at, rendered)), max(end, at))
    }

    public var duration: Double { end }

    public var speed: Float = 1 { didSet { let s = Double(speed) * trim; core.with { $0.speed = s } } }
    public var trim: Double = 1 { didSet { if trim != oldValue { let s = Double(speed) * trim; core.with { $0.speed = s } } } }
    public var repeatSpan: ClosedRange<Double>? { didSet { let r = repeatSpan; core.with { $0.repeatSpan = r } } }
    public var notes = true { didSet { let n = notes; core.with { $0.notes = n } } }
    public var metronome = false { didSet { let m = metronome; core.with { $0.metronome = m } } }

    public func countIn(beats: Int, beatSeconds: Double) {
        core.with { $0.countIn(beats: beats, beatSeconds: beatSeconds) }
    }

    public func play() {
        if asked { return }
        if at >= end - 0.05 && repeatSpan == nil { seek(to: 0) }
        do { if !engine.isRunning { try engine.start() } } catch {
            PracticeModel.log.warning("the tab's sound could not start: \(error.localizedDescription, privacy: .public)")
            listener?.recordingFailed()
            return
        }
        asked = true
        core.run(true)
        watch?.cancel()
        watch = Task { [weak self] in
            // Looked at a few times a second: the tab's end, and the device taking the sound away.
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(50))
                guard let self, self.asked else { return }
                if self.core.ended { self.reachedEnd(); return }
                if !self.engine.isRunning { self.stop(at: self.position); self.listener?.recordingPlaying(false); return }
            }
        }
        listener?.recordingPlaying(true)
    }

    public func pause() {
        if !asked { return }
        stop(at: position)
        listener?.recordingPlaying(false)
    }

    private func reachedEnd() {
        stop(at: end)
        listener?.recordingEnded()
    }

    /// Stops the sound at once, with the song at `seconds`.
    private func stop(at seconds: Double) {
        at = seconds
        asked = false
        watch?.cancel()
        watch = nil
        core.run(false)
        core.with { $0.seek(seconds) }
        if !engine.isInManualRenderingMode { engine.pause() }
    }

    public func seek(to seconds: Double) {
        at = max(seconds, 0)
        let to = at
        core.with { $0.seek(to) }
    }

    public func release() {
        watch?.cancel()
        watch = nil
        asked = false
        core.run(false)
        engine.stop()
    }

    /// For the tests, with `offline`: the next `frames` frames of what would be heard, one channel.
    func rendered(frames: Int) throws -> [Float] {
        var out: [Float] = []
        let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: engine.manualRenderingMaximumFrameCount)!
        while out.count < frames {
            let n = min(AVAudioFrameCount(frames - out.count), buffer.frameCapacity)
            guard try engine.renderOffline(n, to: buffer) == .success, let data = buffer.floatChannelData else { break }
            out += UnsafeBufferPointer(start: data[0], count: Int(buffer.frameLength))
        }
        return out
    }
}

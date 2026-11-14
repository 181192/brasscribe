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

/// The clicks of one render cycle, made before the notes' instrument and the clicks are pulled (the mixer's
/// pre-render pass) and handed out when the clicks are. Used on the sound's thread only; made once, never grown.
final class ClickBuffer: @unchecked Sendable {
    static let capacity = 8_192
    let left = UnsafeMutablePointer<Float>.allocate(capacity: capacity)
    let right = UnsafeMutablePointer<Float>.allocate(capacity: capacity)
    /// Frames made for this cycle.
    var frames = 0

    deinit {
        left.deallocate()
        right.deallocate()
    }

    /// Makes the next `count` frames: the notes are handed to the instrument for this cycle, the clicks kept here.
    func make(_ count: Int, _ core: TabSoundCore) {
        var done = 0
        while done < count {
            let n = min(count - done, Self.capacity)
            left.update(repeating: 0, count: n)
            right.update(repeating: 0, count: n)
            core.render(frames: n, left: left, right: right)
            done += n
        }
        frames = min(count, Self.capacity)
    }

    /// Copies the clicks made for this cycle into the node's output.
    func take(_ count: Int, left out: UnsafeMutablePointer<Float>, right outRight: UnsafeMutablePointer<Float>) {
        let n = min(count, frames)
        out.update(from: left, count: n)
        outRight.update(from: right, count: n)
        if count > n {
            (out + n).update(repeating: 0, count: count - n)
            (outRight + n).update(repeating: 0, count: count - n)
        }
        frames = 0
    }
}

/// A value that is handed to another thread on purpose, where it is used alone.
struct Handed<T>: @unchecked Sendable { let value: T }

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
    /// The notes and the clicks meet here, before the limiter.
    private let mix = AVAudioMixerNode()
    /// Keeps a full chord with a click over it, and anything else that adds up, under full scale.
    private let limiter = AVAudioUnitEffect(audioComponentDescription: AudioComponentDescription(
        componentType: kAudioUnitType_Effect, componentSubType: kAudioUnitSubType_PeakLimiter,
        componentManufacturer: kAudioUnitManufacturer_Apple, componentFlags: 0, componentFlagsMask: 0))
    private let core: TabSoundCore
    private let clickBuffer = ClickBuffer()
    private var observer: Int?
    private let end: Double
    private let soundFont: URL
    private let program: UInt8
    private weak var listener: (any RecordingPlayerListener)?
    private var watch: Task<Void, Never>?
    private var notices: [any NSObjectProtocol] = []
    /// The sound was taken away on purpose (headphones pulled out, a call): it pauses rather than starting again.
    private var takenAway = false
    private var at = 0.0

    public private(set) var asked = false

    /// The player for `score`, without its instrument yet: `load` reads it.
    public init(score: TabSoundScore, program: UInt8, soundFont: URL, listener: any RecordingPlayerListener, silent: Bool = false,
                offline: Bool = false) throws {
        self.listener = listener
        self.soundFont = soundFont
        self.program = program
        end = score.end
        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
        if offline { try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096) }
        let core = TabSoundCore(synth: TabSynth(score: score, voices: SamplerVoices(sampler), sampleRate: format.sampleRate))
        self.core = core
        let clickBuffer = clickBuffer
        let clicks = AVAudioSourceNode(format: format, renderBlock: Self.theClicks(clickBuffer))
        engine.attach(sampler)
        engine.attach(clicks)
        engine.attach(mix)
        engine.attach(limiter)
        engine.connect(sampler, to: mix, format: format)
        engine.connect(clicks, to: mix, format: format)
        engine.connect(mix, to: limiter, format: format)
        engine.connect(limiter, to: engine.mainMixerNode, format: format)
        // Each cycle the notes are handed to the instrument, and the clicks made, before the mixer pulls either: the
        // notes sound in the cycle they are written for, with the clicks, whichever of the two the mixer pulls first.
        observer = mix.auAudioUnit.token(byAddingRenderObserver: Self.beforeTheMix(clickBuffer, core))
        // The notes go out 6 dB down (the clicks are made at their level): a full chord with a click over it, and the
        // recording beside it in the device's mixer, have room.
        sampler.overallGain = -6
        if silent { engine.mainMixerNode.outputVolume = 0 }
        watchTheDevice()
    }

    /// Where instruments are read, one after the other.
    private static let reading = DispatchQueue(label: "no.kalli.scribe.tab.instrument", qos: .userInitiated)

    /// The tab's sound on this device with its instrument read, or nil when the build has no SoundFont or it cannot be read.
    public static func make(score: TabSoundScore, program: UInt8, listener: any RecordingPlayerListener) async -> (any TabSoundPlaying)? {
        guard let font = soundFont, let player = try? EngineTabSoundPlayer(score: score, program: program, soundFont: font, listener: listener) else { return nil }
        do { try await player.load() } catch {
            PracticeModel.log.warning("the tab's instrument could not be read: \(error.localizedDescription, privacy: .public)")
            player.release()
            return nil
        }
        return player
    }

    /// The notes' level in dB (they go out at -6); for the tests.
    var notesGain: Float {
        get { sampler.overallGain }
        set { sampler.overallGain = newValue }
    }

    /// Reads the instrument from the SoundFont, away from the main thread (it is over a megabyte to parse). Throws
    /// when the SoundFont cannot be read or has no such program.
    public func load() async throws {
        let sampler = Handed(value: sampler), font = soundFont, program = program
        // One instrument is read at a time: Core Audio stops the process when two samplers read theirs at once.
        try await withCheckedThrowingContinuation { (done: CheckedContinuation<Void, any Error>) in
            Self.reading.async {
                do {
                    try sampler.value.loadSoundBankInstrument(at: font, program: program, bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB),
                                                              bankLSB: UInt8(kAUSampler_DefaultBankLSB))
                    done.resume()
                } catch {
                    done.resume(throwing: error)
                }
            }
        }
        engine.prepare()
    }

    /// The device's sound changing under the player: a new output (headphones plugged in, another device chosen on a
    /// Mac) stops the engine, and it starts again where it was; headphones pulled out, or a call, pause it.
    private func watchTheDevice() {
        let center = NotificationCenter.default
        notices.append(center.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.outputChanged() }
        })
        #if os(iOS)
        notices.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] note in
            let reason = (note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt).flatMap(AVAudioSession.RouteChangeReason.init)
            MainActor.assumeIsolated { if reason == .oldDeviceUnavailable { self?.soundTakenAway() } }
        })
        notices.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            let kind = (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt).flatMap(AVAudioSession.InterruptionType.init)
            MainActor.assumeIsolated { if kind == .began { self?.soundTakenAway() } }
        })
        #endif
    }

    /// Headphones pulled out, a call: the song pauses where it is.
    func soundTakenAway() {
        takenAway = true
        if asked { stop(at: position); listener?.recordingPlaying(false) }
    }

    /// The engine stopped for a new output: it starts again, unless the sound was taken away on purpose.
    func outputChanged() {
        guard asked, !engine.isInManualRenderingMode else { return }
        if takenAway { stop(at: position); listener?.recordingPlaying(false); return }
        if !engine.isRunning { restart() }
    }

    // The two blocks the sound's thread runs are made outside the main actor: made inside it, they would check on
    // that thread that they run on the main one, and stop the app.

    nonisolated private static func theClicks(_ clicks: ClickBuffer) -> AVAudioSourceNodeRenderBlock {
        { _, _, frames, buffers -> OSStatus in
            let out = UnsafeMutableAudioBufferListPointer(buffers)
            guard out.count >= 2, let left = out[0].mData?.assumingMemoryBound(to: Float.self),
                  let right = out[1].mData?.assumingMemoryBound(to: Float.self) else { return noErr }
            clicks.take(Int(frames), left: left, right: right)
            return noErr
        }
    }

    nonisolated private static func beforeTheMix(_ clicks: ClickBuffer, _ core: TabSoundCore) -> AURenderObserver {
        { flags, _, frames, _ in
            if flags.contains(.unitRenderAction_PreRender) { clicks.make(Int(frames), core) }
        }
    }

    /// For the tests: the device stops the engine, as it does for a new output.
    func deviceStoppedTheEngine() { engine.stop() }

    private func restart() {
        do { try engine.start() } catch {
            PracticeModel.log.warning("the tab's sound could not go on on the new output: \(error.localizedDescription, privacy: .public)")
            stop(at: position)
            listener?.recordingPlaying(false)
        }
    }

    public var playing: Bool { asked && engine.isRunning }

    public var countingIn: Bool { asked && core.with { $0.countingIn } }

    /// Times the stretch being repeated has turned back to its start.
    public var turns: Int { core.with { $0.turns } }

    public var position: Double {
        guard asked else { return at }
        // What is heard now was rendered a moment ago.
        let behind = (engine.isInManualRenderingMode ? 0 : engine.outputNode.presentationLatency) + limiter.auAudioUnit.latency
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
        takenAway = false
        core.run(true)
        watch?.cancel()
        watch = Task { [weak self] in
            // Looked at a few times a second: the tab's end, and the device taking the sound away.
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(50))
                guard let self, self.asked else { return }
                if self.core.ended { self.reachedEnd(); return }
                // Stopped under it: a new output is played on (its notice may come after this look); else it pauses.
                if !self.engine.isRunning {
                    if self.takenAway { self.stop(at: self.position); self.listener?.recordingPlaying(false); return }
                    self.restart()
                    if !self.asked { return }
                }
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
        for notice in notices { NotificationCenter.default.removeObserver(notice) }
        notices = []
        if let observer { mix.auAudioUnit.removeRenderObserver(observer) }
        observer = nil
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

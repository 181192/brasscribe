import AudioUnitCatch
import AVFoundation
import Foundation
import ScoreKit

/// Score and original-recording playback for practice.
///
/// Graph:
/// ```
/// sequencer tracks ─▶ one AVAudioUnitSampler per part ─▶ AVAudioEnvironmentNode (seat + hall) ─▶ band bus
/// band bus ─▶ output stage (make-up gain + soft limiter) ────────────────────────────────────┐
/// metronome track  ─▶ metronome sampler ─────────────────────────────────────────────────────├▶ main mixer
/// original file    ─▶ AVAudioPlayerNode ─▶ AVAudioUnitTimePitch ─▶ output stage (level match) ─┘
/// ```
/// Band and recording play at the same loudness (sounds/playback-levels.json): the band through
/// its make-up gain and limiter, the recording measured once when loaded and gained to the loudness
/// the band plays this score at (`recordingTargetLUFS`, from the score's dynamics and parts).
/// Positions are in quarter-note beats from the start of bar 1, shared by score and
/// original; the Composition's tempo map converts to seconds in the recording.
public final class PlaybackEngine {
    public enum Source: Equatable { case score, original }
    public enum State: Equatable { case stopped, countingIn(beat: Int), playing }

    public let score: Score
    public let tempoMap: TempoMap?
    public let engine = AVAudioEngine()
    public private(set) var soundBank: SoundBank
    public private(set) var state: State = .stopped
    public private(set) var source: Source = .score
    public private(set) var loadedInstruments = 0

    // Practice settings
    public var rate: Double = 1 { didSet { rate = min(1.5, max(0.25, rate)); applyRate() } }
    public var transposeSemitones: Int = 0 { didSet { applyTranspose() } }
    public var metronomeOn = false { didSet { applyMutes() } }
    public var countInBars = 0
    public var roomOn = true { didSet { applyRoom() } }
    /// Inclusive bar range (0-based measure indices) to loop, nil for none.
    public private(set) var loop: ClosedRange<Int>?

    private var muted: Set<String> = []
    private var soloed: Set<String> = []

    // Nodes
    let environment = AVAudioEnvironmentNode()
    var samplers: [String: AVAudioUnitSampler] = [:]

    /// One sampler per part, always: two parts on one sampler share its MIDI channels, so one
    /// part's note-off would end the other's note on the same pitch (unisons are everywhere in
    /// band scores), and the first part's preset would play the other part too.
    func samplerKey(_ part: Part) -> String { "part:\(part.id)" }

    /// The sampler playing a part.
    public func sampler(for part: Part) -> AVAudioUnitSampler? { samplers[samplerKey(part)] }
    let metronome = AVAudioUnitSampler()
    let player = AVAudioPlayerNode()
    let timePitch = AVAudioUnitTimePitch()
    var sequencer: AVAudioSequencer!
    /// Each part's sequencer tracks: one, or for a band kit one per drum group (`PlaybackLevels.kitGroups`).
    var partTracks: [String: [AVMusicTrack]] = [:]
    /// The score's MIDI options: the sampler's velocity curve, and the band kit in drum groups.
    lazy var midiOptions: MIDIWriter.Options = {
        var o = MIDIWriter.Options(includeMetronome: true, velocityMap: { v, percussion in
            PlaybackLevels.samplerVelocity(v, percussion: percussion)
        })
        if let kit = kitGroups {
            o.drumGroup = { kit.of($0) }
        }
        return o
    }()

    /// The drum groups of the score's band kit (its first percussion part's kit), nil without one.
    lazy var kitGroups: PlaybackLevels.KitGroups? = score.parts.lazy.filter(\.isPercussion)
        .compactMap { self.soundBank.partSound(for: $0) }.first.map { PlaybackLevels.kitGroups(program: $0.program) }

    /// The sampler of a band kit's drum group (the part's own sampler plays its first group).
    func samplerKey(_ part: Part, group: Int) -> String { "part:\(part.id):kit\(group)" }
    var metronomeTrack: AVMusicTrack?

    // Original recording
    public private(set) var originalFile: AVAudioFile?
    private var originalStartSeconds: Double = 0
    private var countInTimer: DispatchSourceTimer?
    private var pendingStartBeat: Double?
    /// Bumped by every count-in and every pause, so a count-in's queued start never plays after a
    /// pause, seek or stop that came in the meantime.
    private var countInGeneration = 0

    /// Called on the main queue when the system's media services were reset (iOS): every audio
    /// object, this engine included, is gone. The owner makes a new engine.
    public var onMediaServicesReset: (() -> Void)?
    private var observers: [NSObjectProtocol] = []
    private var resumeAfterInterruption = false

    /// - Parameters:
    ///   - offlineFormat: when set, the engine runs in offline manual-rendering mode
    ///     (for audio export and tests); otherwise it plays to the output device.
    /// Wet-to-direct energy ratio of the room at the audience seat (sounds/render.py calibration).
    public static let wetToDirectDB = 4.5
    /// How much louder the unit-energy central-hall IR makes a brass band than white noise
    /// would (its reverb is strongest where the band's energy is): measured on the Mikkel
    /// band render, 14.5 dB wet at unit gain with a 4.5 dB send, so 10 dB.
    public static let roomColorationDB = 10.0
    /// "Concert hall sound" without a room IR (the app): the environment node's medium hall at this
    /// level, with sampler reverb blend `hallReverbBlend`. Set so the hall adds about as much as the
    /// reference renderer's calibrated room (wet 4.5 dB over the direct sound, sounds/render.py); at
    /// -6 dB it was 9 dB over, and the band's low end smeared into the reverb.
    public static let hallReverbLevelDB = -10.7
    public static let hallReverbBlend: Float = 0.35
    /// Low shelf on the hall reverb's output: real halls hold their bass longer than their mids, but
    /// the medium hall preset on a band already +2 to +3 dB heavy at 63-125 Hz adds boom, not space.
    public static let hallLowShelfHz = 250.0
    public static let hallLowShelfDB = -4.0
    /// The convolution reverb, when a room IR is loaded.
    public private(set) var convolution: ConvolutionReverbAU?
    public var usesRoomIR: Bool { convolution != nil }

    /// Make-up gain on the band, before the soft limiter. The presets are level-matched to
    /// −24 LUFS and the parts sit metres away in the environment node, so the full-band test
    /// phrase (sounds/phrases.py) peaks near −27 dBFS at unity; this brings it to about −1 dBFS
    /// (−12 LUFS, the shared phrase target) and a solo cornet to about −11. The metronome clicks
    /// at about −10 dBFS on its own; the original recording has its own stage.
    public static let defaultOutputGainDB = PlaybackLevels.bandGainDB
    public var outputGainDB: Double = PlaybackEngine.defaultOutputGainDB {
        didSet { applyStageGain() }
    }
    let bandBus = AVAudioMixerNode()
    let recordingBus = AVAudioMixerNode()
    public private(set) var outputStage: OutputStageAU?
    /// The original recording's stage: its level-matching gain, then the same limiter.
    public private(set) var recordingStage: OutputStageAU?
    /// The recording's integrated loudness (whole file), once measured; nil before.
    public private(set) var originalLUFS: Double?
    /// The gain the recording plays with (PlaybackLevels.recordingGainDB), 0 until measured.
    public private(set) var originalGainDB: Double = 0
    /// The loudness the recording is brought to: the band's estimated loudness for this score
    /// (PlaybackLevels.recordingTargetLUFS(for:)), so switching Band and Recording keeps the level.
    public let recordingTargetLUFS: Double
    private var measuredGainDB: Double?

    public init(score: Score, tempoMap: TempoMap? = nil, originalURL: URL? = nil,
                soundBank: SoundBank = .locate(), roomIR: URL? = RoomIR.locate(), offlineFormat: AVAudioFormat? = nil) throws {
        self.score = score
        self.recordingTargetLUFS = PlaybackLevels.recordingTargetLUFS(for: score)
        self.tempoMap = tempoMap
        self.soundBank = soundBank
        if let f = offlineFormat {
            try engine.enableManualRenderingMode(.offline, format: f, maximumFrameCount: 4096)
        }
        let main = engine.mainMixerNode
        engine.attach(environment)
        let stereo = AVAudioFormat(standardFormatWithSampleRate: main.outputFormat(forBus: 0).sampleRate > 0
                                   ? main.outputFormat(forBus: 0).sampleRate : 44100, channels: 2)!
        // the band's own bus, through the output stage into the main mixer
        engine.attach(bandBus)
        Self.prepare()
        let stage = try Self.makeEffect(OutputStageAU.componentDescription)
        engine.attach(stage)
        engine.connect(bandBus, to: stage, format: stereo)
        engine.connect(stage, to: main, format: stereo)
        outputStage = stage.auAudioUnit as? OutputStageAU
        applyStageGain()
        let out = bandBus
        if let irURL = roomIR, let (ch, sr) = try? RoomIR.load(irURL) {
            // Direct sound from the environment node, reverberant field from the room IR.
            let conv = try Self.makeEffect(ConvolutionReverbAU.componentDescription)
            engine.attach(conv)
            engine.connect(environment, to: [AVAudioConnectionPoint(node: out, bus: out.nextAvailableInputBus),
                                             AVAudioConnectionPoint(node: conv, bus: 0)], fromBus: 0, format: stereo)
            engine.connect(conv, to: out, format: stereo)
            if let au = conv.auAudioUnit as? ConvolutionReverbAU {
                au.kernel.setIR(ch, sampleRate: sr, normalize: true)
                au.kernel.wetGain = Float(pow(10, (Self.wetToDirectDB - Self.roomColorationDB) / 20))
                convolution = au
            }
        } else {
            engine.connect(environment, to: out, format: stereo)
        }
        environment.renderingAlgorithm = .HRTFHQ
        environment.outputType = .auto
        environment.listenerPosition = AVAudio3DPoint(x: 0, y: 0, z: 0)
        environment.reverbParameters.enable = true
        environment.reverbParameters.loadFactoryReverbPreset(.mediumHall)
        environment.reverbParameters.level = Float(Self.hallReverbLevelDB)
        // the hall's low end: a shelf on the reverb only, so held bass notes do not bloom in it
        environment.reverbParameters.filterParameters.filterType = .lowShelf
        environment.reverbParameters.filterParameters.frequency = Float(Self.hallLowShelfHz)
        environment.reverbParameters.filterParameters.gain = Float(Self.hallLowShelfDB)
        environment.reverbParameters.filterParameters.bypass = false

        let mono = AVAudioFormat(standardFormatWithSampleRate: out.outputFormat(forBus: 0).sampleRate > 0
                                 ? out.outputFormat(forBus: 0).sampleRate : 44100, channels: 1)
        // One sampler per part, placed at its seat: the part's band preset (PartSoundResolver),
        // or the basic tier when the band sounds are missing or the part is not brass.
        for part in score.parts {
            let key = samplerKey(part)
            if samplers[key] != nil { continue }
            let s = AVAudioUnitSampler()
            engine.attach(s)
            engine.connect(s, to: environment, format: mono)
            let own = soundBank.partSound(for: part)
            let seat = part.section.defaultSeat
            let az = (own?.azimuth ?? seat.azimuth) * .pi / 180
            let dist = own?.distance ?? seat.distance
            s.position = AVAudio3DPoint(x: Float(dist * sin(az)), y: 0, z: Float(-dist * cos(az)))
            s.renderingAlgorithm = .HRTFHQ
            s.reverbBlend = Self.hallReverbBlend
            samplers[key] = s
            if soundBank.load(into: s, part: part) { loadedInstruments += 1 }
            // A band kit plays on one sampler per drum group, each at its group's trim: AVAudioUnitSampler hardly
            // applies the kit's zone attenuation, which alphaSynth applies in full (band.apple_kit_trim_db).
            if let groups = MIDIWriter.drumGroups(for: score, options: midiOptions)[part.id] {
                for (i, g) in groups.enumerated() {
                    let gs: AVAudioUnitSampler
                    if i == 0 {
                        gs = s
                    } else {
                        gs = AVAudioUnitSampler()
                        engine.attach(gs)
                        engine.connect(gs, to: environment, format: mono)
                        gs.position = s.position
                        gs.renderingAlgorithm = .HRTFHQ
                        gs.reverbBlend = Self.hallReverbBlend
                        soundBank.load(into: gs, part: part)
                        samplers[samplerKey(part, group: g)] = gs
                    }
                    gs.overallGain += Float(kitGroups?.trimDB[g] ?? 0)
                }
            }
        }
        engine.attach(metronome)
        engine.connect(metronome, to: main, format: nil)
        loadMetronome()

        engine.attach(player)
        engine.attach(timePitch)
        // the recording's own bus converts to the stage's stereo format (a mono file plays from both sides)
        engine.attach(recordingBus)
        let recStage = try Self.makeEffect(OutputStageAU.componentDescription)
        engine.attach(recStage)
        engine.connect(recordingBus, to: recStage, format: stereo)
        engine.connect(recStage, to: main, format: stereo)
        recordingStage = recStage.auAudioUnit as? OutputStageAU
        if let originalURL {
            let f = try AVAudioFile(forReading: originalURL)
            originalFile = f
            engine.connect(player, to: timePitch, format: f.processingFormat)
            engine.connect(timePitch, to: recordingBus, format: f.processingFormat)
            if offlineFormat != nil { levelOriginal(url: originalURL) }
        } else {
            engine.connect(player, to: timePitch, format: nil)
            engine.connect(timePitch, to: recordingBus, format: nil)
        }

        sequencer = AVAudioSequencer(audioEngine: engine)
        try loadSequence()
        engine.prepare()
        try engine.start()
        applyRate(); applyRoom()
        // Measured in the background once the engine is complete: the result is applied on the main
        // thread, which may already own the engine while an init on another thread is still running.
        if let originalURL, offlineFormat == nil {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in self?.levelOriginal(url: originalURL) }
        }
        if offlineFormat == nil { observeAudioSystem() }
    }

    // MARK: audio system events

    /// Keeps `state` true to what is heard when the system takes the audio away: another output
    /// device (AVAudioEngineConfigurationChange stops the engine), a call or alarm, unplugged
    /// headphones, a media-services reset. The handlers run on the main queue, where the owner uses
    /// the engine.
    private func observeAudioSystem() {
        let nc = NotificationCenter.default
        observers.append(nc.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            self?.configurationChanged()
        })
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        observers.append(nc.addObserver(forName: AVAudioSession.interruptionNotification, object: session, queue: .main) { [weak self] n in
            self?.interrupted(n)
        })
        observers.append(nc.addObserver(forName: AVAudioSession.routeChangeNotification, object: session, queue: .main) { [weak self] n in
            self?.routeChanged(n)
        })
        observers.append(nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: session, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.stopForLostAudio()
            self.onMediaServicesReset?()
        })
        #endif
    }

    /// The output device or its format changed and the engine stopped itself: stop, so the next
    /// play starts the engine again on the new device.
    private func configurationChanged() {
        guard !engine.isRunning else { return }
        stopForLostAudio()
    }

    /// Stops without the fade (the engine may no longer render) and keeps the position.
    private func stopForLostAudio() {
        guard state != .stopped else { return }
        pause()
        cancelFade()
    }

    #if os(iOS)
    private func interrupted(_ n: Notification) {
        guard let raw = n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        switch type {
        case .began:
            resumeAfterInterruption = state != .stopped
            stopForLostAudio()
        case .ended:
            let opts = (n.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt).map(AVAudioSession.InterruptionOptions.init) ?? []
            defer { resumeAfterInterruption = false }
            guard resumeAfterInterruption, opts.contains(.shouldResume) else { return }
            try? AVAudioSession.sharedInstance().setActive(true)
            try? play()
        @unknown default: break
        }
    }

    /// Headphones unplugged (or a Bluetooth device gone): pause rather than play out of the speaker.
    private func routeChanged(_ n: Notification) {
        guard let raw = n.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              AVAudioSession.RouteChangeReason(rawValue: raw) == .oldDeviceUnavailable else { return }
        stopForLostAudio()
    }
    #endif

    /// Registers the in-process audio units (the output stage and the convolution reverb). The app
    /// calls it at launch on the main thread; every engine calls it again before it makes the units,
    /// so the order does not matter. Idempotent and thread-safe.
    public static func prepare() {
        _ = OutputStageAU.registered
        _ = ConvolutionReverbAU.registered
    }

    /// An effect unit, or `PlaybackError.audioUnit` when it cannot be made. AVFAudio raises an
    /// Objective-C exception for a unit it cannot instantiate, which would end the app.
    static func makeEffect(_ description: AudioComponentDescription) throws -> AVAudioUnitEffect {
        var error: NSError?
        guard let unit = makeAudioUnitEffect(description, &error) else {
            throw PlaybackError.audioUnit("\(fourCCString(description.componentSubType)): \(error?.localizedDescription ?? "unknown")")
        }
        return unit
    }

    deinit {
        for o in observers { NotificationCenter.default.removeObserver(o) }
        countInTimer?.cancel()
        sequencer?.stop()
        engine.stop()
    }

    private func loadSequence() throws {
        // the score's dynamics, on AVAudioUnitSampler's velocity curve
        let midi = MIDIWriter.data(for: score, options: midiOptions)
        try sequencer.load(from: midi, options: [])
        // The file's conductor track (title, tempo, meter) may or may not be folded into `tempoTrack`; then come
        // one track per part, the metronome's, and a band kit's other drum groups.
        let tracks = sequencer.tracks
        let extra = MIDIWriter.drumGroupTracks(for: score, options: midiOptions)
        let offset = max(0, tracks.count - (score.parts.count + 1 + extra.count))
        for (i, part) in score.parts.enumerated() where offset + i < tracks.count {
            tracks[offset + i].destinationAudioUnit = samplers[samplerKey(part)]
            partTracks[part.id] = [tracks[offset + i]]
        }
        if offset > 0 { for t in tracks[..<offset] { t.isMuted = true } }
        if tracks.count > offset + score.parts.count {
            metronomeTrack = tracks[offset + score.parts.count]
            metronomeTrack?.destinationAudioUnit = metronome
        }
        for (j, (id, g)) in extra.enumerated() where offset + score.parts.count + 1 + j < tracks.count {
            guard let part = score.parts.first(where: { $0.id == id }) else { continue }
            let t = tracks[offset + score.parts.count + 1 + j]
            t.destinationAudioUnit = samplers[samplerKey(part, group: g)]
            partTracks[id, default: []].append(t)
        }
        applyMutes()
        applyLoop()
        sequencer.prepareToPlay()
    }

    // MARK: transport

    /// Current position in quarter-note beats from the start of bar 1.
    public var position: Double {
        switch source {
        case .score:
            if let p = pendingStartBeat { return p }
            var beat = sequencer.currentPositionInBeats
            if let loop, state == .playing {
                let (s, e) = loopBeats(loop)
                if beat >= e { beat = s + (beat - s).truncatingRemainder(dividingBy: e - s) }
            }
            return beat
        case .original:
            return beat(atSeconds: originalSeconds)
        }
    }

    public var positionTick: Int { Int(position * Double(Score.ticksPerQuarter)) }

    /// Seconds into the original recording at the current position.
    public var originalSeconds: Double {
        guard source == .original, state == .playing,
              let nodeTime = player.lastRenderTime, let pt = player.playerTime(forNodeTime: nodeTime) else {
            return seconds(atBeat: stoppedBeat)
        }
        return originalStartSeconds + Double(pt.sampleTime) / pt.sampleRate
    }

    private var stoppedBeat: Double = 0

    /// Seconds in the original recording (tempo map) or, without one, at the notated tempi.
    public func seconds(atBeat beat: Double) -> Double {
        tempoMap?.seconds(atBeat: beat) ?? score.seconds(atTick: Int(beat * Double(Score.ticksPerQuarter)))
    }

    public func beat(atSeconds s: Double) -> Double {
        if let tempoMap { return tempoMap.beat(atSeconds: s) }
        var lo = 0.0, hi = Double(score.endTick) / Double(Score.ticksPerQuarter) + 1000
        for _ in 0..<60 { let mid = (lo + hi) / 2; if seconds(atBeat: mid) < s { lo = mid } else { hi = mid } }
        return lo
    }

    /// Wall-clock seconds of score playback between two beats at the current rate.
    func playSeconds(from a: Double, to b: Double) -> Double {
        let q = Double(Score.ticksPerQuarter)
        return (score.seconds(atTick: Int(b * q)) - score.seconds(atTick: Int(a * q))) / rate
    }

    /// Measure the recording once (whole file, EBU R128 integrated) and pick its gain. Applied the
    /// next time the recording starts, never while it plays (the stage has no smoothing).
    private func levelOriginal(url: URL) {
        let lufs = (try? LoudnessMeter.integrated(url: url, monoAsDualMono: true)) ?? -.infinity
        let gain = PlaybackLevels.recordingGainDB(forLUFS: lufs, target: recordingTargetLUFS)
        let apply = { [weak self] in
            guard let self else { return }
            self.originalLUFS = lufs
            self.measuredGainDB = gain
            if !(self.source == .original && self.state == .playing) { self.applyRecordingGain() }
        }
        if Thread.isMainThread || engine.isInManualRenderingMode { apply() } else { DispatchQueue.main.async(execute: apply) }
    }

    private func applyRecordingGain() {
        guard let g = measuredGainDB else { return }
        originalGainDB = g
        // the recording bus spreads a mono file equal-power (−3 dB a side); make it up, so a mono
        // recording plays from both speakers at the level it was measured at (dual mono)
        let upmix = originalFile?.processingFormat.channelCount == 1 ? 10 * log10(2.0) : 0
        recordingStage?.kernel.gain = Float(pow(10, (g + upmix) / 20))
    }

    public func play() throws {
        guard state == .stopped else { return }
        cancelFade()
        if !engine.isRunning { try engine.start() }
        let start = stoppedBeat
        if countInBars > 0 && source == .score {
            startCountIn(then: start)
        } else {
            try startNow(at: start)
        }
    }

    public func pause() {
        let p = position
        countInTimer?.cancel(); countInTimer = nil
        countInGeneration += 1
        pendingStartBeat = nil
        sequencer.stop()
        if source == .original && state == .playing && !engine.isInManualRenderingMode {
            fadeOutRecording()  // the player keeps going for the fade; play() and seeking stop it at once
        } else {
            player.stop()
        }
        allNotesOff()
        if state != .stopped { fadeOutThenRestore() }  // play() cancels it, so seeking keeps the release
        stoppedBeat = p
        state = .stopped
    }

    public func stop() { pause(); seek(toBeat: loop.map { loopBeats($0).0 } ?? 0) }

    public func togglePlay() throws { if state == .stopped { try play() } else { pause() } }

    public func seek(toBeat beat: Double) {
        let wasPlaying = state != .stopped
        if wasPlaying { pause() }
        stoppedBeat = max(0, min(beat, Double(score.endTick) / Double(Score.ticksPerQuarter)))
        sequencer.currentPositionInBeats = stoppedBeat
        if wasPlaying { try? play() }
    }

    public func seek(toBar index: Int) {
        let i = max(0, min(index, score.measures.count - 1))
        seek(toBeat: Double(score.measures[i].startTick) / Double(Score.ticksPerQuarter))
    }

    /// Switch between hearing the score and the original recording, keeping the position.
    public func setSource(_ s: Source) {
        guard s != source else { return }
        let wasPlaying = state != .stopped
        let p = position
        if wasPlaying { pause() }
        source = s
        stoppedBeat = p
        if wasPlaying { try? play() }
    }

    private func startNow(at beat: Double) throws {
        pendingStartBeat = nil
        switch source {
        case .score:
            sequencer.currentPositionInBeats = beat
            sequencer.prepareToPlay()
            try sequencer.start()
        case .original:
            guard let f = originalFile else { throw PlaybackError.noOriginal }
            let secs = max(0, seconds(atBeat: beat))
            let startFrame = AVAudioFramePosition(secs * f.processingFormat.sampleRate)
            guard startFrame < f.length else { return }
            originalStartSeconds = secs
            player.stop()
            player.volume = 1
            applyRecordingGain()
            player.scheduleSegment(f, startingFrame: startFrame, frameCount: AVAudioFrameCount(f.length - startFrame), at: nil)
            player.play()
        }
        state = .playing
    }

    private func startCountIn(then beat: Double) {
        let m = score.measures[score.measureIndex(atTick: Int(beat * Double(Score.ticksPerQuarter)))]
        let clicks = m.beats * countInBars
        let interval = 60 / (score.tempo(atTick: Int(beat * Double(Score.ticksPerQuarter))) * rate) * 4 / Double(m.beatType)
        var n = 0
        countInGeneration += 1
        let generation = countInGeneration
        pendingStartBeat = beat
        state = .countingIn(beat: 1)
        let t = DispatchSource.makeTimerSource(flags: .strict, queue: .global(qos: .userInteractive))
        t.schedule(deadline: .now(), repeating: interval, leeway: .milliseconds(1))
        t.setEventHandler { [weak self] in
            guard let self else { return }
            if n == clicks {
                t.cancel()
                DispatchQueue.main.async {
                    // a pause, seek or stop since the count-in began cancels the start
                    guard self.countInGeneration == generation, case .countingIn = self.state else { return }
                    try? self.startNow(at: beat)
                }
                return
            }
            let key = UInt8(n % m.beats == 0 ? MIDIWriter.metronomeHigh : MIDIWriter.metronomeLow)
            self.metronome.startNote(key, withVelocity: n % m.beats == 0 ? 110 : 80, onChannel: 9)
            let beatNo = n % m.beats + 1
            DispatchQueue.main.async {
                if self.countInGeneration == generation, case .countingIn = self.state { self.state = .countingIn(beat: beatNo) }
            }
            n += 1
        }
        countInTimer = t
        t.resume()
    }

    private func loadMetronome() {
        if let kit = soundBank.band?.soundFont {
            SoundBank.loadIntoMemory(metronome)
            if (try? metronome.loadSoundBankInstrument(at: kit, program: 0, bankMSB: UInt8(kAUSampler_DefaultPercussionBankMSB),
                                                       bankLSB: 0)) != nil { return }
        }
        soundBank.load(into: metronome, section: .percussion, program: nil)
    }

    /// Stop fade: CC 123 (all notes off) releases every voice through the preset's release
    /// envelope, never a hard cut (CC 120 cuts within 10 ms and clicks). Live playback also ramps
    /// the samplers down over `stopFadeSeconds`, so a long release does not ring on after the user
    /// asked for silence; seeking and ordinary note-offs keep the natural release.
    public static let stopFadeSeconds = 0.08
    private var fadeTimer: DispatchSourceTimer?

    private func fadeOutThenRestore() {
        fadeTimer?.cancel()
        guard !engine.isInManualRenderingMode else { return }
        let steps = 8
        var i = 0
        let all = Array(samplers.values)
        let t = DispatchSource.makeTimerSource(queue: .main)
        t.schedule(deadline: .now(), repeating: Self.stopFadeSeconds / Double(steps))
        t.setEventHandler { [weak self] in
            i += 1
            let v = Float(max(0, 1 - Double(i) / Double(steps)))
            for s in all { s.volume = v }
            if i >= steps + 2 {  // two more ticks at zero, then back to full for the next play
                for s in all { s.volume = 1 }
                self?.fadeTimer?.cancel()
                self?.fadeTimer = nil
            }
        }
        fadeTimer = t
        t.resume()
    }

    /// The recording fades over the same 80 ms as the band, then stops.
    private var recordingFadeTimer: DispatchSourceTimer?

    private func fadeOutRecording() {
        recordingFadeTimer?.cancel()
        let steps = 8
        var i = 0
        let t = DispatchSource.makeTimerSource(queue: .main)
        t.schedule(deadline: .now(), repeating: Self.stopFadeSeconds / Double(steps))
        t.setEventHandler { [weak self] in
            guard let self else { return }
            i += 1
            self.player.volume = Float(max(0, 1 - Double(i) / Double(steps)))
            if i >= steps + 1 { self.endRecordingFade() }
        }
        recordingFadeTimer = t
        t.resume()
    }

    private func endRecordingFade() {
        recordingFadeTimer?.cancel()
        recordingFadeTimer = nil
        player.stop()
        player.volume = 1
    }

    private func cancelFade() {
        if recordingFadeTimer != nil { endRecordingFade() }
        guard fadeTimer != nil else { return }
        fadeTimer?.cancel()
        fadeTimer = nil
        for s in samplers.values { s.volume = 1 }
    }

    private func allNotesOff() {
        for s in samplers.values { for ch in 0..<16 { s.sendController(123, withValue: 0, onChannel: UInt8(ch)) } }
        metronome.sendController(123, withValue: 0, onChannel: 9)
    }

    // MARK: parts

    public func isMuted(_ partID: String) -> Bool { muted.contains(partID) }
    public func isSoloed(_ partID: String) -> Bool { soloed.contains(partID) }

    public func setMuted(_ partID: String, _ on: Bool) {
        if on { muted.insert(partID) } else { muted.remove(partID) }
        applyMutes()
    }

    public func setSoloed(_ partID: String, _ on: Bool) {
        if on { soloed.insert(partID) } else { soloed.remove(partID) }
        applyMutes()
    }

    /// Whether a part is heard with the current mute/solo settings.
    public func isAudible(_ partID: String) -> Bool {
        !muted.contains(partID) && (soloed.isEmpty || soloed.contains(partID))
    }

    private func applyMutes() {
        for (id, ts) in partTracks { for t in ts { t.isMuted = !isAudible(id) } }
        metronomeTrack?.isMuted = !metronomeOn
    }

    // MARK: loop, rate, transpose, room

    public func setLoop(_ bars: ClosedRange<Int>?) {
        if let b = bars {
            let lo = max(0, min(b.lowerBound, score.measures.count - 1))
            let hi = max(lo, min(b.upperBound, score.measures.count - 1))
            loop = lo...hi
        } else {
            loop = nil
        }
        applyLoop()
        if let loop {
            let (s, e) = loopBeats(loop)
            if position < s || position >= e { seek(toBeat: s) }
        }
    }

    func loopBeats(_ bars: ClosedRange<Int>) -> (Double, Double) {
        let q = Double(Score.ticksPerQuarter)
        let s = Double(score.measures[bars.lowerBound].startTick) / q
        let last = score.measures[bars.upperBound]
        return (s, Double(last.startTick + last.lengthTicks) / q)
    }

    private func applyLoop() {
        let all = partTracks.values.flatMap { $0 } + [metronomeTrack].compactMap { $0 }
        for t in all {
            if let loop {
                let (s, e) = loopBeats(loop)
                t.loopRange = AVBeatRange(start: s, length: e - s)
                t.numberOfLoops = AVMusicTrackLoopCount.forever.rawValue
                t.isLoopingEnabled = true
            } else {
                t.isLoopingEnabled = false
            }
        }
    }

    private func applyRate() {
        sequencer?.rate = Float(rate)
        timePitch.rate = Float(rate)
    }

    private func applyTranspose() {
        for part in score.parts where !part.isPercussion {
            sampler(for: part)?.globalTuning = Float(transposeSemitones * 100)
        }
    }

    private func applyRoom() {
        // the environment node's hall reverb stands in only when no room IR is loaded
        environment.reverbParameters.enable = roomOn && convolution == nil
        for s in samplers.values { s.reverbBlend = roomOn && convolution == nil ? Self.hallReverbBlend : 0 }
        convolution?.kernel.enabled = roomOn
        applyStageGain()
    }

    /// The band stage's make-up gain: `outputGainDB`, plus PlaybackLevels.dryRoomGainDB when the hall
    /// is off (without a room IR), so switching "Concert hall sound" keeps the band's loudness.
    private func applyStageGain() {
        let dry = !roomOn && convolution == nil ? PlaybackLevels.dryRoomGainDB : 0
        outputStage?.kernel.gain = Float(pow(10, (outputGainDB + dry) / 20))
    }

    /// Place a section's parts (azimuth in degrees, negative = left of the conductor; distance in m).
    public func place(_ section: Section, azimuth: Double, distance: Double) {
        let az = azimuth * .pi / 180
        for part in score.parts where part.section == section {
            let p = AVAudio3DPoint(x: Float(distance * sin(az)), y: 0, z: Float(-distance * cos(az)))
            for (key, s) in samplers where key == samplerKey(part) || key.hasPrefix(samplerKey(part) + ":") { s.position = p }
        }
    }

    // MARK: offline rendering

    /// Render score playback from `fromBeat` for `beats` beats into a buffer (offline mode only).
    public func renderScore(fromBeat: Double, beats: Double) throws -> AVAudioPCMBuffer {
        guard engine.isInManualRenderingMode else { throw PlaybackError.notOffline }
        let format = engine.manualRenderingFormat
        let seconds = playSeconds(from: fromBeat, to: fromBeat + beats)
        let total = AVAudioFrameCount(seconds * format.sampleRate)
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: total),
              let chunk = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: engine.manualRenderingMaximumFrameCount)
        else { throw PlaybackError.render("buffer") }
        source = .score
        stoppedBeat = fromBeat
        try startNow(at: fromBeat)
        while out.frameLength < total {
            let n = min(chunk.frameCapacity, total - out.frameLength)
            let status = try engine.renderOffline(n, to: chunk)
            guard status == .success else { throw PlaybackError.render("status \(status.rawValue)") }
            for c in 0..<Int(format.channelCount) {
                memcpy(out.floatChannelData![c] + Int(out.frameLength), chunk.floatChannelData![c], Int(chunk.frameLength) * 4)
            }
            out.frameLength += chunk.frameLength
        }
        pause()
        return out
    }

    /// Render the original recording from `fromBeat` for `seconds` into a buffer (offline mode only).
    public func renderOriginal(fromBeat: Double, seconds: Double) throws -> AVAudioPCMBuffer {
        guard engine.isInManualRenderingMode else { throw PlaybackError.notOffline }
        let format = engine.manualRenderingFormat
        let total = AVAudioFrameCount(seconds * format.sampleRate)
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: total),
              let chunk = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: engine.manualRenderingMaximumFrameCount)
        else { throw PlaybackError.render("buffer") }
        source = .original
        stoppedBeat = fromBeat
        try startNow(at: fromBeat)
        while out.frameLength < total {
            let n = min(chunk.frameCapacity, total - out.frameLength)
            guard try engine.renderOffline(n, to: chunk) == .success else { throw PlaybackError.render("render") }
            for c in 0..<Int(format.channelCount) {
                memcpy(out.floatChannelData![c] + Int(out.frameLength), chunk.floatChannelData![c], Int(chunk.frameLength) * 4)
            }
            out.frameLength += chunk.frameLength
        }
        pause()
        source = .score
        return out
    }

    /// Render the whole score (audible parts only) to an audio file (offline mode only).
    public func exportScore(to url: URL, tailSeconds: Double = 2) throws {
        let fmt = engine.manualRenderingFormat
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: fmt.sampleRate,
            AVNumberOfChannelsKey: fmt.channelCount, AVEncoderBitRateKey: 192_000,
        ])
        guard let chunk = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: engine.manualRenderingMaximumFrameCount)
        else { throw PlaybackError.render("buffer") }
        let total = AVAudioFramePosition((score.durationSeconds / rate + tailSeconds) * fmt.sampleRate)
        var done: AVAudioFramePosition = 0
        try startNow(at: 0)
        while done < total {
            let n = AVAudioFrameCount(min(AVAudioFramePosition(chunk.frameCapacity), total - done))
            guard try engine.renderOffline(n, to: chunk) == .success else { throw PlaybackError.render("render") }
            try file.write(from: chunk)
            done += AVAudioFramePosition(chunk.frameLength)
        }
        pause()
    }

    public static func offlineFormat() -> AVAudioFormat {
        AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)!
    }
}

public enum PlaybackError: Error, Equatable {
    case noOriginal, notOffline, render(String)
    /// An audio unit could not be instantiated: its subtype and the reason.
    case audioUnit(String)
}

private func fourCCString(_ code: OSType) -> String {
    String(decoding: [24, 16, 8, 0].map { UInt8((code >> $0) & 0xff) }, as: UTF8.self)
}

public extension AVAudioPCMBuffer {
    /// Peak absolute sample value over all channels.
    var peak: Float {
        guard let d = floatChannelData else { return 0 }
        var p: Float = 0
        for c in 0..<Int(format.channelCount) { for i in 0..<Int(frameLength) { p = max(p, abs(d[c][i])) } }
        return p
    }

    /// RMS over a frame range of channel 0.
    func rms(from: Int, to: Int) -> Float {
        guard let d = floatChannelData, to > from else { return 0 }
        var s: Float = 0
        for i in from..<min(to, Int(frameLength)) { s += d[0][i] * d[0][i] }
        return (s / Float(to - from)).squareRoot()
    }
}

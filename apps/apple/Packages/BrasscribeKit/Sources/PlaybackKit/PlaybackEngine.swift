import AVFoundation
import Foundation
import ScoreKit

/// Score and original-recording playback for practice.
///
/// Graph:
/// ```
/// sequencer tracks ─▶ one AVAudioUnitSampler per section ─▶ AVAudioEnvironmentNode (seat + hall) ─┐
/// metronome track  ─▶ metronome sampler ─────────────────────────────────────────────────────────├▶ main mixer
/// original file    ─▶ AVAudioPlayerNode ─▶ AVAudioUnitTimePitch (speed without pitch change) ────┘
/// ```
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
    var samplers: [Section: AVAudioUnitSampler] = [:]
    let metronome = AVAudioUnitSampler()
    let player = AVAudioPlayerNode()
    let timePitch = AVAudioUnitTimePitch()
    var sequencer: AVAudioSequencer!
    var partTracks: [String: AVMusicTrack] = [:]
    var metronomeTrack: AVMusicTrack?

    // Original recording
    public private(set) var originalFile: AVAudioFile?
    private var originalStartSeconds: Double = 0
    private var countInTimer: DispatchSourceTimer?
    private var pendingStartBeat: Double?

    /// - Parameters:
    ///   - offlineFormat: when set, the engine runs in offline manual-rendering mode
    ///     (for audio export and tests); otherwise it plays to the output device.
    public init(score: Score, tempoMap: TempoMap? = nil, originalURL: URL? = nil,
                soundBank: SoundBank = .locate(), offlineFormat: AVAudioFormat? = nil) throws {
        self.score = score
        self.tempoMap = tempoMap
        self.soundBank = soundBank
        if let f = offlineFormat {
            try engine.enableManualRenderingMode(.offline, format: f, maximumFrameCount: 4096)
        }
        let out = engine.mainMixerNode
        engine.attach(environment)
        engine.connect(environment, to: out, format: nil)
        environment.renderingAlgorithm = .HRTFHQ
        environment.outputType = .auto
        environment.listenerPosition = AVAudio3DPoint(x: 0, y: 0, z: 0)
        environment.reverbParameters.enable = true
        environment.reverbParameters.loadFactoryReverbPreset(.mediumHall)
        environment.reverbParameters.level = -6

        let mono = AVAudioFormat(standardFormatWithSampleRate: out.outputFormat(forBus: 0).sampleRate > 0
                                 ? out.outputFormat(forBus: 0).sampleRate : 44100, channels: 1)
        for part in score.parts where samplers[part.section] == nil {
            let s = AVAudioUnitSampler()
            engine.attach(s)
            engine.connect(s, to: environment, format: mono)
            let seat = part.section.defaultSeat
            let az = seat.azimuth * .pi / 180
            s.position = AVAudio3DPoint(x: Float(seat.distance * sin(az)), y: 0, z: Float(-seat.distance * cos(az)))
            s.renderingAlgorithm = .HRTFHQ
            s.reverbBlend = 0.35
            samplers[part.section] = s
            if soundBank.load(into: s, section: part.section, program: part.midiProgram) { loadedInstruments += 1 }
        }
        engine.attach(metronome)
        engine.connect(metronome, to: out, format: nil)
        soundBank.load(into: metronome, section: .percussion, program: nil)

        engine.attach(player)
        engine.attach(timePitch)
        if let originalURL {
            let f = try AVAudioFile(forReading: originalURL)
            originalFile = f
            engine.connect(player, to: timePitch, format: f.processingFormat)
            engine.connect(timePitch, to: out, format: f.processingFormat)
        } else {
            engine.connect(player, to: timePitch, format: nil)
            engine.connect(timePitch, to: out, format: nil)
        }

        sequencer = AVAudioSequencer(audioEngine: engine)
        try loadSequence()
        engine.prepare()
        try engine.start()
        applyRate(); applyRoom()
    }

    deinit {
        countInTimer?.cancel()
        sequencer?.stop()
        engine.stop()
    }

    private func loadSequence() throws {
        let midi = MIDIWriter.data(for: score, options: .init(includeMetronome: true))
        try sequencer.load(from: midi, options: [])
        // The file's conductor track (title, tempo, meter) may or may not be folded into
        // `tempoTrack`; the last track is always the metronome, preceded by one per part.
        let tracks = sequencer.tracks
        let offset = max(0, tracks.count - (score.parts.count + 1))
        for (i, part) in score.parts.enumerated() where offset + i < tracks.count {
            tracks[offset + i].destinationAudioUnit = samplers[part.section]
            partTracks[part.id] = tracks[offset + i]
        }
        if offset > 0 { for t in tracks[..<offset] { t.isMuted = true } }
        if tracks.count > offset + score.parts.count {
            metronomeTrack = tracks[offset + score.parts.count]
            metronomeTrack?.destinationAudioUnit = metronome
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

    public func seconds(atBeat beat: Double) -> Double {
        tempoMap?.seconds(atBeat: beat) ?? beat * 60 / score.tempoBPM
    }

    public func beat(atSeconds s: Double) -> Double {
        tempoMap?.beat(atSeconds: s) ?? s * score.tempoBPM / 60
    }

    public func play() throws {
        guard state == .stopped else { return }
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
        pendingStartBeat = nil
        sequencer.stop()
        player.stop()
        allNotesOff()
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
            player.scheduleSegment(f, startingFrame: startFrame, frameCount: AVAudioFrameCount(f.length - startFrame), at: nil)
            player.play()
        }
        state = .playing
    }

    private func startCountIn(then beat: Double) {
        let m = score.measures[score.measureIndex(atTick: Int(beat * Double(Score.ticksPerQuarter)))]
        let clicks = m.beats * countInBars
        let interval = 60 / (score.tempoBPM * rate) * 4 / Double(m.beatType)
        var n = 0
        pendingStartBeat = beat
        state = .countingIn(beat: 1)
        let t = DispatchSource.makeTimerSource(flags: .strict, queue: .global(qos: .userInteractive))
        t.schedule(deadline: .now(), repeating: interval, leeway: .milliseconds(1))
        t.setEventHandler { [weak self] in
            guard let self else { return }
            if n == clicks {
                t.cancel()
                DispatchQueue.main.async { try? self.startNow(at: beat) }
                return
            }
            let key = UInt8(n % m.beats == 0 ? MIDIWriter.metronomeHigh : MIDIWriter.metronomeLow)
            self.metronome.startNote(key, withVelocity: n % m.beats == 0 ? 110 : 80, onChannel: 9)
            let beatNo = n % m.beats + 1
            DispatchQueue.main.async { if case .countingIn = self.state { self.state = .countingIn(beat: beatNo) } }
            n += 1
        }
        countInTimer = t
        t.resume()
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
        for (id, t) in partTracks { t.isMuted = !isAudible(id) }
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
        let all = Array(partTracks.values) + [metronomeTrack].compactMap { $0 }
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
        for (section, s) in samplers where section != .percussion {
            s.globalTuning = Float(transposeSemitones * 100)
        }
    }

    private func applyRoom() {
        environment.reverbParameters.enable = roomOn
        for s in samplers.values { s.reverbBlend = roomOn ? 0.35 : 0 }
    }

    /// Place a section (azimuth in degrees, negative = left of the conductor; distance in m).
    public func place(_ section: Section, azimuth: Double, distance: Double) {
        guard let s = samplers[section] else { return }
        let az = azimuth * .pi / 180
        s.position = AVAudio3DPoint(x: Float(distance * sin(az)), y: 0, z: Float(-distance * cos(az)))
    }

    // MARK: offline rendering

    /// Render score playback from `fromBeat` for `beats` beats into a buffer (offline mode only).
    public func renderScore(fromBeat: Double, beats: Double) throws -> AVAudioPCMBuffer {
        guard engine.isInManualRenderingMode else { throw PlaybackError.notOffline }
        let format = engine.manualRenderingFormat
        let seconds = beats * 60 / (score.tempoBPM * rate)
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

    /// Render the whole score (audible parts only) to an audio file (offline mode only).
    public func exportScore(to url: URL, tailSeconds: Double = 2) throws {
        let beats = Double(score.endTick) / Double(Score.ticksPerQuarter) + tailSeconds * score.tempoBPM / 60
        let fmt = engine.manualRenderingFormat
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: fmt.sampleRate,
            AVNumberOfChannelsKey: fmt.channelCount, AVEncoderBitRateKey: 192_000,
        ])
        guard let chunk = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: engine.manualRenderingMaximumFrameCount)
        else { throw PlaybackError.render("buffer") }
        let total = AVAudioFramePosition(beats * 60 / (score.tempoBPM * rate) * fmt.sampleRate)
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

import AVFoundation
import Foundation

/// The recording as the sound of the tab: played from its file at any speed with the pitch kept, from any
/// second, and over a stretch again and again. Used from the main actor only.
@MainActor
public protocol RecordingPlayer: AnyObject {
    /// The recording is sounding, or about to: asked to play, not at its end, and the device lets it (a moment of
    /// reading the file after a jump is still playing; a call that takes the sound away for a while is not).
    var playing: Bool { get }

    /// It was asked to play and has not been paused, whether or not the device lets it sound now.
    var asked: Bool { get }

    /// Where the recording is, in seconds.
    var position: Double { get }

    /// How long the recording is, in seconds; 0 until it has been read.
    var duration: Double { get }

    /// 1 is the recording's own speed. The pitch is the recording's at every speed.
    var speed: Float { get set }

    /// The stretch to play again and again, in seconds; nil plays on to the end.
    var repeatSpan: ClosedRange<Double>? { get set }

    func play()
    func pause()
    func seek(to seconds: Double)
    func release()
}

/// What the screen is told of: playing began or stopped, the end was reached, or the file cannot be played.
@MainActor
public protocol RecordingPlayerListener: AnyObject {
    func recordingPlaying(_ playing: Bool)
    func recordingEnded()
    func recordingFailed()
}

/// `RecordingPlayer` on AVFoundation's `AVPlayer`: it reads what the system's own decoders read (the files the app
/// takes in), stretches time without moving the pitch, and seeks to the millisecond.
///
/// Setting up the audio session (its category, interruptions, headphones pulled out) is the app's job: this player
/// only plays. When the system takes the sound away, `AVPlayer` stops; the player stays asked to play but is not
/// playing, and a press of Play asks again.
@MainActor
public final class AVRecordingPlayer: RecordingPlayer {
    private let player: AVPlayer
    private let item: AVPlayerItem
    private weak var listener: (any RecordingPlayerListener)?
    private var observations: [NSKeyValueObservation] = []
    private var notices: [any NSObjectProtocol] = []
    private var turn: Any?
    private var told = false
    /// The recording played to its end and has not been moved since.
    private var ended = false
    private var failed = false

    public private(set) var asked = false

    public init(file: URL, listener: any RecordingPlayerListener, silent: Bool = false) {
        self.listener = listener
        item = AVPlayerItem(url: file)
        // A speed other than 1 keeps the notes where they are.
        item.audioTimePitchAlgorithm = .spectral
        player = AVPlayer(playerItem: item)
        player.actionAtItemEnd = .pause
        player.automaticallyWaitsToMinimizeStalling = false
        if silent { player.volume = 0 }
        // Play and pause, and the system taking the sound away for a while: the player stays asked to play,
        // but nothing sounds meanwhile, so it is not playing.
        observations.append(player.observe(\.timeControlStatus) { [weak self] _, _ in
            Task { @MainActor in self?.tell() }
        })
        observations.append(item.observe(\.status) { [weak self] item, _ in
            guard item.status == .failed else { return }
            Task { @MainActor in self?.fail() }
        })
        let centre = NotificationCenter.default
        notices.append(centre.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.reachedEnd() }
        })
        notices.append(centre.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.fail() }
        })
    }

    public var playing: Bool { asked && !ended && !failed && player.timeControlStatus != .paused }

    /// Tells the listener when `playing` has changed.
    private func tell() {
        let now = playing
        if now == told { return }
        told = now
        listener?.recordingPlaying(now)
    }

    private func reachedEnd() {
        // A stretch that reaches the end of the recording turns here, when it starts before that end (one that
        // starts past it would end again at once, for ever); else the recording has been played.
        if let again = repeatSpan, asked, turnsBack(again.lowerBound, duration: duration) {
            seek(to: again.lowerBound)
            player.play()
        } else {
            asked = false
            ended = true
            player.pause()
            listener?.recordingEnded()
        }
        tell()
    }

    private func fail() {
        if failed { return }
        failed = true
        listener?.recordingFailed()
    }

    public var position: Double {
        let s = player.currentTime().seconds
        return s.isFinite ? max(s, 0) : 0
    }

    public var duration: Double {
        let s = item.duration.seconds
        return s.isFinite && s > 0 ? s : 0
    }

    public var speed: Float = 1 {
        didSet {
            player.defaultRate = speed
            if player.rate != 0 { player.rate = speed }
        }
    }

    public var repeatSpan: ClosedRange<Double>? {
        didSet {
            if let turn { player.removeTimeObserver(turn) }
            turn = nil
            guard let stretch = repeatSpan else { return }
            // Told at the stretch's last millisecond, every time playing reaches it.
            let at = CMTime(value: max(Int64(stretch.upperBound * 1000), 1), timescale: 1000)
            turn = player.addBoundaryTimeObserver(forTimes: [NSValue(time: at)], queue: .main) { [weak self] in
                MainActor.assumeIsolated {
                    guard let self, self.repeatSpan == stretch else { return }
                    self.seek(to: stretch.lowerBound)
                }
            }
        }
    }

    public func play() {
        if ended { seek(to: repeatSpan.map(\.lowerBound).flatMap { turnsBack($0, duration: duration) ? $0 : nil } ?? 0) }
        asked = true
        player.play()
        tell()
    }

    public func pause() {
        asked = false
        player.pause()
        tell()
    }

    public func seek(to seconds: Double) {
        ended = false
        player.seek(to: CMTime(value: TabClock.millisAt(seconds), timescale: 1000), toleranceBefore: .zero, toleranceAfter: .zero)
    }

    public func release() {
        if let turn { player.removeTimeObserver(turn) }
        turn = nil
        observations.forEach { $0.invalidate() }
        observations = []
        notices.forEach { NotificationCenter.default.removeObserver($0) }
        notices = []
        asked = false
        player.pause()
        player.replaceCurrentItem(with: nil)
    }

    /// The rate the player itself runs at and how it keeps the pitch, for the test that slows it down.
    var appliedRate: Float { player.defaultRate }
    var pitchAlgorithm: AVAudioTimePitchAlgorithm { item.audioTimePitchAlgorithm }
}

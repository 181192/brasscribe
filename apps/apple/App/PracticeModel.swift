import AVFoundation
import Foundation
import NotationKit
import Observation
import PlaybackKit
import ScoreKit
import SwiftUI

/// Everything the score screen needs: the parsed score, the engraving, playback and the
/// practice settings. Position updates at 20 Hz while playing.
@Observable @MainActor
final class PracticeModel {
    let piece: Piece
    let score: Score
    let composition: Composition?
    let uncertainty: UncertaintyIndex
    private(set) var renderer: ScoreRenderer?
    private(set) var engine: PlaybackEngine?
    private(set) var pages: [ScoreRenderer.Page] = []
    private(set) var loadError: String?
    private(set) var engraving = false

    // View settings
    var shownPart: String? { didSet { if shownPart != oldValue { relayout() } } }
    var pitchMode: PitchMode = .written { didSet { if pitchMode != oldValue { relayout() } } }
    var zoom: CGFloat = 1 { didSet { if zoom != oldValue { relayout() } } }
    var viewWidth: CGFloat = 820

    // Transport state mirrored for the UI
    private(set) var position: Double = 0
    private(set) var isPlaying = false
    private(set) var countInBeat: Int?
    var currentBar: Int { score.measureIndex(atTick: Int(position * Double(Score.ticksPerQuarter))) }
    var soundingNotes: Set<String> = []
    var speedPercent: Double = 100 { didSet { engine?.rate = speedPercent / 100 } }
    var transpose: Int = 0 { didSet { engine?.transposeSemitones = transpose } }
    var metronome = false { didSet { engine?.metronomeOn = metronome } }
    var countIn = false { didSet { engine?.countInBars = countIn ? 1 : 0 } }
    var room = true { didSet { engine?.roomOn = room } }
    var hearOriginal = false { didSet { engine?.setSource(hearOriginal ? .original : .score); syncVideo(force: true) } }
    var loopFrom: Int = 0
    var loopTo: Int = 0
    private(set) var looping = false
    /// Part the musician plays themselves (muted in play-along).
    var myPart: String? {
        didSet {
            if playAlong, let old = oldValue, old != myPart { engine?.setMuted(old, false) }
            applyPlayAlong()
        }
    }
    var playAlong = false { didSet { applyPlayAlong() } }
    private(set) var mixVersion = 0

    let video: AVPlayer?
    private var timer: Timer?
    private var announcedBar = -1

    init(piece: Piece) throws {
        self.piece = piece
        score = try piece.loadScore()
        composition = piece.loadComposition()
        uncertainty = composition.map(UncertaintyIndex.init) ?? .empty
        loopTo = min(3, score.measures.count - 1)
        video = piece.videoURL.map { AVPlayer(url: $0) }
        video?.isMuted = true
        myPart = score.parts.first { $0.name.lowercased().contains("solo cornet") }?.id ?? score.parts.first?.id
    }

    func start() {
        guard engine == nil else { return }
        MediaTools.configureSession(recording: false)
        do {
            engine = try PlaybackEngine(score: score, tempoMap: composition?.tempoMap, originalURL: piece.originalURL,
                                        soundBank: .locate())
        } catch {
            loadError = error.localizedDescription
        }
        relayout()
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
    }

    func stopAll() {
        engine?.pause()
        timer?.invalidate()
        timer = nil
        video?.pause()
    }

    var hasOriginal: Bool { engine?.originalFile != nil }
    var soundDescription: String { engine?.soundBank.description ?? "" }

    // MARK: engraving

    func relayout() {
        let xml: String
        do { xml = try piece.musicXML() } catch { loadError = error.localizedDescription; return }
        if renderer == nil { renderer = ScoreRenderer(musicXML: xml) }
        guard let r = renderer else { loadError = String(localized: "The notation engine could not start."); return }
        let layout = ScoreRenderer.Layout(width: max(320, viewWidth), zoom: zoom, parts: shownPart.map { [$0] }, pitch: pitchMode,
                                          height: max(600, viewWidth * 1.3))
        engraving = true
        Task.detached(priority: .userInitiated) { [r] in
            r.apply(layout)
            let pages = r.renderAllPages()
            await MainActor.run {
                self.pages = pages
                self.engraving = false
                self.updateSounding()
            }
        }
    }

    /// Displayed parts, in order.
    var displayedParts: [Part] { shownPart.flatMap { id in score.parts.filter { $0.id == id } } ?? score.parts }

    // MARK: transport

    func togglePlay() {
        guard let engine else { return }
        do { try engine.togglePlay() } catch { loadError = error.localizedDescription }
        tick()
        syncVideo(force: true)
    }

    func stop() { engine?.stop(); tick(); syncVideo(force: true) }

    func goToBar(_ i: Int) {
        engine?.seek(toBar: max(0, min(i, score.measures.count - 1)))
        tick()
        syncVideo(force: true)
    }

    func nextBar() { goToBar(currentBar + 1) }
    func previousBar() { goToBar(currentBar - 1) }

    func changeSpeed(by step: Double) { speedPercent = min(150, max(25, (speedPercent + step).rounded())) }

    func setLoop(_ on: Bool) {
        guard let engine else { return }
        if on {
            let lo = min(loopFrom, loopTo), hi = max(loopFrom, loopTo)
            engine.setLoop(lo...hi)
        } else {
            engine.setLoop(nil)
        }
        looping = on
        tick()
    }

    /// Loop the current bar (keyboard L): set both ends to it and toggle.
    func toggleLoopCurrentBar() {
        if looping { setLoop(false); return }
        loopFrom = currentBar; loopTo = currentBar
        setLoop(true)
    }

    /// "Listen to this bar": loop it, from the original if available.
    func listen(toBar i: Int, original: Bool) {
        hearOriginal = original && hasOriginal
        loopFrom = i; loopTo = i
        setLoop(true)
        goToBar(i)
        if !isPlaying { togglePlay() }
    }

    func setMuted(_ id: String, _ on: Bool) { engine?.setMuted(id, on); mixVersion += 1 }
    func setSoloed(_ id: String, _ on: Bool) { engine?.setSoloed(id, on); mixVersion += 1 }
    func isMuted(_ id: String) -> Bool { _ = mixVersion; return engine?.isMuted(id) ?? false }
    func isSoloed(_ id: String) -> Bool { _ = mixVersion; return engine?.isSoloed(id) ?? false }

    private func applyPlayAlong() {
        guard let engine, let myPart else { return }
        engine.setMuted(myPart, playAlong)
        mixVersion += 1
    }

    private func tick() {
        guard let engine else { return }
        position = engine.position
        isPlaying = engine.state != .stopped
        if case .countingIn(let b) = engine.state { countInBeat = b } else { countInBeat = nil }
        updateSounding()
        if isPlaying { syncVideo(force: false) }
    }

    private func updateSounding() {
        guard let r = renderer else { return }
        soundingNotes = isPlaying || position > 0 ? Set(r.sounding(atBeat: position).notes) : []
    }

    /// Keep the muted video at the musical position; it follows the tempo map in both modes.
    private func syncVideo(force: Bool) {
        guard let video, let engine else { return }
        let target = engine.seconds(atBeat: position)
        let now = video.currentTime().seconds
        if isPlaying {
            if force || abs(now - target) > 0.15 {
                video.seek(to: CMTime(seconds: max(0, target), preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            }
            let rate = Float(speedPercent / 100)
            if video.rate != rate { video.rate = rate }
        } else {
            video.pause()
            if force { video.seek(to: CMTime(seconds: max(0, target), preferredTimescale: 600)) }
        }
    }

    // MARK: text for assistive technology

    var talking: TalkingScore { TalkingScore(score: score, language: .current, pitchMode: pitchMode, uncertainty: uncertainty) }

    func describe(partID: String, bar: Int) -> String {
        guard let p = score.part(id: partID) else { return "" }
        return talking.describe(part: p, measureIndex: bar)
    }

    func barLabel(_ i: Int) -> String { talking.barLabel(i) }

    var positionDescription: String {
        let (bar, beat) = score.position(atTick: Int(position * Double(Score.ticksPerQuarter)))
        return String(localized: "Bar \(bar), beat \(Int(beat))")
    }

    func uncertainCount(bar: Int) -> Int {
        displayedParts.reduce(0) { $0 + $1.notes(inMeasure: bar).filter(uncertainty.isUncertain).count }
    }
}

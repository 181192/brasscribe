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
    /// Free-time (ad lib) passages as 0-based bar ranges.
    let freeTimeBars: [ClosedRange<Int>]
    private(set) var renderer: ScoreRenderer?
    private(set) var engine: PlaybackEngine?
    private(set) var pages: [ScoreRenderer.Page] = []
    private(set) var loadError: String?
    private(set) var engraving = false
    private(set) var layoutVersion = 0
    private var layoutGeneration = 0

    // View settings
    /// Showing your own part alone is the part view: "Mute my part" comes on, so you play it.
    var shownPart: String? {
        didSet {
            guard shownPart != oldValue else { return }
            if shownPart != nil, shownPart == myPart { playAlong = true }
            relayout()
        }
    }
    var pitchMode: PitchMode = .written { didSet { if pitchMode != oldValue { relayout() } } }
    var zoom: CGFloat = 1 { didSet { if zoom != oldValue { relayout() } } }
    var viewWidth: CGFloat = 820
    /// The music stand while it is open (PracticeModel+Stand.swift).
    var stand: MusicStand?
    /// The phone opens the score on your part once; coming back from the stand keeps the parts shown.
    var openedOnMyPart = false
    /// After leaving the stand, focus goes back to the Music stand button.
    var focusStandButton = false

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
    /// A repeat range has been used (the stand's Repeat asks for bars until then).
    private(set) var loopWasSet = false
    /// Part the musician plays themselves (muted in play-along).
    var myPart: String? {
        didSet {
            if playAlong, let old = oldValue, old != myPart { engine?.setMuted(old, false) }
            applyPlayAlong()
        }
    }
    var playAlong = false { didSet { applyPlayAlong() } }
    private(set) var mixVersion = 0

    /// The bars "Listen to this bar" is playing once; nil when it isn't.
    private(set) var listening: ClosedRange<Int>?
    private var listenEndBeat: Double = 0
    /// What listening changed, put back when it stops.
    private var beforeListen: (original: Bool, looping: Bool)?
    /// Screenshots hold the listening state without playing.
    private var listenHeld = false
    private var arming = false

    let video: AVPlayer?
    private var timer: Timer?
    private var announcedBar = -1

    convenience init(piece: Piece) throws {
        self.init(piece: piece, score: try piece.loadScore(), composition: piece.loadComposition())
    }

    /// Where each part comes from (part id → source), from the core. Empty for a score without a
    /// composition (an imported MusicXML file).
    let partSources: [String: PartSourceKind]
    /// Your part is another part than your seat's, because this lineup has none: the sentence that says
    /// so ("This small band has no 1st Baritone…"), shown under the part name and announced once.
    let seatNotice: String?

    init(piece: Piece, score parsed: Score, composition: Composition?, seat: SeatChoice = .stored) {
        self.piece = piece
        score = parsed
        self.composition = composition
        uncertainty = composition.map(UncertaintyIndex.init) ?? .empty
        let q = Double(Score.ticksPerQuarter)
        freeTimeBars = (composition?.freeTimeBeats ?? []).map { r in
            let a = parsed.measureIndex(atTick: Int(r.lowerBound * q))
            let b = parsed.measureIndex(atTick: max(0, Int(r.upperBound * q) - 1))
            return a...max(a, b)
        }
        loopTo = min(3, score.measures.count - 1)
        video = piece.videoURL.map { AVPlayer(url: $0) }
        video?.isMuted = true
        let byName = PartSourceKind.sources(composition: composition, output: piece.output)
        partSources = Dictionary(parsed.parts.compactMap { p in byName[p.name].map { (p.id, $0) } }, uniquingKeysWith: { a, _ in a })
        let mine = Self.resolveMyPart(piece: piece, score: parsed, seat: seat)
        myPart = mine.partID
        seatNotice = mine.notice
    }

    /// Your part in this score, in order: the part picked for it ("Make this my part"); the seat a solo
    /// take was written for; your seat's part in the lineup (the core's table); with no seat set, the
    /// lineup's lead as before. "I conduct or listen" has no part.
    static func resolveMyPart(piece: Piece, score: Score, seat: SeatChoice) -> (partID: String?, notice: String?) {
        func id(named name: String) -> String? { score.parts.first { $0.name == name }?.id }
        if let name = piece.myPart, let id = id(named: name) { return (id, nil) }
        if piece.profile == .solo, let s = piece.output?.seat, let part = Seats.part(s, in: .fullBand)?.part, let id = id(named: part) {
            return (id, nil)
        }
        switch seat {
        case .conductor: return (nil, nil)
        case .notSet:
            // my part: the lineup's lead (the tune), else the first part
            let lead = (piece.output?.lineup ?? .fullBand).lead.lowercased()
            return (score.parts.first { $0.name.lowercased().contains(lead) }?.id
                ?? score.parts.first { $0.name.lowercased().contains("solo cornet") }?.id ?? score.parts.first?.id, nil)
        case .seat(let seatID, let reads):
            guard let info = Seats.info(seatID) else { return (nil, nil) }
            // the score's own lineup first; a score from elsewhere is matched by its part names
            var lineups: [Lineup] = [.fullBand, .minimalBand, .quartet]
            if let own = piece.output?.lineup { lineups.removeAll { $0 == own }; lineups.insert(own, at: 0) }
            for (k, lineup) in lineups.enumerated() {
                guard let sp = Seats.part(seatID, in: lineup) else { continue }
                if let part = sp.part, let id = id(named: part) {
                    return (id, Seats.mappingNotice(seat: info, lineup: lineup, part: sp, reads: reads))
                }
                // the score's own lineup has no part for the seat (percussion): every part opens
                if sp.part == nil, k == 0, piece.output != nil {
                    return (nil, Seats.mappingNotice(seat: info, lineup: lineup, part: sp, reads: reads))
                }
            }
            return (nil, nil)
        }
    }

    /// "Make this my part": the highlight, the mute target, Review's order and Share's scope follow at
    /// once, and the score remembers it. Nothing is arranged again.
    func makeMine(_ id: String?) {
        guard let id, id != myPart, let part = score.part(id: id) else { return }
        myPart = id
        var p = Piece.load(from: piece.metaURL) ?? piece
        p.myPart = part.name
        try? p.save()
    }

    /// The source of your part, when the core knows it.
    var mySource: PartSourceKind? { myPart.flatMap { partSources[$0] } }

    func start() {
        guard engine == nil else { return }
        MediaTools.configureSession(recording: false)
        adopt(Result { try Self.makeEngine(piece: piece, score: score, composition: composition) })
    }

    /// Opens a piece without holding the main thread: the MusicXML parse, the composition decode
    /// and the playback engine (one SoundFont preset load per part) run on a background task, and
    /// the model is made on the main actor once they are ready. `start()` is then already done.
    static func open(_ piece: Piece) async throws -> PracticeModel {
        MediaTools.configureSession(recording: false)
        let opened = try await Task.detached(priority: .userInitiated) { try Opened(piece: piece) }.value
        let m = PracticeModel(piece: piece, score: opened.score, composition: opened.composition)
        m.adopt(opened.engine)
        return m
    }

    /// What `open` prepares off the main actor. The engine is made there and handed over once,
    /// before anything else touches it; from then on only the main actor uses it.
    private struct Opened: @unchecked Sendable {
        let score: Score
        let composition: Composition?
        let engine: Result<PlaybackEngine, Error>

        init(piece: Piece) throws {
            score = try piece.loadScore()
            composition = piece.loadComposition()
            let (score, composition) = (score, composition)
            engine = Result { try PracticeModel.makeEngine(piece: piece, score: score, composition: composition) }
        }
    }

    nonisolated private static func makeEngine(piece: Piece, score: Score, composition: Composition?) throws -> PlaybackEngine {
        try PlaybackEngine(score: score, tempoMap: composition?.tempoMap, originalURL: piece.originalURL, soundBank: .locate())
    }

    private func adopt(_ made: Result<PlaybackEngine, Error>) {
        switch made {
        case .success(let e): engine = e
        case .failure(let error): loadError = error.localizedDescription
        }
        startTimer()
    }

    private func startTimer() {
        guard timer == nil else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
    }

    /// Leaving the screen: stop everything, including the position updates.
    func stopAll() {
        finishListening(announce: false)
        engine?.pause()
        timer?.invalidate()
        timer = nil
        video?.pause()
    }

    var hasOriginal: Bool { engine?.originalFile != nil }
    var soundDescription: String { engine?.soundBank.description ?? "" }
    /// Set when the band sounds are not installed (basic tier): the player shows a line saying so.
    var bandSoundsMissing: BandSoundStatus? {
        guard let s = engine?.soundBank.bandStatus, s.isMissing else { return nil }
        return s
    }

    // MARK: engraving

    func relayout() {
        let xml: String
        do { xml = try piece.musicXML() } catch { loadError = error.localizedDescription; return }
        if renderer == nil { renderer = ScoreRenderer(musicXML: PartNames.localized(xml)) }
        guard let r = renderer else { loadError = String(localized: "The notation engine could not start."); return }
        let layout = stand.map { $0.layout(parts: layoutPart.map { [$0] }, pitch: pitchMode, staves: layoutPart == nil ? score.parts.count : 1) }
            ?? ScoreRenderer.Layout(width: max(320, viewWidth), zoom: zoom, parts: shownPart.map { [$0] }, pitch: pitchMode,
                                    height: max(600, viewWidth * 1.3))
        engraving = true
        layoutGeneration += 1
        let gen = layoutGeneration
        // Pages appear one by one so the first system is readable while the rest engrave;
        // a newer layout request abandons this one.
        Task.detached(priority: .userInitiated) { [r] in
            guard r.apply(layout) else { return }
            let n = r.pageCount
            for i in 1...max(1, n) {
                guard await self.layoutGeneration == gen else { return }
                guard let p = r.page(i) else { continue }
                await MainActor.run {
                    guard self.layoutGeneration == gen else { return }
                    if i == 1 { self.pages = [p]; self.layoutVersion += 1 } else { self.pages.append(p) }
                    if i == n { self.engraving = false }
                    self.updateSounding()
                }
            }
        }
    }

    /// Page (1-based) showing a bar.
    func pageNumber(forBar bar: Int) -> Int {
        guard let ids = renderer?.measureIDs, ids.indices.contains(bar) else { return 1 }
        return pages.first { $0.measureIDs.contains(ids[bar]) }?.number ?? 1
    }

    /// Displayed parts, in order.
    var displayedParts: [Part] { layoutPart.flatMap { id in score.parts.filter { $0.id == id } } ?? score.parts }

    /// The one part engraved, or nil for all: the stand's own choice while it is open.
    var layoutPart: String? {
        guard let stand else { return shownPart }
        if stand.onlyMine { return myPart ?? shownPart }
        // off goes back to the parts shown before, or to all of them when that was your part alone
        return shownPart == myPart ? nil : shownPart
    }

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
            loopWasSet = true
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

    /// "Listen to this bar": play these bars once, from the original recording when there is one, then
    /// go back to the start of the bar. The user's own repeat and sound choice come back afterwards.
    func listen(toBar i: Int, original: Bool) { listen(bars: i...i, original: original) }

    func listen(bars: ClosedRange<Int>, original: Bool) {
        guard let engine, !score.measures.isEmpty else { return }
        let last = score.measures.count - 1
        let range = max(0, min(bars.lowerBound, last))...max(0, min(bars.upperBound, last))
        // while setting up, playback is briefly stopped: that must not count as the end
        arming = true
        defer { arming = false; tick() }
        if engine.state != .stopped { engine.pause() }
        if beforeListen == nil { beforeListen = (hearOriginal, looping) }
        if looping { engine.setLoop(nil); looping = false }
        hearOriginal = original && hasOriginal
        listening = range
        listenHeld = false
        let end = score.measures[range.upperBound]
        listenEndBeat = Double(end.startTick + end.lengthTicks) / Double(Score.ticksPerQuarter)
        goToBar(range.lowerBound)
        startTimer()
        if engine.state == .stopped { togglePlay() }
        AccessibilityNotifier.announce(String(localized: "Playing \(barsLabel(range))"))
    }

    /// The Listen button: listen, or stop while these bars are playing.
    func toggleListen(bars: ClosedRange<Int>, original: Bool) {
        if listening == bars { stopListening() } else { listen(bars: bars, original: original) }
    }

    /// Stop "Listen to this bar" (Stop pressed, or another note chosen). Announced only when asked.
    func stopListening(announce: Bool = true) {
        guard listening != nil, !listenHeld else { return }
        engine?.pause()
        finishListening(announce: announce)
        tick()
    }

    /// Show the listening state without sound, for screenshots.
    func holdListening(bars: ClosedRange<Int>) {
        listening = bars
        listenHeld = true
    }

    private func finishListening(announce: Bool) {
        guard let range = listening else { return }
        listening = nil
        listenHeld = false
        if let b = beforeListen {
            beforeListen = nil
            if hearOriginal != b.original { hearOriginal = b.original }
            if b.looping { setLoop(true) }
        }
        goToBar(range.lowerBound)
        if announce { AccessibilityNotifier.announce(String(localized: "Stopped")) }
    }

    private func barsLabel(_ r: ClosedRange<Int>) -> String {
        r.count == 1 ? barLabel(r.lowerBound) : String(localized: "bars \(r.lowerBound + 1) to \(r.upperBound + 1)")
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
        defer { stand?.follow(self) }
        position = engine.position
        isPlaying = engine.state != .stopped
        if case .countingIn(let b) = engine.state { countInBeat = b } else { countInBeat = nil }
        // "Listen to this bar" ends with its last bar, or when playback was stopped some other way
        if listening != nil, !listenHeld, !arming, !isPlaying || position >= listenEndBeat - 0.001 {
            if isPlaying { engine.pause() }
            finishListening(announce: true)
            position = engine.position
            isPlaying = engine.state != .stopped
        }
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

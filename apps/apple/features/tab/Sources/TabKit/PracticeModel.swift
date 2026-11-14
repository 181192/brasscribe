import CryptoKit
import Foundation
import Observation
import os

/// What is known of the recording of the song on screen.
public enum RecordingState: Equatable, Sendable {
    /// Being looked for on this device.
    case looking
    /// On this device, and it plays.
    case here
    /// Not on this device: the song was opened from the computer's list, or its file is gone.
    case notHere
    /// Being copied from the computer.
    case getting
    /// The computer does not have it either.
    case gone
    /// The computer could not be asked.
    case noAnswer
    /// The computer was not asked: this app is older than its Bandroom.
    case updateApp
    /// The computer was not asked: its Bandroom is older than this app.
    case updateComputer
    /// This device has no room to keep it.
    case noRoom
    /// It is larger than this device takes.
    case tooLarge
    /// On this device, and it cannot be played.
    case unplayable
}

/// What went wrong asking the computer for a recording, as the engine's client says it.
public enum RecordingFetchError: Error, Equatable, Sendable {
    /// The computer answered with this HTTP status.
    case status(Int)
    /// Not asked: this app is older than the computer's Bandroom.
    case updateApp
    /// Not asked: the computer's Bandroom is older than this app.
    case updateComputer
}

/// An error of the engine's client that says which `RecordingFetchError` it is; nil for one that is none of them
/// (the computer was not reached).
public protocol RecordingFetchFailure: Error {
    var recordingFetchError: RecordingFetchError? { get }
}

/// The recordings of the songs this device has practised, one file to a song, by the id of the song's job on
/// the computer: a song's recording is copied here when its tab is first opened with the recording in hand,
/// or when it is fetched from the computer, so the song can be practised when it is opened again.
public struct PracticeRecordings: Sendable {
    /// Why a recording could not be kept here.
    public enum KeepError: Error, Equatable, Sendable {
        /// There is no file to write it to.
        case noPlace
        /// It came empty.
        case cameEmpty
    }

    public let dir: URL

    public init(dir: URL) { self.dir = dir }

    private func named(_ job: String) -> URL? { Self.fileName(job).map { dir.appending(path: $0, directoryHint: .notDirectory) } }

    public func find(_ job: String) -> URL? {
        guard let url = named(job), Self.size(url) > 0 else { return nil }
        return url
    }

    /// Where a recording being fetched or copied is written, until it is whole (`arrived`): a file of this try's own,
    /// so a try that was given up and clears up after itself late never takes the file of the try after it.
    public func arriving(_ job: String) -> URL? {
        guard let to = named(job) else { return nil }
        let fm = FileManager.default
        guard (try? fm.createDirectory(at: dir, withIntermediateDirectories: true)) != nil else { return nil }
        let part = dir.appending(path: "\(to.lastPathComponent).\(UUID().uuidString)\(Self.partSuffix)", directoryHint: .notDirectory)
        return fm.createFile(atPath: part.path, contents: nil) ? part : nil
    }

    /// The try that wrote `part` did not get through: what there is of it goes.
    public func dropped(_ part: URL?) {
        if let part { try? FileManager.default.removeItem(at: part) }
    }

    /// Room left for recordings, in bytes.
    public var room: Int64 {
        var at = dir
        while !FileManager.default.fileExists(atPath: at.path) && at.pathComponents.count > 1 { at.deleteLastPathComponent() }
        let values = try? at.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey, .volumeAvailableCapacityKey])
        return values?.volumeAvailableCapacityForImportantUsage ?? values?.volumeAvailableCapacity.map(Int64.init) ?? 0
    }

    /// `part`, written whole, becomes `job`'s recording; one that came empty goes.
    @discardableResult
    public func arrived(_ job: String, _ part: URL) -> URL? {
        if let to = named(job), Self.size(part) > 0, rename(part.path, to.path) == 0 { return to }
        dropped(part)
        return nil
    }

    /// A copy of `from` kept for `job`; `from` itself when it cannot be copied.
    public func keep(_ job: String, from: URL) -> URL {
        if let kept = find(job), Self.size(kept) == Self.size(from) { return kept }
        guard let part = arriving(job) else { return from }
        do {
            try FileManager.default.removeItem(at: part)
            try FileManager.default.copyItem(at: from, to: part)
            if let kept = arrived(job, part) { return kept }
        } catch {
            dropped(part)
        }
        return from
    }

    /// Drops the recordings of every song but `jobs`: a song deleted from Your songs takes its recording with it.
    /// What a fetch or a copy that did not finish left behind goes too (none is running when this is asked).
    public func prune(keeping jobs: Set<String>) {
        Self.prune(dir, keeping: Set(jobs.compactMap(Self.fileName)))
    }

    static func prune(_ dir: URL, keeping names: Set<String>) {
        let fm = FileManager.default
        for name in (try? fm.contentsOfDirectory(atPath: dir.path)) ?? [] where !names.contains(name) {
            try? fm.removeItem(at: dir.appending(path: name))
        }
    }

    static func size(_ url: URL) -> Int64 {
        guard let a = try? FileManager.default.attributesOfItem(atPath: url.path), a[.type] as? FileAttributeType == .typeRegular else { return -1 }
        return (a[.size] as? NSNumber)?.int64Value ?? 0
    }

    private static let partSuffix = ".part"

    /// The name of `job`'s file: what a file name can hold of the id, and a short hash of the whole id, so two ids
    /// that read the same once their other characters are gone, or past the length kept, are still two files.
    public static func fileName(_ job: String) -> String? {
        if job.isEmpty { return nil }
        let plain = String(job.filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }.prefix(60))
        let hash = SHA256.hash(data: Data(job.utf8)).prefix(4).map { String(format: "%02x", $0) }.joined()
        return "\(plain).\(hash)"
    }

    /// Less room than this after a fetch failed: the device is full.
    public static let fullBytes: Int64 = 16 << 20

    /// Why a recording did not come from the computer, from what went wrong (`error`) and the `room` left on this
    /// device: the computer does not have it; it is larger than the device takes; the device could not keep it
    /// (no room, or the file could not be written); the computer was not asked because one of the two needs an
    /// update; or the computer was not reached.
    public static func whyNot(_ error: any Error, room: Int64) -> RecordingState {
        if let failure = (error as? RecordingFetchError) ?? (error as? any RecordingFetchFailure)?.recordingFetchError {
            switch failure {
            case .updateApp: return .updateApp
            case .updateComputer: return .updateComputer
            case .status(404): return .gone
            case .status(413): return .tooLarge
            case .status: return .noAnswer
            }
        }
        if error as? KeepError == .noPlace || cannotWrite(error) || room < fullBytes { return .noRoom }
        return .noAnswer
    }

    private static func cannotWrite(_ error: any Error) -> Bool {
        if let e = error as? CocoaError {
            return [.fileNoSuchFile, .fileWriteNoPermission, .fileWriteOutOfSpace, .fileWriteVolumeReadOnly].contains(e.code)
        }
        if let e = error as? POSIXError { return e.code == .ENOSPC || e.code == .EDQUOT }
        return false
    }

    /// The kind of sound file `file` is, as a file name's extension, read from its first bytes (a kept recording's
    /// name says nothing of it): WAV, MP4 sound (M4A), MP3, Ogg, FLAC or WebM; "wav" when it is none of these.
    public static func extensionOf(_ file: URL) -> String {
        guard let handle = try? FileHandle(forReadingFrom: file) else { return "wav" }
        defer { try? handle.close() }
        var head = [UInt8]((try? handle.read(upToCount: 12)) ?? Data())
        head += [UInt8](repeating: 0, count: max(0, 12 - head.count))
        func at(_ offset: Int, _ text: String) -> Bool { Array(text.utf8).enumerated().allSatisfy { head[offset + $0.offset] == $0.element } }
        if at(0, "RIFF") && at(8, "WAVE") { return "wav" }
        if at(4, "ftyp") { return "m4a" }
        if at(0, "ID3") || (head[0] == 0xFF && head[1] & 0xE0 == 0xE0) { return "mp3" }
        if at(0, "OggS") { return "ogg" }
        if at(0, "fLaC") { return "flac" }
        if head[0...3] == [0x1A, 0x45, 0xDF, 0xA3] { return "webm" }
        return "wav"
    }
}

/// What is heard in practice. The raw value is what is kept on the device.
public enum PracticeSound: String, CaseIterable, Sendable {
    /// The recording the tab was written from.
    case recording
    /// The tab's own notes, played on the instrument's sound.
    case tab
    /// The recording with the tab's notes over it.
    case both
}

/// What the tab's own sound is made from: the page's notes, and the General MIDI program of the instrument.
public struct TabSoundSource: Sendable {
    public var index: TabIndex
    public var program: UInt8
    public init(index: TabIndex, program: UInt8) { self.index = index; self.program = program }
}

/// Where a song was left in practice: the second of the recording, the speed in per cent, and the bars repeated.
public struct PracticePlace: Equatable, Sendable {
    public var at: Double
    public var speed: Int
    public var repeating: RepeatBars?

    public init(at: Double, speed: Int, repeating: RepeatBars?) {
        self.at = at; self.speed = speed; self.repeating = repeating
    }
}

/// Where each song was left in practice, kept on this device beside the song's recording (`PracticeRecordings`), by
/// the id of the song's job: one small file to a song. A song deleted from Your songs keeps its file until a song that
/// is still in Your songs is next opened on the tab, when the places of the songs no longer there are pruned.
public struct PracticePlaces: Sendable {
    public let dir: URL

    public init(dir: URL) { self.dir = dir }

    private func named(_ job: String) -> URL? { PracticeRecordings.fileName(job).map { dir.appending(path: $0, directoryHint: .notDirectory) } }

    /// Where `job`'s song was left; nil when it was never practised, or what is kept can't be read.
    public func read(_ job: String) -> PracticePlace? {
        guard let url = named(job), let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        let words = text.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: " ", omittingEmptySubsequences: false).map(String.init)
        guard let at = words.first.flatMap(Double.init), at.isFinite, at >= 0,
              let speed = words.count > 1 ? Int(words[1]) : nil else { return nil }
        let first = words.count > 2 ? Int(words[2]) : nil
        let last = words.count > 3 ? Int(words[3]) : nil
        if let first, let last, first >= 0, first <= last {
            return PracticePlace(at: at, speed: speed, repeating: RepeatBars(first: first, last: last))
        }
        return PracticePlace(at: at, speed: speed, repeating: nil)
    }

    /// Keeps `place` for `job`'s song: written whole, then put in the place of what was there.
    public func save(_ job: String, _ place: PracticePlace) {
        guard let to = named(job) else { return }
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            var words = ["\(place.at)", "\(place.speed)"]
            if let r = place.repeating { words += ["\(r.first)", "\(r.last)"] }
            let part = dir.appending(path: to.lastPathComponent + ".part", directoryHint: .notDirectory)
            try Data(words.joined(separator: " ").utf8).write(to: part)
            if rename(part.path, to.path) != 0 { try? FileManager.default.removeItem(at: part) }
        } catch {
            PracticeModel.log.warning("where the song was left could not be kept: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Drops the places of every song but `jobs`: a song deleted from Your songs takes its place with it.
    public func prune(keeping jobs: Set<String>) {
        PracticeRecordings.prune(dir, keeping: Set(jobs.compactMap(PracticeRecordings.fileName)))
    }
}

/// Practice: the recording of the song on screen, where it is, how fast it plays and which bars it repeats.
/// It outlives the tab's views (a new size or a turn of the device is a new view) and is kept for each song
/// while the app runs, and on the device (`PracticePlaces`) for every song in Your songs, so a song opened after
/// the app was closed is where it was left.
@Observable
@MainActor
public final class PracticeModel: RecordingPlayerListener {
    /// Makes the player of a recording's file, telling `listener` what it does.
    public typealias MakePlayer = @MainActor (_ file: URL, _ listener: any RecordingPlayerListener) -> any RecordingPlayer
    /// Makes the tab's own sound for a score on a program, telling `listener` what it does; nil when it cannot be made.
    /// Makes the tab's own sound; it may take a moment (an instrument is read), and nil when it cannot be made.
    public typealias MakeTabPlayer = @MainActor (_ score: TabSoundScore, _ program: UInt8, _ listener: any RecordingPlayerListener) async -> (any TabSoundPlaying)?
    /// Copies `job`'s recording from the computer into the file `into`.
    public typealias Fetch = @Sendable (_ job: String, _ into: URL) async throws -> Void

    nonisolated static let log = Logger(subsystem: "no.kalli.scribe", category: "tab")

    /// How near the end of a stretch counts as its end, in seconds.
    private static let edge = 0.05

    @ObservationIgnored private let store: PracticeRecordings
    @ObservationIgnored private let places: PracticePlaces
    @ObservationIgnored private let makePlayer: MakePlayer
    /// The files are read and written one at a time, in order: an older place never lands after a newer one,
    /// and a prune never runs beside a write.
    @ObservationIgnored private let disk = DispatchQueue(label: "no.kalli.scribe.tab.practice")
    @ObservationIgnored private let makeTabPlayer: MakeTabPlayer
    /// Readies the device's sound for playing (an iPhone's audio session): before anything plays.
    @ObservationIgnored private let readyToPlay: @MainActor () -> Void
    /// The tab's sound being made.
    @ObservationIgnored private var voicing: Task<Void, Never>?
    /// Where the sound, the count-in and the metronome are kept: the same for every song.
    @ObservationIgnored private let choices: UserDefaults
    @ObservationIgnored private var player: (any RecordingPlayer)?
    /// The tab's own sound, when the tab can be followed.
    @ObservationIgnored private var tabPlayer: (any TabSoundPlaying)?
    /// What `tabPlayer` plays: another page, other beats or another instrument make a new one.
    @ObservationIgnored private var tabOf: TabSoundScore?
    @ObservationIgnored private var tabProgram: UInt8?
    @ObservationIgnored private lazy var tabListener = TabListener(self)
    @ObservationIgnored private var following: Task<Void, Never>?
    @ObservationIgnored private var clock: TabClock?
    @ObservationIgnored private var song: String?
    @ObservationIgnored private var job: String?
    @ObservationIgnored private var looking = 0
    @ObservationIgnored private var lookup: Task<Void, Never>?
    @ObservationIgnored private var fetching: Task<Void, Never>?
    /// The last fetch begun, also once it was given up: what `settled` waits for.
    @ObservationIgnored private var lastFetch: Task<Void, Never>?
    /// Counts the player's changes: a place read from the device is not taken over one made since it was asked for.
    @ObservationIgnored private var changes = 0
    /// The song on screen has a place on the device that is not read yet.
    @ObservationIgnored private var unread = false
    @ObservationIgnored private var left: [String: PracticePlace] = [:]
    /// The speed and repeat before `playBarSlowly`, and the bar it repeats.
    @ObservationIgnored private var beforeSlow: (PracticePlace, RepeatBars)?

    public private(set) var recording: RecordingState = .looking
    public private(set) var playing = false
    /// Per cent of the recording's own speed.
    public private(set) var speed = PracticeSpeed.full
    public private(set) var repeating: RepeatBars?
    /// The second of the recording the song is at while it is not playing; while it plays, `now()` says.
    public private(set) var at: Double = 0
    /// Counts the times the player moved the song: a bar back or on, to the start, into a repeat. The page then shows where it went.
    public private(set) var jumps = 0
    /// What the player chose to hear. Without the recording on the device the tab's own sound is heard, whatever was chosen (`hears`).
    public private(set) var sound: PracticeSound
    /// A bar is counted in before the song plays.
    public private(set) var countIn: Bool
    /// The beats tick while the song plays.
    public private(set) var metronome: Bool
    /// The tab's own sound can be played: the tab follows the recording's beats, and its sound was made.
    public private(set) var tabSound = false
    /// The tab follows the recording's beats, and its sound could not be made on this device.
    public private(set) var tabSoundFailed = false
    /// The tab's sound is being made (its instrument read): it can be played in a moment.
    public private(set) var tabSoundLoading = false
    /// A bar is being counted in: the song has not started to move.
    public private(set) var counting = false

    static let soundKey = "practice.sound"
    static let countInKey = "practice.countIn"
    static let metronomeKey = "practice.metronome"
    /// How far apart the tab's sound and the recording may be heard, in seconds, before the tab's sound is moved: more
    /// than what the two outputs can be apart by themselves (a device's own delay, a wireless speaker's), so only a
    /// move of the recording is followed by a move.
    private static let apart = 0.35
    /// Heard apart by less, the tab's sound runs faster or slower by this much of its speed for each second apart, and
    /// by no more than `most`.
    private static let pull = 1.0
    private static let most = 0.05

    /// `recordings` and `places` are the folders the recordings and the places are kept in; `choices` keeps what is heard.
    public init(recordings: URL, places: URL, choices: UserDefaults = .standard,
                makePlayer: @escaping MakePlayer = { AVRecordingPlayer(file: $0, listener: $1) },
                makeTabPlayer: @escaping MakeTabPlayer = EngineTabSoundPlayer.make,
                readyToPlay: @escaping @MainActor () -> Void = {}) {
        store = PracticeRecordings(dir: recordings)
        self.places = PracticePlaces(dir: places)
        self.makePlayer = makePlayer
        self.makeTabPlayer = makeTabPlayer
        self.readyToPlay = readyToPlay
        self.choices = choices
        sound = choices.string(forKey: Self.soundKey).flatMap(PracticeSound.init) ?? .recording
        countIn = choices.bool(forKey: Self.countInKey)
        metronome = choices.bool(forKey: Self.metronomeKey)
    }

    /// There is something to play: the recording, or the tab's own sound.
    public var canPlay: Bool { recording == .here || tabSound }

    /// What is heard: the choice, as far as there is a recording and a tab sound to play it with.
    public var hears: PracticeSound {
        if !tabSound { return .recording }
        if recording != .here { return .tab }
        return sound
    }

    /// The player the song's place is read from: the recording when it is heard, else the tab's sound.
    private var lead: (any RecordingPlayer)? { hears == .tab ? tabPlayer : player }
    private var tabLeads: Bool { hears == .tab && tabPlayer != nil }

    /// The tab's sound plays along with the recording: its notes are heard, or its beats.
    private var along: Bool { tabPlayer != nil && !tabLeads && player != nil && (hears == .both || metronome) }

    /// The second of the recording the song is at.
    public func now() -> Double {
        if playing, !counting, let lead { return lead.position }
        return at
    }

    /// Runs `work` on the files' own queue, in order with every other read and write.
    private func onDisk<T: Sendable>(_ work: @escaping @Sendable () -> T) async -> T {
        await withCheckedContinuation { c in disk.async { c.resume(returning: work()) } }
    }

    /// The song on screen: `song` names it, `job` is its job on the computer (the recording is kept and fetched
    /// by it), `clock` follows the recording in its tab, and `inHand` is the recording's file when the app was
    /// given it. `songs`: the jobs of Your songs, when the list is known; the recordings of the others go.
    public func open(song: String, job: String?, clock: TabClock?, inHand: URL?, songs: Set<String>? = nil, tab: TabSoundSource? = nil) {
        self.clock = clock
        if song != self.song {
            remember()
            release()
            self.song = song
            let was = left[song]
            // Not in memory: the place kept on the device is read with the recording.
            unread = was == nil
            take(was ?? PracticePlace(at: 0, speed: PracticeSpeed.full, repeating: nil))
        }
        self.job = job
        repeating = repeating.flatMap { fits($0) ? $0 : nil }
        voice(tab, clock)
        if player != nil || fetching != nil { stretch(); return }
        let file = inHand.flatMap { PracticeRecordings.size($0) > 0 ? $0 : nil }
        looking += 1
        let look = looking
        let since = changes
        let ask = unread
        recording = .looking
        let store = store, places = places
        lookup = Task {
            let (found, kept) = await onDisk { () -> (URL?, PracticePlace?) in
                if let job, let songs, songs.contains(job) {
                    store.prune(keeping: songs)
                    places.prune(keeping: songs)
                }
                let found: URL? = if let job { file.map { store.keep(job, from: $0) } ?? store.find(job) } else { file }
                return (found, ask ? job.flatMap(places.read) : nil)
            }
            guard look == looking else { return }
            if unread, let kept, changes == since {
                take(kept)
                repeating = repeating.flatMap { fits($0) ? $0 : nil }
                // The page goes to where the song was left, as it does when the player moves it.
                jumps += 1
            }
            unread = false
            if let found { load(found) } else { recording = .notHere }
        }
    }

    private func take(_ place: PracticePlace) {
        at = place.at
        speed = min(max(place.speed, PracticeSpeed.min), PracticeSpeed.max)
        repeating = place.repeating
    }

    /// `bars` are bars of the tab on screen.
    private func fits(_ bars: RepeatBars) -> Bool {
        guard let clock else { return true }
        return bars.first >= 0 && bars.first <= bars.last && bars.last < clock.bars
    }

    private func load(_ file: URL) {
        // The tab's own sound was playing in the recording's place: the song goes on in the sound chosen.
        let was = playing
        if was { halt() }
        let p = makePlayer(file, self)
        p.speed = Float(speed) / 100
        if at > 0 { p.seek(to: at) }
        player = p
        stretch()
        recording = .here
        if was { start(counted: false) }
    }

    /// Makes the tab's own sound for the page and beats on screen; the one of another page or other beats goes.
    private func voice(_ tab: TabSoundSource?, _ clock: TabClock?) {
        let score = tab.flatMap { t in clock.map { TabSoundScore.of(t.index, clock: $0) } }
        if score == tabOf && tab?.program == tabProgram && (tabPlayer != nil || voicing != nil || score == nil) { return }
        if playing { halt() }
        voicing?.cancel()
        voicing = nil
        tabPlayer?.release()
        tabPlayer = nil
        tabOf = score
        tabProgram = tab?.program
        tabSound = false
        tabSoundFailed = false
        tabSoundLoading = false
        guard let score, let tab, !score.notes.isEmpty else { return }
        tabSoundLoading = true
        let program = tab.program
        voicing = Task {
            let made = await makeTabPlayer(score, program, tabListener)
            // Another page, other beats or another song came meanwhile: this one is not needed.
            guard !Task.isCancelled, score == tabOf, program == tabProgram else { made?.release(); return }
            voicing = nil
            tabSoundLoading = false
            guard let p = made else { tabSoundFailed = true; return }
            p.speed = Float(speed) / 100
            p.seek(to: now())
            tabPlayer = p
            tabSound = true
            stretch()
            // The recording was played while the sound was made: the tab's sound joins it when it is to be heard beside it.
            if playing && !counting && along { join() }
        }
    }

    /// Gives the players the seconds of the bars to repeat.
    private func stretch() {
        let span = repeating.flatMap { r in clock?.span(r) }
        player?.repeatSpan = span
        tabPlayer?.repeatSpan = span
    }

    /// Hears the recording, the tab's own sound, or both. While the song plays it goes on in the new sound.
    public func hear(_ sound: PracticeSound) {
        if sound == self.sound { return }
        let was = playing
        if was { halt() }
        self.sound = sound
        choices.set(sound.rawValue, forKey: Self.soundKey)
        // The player that was not heard till now is where it was left: both go to where the song is.
        player?.seek(to: at)
        tabPlayer?.seek(to: at)
        if was { start(counted: false) }
    }

    /// A bar is counted in before the song plays, or not.
    public func countIn(_ on: Bool) {
        countIn = on
        choices.set(on, forKey: Self.countInKey)
    }

    /// The beats tick while the song plays, or not.
    public func metronome(_ on: Bool) {
        metronome = on
        choices.set(on, forKey: Self.metronomeKey)
        guard let tab = tabPlayer else { return }
        tab.metronome = on
        // Beside the recording the tab's sound runs only while something of it is heard.
        if playing && !counting && !tabLeads {
            if along && !tab.asked { join() } else if !along && tab.asked { tab.pause() }
        }
    }

    /// Stops what sounds, with the song where it is.
    private func halt() {
        let now = now()
        following?.cancel()
        following = nil
        counting = false
        tabPlayer?.pause()
        player?.pause()
        at = now
        playing = false
    }

    /// Plays from where the song is: after a bar counted in when that is chosen (`counted`), in the sound chosen.
    private func start(counted: Bool? = nil) {
        guard let lead else { return }
        readyToPlay()
        let tab = tabPlayer
        tab?.notes = hears != .recording
        tab?.metronome = metronome
        tab?.trim = 1
        if counted ?? countIn, let tab, let clock {
            // A bar as it is counted where the song is: a bar of six-eight is two beats.
            let bar = clock.placeAt(at).bar
            let (beats, ticks) = TabSoundScore.counted(clock.measure(bar))
            tab.seek(to: at)
            tab.countIn(beats: beats, beatSeconds: clock.secondsAt(bar, tick: ticks) - clock.secondsAt(bar))
            counting = true
            playing = true
            tab.play()
            keepFollowing()
        } else {
            lead.play()
            if along { join() }
        }
    }

    /// The tab's sound joins the recording where it is.
    private func join() {
        guard let tab = tabPlayer, let recording = player else { return }
        tab.trim = 1
        tab.seek(to: recording.position)
        tab.play()
        keepFollowing()
    }

    private func keepFollowing() {
        following?.cancel()
        following = Task { [weak self] in
            while !Task.isCancelled {
                // The end of a count is looked for closely, so the recording starts on the beat.
                try? await Task.sleep(for: .milliseconds(self?.counting == true ? 4 : 100))
                guard !Task.isCancelled, let self, self.follow() else { return }
            }
        }
    }

    /// Looked at while the tab's sound plays beside the recording, or counts a bar in for it. The recording starts when
    /// the bar has been counted. Then the tab's sound is kept where the recording is: it stops when the recording does;
    /// heard a little apart, it runs a little faster or slower until the two are together again, so no ringing note is
    /// cut; and only heard far apart (the recording was moved) is it moved. False when there is nothing more to look at.
    @discardableResult
    func follow() -> Bool {
        guard let tab = tabPlayer else { return false }
        if counting {
            if !tab.asked { counting = false; playing = false; return false }
            if tab.countingIn { return true }
            counting = false
            if tabLeads { playingChanged(true); return false }
            if !along { tab.pause() }
            player?.play()
        }
        guard let recording = player, !tabLeads, along else { return false }
        if !recording.playing { if tab.asked { tab.pause() }; return false }
        if !tab.asked { tab.trim = 1; tab.seek(to: recording.position); tab.play() }
        else {
            let ahead = tab.position - recording.position
            if abs(ahead) > Self.apart { tab.trim = 1; tab.seek(to: recording.position) }
            else { tab.trim = min(max(1 - ahead * Self.pull, 1 - Self.most), 1 + Self.most) }
        }
        return true
    }

    /// Copies the recording from the computer, which holds what it was sent.
    public func fetch(_ get: @escaping Fetch) {
        guard let job else { return }
        // One fetch at a time: a second press while one runs does nothing.
        if fetching != nil || player != nil { return }
        looking += 1
        let look = looking
        recording = .getting
        let store = store
        fetching = Task {
            defer { if look == looking { fetching = nil } }
            // This fetch's own file: a fetch given up on leaving the screen clears it, also after the next one has begun.
            let part = await onDisk { store.arriving(job) }
            do {
                guard let part else { throw PracticeRecordings.KeepError.noPlace }
                try await get(job, part)
                try Task.checkCancellation()
                guard let got = await onDisk({ store.arrived(job, part) }) else { throw PracticeRecordings.KeepError.cameEmpty }
                if look == looking { load(got) }
            } catch {
                await onDisk { store.dropped(part) }
                if error is CancellationError || Task.isCancelled { return }
                Self.log.warning("the recording could not be fetched: \(String(describing: error), privacy: .public)")
                let why = PracticeRecordings.whyNot(error, room: await onDisk { store.room })
                if look == looking { recording = why }
            }
        }
        lastFetch = fetching
    }

    public func toggle() {
        guard let p = lead else { return }
        if playing || p.playing { halt(); remember(); return }
        // Asked to play while the system holds the sound back: asked again, from the start of the asking.
        if p.asked { p.pause() }
        // From the end, or from outside the bars being repeated, it starts over.
        let span = repeating.flatMap { clock?.span($0) }
        let end = clock?.end
        if let span, at < span.lowerBound - Self.edge || at >= span.upperBound - Self.edge { seek(span.lowerBound) }
        else if let end, at >= end - Self.edge { seek(0) }
        start()
    }

    public func pause() {
        if playing || lead?.asked == true { halt(); remember() }
    }

    private func seek(_ seconds: Double) {
        changes += 1
        let to = max(seconds, 0)
        // A bar being counted in is given up: the song plays on from where it is moved to.
        let counted = counting
        if counted { halt() }
        player?.seek(to: to)
        tabPlayer?.seek(to: to)
        at = to
        jumps += 1
        remember()
        if counted { start(counted: false) }
    }

    /// To the line of `bar`, kept inside the bars being repeated.
    public func toBar(_ bar: Int) {
        guard let clock else { return }
        let within = repeating.map { min(max(bar, $0.first), $0.last) } ?? min(max(bar, 0), clock.bars - 1)
        seek(clock.secondsAt(within))
    }

    /// A bar back or on from the bar the song is in. In the last bar (of the tab, or of the bars being repeated) there is no bar on: nothing happens.
    public func step(_ bars: Int) {
        guard let clock else { return }
        let bar = clock.placeAt(now()).bar
        if bars > 0 && !hasBarOn(bar) { return }
        toBar(bar + bars)
    }

    /// There is a bar after `bar` to step on to: it is not the last of the tab, nor the last of the bars being repeated.
    public func hasBarOn(_ bar: Int) -> Bool {
        guard let clock else { return false }
        return bar < (repeating?.last ?? (clock.bars - 1))
    }

    /// Back to where the repeat starts; to the start of the tab when nothing is repeated.
    public func toStart() { toBar(repeating?.first ?? 0) }

    public func slower() { speedTo(PracticeSpeed.slower(speed)) }
    public func faster() { speedTo(PracticeSpeed.faster(speed)) }

    private func speedTo(_ percent: Int) {
        changes += 1
        speed = percent
        player?.speed = Float(percent) / 100
        tabPlayer?.speed = Float(percent) / 100
        remember()
    }

    /// One bar again and again, slowly, from its start: to listen to a note Fretscribe is not sure of. `bar` is counted
    /// from 0; it plays when the recording is on the device.
    public func playBarSlowly(_ bar: Int) {
        guard let clock, bar >= 0, bar < clock.bars else { return }
        let one = RepeatBars(first: bar, last: bar)
        // The player's own speed and repeat, to go back to when the note is left (the first of several bars played slowly).
        if let slow = beforeSlow, speed == PracticeSpeed.slow, repeating == slow.1 { beforeSlow = (slow.0, one) }
        else { beforeSlow = (PracticePlace(at: at, speed: speed, repeating: repeating), one) }
        speedTo(PracticeSpeed.slow)
        `repeat`(one)
        toBar(bar)
        if !playing { toggle() }
    }

    /// The note a bar was played slowly for is left: the speed and repeat the player had come back, unless the player
    /// changed them since. The song plays on, or stays paused, where it is.
    public func endSlowly() {
        guard let slow = beforeSlow else { return }
        let (was, bar) = slow
        beforeSlow = nil
        if speed != PracticeSpeed.slow || repeating != bar { return }
        speedTo(was.speed)
        `repeat`(was.repeating)
    }

    /// Repeats `bars`; nil plays on. The song goes to the first of them when it is outside them.
    public func `repeat`(_ bars: RepeatBars?) {
        changes += 1
        repeating = bars
        stretch()
        if let bars, let clock, !(bars.first...bars.last).contains(clock.placeAt(now()).bar) { toBar(bars.first) }
        remember()
    }

    /// The tab is left: the sound stops, a fetch that is running is given up, and the song is kept where it was.
    public func leave() {
        looking += 1
        fetching?.cancel()
        fetching = nil
        remember()
        release()
        recording = .looking
    }

    private func release() {
        at = now()
        following?.cancel()
        following = nil
        player?.release()
        player = nil
        voicing?.cancel()
        voicing = nil
        tabPlayer?.release()
        tabPlayer = nil
        tabOf = nil
        tabProgram = nil
        tabSound = false
        tabSoundFailed = false
        tabSoundLoading = false
        counting = false
        playing = false
    }

    private func remember() {
        guard let song else { return }
        let place = PracticePlace(at: now(), speed: speed, repeating: repeating)
        left[song] = place
        // Not before the place kept on the device was read: what is there is not written over with the defaults.
        guard let job, !unread else { return }
        let places = places
        disk.async { places.save(job, place) }
    }

    // What the recording tells is the song's while the recording is what is heard.
    public func recordingPlaying(_ playing: Bool) {
        if !tabLeads && !counting { playingChanged(playing) }
    }

    public func recordingEnded() {
        if !tabLeads { endedNow() }
    }

    public func recordingFailed() {
        let now = now()
        following?.cancel()
        following = nil
        tabPlayer?.pause()
        player?.release()
        player = nil
        counting = false
        playing = false
        at = now
        recording = .unplayable
    }

    private func playingChanged(_ playing: Bool) {
        if !playing, let lead { at = lead.position }
        self.playing = playing
        if playing && along { keepFollowing() }
        if !playing {
            if !tabLeads { tabPlayer?.pause() }
            remember()
        }
    }

    private func endedNow() {
        if let lead { at = lead.position }
        if !tabLeads { tabPlayer?.pause() }
        playing = false
    }

    // What the tab's sound tells is the song's while the tab's sound is what the song's place is read from.
    fileprivate func tabPlaying(_ playing: Bool) {
        if tabLeads && !counting { playingChanged(playing) }
    }

    fileprivate func tabEnded() {
        if tabLeads { endedNow() }
    }

    fileprivate func tabFailed() {
        let led = tabLeads
        following?.cancel()
        following = nil
        tabPlayer?.release()
        tabPlayer = nil
        tabSound = false
        tabSoundFailed = true
        if led { counting = false; playing = false }
    }

    /// Waits for what was started to be done: the look for the recording, a fetch, and the writes of the places.
    func settled() async {
        await voicing?.value
        await lookup?.value
        await lastFetch?.value
        await onDisk {}
    }
}

/// What the tab's own sound tells the model, apart from what the recording tells it.
@MainActor
private final class TabListener: RecordingPlayerListener {
    private weak var model: PracticeModel?
    init(_ model: PracticeModel) { self.model = model }
    func recordingPlaying(_ playing: Bool) { model?.tabPlaying(playing) }
    func recordingEnded() { model?.tabEnded() }
    func recordingFailed() { model?.tabFailed() }
}

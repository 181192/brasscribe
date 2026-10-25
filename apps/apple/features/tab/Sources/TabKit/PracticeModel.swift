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
    @ObservationIgnored private var player: (any RecordingPlayer)?
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

    /// `recordings` and `places` are the folders the recordings and the places are kept in.
    public init(recordings: URL, places: URL, makePlayer: @escaping MakePlayer = { AVRecordingPlayer(file: $0, listener: $1) }) {
        store = PracticeRecordings(dir: recordings)
        self.places = PracticePlaces(dir: places)
        self.makePlayer = makePlayer
    }

    /// The second of the recording the song is at.
    public func now() -> Double {
        if playing, let player { return player.position }
        return at
    }

    /// Runs `work` on the files' own queue, in order with every other read and write.
    private func onDisk<T: Sendable>(_ work: @escaping @Sendable () -> T) async -> T {
        await withCheckedContinuation { c in disk.async { c.resume(returning: work()) } }
    }

    /// The song on screen: `song` names it, `job` is its job on the computer (the recording is kept and fetched
    /// by it), `clock` follows the recording in its tab, and `inHand` is the recording's file when the app was
    /// given it. `songs`: the jobs of Your songs, when the list is known; the recordings of the others go.
    public func open(song: String, job: String?, clock: TabClock?, inHand: URL?, songs: Set<String>? = nil) {
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
        let p = makePlayer(file, self)
        p.speed = Float(speed) / 100
        if at > 0 { p.seek(to: at) }
        player = p
        stretch()
        recording = .here
    }

    /// Gives the player the seconds of the bars to repeat.
    private func stretch() {
        player?.repeatSpan = repeating.flatMap { r in clock?.span(r) }
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
        guard let p = player else { return }
        if playing || p.playing { p.pause(); return }
        // Asked to play while the system holds the sound back: asked again, from the start of the asking.
        if p.asked { p.pause() }
        // From the end, or from outside the bars being repeated, it starts over.
        let span = repeating.flatMap { clock?.span($0) }
        let end = clock?.end
        if let span, at < span.lowerBound - Self.edge || at >= span.upperBound - Self.edge { seek(span.lowerBound) }
        else if let end, at >= end - Self.edge { seek(0) }
        p.play()
    }

    public func pause() {
        player?.pause()
    }

    private func seek(_ seconds: Double) {
        changes += 1
        let to = max(seconds, 0)
        player?.seek(to: to)
        at = to
        jumps += 1
        remember()
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
        if let p = player {
            if playing { at = p.position }
            p.release()
        }
        player = nil
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

    public func recordingPlaying(_ playing: Bool) {
        if !playing, let player { at = player.position }
        self.playing = playing
        if !playing { remember() }
    }

    public func recordingEnded() {
        if let player { at = player.position }
        playing = false
    }

    public func recordingFailed() {
        release()
        recording = .unplayable
    }

    /// Waits for what was started to be done: the look for the recording, a fetch, and the writes of the places.
    func settled() async {
        await lookup?.value
        await lastFetch?.value
        await onDisk {}
    }
}

import Foundation
import Testing
@testable import TabKit

/// A folder of a test's own, gone when the test is.
final class TempDir {
    let url = FileManager.default.temporaryDirectory.appending(path: "tabkit-\(UUID().uuidString)", directoryHint: .isDirectory)
    init() { try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true) }
    deinit { try? FileManager.default.removeItem(at: url) }
    func file(_ name: String) -> URL { url.appending(path: name) }
}

func size(_ url: URL?) -> Int64 { url.map(PracticeRecordings.size) ?? -1 }

func list(_ dir: URL) -> [String] { ((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []).sorted() }

/// Where each song was left in practice (`PracticePlaces`): kept on the device by the song's job, and gone with the song.
struct PracticePlacesTests {
    let dir = TempDir()
    var places: PracticePlaces { PracticePlaces(dir: dir.file("places")) }

    @Test func aPlaceIsKeptAndReadBack() {
        #expect(places.read("job-1") == nil)
        places.save("job-1", PracticePlace(at: 12.25, speed: 70, repeating: RepeatBars(first: 8, last: 9)))
        places.save("job-2", PracticePlace(at: 0, speed: 100, repeating: nil))
        #expect(places.read("job-1") == PracticePlace(at: 12.25, speed: 70, repeating: RepeatBars(first: 8, last: 9)))
        #expect(places.read("job-2") == PracticePlace(at: 0, speed: 100, repeating: nil))
        // The latest is what is kept.
        places.save("job-1", PracticePlace(at: 3.5, speed: 60, repeating: RepeatBars(first: 2, last: 2)))
        #expect(places.read("job-1") == PracticePlace(at: 3.5, speed: 60, repeating: RepeatBars(first: 2, last: 2)))
        #expect(list(dir.file("places")) == [PracticeRecordings.fileName("job-1")!, PracticeRecordings.fileName("job-2")!].sorted())
    }

    @Test func whatCantBeReadIsNoPlace() throws {
        let folder = dir.file("places")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        func write(_ job: String, _ text: String) throws { try text.write(to: folder.appending(path: PracticeRecordings.fileName(job)!), atomically: true, encoding: .utf8) }
        try write("job-1", "not a place")
        #expect(places.read("job-1") == nil)
        // A repeat that isn't one is left out; the rest is kept.
        try write("job-2", "4.0 80 5 2")
        #expect(places.read("job-2") == PracticePlace(at: 4, speed: 80, repeating: nil))
        #expect(places.read("") == nil)
        // A second that is no number is no place.
        for at in ["NaN", "Infinity", "-1.0"] {
            try write("job-3", "\(at) 80")
            #expect(places.read("job-3") == nil, "\(at)")
        }
    }

    @Test func aSongThatLeftTakesItsPlaceWithIt() {
        places.save("job-1", PracticePlace(at: 1, speed: 90, repeating: nil))
        places.save("job-2", PracticePlace(at: 2, speed: 80, repeating: nil))
        places.prune(keeping: ["job-2"])
        #expect(places.read("job-1") == nil)
        #expect(places.read("job-2") == PracticePlace(at: 2, speed: 80, repeating: nil))
    }
}

/// The recordings kept on the device for practising (`PracticeRecordings`): one to a song, by its job on the computer.
struct PracticeRecordingsTests {
    let dir = TempDir()
    var kept: URL { dir.file("kept") }
    var store: PracticeRecordings { PracticeRecordings(dir: kept) }

    func take(_ bytes: Int, _ name: String = "take.wav") -> URL {
        let url = dir.file(name)
        try! Data((0..<bytes).map { UInt8(truncatingIfNeeded: $0) }).write(to: url)
        return url
    }

    func write(_ bytes: Int, to url: URL) { try! Data(count: bytes).write(to: url) }

    @Test func aRecordingInHandIsCopiedAndFoundAgain() throws {
        #expect(store.find("job-1") == nil)
        let take = take(1000)
        let copy = store.keep("job-1", from: take)
        #expect(copy != take && size(copy) > 0, "the copy is the store's own file")
        #expect(size(copy) == 1000)
        // The take can go: the song still has its recording.
        try FileManager.default.removeItem(at: take)
        #expect(store.find("job-1") == copy)
        // Kept once: the same recording again is the same file.
        #expect(store.keep("job-1", from: self.take(1000)) == copy)
        #expect(store.find("job-2") == nil)
    }

    @Test func aRecordingBeingFetchedIsNotThereUntilItIsWhole() throws {
        let part = try #require(store.arriving("job-1"))
        write(10, to: part)
        #expect(store.find("job-1") == nil, "half a recording is no recording")
        let whole = try #require(store.arrived("job-1", part))
        #expect(store.find("job-1") == whole)
        // One that came empty is dropped.
        let empty = try #require(store.arriving("job-2"))
        #expect(store.arrived("job-2", empty) == nil)
        #expect(store.find("job-2") == nil)
        #expect(!FileManager.default.fileExists(atPath: empty.path))
    }

    @Test func aFetchGivenUpLateNeverTakesTheFileOfTheFetchAfterIt() throws {
        // Leaving the screen gives the first fetch up; it clears its file only once the next fetch has begun.
        let first = try #require(store.arriving("job-1"))
        write(3, to: first)
        let second = try #require(store.arriving("job-1"))
        #expect(first != second, "each fetch writes its own file")
        write(12, to: second)
        store.dropped(first)
        #expect(size(second) == 12, "the second fetch's file is still there")
        #expect(size(store.arrived("job-1", second)) == 12)
        #expect(size(store.find("job-1")) == 12)
        // The first one coming to an end after that changes nothing either.
        #expect(store.arrived("job-1", first) == nil)
        #expect(size(store.find("job-1")) == 12)
    }

    @Test func aSongThatIsGoneTakesItsRecordingWithIt() throws {
        _ = store.keep("job-1", from: take(10))
        _ = store.keep("job-2", from: take(20))
        write(5, to: try #require(store.arriving("job-3")))
        store.prune(keeping: ["job-2"])
        #expect(store.find("job-1") == nil)
        let two = try #require(store.find("job-2"))
        #expect(list(kept) == [two.lastPathComponent])
    }

    @Test func aJobsIdNeverLeavesTheFolder() {
        #expect(store.keep("../../outside", from: take(10)).deletingLastPathComponent().standardizedFileURL == kept.standardizedFileURL)
        #expect(store.keep("/..", from: take(10)).deletingLastPathComponent().standardizedFileURL == kept.standardizedFileURL)
        // No id keeps nothing.
        let take = take(10)
        #expect(store.keep("", from: take) == take)
        #expect(store.find("") == nil)
    }

    @Test func idsThatReadAlikeAreStillTwoSongs() throws {
        let a = store.keep("job/1", from: take(10))
        let b = store.keep("job1", from: take(20))
        #expect(a != b)
        #expect(size(store.find("job/1")) == 10)
        #expect(size(store.find("job1")) == 20)
        // Also past the length a file name keeps of the id.
        let long = String(repeating: "x", count: 200)
        let c = store.keep(long + "a", from: take(30))
        let d = store.keep(long + "b", from: take(40))
        #expect(c != d && c.lastPathComponent.count < 100)
        #expect(size(store.find(long + "a")) == 30)
    }

    @Test func whatATryLeftBehindIsCleared() throws {
        // A fetch that stopped half way: its part is gone when it is given up, and when the songs are gone through.
        let again = try #require(store.arriving("job-1"))
        write(7, to: again)
        store.dropped(again)
        #expect(!FileManager.default.fileExists(atPath: again.path))
        write(7, to: try #require(store.arriving("job-1")))
        write(7, to: try #require(store.arriving("job-1")))
        _ = store.keep("job-2", from: take(5))
        store.prune(keeping: ["job-1", "job-2"])
        #expect(list(kept).count == 1)
        #expect(store.find("job-2") != nil)
        #expect(store.room > 0)
    }

    struct EngineError: RecordingFetchFailure {
        let recordingFetchError: RecordingFetchError?
    }

    @Test func aRecordingThatDidNotComeSaysWhy() {
        let plenty: Int64 = 1 << 30
        #expect(PracticeRecordings.whyNot(RecordingFetchError.status(404), room: plenty) == .gone)
        #expect(PracticeRecordings.whyNot(RecordingFetchError.status(413), room: plenty) == .tooLarge)
        #expect(PracticeRecordings.whyNot(RecordingFetchError.status(500), room: plenty) == .noAnswer)
        // The engine's client says so through its own errors as well.
        #expect(PracticeRecordings.whyNot(EngineError(recordingFetchError: .status(404)), room: plenty) == .gone)
        #expect(PracticeRecordings.whyNot(EngineError(recordingFetchError: nil), room: plenty) == .noAnswer)
        #expect(PracticeRecordings.whyNot(URLError(.cannotConnectToHost), room: plenty) == .noAnswer)
        // Not asked, because one of the two needs an update: said as that, not as a computer that does not answer.
        #expect(PracticeRecordings.whyNot(RecordingFetchError.updateApp, room: plenty) == .updateApp)
        #expect(PracticeRecordings.whyNot(EngineError(recordingFetchError: .updateComputer), room: plenty) == .updateComputer)
        // An answer from the computer is what it is, however full the device.
        #expect(PracticeRecordings.whyNot(RecordingFetchError.status(404), room: 1000) == .gone)
        #expect(PracticeRecordings.whyNot(PracticeRecordings.KeepError.cameEmpty, room: plenty) == .noAnswer)
        // The device is full, or the file could not be made: it is not the computer that is away.
        #expect(PracticeRecordings.whyNot(URLError(.cannotWriteToFile), room: 1000) == .noRoom)
        #expect(PracticeRecordings.whyNot(CocoaError(.fileNoSuchFile), room: plenty) == .noRoom)
        #expect(PracticeRecordings.whyNot(POSIXError(.ENOSPC), room: plenty) == .noRoom)
        #expect(PracticeRecordings.whyNot(PracticeRecordings.KeepError.noPlace, room: plenty) == .noRoom)
    }

    @Test func aKeptRecordingIsSentAgainNamedForTheKindOfFileItIs() {
        func kind(_ head: [UInt8]) -> String {
            let url = dir.file("kind")
            try! Data(head + [UInt8](repeating: 0, count: 16)).write(to: url)
            return PracticeRecordings.extensionOf(url)
        }
        func kind(_ text: String, at: Int = 0) -> String { kind([UInt8](repeating: 0, count: at) + Array(text.utf8)) }
        #expect(kind("RIFF\0\0\0\0WAVE") == "wav")
        #expect(kind("ftypM4A ", at: 4) == "m4a")
        #expect(kind("ID3") == "mp3")
        #expect(kind([0xFF, 0xFB, 0x90]) == "mp3")
        #expect(kind("OggS") == "ogg")
        #expect(kind("fLaC") == "flac")
        #expect(kind([0x1A, 0x45, 0xDF, 0xA3]) == "webm")
        // Anything else is taken as it was before there was a name: the computer reads it as a WAV file.
        #expect(kind("hello") == "wav")
        #expect(PracticeRecordings.extensionOf(dir.file("none")) == "wav")
        // A kept recording is found by the song's job, under the name the store gives it.
        let m4a = dir.file("take.m4a")
        try! Data([0, 0, 0, 0] + Array("ftypM4A ".utf8)).write(to: m4a)
        #expect(PracticeRecordings.extensionOf(store.keep("job-1", from: m4a)) == "m4a")
    }
}

import Foundation
import Testing
@testable import TabKit

/// A player that plays nothing: it says what it was told.
@MainActor
final class FakePlayer: RecordingPlayer {
    let file: URL
    weak var listener: (any RecordingPlayerListener)?
    var playing = false
    var asked = false
    var position: Double = 0
    var duration: Double = 60
    var speed: Float = 1
    var repeatSpan: ClosedRange<Double>?
    var seeks: [Double] = []
    var released = false

    init(file: URL, listener: any RecordingPlayerListener) {
        self.file = file
        self.listener = listener
    }

    func play() { asked = true; playing = true; listener?.recordingPlaying(true) }
    func pause() { asked = false; playing = false; listener?.recordingPlaying(false) }
    func seek(to seconds: Double) { seeks.append(seconds); position = seconds }
    func release() { released = true }
}

/// Practice (`PracticeModel`) with a player that plays nothing: where the song is, how fast and which bars, and
/// where it was left.
@MainActor
struct PracticeModelTests {
    let dir = TempDir()
    let clock: TabClock
    var players: [FakePlayer] { made.players }
    let made = Made()

    final class Made { var players: [FakePlayer] = [] }

    init() throws {
        let index = TabIndex.parse(musicXML: try fixtureText("bass-line/tab.musicxml"))
        clock = try #require(TabClock.of(index, tab: try fixtureTab("bass-line"), saved: nil))
    }

    func model() -> PracticeModel {
        let made = made
        return PracticeModel(recordings: dir.file("recordings"), places: dir.file("places")) { file, listener in
            let p = FakePlayer(file: file, listener: listener)
            made.players.append(p)
            return p
        }
    }

    func take() -> URL {
        let url = dir.file("take.wav")
        try! Data(repeating: 1, count: 100).write(to: url)
        return url
    }

    @Test func aRecordingInHandIsKeptAndPlays() async throws {
        let m = model()
        #expect(m.recording == .looking)
        m.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await m.settled()
        #expect(m.recording == .here)
        let player = try #require(players.last)
        // It plays from the copy kept for the song, not from the file it was given.
        #expect(player.file == PracticeRecordings(dir: dir.file("recordings")).find("job-1"))
        m.toggle()
        #expect(m.playing)
        m.toggle()
        #expect(!m.playing)
    }

    @Test func aSongOpensWhereItWasLeft() async throws {
        let first = model()
        first.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await first.settled()
        first.toBar(3)
        first.faster()
        first.repeat(RepeatBars(first: 3, last: 4))
        first.leave()
        await first.settled()

        // A new start of the app: only what is on the device.
        let again = model()
        again.open(song: "song", job: "job-1", clock: clock, inHand: nil)
        await again.settled()
        #expect(again.recording == .here)
        #expect(near(again.at, clock.secondsAt(3)))
        #expect(again.speed == 105)
        #expect(again.repeating == RepeatBars(first: 3, last: 4))
        // The page goes there, and so does the player.
        #expect(again.jumps == 1)
        let player = try #require(players.last)
        #expect(player.seeks.last.map { near($0, clock.secondsAt(3)) } == true)
        #expect(player.speed == 1.05)
        #expect(player.repeatSpan == clock.span(RepeatBars(first: 3, last: 4)))
    }

    @Test func inMemoryASongIsWhereItWasLeftWithoutAskingTheDevice() async {
        let m = model()
        m.open(song: "a", job: "job-a", clock: clock, inHand: take())
        await m.settled()
        m.toBar(5)
        m.open(song: "b", job: "job-b", clock: clock, inHand: take())
        await m.settled()
        #expect(m.at == 0)
        m.open(song: "a", job: "job-a", clock: clock, inHand: nil)
        await m.settled()
        #expect(near(m.at, clock.secondsAt(5)))
        // The songs no longer in Your songs lose their recordings.
        m.open(song: "b", job: "job-b", clock: clock, inHand: nil, songs: ["job-b"])
        await m.settled()
        #expect(PracticeRecordings(dir: dir.file("recordings")).find("job-a") == nil)
        #expect(PracticePlaces(dir: dir.file("places")).read("job-a") == nil)
    }

    @Test func aRecordingNotHereIsFetchedFromTheComputer() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil)
        await m.settled()
        #expect(m.recording == .notHere)
        m.fetch { job, into in
            #expect(job == "job-1")
            try Data(repeating: 2, count: 50).write(to: into)
        }
        #expect(m.recording == .getting)
        await m.settled()
        #expect(m.recording == .here)
        #expect(players.count == 1)
        #expect(list(dir.file("recordings")) == [PracticeRecordings.fileName("job-1")!])
    }

    @Test(arguments: [(RecordingFetchError.status(404), RecordingState.gone), (.status(413), .tooLarge), (.status(503), .noAnswer),
                      (.updateApp, .updateApp), (.updateComputer, .updateComputer)])
    func aFetchThatFailsSaysWhy(error: RecordingFetchError, state: RecordingState) async {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil)
        await m.settled()
        m.fetch { _, into in
            try Data(repeating: 2, count: 50).write(to: into)
            throw error
        }
        await m.settled()
        #expect(m.recording == state)
        // What came of it is gone.
        #expect(list(dir.file("recordings")).isEmpty)
    }

    @Test func aRecordingThatCameEmptyIsNotKept() async {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil)
        await m.settled()
        m.fetch { _, _ in }
        await m.settled()
        #expect(m.recording == .noAnswer || m.recording == .noRoom)
        #expect(players.isEmpty)
    }

    @Test func leavingGivesAFetchUp() async {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil)
        await m.settled()
        m.fetch { _, into in
            try Data(repeating: 2, count: 50).write(to: into)
            try await Task.sleep(for: .seconds(30))
        }
        try? await Task.sleep(for: .milliseconds(50))
        m.leave()
        await m.settled()
        #expect(m.recording == .looking)
        #expect(players.isEmpty)
        #expect(list(dir.file("recordings")).isEmpty)
    }

    @Test func aBarIsPlayedSlowlyAndTheSpeedAndRepeatComeBack() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await m.settled()
        m.repeat(RepeatBars(first: 0, last: 7))
        m.playBarSlowly(5)
        #expect(m.speed == PracticeSpeed.slow)
        #expect(m.repeating == RepeatBars(first: 5, last: 5))
        #expect(m.playing)
        #expect(near(m.at, clock.secondsAt(5)))
        let player = try #require(players.last)
        #expect(player.repeatSpan == clock.span(RepeatBars(first: 5, last: 5)))
        // A second bar played slowly goes back to the same speed and repeat.
        m.playBarSlowly(6)
        m.endSlowly()
        #expect(m.speed == PracticeSpeed.full)
        #expect(m.repeating == RepeatBars(first: 0, last: 7))
        // Changed since by the player: kept as it is.
        m.playBarSlowly(5)
        m.faster()
        m.endSlowly()
        #expect(m.speed == PracticeSpeed.slow + PracticeSpeed.step)
        #expect(m.repeating == RepeatBars(first: 5, last: 5))
    }

    @Test func theLastBarOfARepeatHasNoBarOn() async {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await m.settled()
        m.repeat(RepeatBars(first: 2, last: 3))
        // The song was outside the bars: it goes to the first of them.
        #expect(clock.placeAt(m.now()).bar == 2)
        m.toBar(3)
        #expect(!m.hasBarOn(3))
        #expect(m.hasBarOn(2))
        let jumps = m.jumps
        m.step(1)
        #expect(m.jumps == jumps)
        #expect(clock.placeAt(m.now()).bar == 3)
        m.step(-1)
        #expect(clock.placeAt(m.now()).bar == 2)
        // A bar outside the repeat is kept inside it.
        m.toBar(10)
        #expect(clock.placeAt(m.now()).bar == 3)
        m.repeat(nil)
        m.toStart()
        #expect(m.now() == clock.secondsAt(0))
        #expect(!m.hasBarOn(clock.bars - 1))
    }

    @Test func playFromTheEndStartsOver() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await m.settled()
        m.toBar(clock.bars - 1)
        let player = try #require(players.last)
        player.position = clock.end
        m.toggle()
        m.toggle()
        // Paused at the end of the tab, play goes back to its start.
        #expect(near(m.at, clock.end))
        m.toggle()
        #expect(m.at == 0)
        #expect(m.playing)
    }

    @Test func aFileThatCannotBePlayedSaysSo() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take())
        await m.settled()
        let player = try #require(players.last)
        m.recordingFailed()
        #expect(m.recording == .unplayable)
        #expect(player.released)
    }
}

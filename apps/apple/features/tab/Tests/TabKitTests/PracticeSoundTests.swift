import Foundation
import Testing
@testable import TabKit

/// A tab sound that sounds nothing: it says what it was told.
@MainActor
final class FakeTabSound: TabSoundPlaying {
    weak var listener: (any RecordingPlayerListener)?
    let program: UInt8
    var playing: Bool { asked }
    var asked = false
    var position: Double = 0
    var duration: Double = 60
    var speed: Float = 1
    var repeatSpan: ClosedRange<Double>?
    var notes = true
    var metronome = false
    var trim = 1.0
    var countingIn = false
    var counts: [(beats: Int, beatSeconds: Double)] = []
    var seeks: [Double] = []
    var released = false

    init(program: UInt8, listener: any RecordingPlayerListener) { self.program = program; self.listener = listener }

    func countIn(beats: Int, beatSeconds: Double) { counts.append((beats, beatSeconds)); countingIn = true }
    func play() { asked = true; listener?.recordingPlaying(true) }
    func pause() { if asked { asked = false; countingIn = false; listener?.recordingPlaying(false) } }
    func seek(to seconds: Double) { seeks.append(seconds); position = seconds; countingIn = false }
    func release() { released = true }
}

/// What is heard in practice (`PracticeModel`), with players that sound nothing: the tab's own notes in place of the
/// recording or over it, a bar counted in, the metronome, and the choices kept for the next song.
@MainActor
struct PracticeSoundTests {
    let dir = TempDir()
    let index: TabIndex
    let clock: TabClock
    let made = Made()
    let suite = "practice-sound-tests-\(UUID().uuidString)"

    final class Made { var players: [FakePlayer] = []; var tabs: [FakeTabSound] = []; var readied: [Bool] = [] }

    init() throws {
        index = TabIndex.parse(musicXML: try fixtureText("bass-line/tab.musicxml"))
        clock = try #require(TabClock.of(index, tab: try fixtureTab("bass-line"), saved: nil))
    }

    func model() -> PracticeModel {
        let made = made
        return PracticeModel(recordings: dir.file("recordings"), places: dir.file("places"), choices: UserDefaults(suiteName: suite)!,
                             makePlayer: { file, listener in
                                 let p = FakePlayer(file: file, listener: listener)
                                 made.players.append(p)
                                 return p
                             }, makeTabPlayer: { _, program, listener in
                                 let t = FakeTabSound(program: program, listener: listener)
                                 made.tabs.append(t)
                                 return t
                             }, readyToPlay: {
                                 // Whether anything already played when the device's sound was readied.
                                 made.readied.append(made.tabs.contains { $0.asked } || made.players.contains { $0.asked })
                             })
    }

    func take() -> URL {
        let url = dir.file("take.wav")
        try! Data(repeating: 1, count: 100).write(to: url)
        return url
    }

    var source: TabSoundSource { TabSoundSource(index: index, program: EngineTabSoundPlayer.bass) }

    @Test func aSongWithoutItsRecordingPlaysTheTabsNotes() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil, tab: source)
        await m.settled()
        #expect(m.recording == .notHere)
        #expect(m.tabSound && m.canPlay && m.hears == .tab)
        let tab = try #require(made.tabs.last)
        #expect(tab.program == EngineTabSoundPlayer.bass)
        m.toggle()
        #expect(m.playing && tab.asked && tab.notes)
        tab.position = 2
        #expect(m.now() == 2)
        m.step(1)
        #expect(tab.seeks.last == clock.secondsAt(clock.placeAt(2).bar + 1))
        m.toggle()
        #expect(!m.playing && !tab.asked)
        // The same page and beats again make no new sound; leaving the tab lets it go.
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil, tab: source)
        #expect(made.tabs.count == 1)
        m.leave()
        #expect(tab.released && !m.tabSound)
    }

    @Test func withTheRecordingTheChoiceIsHeardAndKept() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take(), tab: source)
        await m.settled()
        let recording = try #require(made.players.last), tab = try #require(made.tabs.last)
        #expect(m.hears == .recording)
        m.toggle()
        #expect(recording.asked && !tab.asked)
        // The tab's notes in the recording's place, from where the song is.
        recording.position = 3
        m.hear(.tab)
        #expect(m.playing && !recording.asked && tab.asked && tab.seeks.last == 3)
        // Both: the recording leads again and the tab's sound joins it.
        tab.position = 4
        m.hear(.both)
        #expect(recording.asked && tab.asked && recording.seeks.last == 4 && tab.notes)
        // Heard a little apart, the tab's sound is not moved (a move cuts what rings): it runs a little faster or slower.
        let moves = tab.seeks.count
        recording.position = 4.03
        #expect(m.follow())
        #expect(tab.seeks.count == moves && near(tab.trim, 1.03))
        tab.position = 4.1
        m.follow()
        #expect(tab.seeks.count == moves && near(tab.trim, 0.95))
        tab.position = 4.03
        m.follow()
        #expect(tab.trim == 1)
        // Heard far apart (the recording was moved), it is moved to where the recording is.
        recording.position = 5
        #expect(m.follow())
        #expect(tab.seeks.last == 5 && tab.trim == 1)
        m.toggle()
        #expect(!recording.asked && !tab.asked)
        #expect(model().sound == .both)
    }

    @Test func aBarIsCountedInBeforeTheRecordingStarts() async throws {
        let m = model()
        m.countIn(true)
        m.open(song: "song", job: "job-1", clock: clock, inHand: take(), tab: source)
        await m.settled()
        let recording = try #require(made.players.last), tab = try #require(made.tabs.last)
        m.toggle()
        #expect(m.playing && m.counting && tab.asked && !recording.asked)
        // Two beats, as long as the recording's own at its start.
        #expect(tab.counts.count == 1 && tab.counts[0].beats == 2 && near(tab.counts[0].beatSeconds, clock.secondsAt(0, tick: TabIndex.ticks) - clock.secondsAt(0)))
        #expect(m.now() == 0)
        #expect(m.follow())
        #expect(m.counting)
        tab.countingIn = false
        m.follow()
        // Counted: the recording plays, and the tab's sound, which only counted, is quiet.
        #expect(!m.counting && m.playing && recording.asked && !tab.asked)
        m.toggle()
        // Pause while it counts gives the count up.
        m.toggle()
        #expect(m.counting)
        m.toggle()
        #expect(!m.counting && !m.playing && !tab.asked && !recording.asked)
        #expect(model().countIn)
    }

    @Test func aSoundThatCannotBeMadeSaysSoAndTheRecordingStillPlays() async throws {
        let made = made
        let m = PracticeModel(recordings: dir.file("recordings"), places: dir.file("places"), choices: UserDefaults(suiteName: suite)!,
                              makePlayer: { file, listener in
                                  let p = FakePlayer(file: file, listener: listener)
                                  made.players.append(p)
                                  return p
                              }, makeTabPlayer: { _, _, _ in nil })
        m.countIn(true)
        m.open(song: "song", job: "job-1", clock: clock, inHand: take(), tab: source)
        await m.settled()
        #expect(!m.tabSound && m.tabSoundFailed && m.canPlay && m.hears == .recording)
        m.toggle()
        #expect(m.playing && !m.counting && made.players.last?.asked == true)
        m.leave()
        #expect(!m.tabSoundFailed)
    }

    @Test func theMetronomeTicksBesideTheRecording() async throws {
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: take(), tab: source)
        await m.settled()
        let recording = try #require(made.players.last), tab = try #require(made.tabs.last)
        m.toggle()
        #expect(!tab.asked)
        recording.position = 1.5
        m.metronome(true)
        #expect(tab.asked && tab.metronome && !tab.notes && tab.seeks.last == 1.5)
        m.metronome(false)
        #expect(!tab.asked && recording.asked && m.playing)
        // The recording stopping stops the beats.
        m.metronome(true)
        recording.pause()
        #expect(!m.playing && !tab.asked)
    }

    @Test func theDevicesSoundIsReadiedBeforeAnythingPlays() async throws {
        // On an iPhone: the audio session set for playing, so the silent switch and a locked phone do not mute it.
        let m = model()
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil, tab: source)
        await m.settled()
        m.toggle()
        #expect(m.playing && made.readied == [false])
        m.toggle()
        m.countIn(true)
        m.toggle()
        #expect(m.counting && made.readied == [false, false])
    }

    @Test func whileTheTabsSoundIsMadeNothingPlaysAndASoundMadeTooLateGoes() async throws {
        let made = made
        var finish: [CheckedContinuation<Void, Never>] = []
        let m = PracticeModel(recordings: dir.file("recordings"), places: dir.file("places"), choices: UserDefaults(suiteName: suite)!,
                              makePlayer: { file, listener in FakePlayer(file: file, listener: listener) },
                              makeTabPlayer: { _, program, listener in
                                  await withCheckedContinuation { finish.append($0) }
                                  let t = FakeTabSound(program: program, listener: listener)
                                  made.tabs.append(t)
                                  return t
                              })
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil, tab: source)
        while finish.isEmpty { await Task.yield() }
        #expect(m.tabSoundLoading && !m.tabSound && !m.tabSoundFailed)
        // The same page again while it is made makes no second one.
        m.open(song: "song", job: "job-1", clock: clock, inHand: nil, tab: source)
        for _ in 0..<20 { await Task.yield() }
        #expect(finish.count == 1)
        finish.removeFirst().resume()
        await m.settled()
        #expect(!m.tabSoundLoading && m.tabSound && m.canPlay && made.tabs.count == 1)
        // Another song while the sound is made: the late one is let go.
        m.open(song: "other", job: "job-2", clock: clock, inHand: nil, tab: TabSoundSource(index: index, program: EngineTabSoundPlayer.steel))
        while finish.isEmpty { await Task.yield() }
        m.leave()
        finish.removeFirst().resume()
        for _ in 0..<20 { await Task.yield() }
        #expect(made.tabs.count == 2 && made.tabs[1].released && !m.tabSound && !m.tabSoundLoading)
    }

    @Test func theRecordingPlayedWhileTheTabsSoundIsMadeIsJoinedByIt() async throws {
        var finish: [CheckedContinuation<Void, Never>] = []
        var recordings: [FakePlayer] = [], tabs: [FakeTabSound] = []
        let choices = UserDefaults(suiteName: suite)!
        choices.set(PracticeSound.both.rawValue, forKey: PracticeModel.soundKey)
        let m = PracticeModel(recordings: dir.file("recordings"), places: dir.file("places"), choices: choices,
                              makePlayer: { file, listener in let p = FakePlayer(file: file, listener: listener); recordings.append(p); return p },
                              makeTabPlayer: { _, program, listener in
                                  await withCheckedContinuation { finish.append($0) }
                                  let t = FakeTabSound(program: program, listener: listener)
                                  tabs.append(t)
                                  return t
                              })
        m.open(song: "song", job: "job-1", clock: clock, inHand: take(), tab: source)
        while finish.isEmpty || recordings.isEmpty { await Task.yield() }
        for _ in 0..<20 { await Task.yield() }
        // Played while the tab's sound is made: the recording alone.
        m.toggle()
        let recording = try #require(recordings.last)
        #expect(m.playing && recording.asked && m.tabSoundLoading)
        recording.position = 1.5
        finish.removeFirst().resume()
        await m.settled()
        // Both were chosen: the tab's sound joins where the recording is.
        let tab = try #require(tabs.last)
        #expect(m.tabSound && tab.asked && tab.notes && tab.seeks.last == 1.5)
    }
}

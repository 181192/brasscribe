import Foundation
import Testing
@testable import TabKit

/// The beats saved with a song (composition.json), as far as the clock reads them.
struct SavedSong: Decodable {
    struct Voice: Decodable { struct Note: Decodable { let start: Int }; let notes: [Note] }
    let voices: [Voice]
    let beat_times: [Double]
    let first_downbeat: Int
    let ticks_per_beat: Int

    var beats: SavedBeats {
        SavedBeats(beatTimes: beat_times, firstDownbeat: first_downbeat, ticksPerBeat: ticks_per_beat,
                   startTick: voices.flatMap(\.notes).map(\.start).min() ?? 0)
    }
}

func near(_ a: Double, _ b: Double, _ within: Double = 1e-9) -> Bool { abs(a - b) <= within }

/// Where the tab is at a second of the recording (`TabClock`), on the recorded fixture
/// (apps/fixtures/bass-line: 15 bars of two-four, the beats as the computer tracked them) and on the
/// hand-written probes (a pickup, six-eight).
struct TabClockTests {
    func tab(_ name: String) throws -> (TabIndex, TabData) {
        (TabIndex.parse(musicXML: try fixtureText("\(name)/tab.musicxml")), try fixtureTab(name))
    }

    @Test func theBarsStartOnTheBeatsTheComputerTracked() throws {
        let (index, tab) = try tab("bass-line")
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        #expect(index.bars == clock.bars)
        #expect(index.measures.first?.beats == 2)
        // Two quarter notes to a bar: bar n starts on the tracked beat 2n.
        for bar in 0..<clock.bars {
            let beat = 2 * bar
            if beat < tab.beatTimes.count { #expect(near(tab.beatTimes[beat], clock.secondsAt(bar)), "bar \(bar)") }
            #expect(TabPlace(bar: bar, tick: 0) == clock.placeAt(clock.secondsAt(bar)))
        }
        // The tracked beats are not evenly spaced (0.6, 1.2, 1.8, 2.4, 2.98, 3.6 …): the fifth beat is its own second, not a steady 3.0.
        #expect(near(2.98, clock.secondsAt(2)))
        #expect(near(2.98, clock.secondsAt(1, tick: 2 * TabIndex.ticks)))
        // Half way between two beats is half way through the quarter note.
        #expect(TabPlace(bar: 1, tick: TabIndex.ticks + TabIndex.ticks / 2) == clock.placeAt((2.4 + 2.98) / 2))
    }

    @Test func beforeTheFirstBarAndAfterTheLastTheTabIsAtItsEnds() throws {
        let (index, tab) = try tab("bass-line")
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        // The recording starts 0.6 s before the first bar.
        #expect(TabPlace(bar: 0, tick: 0) == clock.placeAt(0))
        #expect(TabPlace(bar: clock.bars - 1, tick: index.measures.last!.length) == clock.placeAt(clock.end + 5))
        // Past the last tracked beat time runs on as between the last two.
        let last = tab.beatTimes.count - 1
        let step = tab.beatTimes[last] - tab.beatTimes[last - 1]
        #expect(near(tab.beatTimes[last] + step, clock.secondsAt(0, tick: (last + 1) * TabIndex.ticks)))
    }

    @Test func theBeatOfTheBarIsCountedByTheTimeSignature() throws {
        let (index, tab) = try tab("bass-line")
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        #expect(clock.beatAt(TabPlace(bar: 3, tick: 0)) == 1)
        #expect(clock.beatAt(TabPlace(bar: 3, tick: TabIndex.ticks - 1)) == 1)
        #expect(clock.beatAt(TabPlace(bar: 3, tick: TabIndex.ticks)) == 2)
        // The end of the last bar is still its last beat.
        #expect(clock.beatAt(TabPlace(bar: clock.bars - 1, tick: 2 * TabIndex.ticks)) == 2)
        let (six, sixTab) = try self.tab("tab-probes/six-eight")
        let eighths = try #require(TabClock.of(six, tab: sixTab, saved: nil))
        #expect(six.measures.first?.beats == 6)
        #expect(six.measures.first?.length == 3 * TabIndex.ticks)
        #expect(eighths.beatAt(TabPlace(bar: 0, tick: 3 * TabIndex.ticks / 2)) == 4)
        // A bar of six-eight is three tracked beats (quarter notes) long.
        #expect(near(sixTab.beatTimes[3], eighths.secondsAt(1)))
    }

    @Test func aPickupIsTheFirstBarAndEndsOnTheFirstDownbeat() throws {
        let (index, tab) = try tab("tab-probes/pickup")
        #expect(index.measures.first?.pickup == true)
        #expect(index.measures.first?.length == TabIndex.ticks)
        #expect(TabClock.leadOf(index, tab: tab, saved: nil) == TabIndex.ticks)
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        // The first full bar starts on the first downbeat; the pickup's quarter note is one beat before it.
        #expect(near(tab.beatTimes[tab.firstDownbeat], clock.secondsAt(1)))
        #expect(near(tab.beatTimes[0] - (tab.beatTimes[1] - tab.beatTimes[0]), clock.secondsAt(0)))
        #expect(TabPlace(bar: 0, tick: 0) == clock.placeAt(clock.secondsAt(0)))
        // The pickup's one beat is the fourth of the bar it leads into.
        #expect(clock.beatAt(TabPlace(bar: 0, tick: 0)) == 4)
        // Without the tab's data the pickup is read from the page alone.
        #expect(TabClock.leadOf(index, tab: nil, saved: nil) == TabIndex.ticks)
    }

    @Test func aSavedSongHasTheSameClockFromItsSavedNotes() throws {
        let (index, tab) = try tab("bass-line")
        let saved = try JSONDecoder().decode(SavedSong.self, from: try fixture("bass-line/composition.json")).beats
        let fromTab = try #require(TabClock.of(index, tab: tab, saved: nil))
        let fromSaved = try #require(TabClock.of(index, tab: nil, saved: saved))
        for bar in 0...fromTab.bars { #expect(near(fromTab.secondsAt(bar), fromSaved.secondsAt(bar))) }
        // Neither: there is nothing to follow the recording by.
        #expect(TabClock.of(index, tab: nil, saved: nil) == nil)
        #expect(TabClock.of(TabIndex.parse(musicXML: "<not-a-score/>"), tab: tab, saved: nil) == nil)
    }

    @Test func aSavedSongThatStartsBeforeTheFirstDownbeatStartsABarEarlier() {
        let page = [TabMeasure(number: "1", length: 4 * TabIndex.ticks, beats: 4, beatTicks: TabIndex.ticks),
                    TabMeasure(number: "2", length: 4 * TabIndex.ticks, beats: 4, beatTicks: TabIndex.ticks)]
        let index = TabIndex(pieces: [], noPlace: [], bars: 2, staves: 1, tabStaff: 0, header: nil, measures: page)
        // A note a beat before tick 0, and the page writes a whole bar before the first downbeat.
        let saved = SavedBeats(beatTimes: [1, 2, 3, 4, 5, 6, 7, 8], firstDownbeat: 1, ticksPerBeat: 24, startTick: -24)
        #expect(TabClock.leadOf(index, tab: nil, saved: saved) == 4 * TabIndex.ticks)
        #expect(TabClock.of(index, tab: nil, saved: saved).map { near($0.secondsAt(1), 2) } == true)
    }

    @Test func aRepeatCoversItsBarsFromLineToLine() throws {
        let (index, tab) = try tab("bass-line")
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        let span = clock.span(RepeatBars(first: 2, last: 3))
        #expect(near(clock.secondsAt(2), span.lowerBound))
        #expect(near(clock.secondsAt(4), span.upperBound))
        #expect(near(clock.end, clock.span(RepeatBars(first: 0, last: clock.bars - 1)).upperBound))
    }

    @Test func theSpeedMovesInStepsOfFiveAndStopsAtItsEnds() {
        #expect(PracticeSpeed.slower(100) == 95)
        #expect(PracticeSpeed.faster(100) == 105)
        #expect(PracticeSpeed.slower(PracticeSpeed.min) == PracticeSpeed.min)
        #expect(PracticeSpeed.faster(PracticeSpeed.max) == PracticeSpeed.max)
    }

    /// A page of `bars` full bars of `beats` over `unit`, as the clock needs it.
    func measures(_ bars: Int, beats: Int = 4, unit: Int = 4) -> [TabMeasure] {
        (0..<bars).map { TabMeasure(number: String($0 + 1), length: beats * TabIndex.ticks * 4 / unit, beats: beats, beatTicks: TabIndex.ticks * 4 / unit) }
    }

    @Test func aTempoChangeIsFollowedBeatByBeat() {
        // Four beats at 120 a minute, then four at 60: the second bar is twice as long as the first.
        let beats = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0]
        let clock = TabClock(beatTimes: beats, firstDownbeat: 0, measures: measures(2), lead: 0)
        #expect(near(1.0, clock.secondsAt(0)))
        #expect(near(3.0, clock.secondsAt(1)))
        #expect(near(7.0, clock.end))
        // Half a second into each bar: the second beat of the first, half way through the first beat of the second.
        #expect(TabPlace(bar: 0, tick: TabIndex.ticks) == clock.placeAt(1.5))
        #expect(TabPlace(bar: 1, tick: TabIndex.ticks / 2) == clock.placeAt(3.5))
        #expect(clock.beatAt(clock.placeAt(3.9)) == 1)
        #expect(clock.beatAt(clock.placeAt(4.0)) == 2)
        // There and back, all the way through.
        for bar in 0...1 {
            for tick in stride(from: 0, to: 4 * TabIndex.ticks, by: 97) {
                #expect(TabPlace(bar: bar, tick: tick) == clock.placeAt(clock.secondsAt(bar, tick: tick)))
            }
        }
    }

    @Test func aTabLongerThanItsTrackedBeatsRunsOnAtTheLastTempo() {
        // Six beats were tracked, and the page has four bars of four: the bars past them are where the last tempo puts them.
        let beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.1]
        let clock = TabClock(beatTimes: beats, firstDownbeat: 0, measures: measures(4), lead: 0)
        #expect(near(2.5, clock.secondsAt(1)))
        #expect(near(3.1 + 3 * 0.6, clock.secondsAt(2)))
        #expect(near(3.1 + 11 * 0.6, clock.end))
        #expect(TabPlace(bar: 3, tick: 0) == clock.placeAt(clock.secondsAt(3)))
        // A repeat of bars past the end of a recording of 4 seconds has nothing to play, and is not turned back to.
        #expect(turnsBack(clock.span(RepeatBars(first: 1, last: 1)).lowerBound, duration: 4))
        #expect(!turnsBack(clock.span(RepeatBars(first: 2, last: 3)).lowerBound, duration: 4))
        #expect(!turnsBack(4.98, duration: 5))
        // Before the recording has been read its length is not known: nothing is held back.
        #expect(turnsBack(100, duration: 0))
    }

    @Test func aJumpToABarIsInThatBarThoughPlayersCountInMilliseconds() {
        // Beats that fall between milliseconds: 0.1234567 s apart.
        let beats = (0..<40).map { 0.3333333 + Double($0) * 0.1234567 }
        let clock = TabClock(beatTimes: beats, firstDownbeat: 0, measures: measures(9), lead: 0)
        for bar in 0..<clock.bars {
            let ms = TabClock.millisAt(clock.secondsAt(bar))
            #expect(clock.placeAt(Double(ms) / 1000).bar == bar, "bar \(bar) at \(ms) ms")
            #expect(Double(ms) / 1000 - clock.secondsAt(bar) < 0.001)
        }
        // A second that is a whole millisecond stays where it is.
        #expect(TabClock.millisAt(2.98) == 2980)
        #expect(TabClock.millisAt(0.6) == 600)
        #expect(TabClock.millisAt(-0.2) == 0)
    }

    /// Every note is, by the clock, at the second the tab's own ticks put it: the tracked beat `first_downbeat + start / ticks_per_beat`.
    func everyNoteIsAtItsOwnSecond(_ name: String) throws {
        let (index, tab) = try tab(name)
        let clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        func byTicks(_ start: Int) -> Double {
            let beat = Double(start) / Double(tab.ticksPerBeat) + Double(tab.firstDownbeat)
            let step = tab.beatTimes[1] - tab.beatTimes[0]
            if beat < 0 { return tab.beatTimes[0] + beat * step }
            let i = min(Int(beat), tab.beatTimes.count - 2)
            return tab.beatTimes[i] + (beat - Double(i)) * (tab.beatTimes[i + 1] - tab.beatTimes[i])
        }
        var checked = 0
        var moved = 0
        for piece in index.pieces where piece.first && piece.staff == index.markStaff {
            let note = tab.notes[piece.note]
            // A note moved to the grid is written a little off its tick; the others are exactly there.
            if abs(byTicks(note.start) - clock.secondsAt(piece.bar, tick: piece.onset)) > 1e-6 { moved += 1 }
            checked += 1
        }
        #expect(checked > 0, "\(name): notes checked")
        #expect(moved <= tab.adjustedNotes, "\(name): notes not at their second (\(moved) of \(checked)), beyond the ones the page says it moved")
    }

    @Test(arguments: ["bass-line", "bass-line-marks", "tab-probes/six-eight", "tab-probes/pickup", "tab-probes/triplets",
                      "tab-probes/tie-over-the-bar", "tab-probes/chords", "tab-probes/capo"])
    func everyNoteIsAtItsOwnSecondInEveryMetre(name: String) throws {
        try everyNoteIsAtItsOwnSecond(name)
    }

    @Test func eachBarOfSixEightIsThreeTrackedBeats() throws {
        // One step of the tracked beats is a written quarter in six-eight too, so a bar is three steps.
        let (six, sixTab) = try tab("tab-probes/six-eight")
        let clock = try #require(TabClock.of(six, tab: sixTab, saved: nil))
        // The first note of each bar of six-eight is three quarter notes after the first of the bar before.
        let firsts = six.pieces.filter { $0.first && $0.onset == 0 && $0.staff == six.markStaff }
        #expect(firsts.count >= 2)
        for p in firsts {
            #expect(sixTab.notes[p.note].start == 3 * p.bar * TabIndex.ticks / (TabIndex.ticks / sixTab.ticksPerBeat))
            #expect(near(sixTab.beatTimes[3 * p.bar + sixTab.firstDownbeat], clock.secondsAt(p.bar)))
        }
    }
}

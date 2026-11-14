import Foundation
import Testing
@testable import TabKit

/// Voices that sound nothing and write down when each note was struck and let go, in frames rendered.
final class HeardVoices: TabVoices {
    var base = 0
    var on: [(frame: Int, pitch: Int)] = []
    var off: [(frame: Int, pitch: Int)] = []
    var silenced = 0
    func on(_ pitch: Int, at frame: Int) { on.append((base + frame, pitch)) }
    func off(_ pitch: Int, at frame: Int) { off.append((base + frame, pitch)) }
    func silence() { silenced += 1 }
}

/// The tab's own sound (`TabSoundScore`, `TabSynth`) on the recorded fixture (apps/fixtures/bass-line): every note
/// sounds at the second the recording plays it, at any speed, with a bar counted in, the beats ticking, and over a
/// stretch again and again.
struct TabSoundTests {
    let rate = 8_000.0
    let index: TabIndex
    let tab: TabData
    let clock: TabClock
    let score: TabSoundScore

    init() throws {
        index = TabIndex.parse(musicXML: try fixtureText("bass-line/tab.musicxml"))
        tab = try fixtureTab("bass-line")
        clock = try #require(TabClock.of(index, tab: tab, saved: nil))
        score = TabSoundScore.of(index, clock: clock)
    }

    /// Renders `seconds` of sound and gives it back, one channel.
    func play(_ synth: TabSynth, _ voices: HeardVoices, _ seconds: Double) -> [Float] {
        let frames = Int(seconds * rate)
        var left = [Float](repeating: 0, count: frames)
        var right = [Float](repeating: 0, count: frames)
        left.withUnsafeMutableBufferPointer { l in
            right.withUnsafeMutableBufferPointer { r in _ = synth.render(frames: frames, left: l.baseAddress!, right: r.baseAddress!) }
        }
        voices.base += frames
        return left
    }

    /// The frames a click starts at: where the sound comes up from silence.
    func clicks(_ sound: [Float], over level: Float = 0.05) -> [Int] {
        var starts: [Int] = []
        var quietSince = -Int(rate)
        for (i, v) in sound.enumerated() where abs(v) > level {
            if i - quietSince > Int(rate) / 50 { starts.append(i) }
            quietSince = i
        }
        return starts
    }

    @Test func everyNoteOfThePageSoundsWhereTheRecordingPlaysIt() {
        #expect(score.notes.count == tab.notes.count)
        #expect(score.notes.allSatisfy { $0.end > $0.start })
        #expect(score.notes.map(\.pitch).sorted() == tab.notes.map(\.pitch).sorted())
        #expect(score.notes.first.map { $0.start >= clock.secondsAt(0) } == true)
        // A beat for each of the two beats of every bar, the first of each marked.
        #expect(score.beats.count == 2 * clock.bars)
        #expect(near(score.beats[6].at, clock.secondsAt(3)))
        #expect(score.beats[6].first && !score.beats[7].first)
        #expect(score.end == clock.end)
    }

    @Test func aBarOfSixEightIsCountedInTwo() throws {
        let six = TabIndex.parse(musicXML: try fixtureText("tab-probes/six-eight/tab.musicxml"))
        let eighths = try #require(TabClock.of(six, tab: try fixtureTab("tab-probes/six-eight"), saved: nil))
        let measure = eighths.measure(0)
        #expect(measure.beats == 6)
        // Two dotted quarters: the first and the fourth eighth, the first of the bar marked.
        #expect(TabSoundScore.counted(measure) == (2, 3 * TabIndex.ticks / 2))
        let beats = TabSoundScore.of(six, clock: eighths).beats
        #expect(beats.count == 2 * eighths.bars)
        #expect(near(beats[1].at, eighths.secondsAt(0, tick: 3 * TabIndex.ticks / 2)))
        #expect(beats.prefix(4).map(\.first) == [true, false, true, false])
        #expect(TabSoundScore.counted(TabMeasure(number: "1", length: 4 * TabIndex.ticks, beats: 4, beatTicks: TabIndex.ticks)) == (4, TabIndex.ticks))
    }

    @Test func theNotesAreStruckOnTimeAndTwiceAsLateAtHalfSpeed() {
        for speed in [1.0, 0.5] {
            let voices = HeardVoices()
            let synth = TabSynth(score: score, voices: voices, sampleRate: rate)
            synth.speed = speed
            _ = play(synth, voices, score.end / speed + 1)
            #expect(voices.on.count == score.notes.count)
            for (struck, note) in zip(voices.on, score.notes) {
                #expect(struck.pitch == note.pitch)
                #expect(near(Double(struck.frame) / rate, note.start / speed, 2 * Double(TabSynth.block) / rate), "at speed \(speed)")
            }
            #expect(voices.off.count == score.notes.count)
            #expect(synth.ended)
        }
    }

    @Test func aBarIsCountedInBeforeTheSongMoves() {
        let voices = HeardVoices()
        let synth = TabSynth(score: score, voices: voices, sampleRate: rate)
        let from = clock.secondsAt(2)
        synth.seek(from)
        synth.countIn(beats: 2, beatSeconds: 0.5)
        #expect(synth.countingIn)
        let sound = play(synth, voices, 0.99)
        // Two clicks half a second apart, and the song has not moved nor sounded a note.
        #expect(clicks(sound, over: 0.02).map { (Double($0) / rate * 100).rounded() / 100 } == [0, 0.5])
        #expect(synth.position == from)
        #expect(voices.on.isEmpty)
        _ = play(synth, voices, 0.5)
        #expect(!synth.countingIn)
        #expect(near(synth.position, from + 0.49, 0.02))
        #expect(!voices.on.isEmpty)
    }

    @Test func theMetronomeTicksOnEveryBeatAndTheNotesCanBeLeftOut() {
        let voices = HeardVoices()
        let synth = TabSynth(score: score, voices: voices, sampleRate: rate)
        synth.metronome = true
        synth.notes = false
        let ticks = clicks(play(synth, voices, score.end), over: 0.02).map { Double($0) / rate }
        #expect(ticks.count == score.beats.count)
        for (tick, beat) in zip(ticks, score.beats) { #expect(near(tick, beat.at, 0.02)) }
        #expect(voices.on.isEmpty)
        // Without the metronome and the notes nothing sounds.
        let quiet = TabSynth(score: score, voices: HeardVoices(), sampleRate: rate)
        quiet.notes = false
        #expect(play(quiet, HeardVoices(), score.end).allSatisfy { $0 == 0 })
    }

    @Test func aStretchTurnsBackToItsStartWithItsNotesStruckAgain() {
        let voices = HeardVoices()
        let synth = TabSynth(score: score, voices: voices, sampleRate: rate)
        let stretch = clock.span(RepeatBars(first: 1, last: 2))
        let inIt = score.notes.filter { $0.start >= stretch.lowerBound && $0.start < stretch.upperBound }.count
        #expect(inIt > 0)
        synth.repeatSpan = stretch
        synth.seek(stretch.lowerBound)
        _ = play(synth, voices, (stretch.upperBound - stretch.lowerBound) * 2.5)
        #expect(synth.turns == 2)
        #expect(stretch.contains(synth.position))
        #expect(!synth.ended)
        #expect((2 * inIt...3 * inIt).contains(voices.on.count))
    }
}

/// A listener that writes down what it is told.
@MainActor
final class ToldListener: RecordingPlayerListener {
    var said: [String] = []
    func recordingPlaying(_ playing: Bool) { said.append(playing ? "playing" : "paused") }
    func recordingEnded() { said.append("ended") }
    func recordingFailed() { said.append("failed") }
}

/// The tab's sound through the device's sound engine (`EngineTabSoundPlayer`), rendered without a sound output: the
/// SoundFont alphaTab comes with has each program the app plays, a note sounds where it is written, and the clicks
/// are mixed in.
@MainActor
struct EngineTabSoundPlayerTests {
    let score = TabSoundScore(
        notes: [SoundNote(start: 0.5, end: 0.9, pitch: 40), SoundNote(start: 1.0, end: 1.4, pitch: 45)],
        beats: (0..<4).map { SoundBeat(at: Double($0) * 0.5, first: $0 % 2 == 0) },
        end: 2.0)

    func level(_ sound: ArraySlice<Float>) -> Double { (sound.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(max(sound.count, 1))).squareRoot() }

    @Test func theNotesSoundWhereTheyAreWrittenOnEveryProgram() throws {
        let font = try #require(EngineTabSoundPlayer.soundFont, "make alphatab puts the SoundFont in the package")
        for program in [EngineTabSoundPlayer.bass, EngineTabSoundPlayer.nylon, EngineTabSoundPlayer.steel] {
            let told = ToldListener()
            let p = try EngineTabSoundPlayer(score: score, program: program, soundFont: font, listener: told, offline: true)
            p.play()
            #expect(p.playing)
            let sound = try p.rendered(frames: 88_200)
            #expect(sound.count == 88_200)
            // Silence before the first note, sound in both notes.
            #expect(level(sound[0..<20_000]) < 1e-4, "program \(program)")
            #expect(level(sound[23_000..<38_000]) > 0.003, "program \(program): \(level(sound[23_000..<38_000]))")
            #expect(level(sound[45_000..<60_000]) > 0.003, "program \(program)")
            #expect(near(p.position, 2.0, 0.01))
            p.release()
        }
    }

    @Test func aFullChordWithAClickOverItGoesOutUnderFullScale() throws {
        // Six notes struck at once, on the first beat of a bar with the metronome on.
        let font = try #require(EngineTabSoundPlayer.soundFont)
        let chord = TabSoundScore(notes: (0..<6).map { SoundNote(start: 0.1, end: 1.0, pitch: 40 + 5 * $0) }, beats: [SoundBeat(at: 0.1, first: true)], end: 1.0)
        for program in [EngineTabSoundPlayer.steel, EngineTabSoundPlayer.bass] {
            let p = try EngineTabSoundPlayer(score: chord, program: program, soundFont: font, listener: ToldListener(), offline: true)
            p.metronome = true
            p.play()
            let sound = try p.rendered(frames: 44_100)
            let peak = sound.map { abs($0) }.max() ?? 0
            #expect(peak > 0.05, "program \(program) sounds (\(peak))")
            #expect(peak < 0.9, "program \(program) peaks at \(peak)")
            p.release()
        }
    }

    @Test func theMetronomeIsMixedInAndTheNotesCanBeLeftOut() throws {
        let font = try #require(EngineTabSoundPlayer.soundFont)
        let p = try EngineTabSoundPlayer(score: score, program: EngineTabSoundPlayer.bass, soundFont: font, listener: ToldListener(), offline: true)
        p.notes = false
        p.metronome = true
        p.play()
        let sound = try p.rendered(frames: 88_200)
        for beat in 0..<4 {
            let at = beat * 22_050
            #expect(level(sound[at..<(at + 1_000)]) > 0.01, "beat \(beat)")
            #expect(level(sound[(at + 6_000)..<(at + 20_000)]) < 1e-4, "after beat \(beat)")
        }
        p.release()
    }

    @Test func itIsPausedWhereItIsAndCountsABarIn() throws {
        let font = try #require(EngineTabSoundPlayer.soundFont)
        let told = ToldListener()
        let p = try EngineTabSoundPlayer(score: score, program: EngineTabSoundPlayer.bass, soundFont: font, listener: told, offline: true)
        p.seek(to: 0.25)
        p.countIn(beats: 2, beatSeconds: 0.25)
        p.play()
        #expect(p.countingIn)
        _ = try p.rendered(frames: 11_025)
        #expect(p.countingIn && p.position == 0.25)
        _ = try p.rendered(frames: 22_050)
        #expect(!p.countingIn)
        #expect(near(p.position, 0.5, 0.01))
        p.pause()
        let at = p.position
        _ = try p.rendered(frames: 4_410)
        #expect(p.position == at && !p.playing)
        #expect(told.said == ["playing", "paused"])
        p.release()
    }
}

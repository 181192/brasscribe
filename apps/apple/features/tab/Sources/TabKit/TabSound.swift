import Foundation

/// A note of the tab as it sounds: from `start` to `end`, in seconds of the recording, at the MIDI `pitch`.
public struct SoundNote: Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var pitch: Int
    public init(start: Double, end: Double, pitch: Int) { self.start = start; self.end = end; self.pitch = pitch }
}

/// A beat of the metronome, at `at` seconds of the recording; `first` is the first beat of its bar.
public struct SoundBeat: Equatable, Sendable {
    public var at: Double
    public var first: Bool
    public init(at: Double, first: Bool) { self.at = at; self.first = first }
}

/// The tab as sound, on the recording's own time: every note starts where the recording plays it, because
/// both are placed by the beats the computer tracked (`TabClock`). So the tab's sound, the metronome and
/// the recording can play together, and one cursor follows all three.
public struct TabSoundScore: Equatable, Sendable {
    public var notes: [SoundNote]
    public var beats: [SoundBeat]
    public var end: Double

    public init(notes: [SoundNote], beats: [SoundBeat], end: Double) { self.notes = notes; self.beats = beats; self.end = end }

    /// A grace note is written without a length: it sounds for a moment.
    private static let graceSeconds = 0.08

    /// The notes the page writes on the staff its marks stand on, and a beat for every beat of every bar.
    public static func of(_ index: TabIndex, clock: TabClock) -> TabSoundScore {
        var byNote: [Int: [TabPiece]] = [:]
        var order: [Int] = []
        for p in index.pieces where p.staff == index.markStaff && p.bar < clock.bars {
            if byNote[p.note] == nil { order.append(p.note) }
            byNote[p.note, default: []].append(p)
        }
        var notes: [SoundNote] = order.map { note in
            let pieces = byNote[note]!
            let first = pieces.first(where: \.first) ?? pieces[0]
            let start = clock.secondsAt(first.bar, tick: first.onset)
            let end = pieces.map { clock.secondsAt($0.bar, tick: $0.onset + $0.length) }.max() ?? start
            return SoundNote(start: start, end: max(end, start + graceSeconds), pitch: first.pitch)
        }
        notes.sort { $0.start < $1.start }
        var beats: [SoundBeat] = []
        for bar in 0..<clock.bars {
            let m = clock.measure(bar)
            let (count, ticks) = counted(m)
            // A pickup holds the last beats of a bar: its beats are counted back from its end.
            let before = m.pickup ? m.beats * m.beatTicks - m.length : 0
            for beat in 0..<count {
                let tick = beat * ticks - before
                if tick >= 0 { beats.append(SoundBeat(at: clock.secondsAt(bar, tick: tick), first: beat == 0)) }
            }
        }
        return TabSoundScore(notes: notes, beats: beats, end: clock.end)
    }

    /// How a bar of `measure` is counted: how many beats, and how long each is in `TabIndex.ticks`. A bar written in
    /// eighths in threes (six-eight, nine-eight, twelve-eight) is counted in its dotted quarters: two, three or four.
    public static func counted(_ measure: TabMeasure) -> (beats: Int, ticks: Int) {
        if measure.beatTicks < TabIndex.ticks && measure.beats >= 6 && measure.beats % 3 == 0 { return (measure.beats / 3, 3 * measure.beatTicks) }
        return (measure.beats, measure.beatTicks)
    }
}

/// The instrument's voices: what sounds a note. `frame` is how far into the sound being rendered the note
/// starts or stops. Used from the thread that renders the sound.
public protocol TabVoices: AnyObject {
    func on(_ pitch: Int, at frame: Int)
    func off(_ pitch: Int, at frame: Int)
    /// Every note stops at once: the song jumped.
    func silence()
}

/// Plays a `TabSoundScore`: the notes through its voices and the metronome's beats as short clicks, at any
/// speed (a slower song has the same notes, later), over a stretch again and again, and after a count-in
/// of one bar. It renders the clicks a block at a time and keeps the second of the recording it is at, so what
/// hears it (a device's sound output, or a test) decides when. Used from one thread at a time; it allocates
/// nothing while it renders.
public final class TabSynth {
    /// Frames rendered at a time: a note starts within a thousandth or two of a second of its place.
    public static let block = 64
    private static let clickSeconds = 0.05
    /// A click's peak: with the notes 6 dB down beside it, a full chord and a click have room under full scale.
    private static let clickLevel = 0.25

    private struct Event { var at: Double; var pitch: Int; var on: Bool }

    private let score: TabSoundScore
    private let voices: any TabVoices
    private let sampleRate: Double
    private let events: [Event]
    private var nextEvent = 0
    private var nextBeat = 0
    private var sounding = [Bool](repeating: false, count: 128)
    private let high: [Float]
    private let low: [Float]
    /// The clicks sounding now: the higher one or not, and how far into its wave (negative: it starts later in the block).
    private var clicks: [(high: Bool, from: Int)] = []
    /// A count-in under way: the frames until each of its beats and, last, until the song starts.
    private var counting: [Int]?
    private var countFrame = 0

    /// The second of the recording the sound is at.
    public private(set) var position = 0.0
    /// 1 is the recording's own speed.
    public var speed = 1.0
    /// The notes sound.
    public var notes = true { didSet { if oldValue && !notes { quiet() } } }
    /// The metronome sounds.
    public var metronome = false
    /// The stretch to play again and again, in seconds; nil plays on to the end.
    public var repeatSpan: ClosedRange<Double>?
    /// Times the stretch has turned back to its start.
    public private(set) var turns = 0
    /// How many turns there were when the song was last moved.
    public private(set) var turnsAtJump = 0

    public init(score: TabSoundScore, voices: any TabVoices, sampleRate: Double) {
        self.score = score
        self.voices = voices
        self.sampleRate = sampleRate
        // A note's end comes before another note's start at the same moment: a repeated note is struck again.
        events = score.notes.flatMap { [Event(at: $0.start, pitch: $0.pitch, on: true), Event(at: $0.end, pitch: $0.pitch, on: false)] }
            .sorted { $0.at != $1.at ? $0.at < $1.at : (!$0.on && $1.on) }
        high = Self.click(1760, sampleRate)
        low = Self.click(1320, sampleRate)
        clicks.reserveCapacity(64)
    }

    /// Counting in: the song has not started to move yet.
    public var countingIn: Bool { counting != nil }

    /// The end of the tab has been reached (with nothing to repeat).
    public var ended: Bool { repeatSpan == nil && position >= score.end }

    public func seek(_ seconds: Double) {
        turnsAtJump = turns
        move(seconds)
    }

    private func move(_ seconds: Double) {
        quiet()
        counting = nil
        position = max(seconds, 0)
        nextEvent = events.firstIndex { $0.at >= position } ?? events.count
        nextBeat = score.beats.firstIndex { $0.at >= position } ?? score.beats.count
    }

    /// `beats` clicks, `beatSeconds` apart at the speed it plays at, before the song moves on from where it is.
    public func countIn(beats: Int, beatSeconds: Double) {
        let step = max(Int(beatSeconds / speed * sampleRate), 1)
        counting = (0...max(beats, 1)).map { $0 * step }
        countFrame = 0
    }

    private func quiet() {
        voices.silence()
        for i in sounding.indices { sounding[i] = false }
    }

    /// Adds `frames` frames of clicks to `left` and `right`, tells the voices what starts and stops in them, and
    /// moves on by them. False once the tab's end is reached.
    public func render(frames: Int, left: UnsafeMutablePointer<Float>, right: UnsafeMutablePointer<Float>) -> Bool {
        var at = 0
        while at < frames {
            let block = min(Self.block, frames - at)
            if let count = counting {
                for i in 0..<(count.count - 1) where count[i] >= countFrame && count[i] < countFrame + block {
                    clicks.append((high: i == 0, from: countFrame - count[i]))
                }
                countFrame += block
                if countFrame >= count[count.count - 1] { counting = nil }
            } else if ended {
                // What still sounds is let go, and rings out.
                for p in sounding.indices where sounding[p] { voices.off(p, at: at); sounding[p] = false }
            } else {
                let again = repeatSpan
                let until = position + Double(block) / sampleRate * speed
                // Nothing past the end of the stretch is struck: the first note of the bar after it is not part of it.
                let within = again.map { min(until, $0.upperBound) } ?? until
                while nextEvent < events.count && events[nextEvent].at < within {
                    let e = events[nextEvent]
                    nextEvent += 1
                    if !notes || e.pitch < 0 || e.pitch > 127 { continue }
                    if e.on { voices.on(e.pitch, at: at); sounding[e.pitch] = true }
                    else if sounding[e.pitch] { voices.off(e.pitch, at: at); sounding[e.pitch] = false }
                }
                while nextBeat < score.beats.count && score.beats[nextBeat].at < within {
                    if metronome { clicks.append((high: score.beats[nextBeat].first, from: 0)) }
                    nextBeat += 1
                }
                position = until
                if let again, position >= again.upperBound {
                    move(again.lowerBound)
                    turns += 1
                }
            }
            mix(left + at, right + at, block)
            at += block
        }
        return !ended
    }

    /// Adds the clicks that sound to the block, and moves them on.
    private func mix(_ left: UnsafeMutablePointer<Float>, _ right: UnsafeMutablePointer<Float>, _ frames: Int) {
        var i = 0
        while i < clicks.count {
            let (isHigh, from) = clicks[i]
            let wave = isHigh ? high : low
            var k = max(0, -from)
            while k < frames && from + k < wave.count {
                left[k] += wave[from + k]
                right[k] += wave[from + k]
                k += 1
            }
            if from + frames >= wave.count { clicks.remove(at: i) } else { clicks[i].from = from + frames; i += 1 }
        }
    }

    /// A short click: a tone that dies away in a few hundredths of a second.
    private static func click(_ hz: Double, _ sampleRate: Double) -> [Float] {
        (0..<Int(clickSeconds * sampleRate)).map { i in
            let t = Double(i) / sampleRate
            return Float(clickLevel * sin(2 * .pi * hz * t) * exp(-t / (clickSeconds / 5)))
        }
    }
}

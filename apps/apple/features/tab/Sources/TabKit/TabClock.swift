import Foundation

/// A place in the tab: the bar (counted from 0, as written) and how far into it, in `TabIndex.ticks` to a quarter note.
public struct TabPlace: Equatable, Hashable, Sendable {
    public var bar: Int
    public var tick: Int
    public init(bar: Int, tick: Int) { self.bar = bar; self.tick = tick }
}

/// Bars to play again and again, counted from 0 as written, both included.
public struct RepeatBars: Equatable, Hashable, Sendable {
    public var first: Int
    public var last: Int
    public init(first: Int, last: Int) { self.first = first; self.last = last }
}

/// The engine's tab.json, as far as the tab view reads it: the notes' starts and the recording's beats.
public struct TabData: Decodable, Sendable {
    public struct Note: Decodable, Sendable {
        /// Concert MIDI pitch, as written in the tab.
        public var pitch: Int
        /// Ticks from the first downbeat.
        public var start: Int
        /// Written duration in ticks.
        public var dur: Int
        /// 1 is the highest line of the tab; nil: the note has no place on the instrument.
        public var string: Int?
        public var fret: Int?
        /// 0 to 1; below the doubt threshold the note is one to check.
        public var confidence: Double

        public init(pitch: Int, start: Int, dur: Int, string: Int?, fret: Int?, confidence: Double = 1) {
            self.pitch = pitch; self.start = start; self.dur = dur; self.string = string; self.fret = fret; self.confidence = confidence
        }

        enum CodingKeys: String, CodingKey { case pitch, start, dur, string, fret, confidence }

        public init(from decoder: any Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            pitch = try c.decode(Int.self, forKey: .pitch)
            start = try c.decode(Int.self, forKey: .start)
            dur = try c.decode(Int.self, forKey: .dur)
            string = try c.decodeIfPresent(Int.self, forKey: .string)
            fret = try c.decodeIfPresent(Int.self, forKey: .fret)
            confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 1
        }
    }

    /// The instrument and tuning the tab was made for, e.g. bass-4-standard.
    public var preset: String
    /// In time order.
    public var notes: [Note]
    /// Seconds of beat 0, 1, 2 …
    public var beatTimes: [Double]
    /// Index into `beatTimes` of tick 0; negative when the line starts before the first tracked downbeat (a pickup).
    public var firstDownbeat: Int
    public var ticksPerBeat: Int
    /// Notes written at the nearest start or length a note value can spell; in tab.musicxml only, `notes` are unchanged.
    public var adjustedNotes: Int

    public init(preset: String, notes: [Note], beatTimes: [Double], firstDownbeat: Int, ticksPerBeat: Int = 24, adjustedNotes: Int = 0) {
        self.preset = preset; self.notes = notes; self.beatTimes = beatTimes; self.firstDownbeat = firstDownbeat
        self.ticksPerBeat = ticksPerBeat; self.adjustedNotes = adjustedNotes
    }

    enum CodingKeys: String, CodingKey {
        case preset, notes
        case beatTimes = "beat_times", firstDownbeat = "first_downbeat", ticksPerBeat = "ticks_per_beat", adjustedNotes = "adjusted_notes"
    }

    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        preset = try c.decode(String.self, forKey: .preset)
        notes = try c.decode([Note].self, forKey: .notes)
        beatTimes = try c.decode([Double].self, forKey: .beatTimes)
        firstDownbeat = try c.decode(Int.self, forKey: .firstDownbeat)
        ticksPerBeat = try c.decodeIfPresent(Int.self, forKey: .ticksPerBeat) ?? 24
        adjustedNotes = try c.decodeIfPresent(Int.self, forKey: .adjustedNotes) ?? 0
    }
}

/// The recording's beats as they were saved with the song's notes: what the clock needs when the tab's data is not at hand.
public struct SavedBeats: Equatable, Sendable {
    /// Seconds of beat 0, 1, 2 … of the recording.
    public var beatTimes: [Double]
    /// Index into `beatTimes` of tick 0.
    public var firstDownbeat: Int
    public var ticksPerBeat: Int
    /// The earliest note's start, in the song's ticks; 0 when none starts before tick 0.
    public var startTick: Int

    public init(beatTimes: [Double], firstDownbeat: Int, ticksPerBeat: Int, startTick: Int) {
        self.beatTimes = beatTimes; self.firstDownbeat = firstDownbeat; self.ticksPerBeat = ticksPerBeat; self.startTick = min(0, startTick)
    }
}

/// Where in the tab the recording is at any second, and the other way round. The computer tracked the
/// recording's beats (`beat_times`, with `first_downbeat` the one tick 0 falls on) and counts the notes'
/// ticks from them: one step of `beat_times` is `ticks_per_beat` ticks, which the page writes as a quarter
/// note in every time signature (a bar of six-eight is three steps; a song the computer hears in two with
/// its beats divided in three it writes in two-four). The page says how long each of its bars is. Between
/// two tracked beats time runs evenly, and before the first and after the last it runs as between the
/// nearest two, so a recording that speeds up or drags keeps its cursor on the note being played.
public struct TabClock: Sendable {
    private let beatTimes: [Double]
    private let firstDownbeat: Int
    private let measures: [TabMeasure]
    /// From the start of the first written bar to tick 0, in `TabIndex.ticks`: what a pickup holds, or the bars before the first downbeat.
    private let lead: Int
    /// Where each bar starts, from the start of the first, and where the last one ends.
    private let starts: [Int]

    public init(beatTimes: [Double], firstDownbeat: Int, measures: [TabMeasure], lead: Int) {
        precondition(beatTimes.count >= 2 && !measures.isEmpty)
        self.beatTimes = beatTimes
        self.firstDownbeat = firstDownbeat
        self.measures = measures
        self.lead = lead
        starts = Self.starts(of: measures)
    }

    private static func starts(of measures: [TabMeasure]) -> [Int] {
        var s = [0]
        for m in measures { s.append(s[s.count - 1] + m.length) }
        return s
    }

    public var bars: Int { measures.count }

    private func secondsOf(_ ticks: Int) -> Double {
        let beat = Double(ticks - lead) / Double(TabIndex.ticks) + Double(firstDownbeat)
        let last = beatTimes.count - 1
        if beat < 0 { return beatTimes[0] + beat * (beatTimes[1] - beatTimes[0]) }
        if beat >= Double(last) { return beatTimes[last] + (beat - Double(last)) * (beatTimes[last] - beatTimes[last - 1]) }
        let i = Int(beat.rounded(.down))
        return beatTimes[i] + (beat - Double(i)) * (beatTimes[i + 1] - beatTimes[i])
    }

    /// The second of the recording at `tick` of `bar`; a bar past the last is the end of the tab.
    public func secondsAt(_ bar: Int, tick: Int = 0) -> Double { secondsOf(starts[min(max(bar, 0), bars)] + tick) }

    /// The second the tab ends at.
    public var end: Double { secondsOf(starts[bars]) }

    /// The seconds `repeat` covers in the recording: from its first bar's line to the line after its last.
    public func span(_ bars: RepeatBars) -> ClosedRange<Double> { secondsAt(bars.first)...secondsAt(bars.last + 1) }

    /// Where the tab is at `seconds` of the recording: before the first bar is its start, after the last is the last bar's end.
    public func placeAt(_ seconds: Double) -> TabPlace {
        let last = beatTimes.count - 1
        let beat: Double
        if seconds < beatTimes[0] {
            beat = (seconds - beatTimes[0]) / (beatTimes[1] - beatTimes[0])
        } else if seconds >= beatTimes[last] {
            beat = Double(last) + (seconds - beatTimes[last]) / (beatTimes[last] - beatTimes[last - 1])
        } else {
            let i = min(max(Self.lastIndex(in: beatTimes, atOrBelow: seconds), 0), last - 1)
            beat = Double(i) + (seconds - beatTimes[i]) / (beatTimes[i + 1] - beatTimes[i])
        }
        // A thousandth of a tick over, so the second a bar starts at is in that bar.
        let ticks = Int(((beat - Double(firstDownbeat)) * Double(TabIndex.ticks) + Double(lead) + 0.001).rounded(.down))
        if ticks <= 0 { return TabPlace(bar: 0, tick: 0) }
        if ticks >= starts[bars] { return TabPlace(bar: bars - 1, tick: measures[bars - 1].length) }
        let bar = min(max(Self.lastIndex(in: starts, atOrBelow: ticks), 0), bars - 1)
        return TabPlace(bar: bar, tick: ticks - starts[bar])
    }

    /// The beat of its bar `place` is in, 1 the first.
    public func beatAt(_ place: TabPlace) -> Int { measures[min(max(place.bar, 0), bars - 1)].beatAt(place.tick) }

    /// The last index of sorted `values` whose value is at or below `x`; -1 when all are above it.
    private static func lastIndex<T: Comparable>(in values: [T], atOrBelow x: T) -> Int {
        var lo = 0, hi = values.count
        while lo < hi {
            let mid = (lo + hi) / 2
            if values[mid] <= x { lo = mid + 1 } else { hi = mid }
        }
        return lo - 1
    }

    /// `seconds` as the millisecond a player is sent to: the first whole one at or after it, so the place there
    /// is not before the place at `seconds` (a bar's line that falls between two milliseconds is reached, not
    /// stopped short of).
    public static func millisAt(_ seconds: Double) -> Int64 { max(Int64((seconds * 1000 - 1e-6).rounded(.up)), 0) }

    /// The clock of a tab: from the tab's data when the computer gave it, else from the beats saved with the
    /// song (the same beats). Nil when neither has the recording's beats, or the page has no bars.
    public static func of(_ index: TabIndex, tab: TabData?, saved: SavedBeats?) -> TabClock? {
        guard let beats = tab?.beatTimes ?? saved?.beatTimes else { return nil }
        if beats.count < 2 || index.measures.isEmpty || zip(beats, beats.dropFirst()).contains(where: { $1 <= $0 }) { return nil }
        return TabClock(beatTimes: beats, firstDownbeat: tab?.firstDownbeat ?? saved?.firstDownbeat ?? 0, measures: index.measures,
                        lead: leadOf(index, tab: tab, saved: saved))
    }

    /// How far the first written bar starts before tick 0. Read off the page where the tab's data is there:
    /// each note's start in the data against where its first piece is written, as most notes have it (a
    /// note moved to the grid is written a little off). Else by the rule the page is written by: a pickup
    /// shorter than a bar is the first measure, and a longer one starts on a bar line.
    public static func leadOf(_ index: TabIndex, tab: TabData?, saved: SavedBeats?) -> Int {
        let starts = starts(of: index.measures)
        if let tab, tab.ticksPerBeat > 0 {
            // Counted in the order they are first met, so a tie goes to the first.
            var counts: [Int: Int] = [:]
            var order: [Int] = []
            for p in index.pieces where p.first && p.staff == index.markStaff && p.bar < index.measures.count && p.note >= 0 && p.note < tab.notes.count {
                let lead = starts[p.bar] + p.onset - tab.notes[p.note].start * TabIndex.ticks / tab.ticksPerBeat
                if counts[lead] == nil { order.append(lead) }
                counts[lead, default: 0] += 1
            }
            var best: Int?
            for lead in order where best == nil || counts[lead]! > counts[best!]! { best = lead }
            if let best { return best }
        }
        guard let first = index.measures.first else { return 0 }
        if first.pickup { return first.length }
        let earliest = saved.flatMap { $0.ticksPerBeat > 0 ? $0.startTick * TabIndex.ticks / $0.ticksPerBeat : nil } ?? 0
        return earliest >= 0 ? 0 : (-earliest + first.length - 1) / first.length * first.length
    }
}

/// The speeds the recording is played at, in per cent of its own: steps of five, the pitch kept.
public enum PracticeSpeed {
    public static let min = 25
    public static let max = 150
    public static let step = 5
    public static let full = 100
    /// Slow enough to hear each note of a bar being checked: the bar of a doubtful note repeats at this speed (design/brands/fretscribe/flows.md).
    public static let slow = 60

    public static func slower(_ percent: Int) -> Int { Swift.max(percent - step, min) }
    public static func faster(_ percent: Int) -> Int { Swift.min(percent + step, max) }
}

/// A stretch that starts at `start` seconds can be played again when the recording, `duration` seconds long
/// (0 while that is not known), has reached its end: it starts before that end. A tab can be longer than its
/// recording, and a repeat of bars past the recording's end has nothing to play.
public func turnsBack(_ start: Double, duration: Double) -> Bool { duration <= 0 || start < duration - 0.05 }

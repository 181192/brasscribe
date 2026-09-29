import Foundation

/// A score read from MusicXML: the arranged parts as the musician sees and hears them.
/// Times are in `Score.ticksPerQuarter` ticks from the start of bar 1.
public struct Score: Sendable, Equatable {
    public static let ticksPerQuarter = 960

    public var title: String
    public var parts: [Part]
    public var measures: [Measure]
    /// Tempo changes (`<sound tempo>`), quarter notes per minute, sorted by tick; first at tick 0.
    public var tempos: [Tempo]
    /// Rehearsal marks and text directions such as "ad lib." and "a tempo", from the first part.
    public var directions: [Direction]

    public struct Tempo: Sendable, Equatable { public var tick: Int; public var bpm: Double }
    public struct Direction: Sendable, Equatable {
        public enum Kind: Sendable, Equatable { case rehearsal, words }
        public var tick: Int
        public var kind: Kind
        public var text: String
    }

    /// The tempo at the start (kept for callers that need one number).
    public var tempoBPM: Double { tempos.first?.bpm ?? 120 }

    public var endTick: Int { measures.last.map { $0.startTick + $0.lengthTicks } ?? 0 }
    public var durationSeconds: Double { seconds(atTick: endTick) }

    public init(title: String, parts: [Part], measures: [Measure], tempos: [Tempo], directions: [Direction] = []) {
        self.title = title; self.parts = parts; self.measures = measures
        self.tempos = tempos.isEmpty ? [Tempo(tick: 0, bpm: 120)] : tempos
        self.directions = directions
    }

    public init(title: String, parts: [Part], measures: [Measure], tempoBPM: Double) {
        self.init(title: title, parts: parts, measures: measures, tempos: [Tempo(tick: 0, bpm: tempoBPM)])
    }

    public func tempo(atTick tick: Int) -> Double { tempos.last { $0.tick <= tick }?.bpm ?? tempoBPM }

    /// Seconds from the start of bar 1 at the notated tempi.
    public func seconds(atTick tick: Int) -> Double {
        var s = 0.0
        let q = Double(Self.ticksPerQuarter)
        for (i, t) in tempos.enumerated() {
            let next = i + 1 < tempos.count ? tempos[i + 1].tick : Int.max
            guard tick > t.tick else { break }
            s += Double(min(tick, next) - t.tick) / q * 60 / t.bpm
        }
        return s
    }

    /// Text directions starting in a measure.
    public func directions(inMeasure i: Int) -> [Direction] {
        guard measures.indices.contains(i) else { return [] }
        let m = measures[i]
        return directions.filter { $0.tick >= m.startTick && $0.tick < m.startTick + m.lengthTicks }
    }

    public func part(id: String) -> Part? { parts.first { $0.id == id } }

    /// Index of the measure containing `tick` (clamped to the score).
    public func measureIndex(atTick tick: Int) -> Int {
        guard !measures.isEmpty else { return 0 }
        var lo = 0, hi = measures.count - 1
        while lo < hi {
            let mid = (lo + hi + 1) / 2
            if measures[mid].startTick <= tick { lo = mid } else { hi = mid - 1 }
        }
        return lo
    }

    /// Bar (1-based index into `measures`) and 1-based beat at a tick.
    public func position(atTick tick: Int) -> (bar: Int, beat: Double) {
        let i = measureIndex(atTick: max(0, tick))
        let m = measures[i]
        let beatTicks = Double(Self.ticksPerQuarter) * 4 / Double(m.beatType)
        return (i + 1, 1 + Double(tick - m.startTick) / beatTicks)
    }
}

public struct Measure: Sendable, Equatable {
    /// The printed measure number (MusicXML `number` attribute).
    public var number: String
    public var startTick: Int
    public var lengthTicks: Int
    public var beats: Int
    public var beatType: Int
    public var fifths: Int

    public var beatTicks: Int { Score.ticksPerQuarter * 4 / beatType }
}

public struct Part: Sendable, Equatable, Identifiable {
    public var id: String
    public var name: String
    public var abbreviation: String
    public var instrumentName: String
    /// MusicXML `<instrument-sound>` id such as `brass.cornet`.
    public var instrumentSound: String
    /// General MIDI program, 1-based as in MusicXML; for percussion, the kit (2 is the band SoundFont's pop kit).
    public var midiProgram: Int?
    public var midiChannel: Int
    /// Semitones from written to concert pitch (`chromatic` + 12 × `octave-change`).
    public var transposeSemitones: Int
    public var isPercussion: Bool
    /// Key signature (fifths) as written at the start of the part.
    public var writtenFifths: Int
    public var notes: [ScoreNote]
    /// Dynamic marks (`p`, `mf`, …) by tick.
    public var dynamics: [Int: String] = [:]
    /// Hairpins (`<wedge>`), in score order.
    public var wedges: [Wedge] = []
    /// Written key signature per measure (follows key changes).
    public var measureFifths: [Int] = []
    /// The arranger coloured some of its notes as uncertain.
    public var hasMarks = false

    /// Concert key signature in a measure.
    public func concertFifths(inMeasure i: Int) -> Int {
        let written = measureFifths.indices.contains(i) ? measureFifths[i] : writtenFifths
        var f = written + ((transposeSemitones % 12) * 7 % 12 + 12) % 12
        while f > 6 { f -= 12 }
        while f < -6 { f += 12 }
        return f
    }

    /// Key signature at concert pitch, derived from the written key and transposition.
    public var concertFifths: Int {
        var f = writtenFifths + ((transposeSemitones % 12) * 7 % 12 + 12) % 12
        while f > 6 { f -= 12 }
        while f < -6 { f += 12 }
        return f
    }

    public var section: Section { Section(instrumentSound: instrumentSound, name: name, isPercussion: isPercussion) }

    public func notes(inMeasure index: Int) -> [ScoreNote] { notes.filter { $0.measureIndex == index } }
}

public struct ScoreNote: Sendable, Equatable {
    public enum Kind: Sendable, Equatable {
        case pitched(written: SpelledPitch)
        case unpitched(displayStep: String, displayOctave: Int, notehead: String)
        case rest
    }

    public var kind: Kind
    public var measureIndex: Int
    public var startTick: Int
    public var durTicks: Int
    /// Notated value (`whole`, `half`, `quarter`, `eighth`, `16th` …) when given.
    public var type: String?
    public var dots: Int
    public var isChordTone: Bool
    public var tieStart: Bool
    public var tieStop: Bool
    /// Concert MIDI pitch for pitched notes; GM drum key for percussion; nil for rests.
    public var midiPitch: Int?
    /// The dynamic mark the note is played under (`Dynamics`).
    public var dynamic: String = Dynamics.defaultMark
    /// Accent steps: 1 for an accent, 2 for a strong accent (marcato).
    public var accent: Int = 0
    /// MIDI velocity from the dynamics, hairpins and accents (`Dynamics`).
    public var velocity: Int = Dynamics.velocity(mark: Dynamics.defaultMark)

    public var isRest: Bool { if case .rest = kind { return true } else { return false } }
    public var endTick: Int { startTick + durTicks }
}

/// Pitch as written on the page: step, alteration and octave.
public struct SpelledPitch: Sendable, Equatable, Hashable {
    public var step: String
    public var alter: Int
    public var octave: Int

    public init(step: String, alter: Int, octave: Int) { self.step = step; self.alter = alter; self.octave = octave }

    public var midi: Int {
        let base = ["C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11][step] ?? 0
        return (octave + 1) * 12 + base + alter
    }

    /// Respell a MIDI pitch using sharps or flats depending on key signature.
    public static func spelling(midi: Int, fifths: Int) -> SpelledPitch {
        let pc = ((midi % 12) + 12) % 12
        let sharps: [(String, Int)] = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
                                       ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]
        let flats: [(String, Int)] = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
                                      ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)]
        let (s, a) = (fifths < 0 ? flats : sharps)[pc]
        return SpelledPitch(step: s, alter: a, octave: (midi - pc) / 12 - 1)
    }
}

/// Brass-band sections: the unit for seating placement and sampler sharing.
public enum Section: String, CaseIterable, Sendable {
    case sopranoCornet, cornets, flugelhorn, horns, baritones, trombones, bassTrombone, euphonium, basses, percussion, other

    public init(instrumentSound: String, name: String, isPercussion: Bool) {
        let n = name.lowercased()
        if isPercussion || instrumentSound.hasPrefix("drum") { self = .percussion }
        else if n.contains("soprano") { self = .sopranoCornet }
        else if n.contains("cornet") { self = .cornets }
        else if n.contains("flugel") { self = .flugelhorn }
        else if n.contains("horn") { self = .horns }
        else if n.contains("baritone") { self = .baritones }
        else if n.contains("bass trombone") { self = .bassTrombone }
        else if n.contains("trombone") { self = .trombones }
        else if n.contains("euph") { self = .euphonium }
        else if n.contains("bass") { self = .basses }
        else { self = .other }
    }

    /// Contest seating as seen from the conductor: azimuth in degrees (negative = left)
    /// and distance in metres. Used when no seating file is supplied.
    public var defaultSeat: (azimuth: Double, distance: Double) {
        switch self {
        case .sopranoCornet: return (-35, 3.5)
        case .cornets: return (-55, 2.5)
        case .flugelhorn: return (-20, 3.5)
        case .horns: return (-5, 2.5)
        case .baritones: return (10, 2.8)
        case .trombones: return (40, 3.5)
        case .bassTrombone: return (50, 3.8)
        case .euphonium: return (30, 2.5)
        case .basses: return (15, 4.5)
        case .percussion: return (0, 6)
        case .other: return (0, 3)
        }
    }
}

import Foundation

/// How a score's dynamics become MIDI velocities: alphaTab's rules, so every Play app plays a score at
/// the same levels (sounds/playback-levels.json "dynamics", which the tests check these against;
/// docs/research/12-band-sound.md §11).
///
/// - A dynamic mark (`<dynamics>` in a direction or in a note's notations) holds from where it is read
///   until the next one, in document order; a part starts at f.
/// - Every mark has one velocity (alphaTab `MidiUtils.dynamicToVelocity`): ppp 15, then 16 per step
///   up to fff 127. The forced marks (sf, sfz, fz, sfp) play as ff and hold like any mark, as alphaTab
///   plays them.
/// - An accent adds one step (16), a strong accent (marcato) two (alphaTab `_getNoteVelocity`).
/// - A hairpin (`<wedge>`) moves the velocity linearly in time from the mark in effect where it starts
///   to the first mark at or after where it stops; without such a mark, one step up or down. alphaTab
///   1.8.4 draws hairpins but plays them flat, so on Android and Windows a hairpin jumps at the next
///   mark instead.
public enum Dynamics {
    /// The mark a part plays at before its first one.
    public static let defaultMark = "f"
    /// One dynamic step, and an accent's boost.
    public static let step = 16

    /// alphaTab 1.8.4 `MidiUtils.dynamicToVelocity`, by MusicXML element name.
    public static let velocity: [String: Int] = [
        "pppppp": 3, "ppppp": 5, "pppp": 10,
        "ppp": 15, "pp": 31, "p": 47, "mp": 63, "mf": 79, "f": 95, "ff": 111, "fff": 127,
        "ffff": 127, "fffff": 127, "ffffff": 127,
        "sf": 111, "sfz": 111, "fz": 111, "sfp": 111, "sfpp": 111, "sfzp": 111,
        "fp": 95, "rf": 95, "rfz": 95, "sffz": 95, "pf": 87, "n": 1,
    ]

    /// Accent articulations and their steps.
    public static let accentSteps: [String: Int] = ["accent": 1, "strong-accent": 2]

    public static func isMark(_ name: String) -> Bool { velocity[name] != nil }

    /// Velocity of a note under `mark` with `accent` steps, clamped to 1...127.
    public static func velocity(mark: String, accent: Int = 0) -> Int {
        clamp((velocity[mark] ?? velocity[defaultMark]!) + accent * step)
    }

    static func clamp(_ v: Int) -> Int { max(1, min(127, v)) }
}

/// A hairpin in one part, in score ticks.
public struct Wedge: Sendable, Equatable {
    public enum Kind: Sendable, Equatable { case crescendo, diminuendo }
    public var kind: Kind
    public var startTick: Int
    public var stopTick: Int
    public init(kind: Kind, startTick: Int, stopTick: Int) { self.kind = kind; self.startTick = startTick; self.stopTick = stopTick }
}

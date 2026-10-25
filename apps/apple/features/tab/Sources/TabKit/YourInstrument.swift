import Foundation

/// The instrument a tab is written for, as the engine names it, with the tunings the engine has for it (its default first).
///
/// `family` names the instrument's presets in the core's `target-fretted` crate: "<family>-<tuning>", or the
/// family alone for an instrument with one preset. A six-string guitar's family is "guitar".
public enum FrettedInstrument: String, CaseIterable, Sendable {
    case bass4 = "bass-4"
    case bass5 = "bass-5"
    case bass6 = "bass-6"
    case guitar6 = "guitar-6"
    case guitar7 = "guitar-7"
    case guitar8 = "guitar-8"
    /// Soprano, concert and tenor: one tuning, with the fourth string high or low.
    case ukulele
    case ukuleleBaritone = "ukulele-baritone"
    case mandolin

    public static let standardTuning = "standard"

    /// The engine's instrument id: "guitar-6", "bass-4", "ukulele", "mandolin".
    public var id: String { rawValue }

    public var tunings: [String] {
        switch self {
        case .bass4: ["standard", "eb-standard", "d-standard", "drop-d", "bead"]
        case .bass5: ["standard", "drop-a"]
        case .bass6, .guitar8, .ukuleleBaritone, .mandolin: ["standard"]
        case .guitar6: ["standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"]
        case .guitar7: ["standard", "eb-standard"]
        case .ukulele: ["high-g", "low-g"]
        }
    }

    private var family: String { self == .guitar6 ? "guitar" : rawValue }
    private var onePreset: Bool { self == .ukuleleBaritone || self == .mandolin }

    /// The tuning of a job that names none.
    public var defaultTuning: String { tunings.first ?? Self.standardTuning }

    /// The engine's preset id for this instrument in `tuning`, as tab.json's `preset` names it.
    public func preset(_ tuning: String? = nil) -> String { onePreset ? family : "\(family)-\(tuning ?? defaultTuning)" }
}

/// The instruments of "Your instrument", in the order they are listed, each with the kinds of it that can be
/// chosen: a guitar or a bass by its number of strings, a ukulele by its size.
public enum Instrument: String, CaseIterable, Sendable {
    case guitar
    case bass
    /// Soprano, concert and tenor are one kind: they are tuned alike. The baritone is tuned as a guitar's top four strings.
    case ukulele
    case mandolin

    public var id: String { rawValue }

    public var kinds: [FrettedInstrument] {
        switch self {
        case .guitar: [.guitar6, .guitar7, .guitar8]
        case .bass: [.bass4, .bass5, .bass6]
        case .ukulele: [.ukulele, .ukuleleBaritone]
        case .mandolin: [.mandolin]
        }
    }

    /// A capo is used on it: asked about on Check the song.
    public var takesCapo: Bool { self == .guitar || self == .ukulele }

    /// The instrument `kind` is a kind of.
    public static func of(_ kind: FrettedInstrument) -> Instrument { allCases.first { $0.kinds.contains(kind) }! }
}

/// Which hand frets (docs/fretscribe/research/02-accessibility.md §6). Tab is the same for all three;
/// chord boxes and the fretboard turn round for the two right-hand setups.
public enum FrettingHand: String, CaseIterable, Sendable {
    /// The left hand frets: most players.
    case left
    /// The right hand frets, on an instrument strung for it.
    case right
    /// The right hand frets on an ordinary instrument turned upside down: the low string is nearest the floor.
    case rightUpsideDown = "right-upside-down"

    public var id: String { rawValue }
}

/// What the player reads. The id is the engine's `layout`.
public enum Reads: String, CaseIterable, Sendable {
    case tab
    case tabAndNotation = "tab-and-notation"
    case notation

    public var id: String { rawValue }
}

/// The options of a `tab` job that come from the player's instrument.
public struct TabJobOptions: Equatable, Sendable {
    public var instrument: String
    public var tuning: String
    public var layout: String

    public init(instrument: String, tuning: String, layout: String) {
        self.instrument = instrument; self.tuning = tuning; self.layout = layout
    }
}

/// The player's answer to "Your instrument" (design/brands/fretscribe/flows.md §2): what new tabs are written for.
/// A song already written keeps the instrument it was made for.
///
/// `kind` is the engine's instrument ("guitar-6", "bass-5", "ukulele-baritone") and `tuning` one of the
/// tunings the engine has for it ("standard", "drop-d", "high-g"); together they name a preset of the
/// core's `target-fretted` crate (`preset`, "guitar-drop-d").
public struct YourInstrument: Equatable, Sendable {
    public var kind: FrettedInstrument
    public var tuning: String
    public var hand: FrettingHand
    public var reads: Reads

    public init(_ kind: FrettedInstrument = .guitar6, tuning: String? = nil, hand: FrettingHand = .left, reads: Reads = .tab) {
        self.kind = kind
        self.tuning = tuning ?? kind.defaultTuning
        self.hand = hand
        self.reads = reads
    }

    /// "Not now": a six-string guitar in standard tuning, the left hand frets, tab.
    public static let `default` = YourInstrument()

    /// Guitar, bass, ukulele or mandolin.
    public var instrument: Instrument { Instrument.of(kind) }

    /// The number of strings, for a guitar or a bass (they are chosen by it); nil for the others.
    public var strings: Int? { Self.stringsOf(kind) }

    /// The engine's `instrument`: "guitar-6", "bass-4", "ukulele", "mandolin".
    public var family: String { kind.id }

    /// The crate's preset id for this instrument in this tuning.
    public var preset: String { let v = valid(); return v.kind.preset(v.tuning) }

    /// The tunings offered for this instrument, its usual one first.
    public var tunings: [String] { kind.tunings }

    /// Another instrument: its first kind in its usual tuning. The same instrument changes nothing.
    public func withInstrument(_ other: Instrument) -> YourInstrument {
        guard other != instrument, let kind = other.kinds.first else { return self }
        var v = self
        v.kind = kind
        v.tuning = kind.defaultTuning
        return v
    }

    /// Another kind of the instrument: the tuning stays when the new kind has it, and is its usual one otherwise.
    public func withKind(_ other: FrettedInstrument) -> YourInstrument {
        var v = self
        v.kind = other
        return v.valid()
    }

    /// This answer with a tuning the instrument has no preset for replaced by its usual one.
    public func valid() -> YourInstrument {
        if kind.tunings.contains(tuning) { return self }
        var v = self
        v.tuning = kind.defaultTuning
        return v
    }

    /// What a job is asked for. The fretting hand changes only how things are drawn, so it is not among them.
    public func jobOptions() -> TabJobOptions {
        let v = valid()
        return TabJobOptions(instrument: v.kind.id, tuning: v.tuning, layout: v.reads.id)
    }

    /// The number of strings a guitar or a bass is chosen by ("guitar-7" has 7); nil for a ukulele and a mandolin.
    public static func stringsOf(_ kind: FrettedInstrument) -> Int? {
        let i = Instrument.of(kind)
        guard i == .guitar || i == .bass, let n = kind.id.split(separator: "-").last else { return nil }
        return Int(n)
    }
}

/// Keeps the answer on this device, in the given defaults (the app keeps it out of backup, like Appearance).
/// Anything stored that this version can't offer reads as its default.
public struct YourInstrumentStore: @unchecked Sendable {
    /// The engine's instrument id.
    public static let kindKey = "fret_kind"
    public static let tuningKey = "fret_tuning"
    public static let handKey = "fret_hand"
    public static let readsKey = "fret_reads"

    private let defaults: UserDefaults

    public init(_ defaults: UserDefaults) { self.defaults = defaults }

    public func load() -> YourInstrument {
        let stored = defaults.string(forKey: Self.kindKey).flatMap(FrettedInstrument.init(rawValue:))
        let kind = stored ?? YourInstrument.default.kind
        return YourInstrument(
            kind,
            // A tuning stored for an instrument this version can't read says nothing about the default one.
            tuning: stored != nil ? defaults.string(forKey: Self.tuningKey) : nil,
            hand: defaults.string(forKey: Self.handKey).flatMap(FrettingHand.init(rawValue:)) ?? YourInstrument.default.hand,
            reads: defaults.string(forKey: Self.readsKey).flatMap(Reads.init(rawValue:)) ?? YourInstrument.default.reads
        ).valid()
    }

    public func save(_ value: YourInstrument) {
        let v = value.valid()
        defaults.set(v.kind.id, forKey: Self.kindKey)
        defaults.set(v.tuning, forKey: Self.tuningKey)
        defaults.set(v.hand.id, forKey: Self.handKey)
        defaults.set(v.reads.id, forKey: Self.readsKey)
    }
}

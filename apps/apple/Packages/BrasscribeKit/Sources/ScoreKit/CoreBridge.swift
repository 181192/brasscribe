import Foundation

/// The seam to the shared Rust core (`core/swift/BrasscribeCore`, UniFFI). The app talks
/// only to this protocol; `SwiftCoreBridge` implements it in Swift until the core package
/// is available, at which point a `RustCoreBridge` replaces it without touching callers.
public protocol CoreBridge: Sendable {
    /// Decode a Composition from its JSON contract.
    func composition(fromJSON data: Data) throws -> Composition
    /// Read an arranged score.
    func score(fromMusicXML data: Data) throws -> Score
    /// MIDI export of a score.
    func midi(for score: Score, options: MIDIWriter.Options) -> Data
    /// Talking-score text.
    func talkingScore(for score: Score, composition: Composition?, language: ScoreLanguage, pitchMode: PitchMode) -> String
    /// Arrange a Composition for a lineup. Nil when this bridge cannot arrange on device
    /// (the companion engine does it instead).
    func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?, seat: SeatOptions) throws -> Data?
}

extension CoreBridge {
    /// Arranged with no seat: today's output, byte for byte.
    public func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?) throws -> Data? {
        try arrange(composition, lineup: lineup, difficulty: difficulty, keyFifths: keyFifths, seat: SeatOptions())
    }
}

/// The player's seat, reading and who plays the tune, as the core's arrangement options take them
/// (`seat`, `reads`, `lead`). All nil: no seat, and the output is what it was before seats.
public struct SeatOptions: Sendable, Equatable, Codable {
    /// A core seat id (`seats()`), e.g. "euphonium".
    public var seat: String?
    /// "treble" or "bass"; nil: the brass-band part's own clef.
    public var reads: String?
    /// "lineup" or "seat"; nil: the lineup's lead (a solo take with a seat always writes the seat).
    public var lead: String?
    public init(seat: String? = nil, reads: String? = nil, lead: String? = nil) {
        self.seat = seat; self.reads = reads; self.lead = lead
    }
}

/// Which ensemble the score is arranged for. Raw values are what a saved piece records.
public enum Lineup: String, CaseIterable, Sendable, Codable {
    case fullBand = "full-band", minimalBand = "minimal-band"
    /// 1st Cornet, 2nd Cornet, Tenor Horn and Euphonium, one player each.
    case quartet

    /// The engine's `lineup` value (engine/openapi.json).
    public var engineValue: String {
        switch self {
        case .fullBand: return "full"
        case .minimalBand: return "minimal"
        case .quartet: return "quartet"
        }
    }

    /// The shared core's lineup name (ArrangeOptions.lineup, LayersSongOptions.lineup).
    public var coreValue: String {
        switch self {
        case .fullBand: return "band"
        case .minimalBand: return "minimal"
        case .quartet: return "quartet"
        }
    }

    /// The part that carries the tune: the musician's own part by default.
    public var lead: String {
        switch self {
        case .fullBand, .minimalBand: return "Solo Cornet"
        case .quartet: return "1st Cornet"
        }
    }

    /// The lineup a score was arranged for, from the composition's record of it
    /// (`arrangement.lineup`), when it has one.
    public init?(recorded value: String?) {
        switch value {
        case "band", "full": self = .fullBand
        case "minimal": self = .minimalBand
        case "quartet": self = .quartet
        default: return nil
        }
    }
}

public enum Difficulty: String, CaseIterable, Sendable, Codable {
    case faithful, standard, easier
}

public struct SwiftCoreBridge: CoreBridge {
    public init() {}

    public func composition(fromJSON data: Data) throws -> Composition { try Composition.decode(data) }
    public func score(fromMusicXML data: Data) throws -> Score { try MusicXMLParser.parse(data) }
    public func midi(for score: Score, options: MIDIWriter.Options) -> Data { MIDIWriter.data(for: score, options: options) }

    public func talkingScore(for score: Score, composition: Composition?, language: ScoreLanguage, pitchMode: PitchMode) -> String {
        TalkingScore(score: score, language: language, pitchMode: pitchMode,
                     uncertainty: composition.map(UncertaintyIndex.init) ?? .empty).text()
    }

    public func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?, seat: SeatOptions) throws -> Data? { nil }
}

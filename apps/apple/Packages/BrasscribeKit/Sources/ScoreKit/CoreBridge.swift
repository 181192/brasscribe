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
    func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?) throws -> Data?
}

public enum Lineup: String, CaseIterable, Sendable, Codable {
    case fullBand = "full-band", minimalBand = "minimal-band"
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

    public func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?) throws -> Data? { nil }
}

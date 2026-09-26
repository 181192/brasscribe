import BrasscribeCore
import Foundation
import ScoreKit

/// `CoreBridge` backed by the shared Rust core (UniFFI). Arranging runs on the device, so a
/// Composition becomes a brass-band score without the companion engine. Reading and
/// describing scores stay in Swift (ScoreKit), which is tested against the same golden files.
struct RustCoreBridge: CoreBridge {
    private let swift = SwiftCoreBridge()

    var version: String { coreVersion() }

    func composition(fromJSON data: Data) throws -> Composition {
        // normalize through the core so both sides agree on field defaults
        let normalized = try normalizeComposition(json: String(decoding: data, as: UTF8.self))
        return try Composition.decode(Data(normalized.utf8))
    }

    func score(fromMusicXML data: Data) throws -> Score { try swift.score(fromMusicXML: data) }

    func midi(for score: Score, options: MIDIWriter.Options) -> Data { swift.midi(for: score, options: options) }

    func talkingScore(for score: Score, composition: Composition?, language: ScoreLanguage, pitchMode: PitchMode) -> String {
        swift.talkingScore(for: score, composition: composition, language: language, pitchMode: pitchMode)
    }

    /// Difficulty and key are not offered by the core's arranger yet; they are ignored here
    /// and applied by the engine when it supports them.
    func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?) throws -> Data? {
        let json = String(decoding: try JSONEncoder().encode(composition), as: UTF8.self)
        let xml = try arrangeMusicxml(compositionJson: json, arranger: lineup == .minimalBand ? "minimal" : "auto")
        return Data(xml.utf8)
    }
}

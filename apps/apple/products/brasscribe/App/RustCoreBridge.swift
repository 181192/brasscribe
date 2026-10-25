import ScribeCore
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

    /// Arranged by the core for the lineup and difficulty, in the target key (fifths) when one
    /// is given. A whole-band take has no layers for the full band and gets the small band.
    /// The seat, reading and lead go along every time: the call rewrites the whole arrangement.
    func arrange(_ composition: Composition, lineup: Lineup, difficulty: Difficulty, keyFifths: Int?, seat: SeatOptions) throws -> Data? {
        let json = String(decoding: try JSONEncoder().encode(composition), as: UTF8.self)
        let options = ArrangeOptions(lineup: lineup.coreValue, difficulty: difficulty.rawValue,
                                     key: keyFifths.map { String($0) }, transpose: nil,
                                     seat: seat.seat, reads: seat.reads, lead: seat.lead)
        return Data(try arrangeMusicxmlWith(compositionJson: json, options: options).utf8)
    }
}

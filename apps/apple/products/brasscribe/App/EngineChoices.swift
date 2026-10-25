import Foundation
import ScoreKit
import TranscriptionKit

/// "What is this?" — the answer picks the pipeline profile. The app never guesses.
/// Raw values are the engine's profile ids.
enum SourceProfile: String, CaseIterable, Codable, Sendable, Identifiable {
    case solo
    case brassBand = "brass-band"
    case orchestraWithSoloist = "orchestra-with-soloist"
    case popRock = "pop-rock"
    var id: String { rawValue }
    /// The engine's target these profiles belong to: this app makes band scores.
    static let target = "brass"
}

/// What the musician wants out, sent along when the engine supports it.
struct OutputChoice: Sendable, Equatable, Codable {
    var lineup: Lineup
    var difficulty: Difficulty
    /// Target key in fifths (nil = keep the detected key).
    var keyFifths: Int?
    /// The player's seat (a core seat id), the clef they read ("treble"/"bass") and who plays the
    /// tune ("lineup"/"seat"). Nil: no seat, and the score is what it was before seats.
    var seat: String?
    var reads: String?
    var lead: String?
    init(lineup: Lineup = .fullBand, difficulty: Difficulty = .faithful, keyFifths: Int? = nil,
         seat: String? = nil, reads: String? = nil, lead: String? = nil) {
        self.lineup = lineup; self.difficulty = difficulty; self.keyFifths = keyFifths
        self.seat = seat; self.reads = reads; self.lead = lead
    }

    /// The seat options as the core's arrangers take them.
    var seatOptions: SeatOptions { SeatOptions(seat: seat, reads: reads, lead: lead) }

    /// The arrangement options as the engine's upload form takes them (engine/openapi.json: lineup
    /// full|minimal|quartet, difficulty, key as FIFTHS[:MODE]). The seat, the reading and who plays the tune only
    /// when set, so a job without a seat is the same job as before.
    var fields: [EngineField] {
        var f = [EngineField("lineup", lineup.engineValue), EngineField("difficulty", difficulty.rawValue)]
        if let keyFifths { f.append(EngineField("key", String(keyFifths))) }
        if let seat { f.append(EngineField("seat", seat)) }
        if let reads { f.append(EngineField("reads", reads)) }
        if let lead { f.append(EngineField("lead", lead)) }
        return f
    }

    /// The choice a request was made with: what `fields` sent.
    init(request: TranscriptionRequest) {
        self.init(lineup: Lineup.allCases.first { $0.engineValue == request.field("lineup") } ?? .fullBand,
                  difficulty: request.field("difficulty").flatMap(Difficulty.init(rawValue:)) ?? .faithful,
                  keyFifths: request.field("key").flatMap { Int($0) },
                  seat: request.field("seat"), reads: request.field("reads"), lead: request.field("lead"))
    }
}

extension TranscriptionRequest {
    init(audioURL: URL, profile: SourceProfile, title: String? = nil, output: OutputChoice = .init()) {
        self.init(audioURL: audioURL, profile: profile.rawValue, title: title, fields: output.fields)
    }

    var output: OutputChoice { OutputChoice(request: self) }
}

/// A quartet was asked for a take with one line only: the engine refuses it, and so does this device.
struct NeedsWholeGroup: Error {}

extension Error {
    /// The engine's refusal of a quartet for a take with one line, or this device's.
    func needsWholeGroup(lineup: Lineup) -> Bool {
        if self is NeedsWholeGroup { return true }
        if case .http(422, _)? = self as? TranscriptionError { return lineup == .quartet }
        return false
    }
}

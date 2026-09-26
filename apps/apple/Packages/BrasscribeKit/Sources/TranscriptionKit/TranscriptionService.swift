import Foundation
import ScoreKit

/// "What is this?" — the answer picks the pipeline profile. The app never guesses.
/// Raw values are the engine's profile ids.
public enum SourceProfile: String, CaseIterable, Codable, Sendable, Identifiable {
    case solo
    case brassBand = "brass-band"
    case orchestraWithSoloist = "orchestra-with-soloist"
    case popRock = "pop-rock"
    public var id: String { rawValue }
}

/// What the musician wants out, sent along when the engine supports it.
public struct OutputChoice: Sendable, Equatable, Codable {
    public var lineup: Lineup
    public var difficulty: Difficulty
    /// Target key in fifths (nil = keep the detected key).
    public var keyFifths: Int?
    public init(lineup: Lineup = .fullBand, difficulty: Difficulty = .faithful, keyFifths: Int? = nil) {
        self.lineup = lineup; self.difficulty = difficulty; self.keyFifths = keyFifths
    }
}

public struct TranscriptionRequest: Sendable {
    public var audioURL: URL
    public var profile: SourceProfile
    public var title: String?
    public var output: OutputChoice
    public init(audioURL: URL, profile: SourceProfile, title: String? = nil, output: OutputChoice = .init()) {
        self.audioURL = audioURL; self.profile = profile; self.title = title; self.output = output
    }
}

/// Plain-language step names; the app localises them.
public enum StageKind: String, Sendable, CaseIterable {
    case uploading, preparing, separating, findingBeat, transcribing, arranging, engraving, rendering, working

    /// Map an engine stage name/kind onto a step a musician understands.
    public static func classify(name: String?, kind: String?) -> StageKind {
        let s = "\(name ?? "") \(kind ?? "")".lowercased()
        if s.contains("upload") { return .uploading }
        if s.contains("separat") || s.contains("stem") || s.contains("roformer") || s.contains("demucs") { return .separating }
        if s.contains("beat") || s.contains("tempo") || s.contains("downbeat") { return .findingBeat }
        if s.contains("arrang") || s.contains("band") && !s.contains("brass-band.") { return .arranging }
        if s.contains("musicxml") || s.contains("pdf") || s.contains("score") || s.contains("engrav") { return .engraving }
        if s.contains("audio") || s.contains("mp3") || s.contains("render") || s.contains("synth") { return .rendering }
        if s.contains("transcri") || s.contains("muscriptor") || s.contains("pitch") || s.contains("f0")
            || s.contains("mega") || s.contains("note") || s.contains("vote") || s.contains("quantiz") { return .transcribing }
        if s.contains("load") || s.contains("decode") || s.contains("resample") || s.contains("prepare") { return .preparing }
        return .working
    }
}

public struct TranscriptionProgress: Sendable, Equatable {
    public var stage: StageKind
    /// Engine stage id, for diagnostics.
    public var stageName: String?
    /// 0...1 share of the job done.
    public var fraction: Double
    /// Estimated seconds left, nil until there is enough evidence.
    public var etaSeconds: Double?
    /// Where the engine runs the heavy models (cuda, mps, cpu), when known.
    public var device: String?

    public init(stage: StageKind, stageName: String? = nil, fraction: Double, etaSeconds: Double?, device: String? = nil) {
        self.stage = stage; self.stageName = stageName; self.fraction = fraction; self.etaSeconds = etaSeconds; self.device = device
    }
}

public enum ArtifactKind: String, CaseIterable, Sendable, Codable {
    case composition, musicXML, pdf, midi, audio, brailleBRF, talkingScore

    /// File name the engine uses for this artifact.
    public var engineName: String {
        switch self {
        case .composition: return "composition.json"
        case .musicXML: return "brass-band.musicxml"
        case .pdf: return "brass-band.pdf"
        case .midi: return "brass-band.mid"
        case .audio: return "brass-band.mp3"
        case .brailleBRF: return "brass-band.brf"
        case .talkingScore: return "talking-score.txt"
        }
    }

    public var fileExtension: String { String(engineName.split(separator: ".").last ?? "") }
}

public struct TranscriptionResult: Sendable {
    public var jobID: String
    public var composition: Composition?
    public var musicXML: Data
    public var available: Set<ArtifactKind>
    public init(jobID: String, composition: Composition?, musicXML: Data, available: Set<ArtifactKind>) {
        self.jobID = jobID; self.composition = composition; self.musicXML = musicXML; self.available = available
    }
}

public enum TranscriptionEvent: Sendable {
    case progress(TranscriptionProgress)
    case finished(TranscriptionResult)
}

public enum TranscriptionError: Error, Equatable, Sendable, LocalizedError {
    case notPaired
    case pairingRejected
    case unreachable(String)
    case http(Int, String)
    case jobFailed(String)
    case cancelled
    case artifactUnavailable(ArtifactKind)

    public var errorDescription: String? {
        switch self {
        case .notPaired: return "Not paired with a computer yet."
        case .pairingRejected: return "The pairing code was not accepted."
        case .unreachable(let s): return "Can't reach the computer: \(s)"
        case .http(let c, let s): return "The computer answered \(c): \(s)"
        case .jobFailed(let s): return "Transcription failed: \(s)"
        case .cancelled: return "Cancelled."
        case .artifactUnavailable(let k): return "\(k.engineName) is not available for this transcription."
        }
    }
}

/// Turns audio into a score. Implementations: the companion engine on the LAN, a local
/// fixture for tests and demos, and later on-device models.
///
/// Cancelling the consuming task (or dropping the stream) cancels the job.
public protocol TranscriptionService: Sendable {
    var displayName: String { get }
    func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error>
    func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data
}

/// Remaining-time estimate from progress over wall time. Needs at least 5 % progress and
/// 3 s of evidence; smooths so the number doesn't jump around.
public struct ETAEstimator: Sendable {
    let start: Date
    var smoothed: Double?

    public init(start: Date = Date()) { self.start = start }

    public mutating func update(fraction: Double, now: Date = Date()) -> Double? {
        let elapsed = now.timeIntervalSince(start)
        guard fraction >= 0.05, fraction < 1, elapsed >= 3 else { return fraction >= 1 ? 0 : nil }
        let raw = elapsed * (1 - fraction) / fraction
        let s = smoothed.map { 0.7 * $0 + 0.3 * raw } ?? raw
        smoothed = s
        return s
    }
}

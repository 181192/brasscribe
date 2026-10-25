import Foundation
import ScoreKit

/// One of a target's own options for a job, as the engine's upload form takes it (engine/openapi.json).
public struct EngineField: Sendable, Equatable {
    public var name: String
    public var value: String
    public init(_ name: String, _ value: String) { self.name = name; self.value = value }
}

public struct TranscriptionRequest: Sendable {
    public var audioURL: URL
    /// The engine's profile id.
    public var profile: String
    public var title: String?
    /// The target's options, sent with the recording.
    public var fields: [EngineField]
    public init(audioURL: URL, profile: String, title: String? = nil, fields: [EngineField] = []) {
        self.audioURL = audioURL; self.profile = profile; self.title = title; self.fields = fields
    }

    /// The value sent as [name]; nil when it is not sent.
    public func field(_ name: String) -> String? { fields.last { $0.name == name }?.value }
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
    case composition, musicXML, pdf, midi, audio, brailleBRF, talkingScore, tab

    /// Where the engine serves it for a job: `v1/jobs/<id>/<endpoint>`, whatever the target names its file.
    public var endpoint: String {
        switch self {
        case .composition: "composition"
        case .musicXML: "musicxml"
        case .pdf: "pdf"
        case .midi: "midi"
        case .audio: "audio"
        case .brailleBRF: "braille"
        case .talkingScore: "talking-score"
        case .tab: "tab"
        }
    }

    /// Whether a job's output file of this name is this kind. The target names its files (`brass-band.musicxml`,
    /// `tab.musicxml`); the shared ones have one name.
    public func isOutput(_ name: String) -> Bool {
        switch self {
        case .composition: name == "composition.json"
        case .talkingScore: name == "talking-score.txt"
        case .tab: name == "tab.json"
        default: name.hasSuffix("." + fileExtension)
        }
    }

    public var fileExtension: String {
        switch self {
        case .composition, .tab: "json"
        case .musicXML: "musicxml"
        case .pdf: "pdf"
        case .midi: "mid"
        case .audio: "mp3"
        case .brailleBRF: "brf"
        case .talkingScore: "txt"
        }
    }

    /// The kinds among a job's output files.
    public static func available(in outputs: some Sequence<String>) -> Set<ArtifactKind> {
        let names = Array(outputs)
        return Set(allCases.filter { kind in names.contains { kind.isOutput($0) } })
    }
}

public struct TranscriptionResult: Sendable {
    public var jobID: String
    public var composition: Composition?
    public var musicXML: Data
    public var available: Set<ArtifactKind>
    public var evidence: NoteEvidence?
    public init(jobID: String, composition: Composition?, musicXML: Data, available: Set<ArtifactKind>, evidence: NoteEvidence? = nil) {
        self.jobID = jobID; self.composition = composition; self.musicXML = musicXML; self.available = available
        self.evidence = evidence
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
    /// The computer's interface version is not this app's: nothing was sent to it (the app shows its own words).
    case interfaceMismatch(InterfaceMatch.Update)

    public var errorDescription: String? {
        switch self {
        case .notPaired: return "Not paired with a computer yet."
        case .pairingRejected: return "The pairing code was not accepted."
        case .unreachable(let s): return "Can't reach the computer: \(s)"
        case .http(let c, let s): return "The computer answered \(c): \(s)"
        case .jobFailed(let s): return "Transcription failed: \(s)"
        case .cancelled: return "Cancelled."
        case .artifactUnavailable(let k): return "The \(k.endpoint) is not available for this transcription."
        case .interfaceMismatch(.app): return "This app is older than the program on the computer."
        case .interfaceMismatch(.computer): return "The program on the computer is older than this app."
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

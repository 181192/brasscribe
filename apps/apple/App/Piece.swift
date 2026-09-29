import Foundation
import ScoreKit
import TranscriptionKit

/// One transcribed piece on disk: `Application Support/Brasscribe/Pieces/<id>/`
/// with `score.musicxml`, optional `composition.json`, the original recording and video.
struct Piece: Identifiable, Hashable, Codable, Sendable {
    var id: UUID
    var title: String
    var created: Date
    var profile: SourceProfile?
    var originalFile: String?
    var videoFile: String?
    /// Artifacts the transcription service can still provide (for exports).
    var remoteJobID: String?
    var remoteArtifacts: [ArtifactKind]
    /// Folder with engine outputs when the piece came from the fixture service.
    var fixtureDirectory: String?
    /// The band, difficulty and key the score is arranged for.
    var output: OutputChoice?
    /// "Make this my part": the part name the player chose for this score, over their seat's.
    var myPart: String?
    /// The "this lineup has no <seat>" banner was closed for this score.
    var seatNoticeDismissed: Bool?
    /// Summary for the library: number of bars, and uncertain notes still to check.
    var bars: Int?
    var toCheck: Int?
    /// The player's seat for this score (`SeatChoice.encoded`), kept from the first time it was
    /// opened: a new answer in Settings leaves the scores you already have on the part you chose.
    var seat: String? = nil

    static var libraryURL: URL {
        // unit tests keep their scores out of the user's library
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil {
            return FileManager.default.temporaryDirectory.appending(path: "BrasscribeTests/Pieces", directoryHint: .isDirectory)
        }
        let base = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        return base.appending(path: "Brasscribe/Pieces", directoryHint: .isDirectory)
    }

    var folder: URL { Self.libraryURL.appending(path: id.uuidString, directoryHint: .isDirectory) }
    var scoreURL: URL { folder.appending(path: "score.musicxml") }
    var compositionURL: URL { folder.appending(path: "composition.json") }
    var originalURL: URL? { originalFile.map { folder.appending(path: $0) } }
    var videoURL: URL? { videoFile.map { folder.appending(path: $0) } }
    var metaURL: URL { folder.appending(path: "piece.json") }
    var evidenceURL: URL { folder.appending(path: "evidence.json") }

    func loadScore() throws -> Score { try MusicXMLParser.parse(url: scoreURL) }
    func loadComposition() -> Composition? { try? Composition.decode(Data(contentsOf: compositionURL)) }
    func loadEvidence() -> NoteEvidence? { try? JSONDecoder().decode(NoteEvidence.self, from: Data(contentsOf: evidenceURL)) }
    func saveEvidence(_ e: NoteEvidence) { try? JSONEncoder().encode(e).write(to: evidenceURL, options: .atomic) }
    func musicXML() throws -> String { try String(contentsOf: scoreURL, encoding: .utf8) }

    func saveMusicXML(_ xml: String) throws {
        try Data(xml.utf8).write(to: scoreURL, options: .atomic)
    }

    func saveComposition(_ c: Composition) throws {
        try JSONEncoder().encode(c).write(to: compositionURL, options: .atomic)
    }

    func save() throws {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        try enc.encode(self).write(to: metaURL)
    }

    static func loadAll() -> [Piece] {
        let fm = FileManager.default
        guard let dirs = try? fm.contentsOfDirectory(at: libraryURL, includingPropertiesForKeys: nil) else { return [] }
        return dirs.compactMap { load(from: $0.appending(path: "piece.json")) }
            .sorted { $0.created > $1.created }
    }

    static func load(from meta: URL) -> Piece? {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return try? dec.decode(Piece.self, from: Data(contentsOf: meta))
    }

    /// Store a finished transcription with its source media.
    static func create(title: String, profile: SourceProfile?, result: TranscriptionResult,
                       original: URL?, video: URL?, fixtureDirectory: URL?, output: OutputChoice? = nil) throws -> Piece {
        var p = Piece(id: UUID(), title: title, created: Date(), profile: profile, originalFile: nil, videoFile: nil,
                      remoteJobID: result.jobID, remoteArtifacts: Array(result.available), fixtureDirectory: fixtureDirectory?.path,
                      output: output)
        let fm = FileManager.default
        try fm.createDirectory(at: p.folder, withIntermediateDirectories: true)
        try result.musicXML.write(to: p.scoreURL)
        if let c = result.composition { try JSONEncoder().encode(c).write(to: p.compositionURL) }
        if let e = result.evidence { p.saveEvidence(e) }
        // a source that is gone (or never existed, as in the screenshot scenes) leaves no original
        if let original, fm.fileExists(atPath: original.path) {
            let name = "original." + (original.pathExtension.isEmpty ? "wav" : original.pathExtension)
            try? fm.removeItem(at: p.folder.appending(path: name))
            try fm.copyItem(at: original, to: p.folder.appending(path: name))
            p.originalFile = name
        }
        if let video {
            let name = "video." + (video.pathExtension.isEmpty ? "mov" : video.pathExtension)
            try fm.copyItem(at: video, to: p.folder.appending(path: name))
            p.videoFile = name
        }
        if let score = try? MusicXMLParser.parse(result.musicXML) {
            p.bars = score.measures.count
            p.toCheck = ReviewList.items(score: score, composition: result.composition, uncertainty: result.composition.map(UncertaintyIndex.init) ?? .empty).count
        }
        try p.save()
        return p
    }

    func delete() { try? FileManager.default.removeItem(at: folder) }

    // Identity is the id; the summary fields change as notes are checked.
    static func == (a: Piece, b: Piece) -> Bool { a.id == b.id }
    func hash(into h: inout Hasher) { h.combine(id) }

    // MARK: checked notes

    var checkedURL: URL { folder.appending(path: "checked.json") }

    /// Review items the musician kept.
    func loadChecked() -> Set<String> {
        (try? JSONDecoder().decode(Set<String>.self, from: Data(contentsOf: checkedURL))) ?? []
    }

    func saveChecked(_ ids: Set<String>, remaining: Int) {
        try? JSONEncoder().encode(ids).write(to: checkedURL)
        // From disk: the score may have been arranged again since this copy was made.
        var p = Self.load(from: metaURL) ?? self
        p.toCheck = remaining
        try? p.save()
    }

    // MARK: changed notes

    var reviewChangesURL: URL { folder.appending(path: "review-changes.json") }

    /// A note changed with Change note…: the pitch Brasscribe wrote, where Review keeps it (the Composition's
    /// concert pitch, or the printed pitch without a Composition), and how it was spelled on the page then.
    struct ReviewChange: Codable, Equatable {
        var pitch: Int
        var written: SpelledPitch?

        init(pitch: Int, written: SpelledPitch?) { self.pitch = pitch; self.written = written }

        private enum Keys: String, CodingKey { case pitch, step, alter, octave }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            pitch = try c.decode(Int.self, forKey: .pitch)
            if let step = try c.decodeIfPresent(String.self, forKey: .step) {
                written = SpelledPitch(step: step, alter: try c.decode(Int.self, forKey: .alter), octave: try c.decode(Int.self, forKey: .octave))
            }
        }
        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: Keys.self)
            try c.encode(pitch, forKey: .pitch)
            if let written {
                try c.encode(written.step, forKey: .step)
                try c.encode(written.alter, forKey: .alter)
                try c.encode(written.octave, forKey: .octave)
            }
        }
    }

    /// The notes changed in Review, by the Composition note behind them ("voice@start"), so the same note
    /// is found again in any arrangement: after reopening, the card still says "Changed to X (was Y)" and
    /// Listen plays the changed score, not the recording.
    func loadReviewChanges() -> [String: ReviewChange] {
        (try? JSONDecoder().decode([String: ReviewChange].self, from: Data(contentsOf: reviewChangesURL))) ?? [:]
    }

    func saveReviewChanges(_ changes: [String: ReviewChange]) {
        if changes.isEmpty { try? FileManager.default.removeItem(at: reviewChangesURL); return }
        try? JSONEncoder().encode(changes).write(to: reviewChangesURL, options: .atomic)
    }

    /// Only the layered arranger writes the full band: a take without layers (a Brass band or Pop or
    /// rock recording) is always arranged for the small band or the quartet, so Full brass band is not
    /// offered for it. Without the composition, the profile says.
    func fullBandPossible(_ comp: Composition?) -> Bool {
        comp.map { $0.voices.contains { $0.layer != nil } } ?? (profile != .brassBand && profile != .popRock)
    }

    /// The lineup the score is made for: the chosen one, the full band made as the small band where
    /// it can't be written.
    func madeLineup(_ comp: Composition?) -> Lineup? {
        output.map { $0.lineup == .fullBand && !fullBandPossible(comp) ? .minimalBand : $0.lineup }
    }

    /// A quartet needs harmony to arrange: not a solo take, and the composition has more than
    /// the tune (a bass or harmony voice with notes).
    func canArrangeQuartet(_ comp: Composition?) -> Bool {
        if profile == .solo { return false }
        guard let comp else { return false }
        return comp.voices.contains { v in
            !v.notes.isEmpty && v.layer != "solo" && v.layer != "drums" && v.role != .melody && v.role != .rhythm
        }
    }

    /// "Brass band · 64 bars · Today · 3 notes to check"
    var summary: String {
        var bits: [String] = []
        if let lineup = madeLineup(nil) { bits.append(lineup.shortTitle) }
        else if let profile { bits.append(profile.shortTitle) }
        if let bars { bits.append(String(localized: "\(bars) bars")) }
        bits.append(ScoreTitles.day(created))
        if let toCheck, toCheck > 0 { bits.append(String(localized: "\(toCheck) to check")) }
        return bits.joined(separator: " · ")
    }

    /// The title to show: the user's name for it, else what it was made from; never a bare timestamp.
    var displayTitle: String { ScoreTitles.display(title, made: created) }
}

extension String {
    var capitalizedFirst: String { prefix(1).uppercased(with: .current) + dropFirst() }
}

extension Composition {
    /// Beat-index ranges (in beats from bar 1) where detected beats are so irregular that
    /// the passage is free time: consecutive intervals more than 1.8× or less than 0.55×
    /// the median. Shown as *ad lib* in review.
    var freeTimeBeats: [ClosedRange<Double>] {
        if !freeRegions.isEmpty {
            let tpb = Double(ticksPerBeat)
            return freeRegions.map { Double($0.start) / tpb...Double($0.end) / tpb }
        }
        guard beatTimes.count > 3 else { return [] }
        let d = zip(beatTimes.dropFirst(), beatTimes).map { $0 - $1 }
        let med = d.sorted()[d.count / 2]
        var out: [ClosedRange<Double>] = []
        var start: Int?
        for (i, x) in d.enumerated() {
            let irregular = x > med * 1.8 || x < med * 0.55
            if irregular, start == nil { start = i }
            if !irregular, let s = start {
                if i - s >= 2 { out.append(Double(s - firstDownbeat)...Double(i - firstDownbeat)) }
                start = nil
            }
        }
        if let s = start, d.count - s >= 2 { out.append(Double(s - firstDownbeat)...Double(d.count - firstDownbeat)) }
        return out
    }
}

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
    /// Summary for the library: number of bars, and uncertain notes still to check.
    var bars: Int?
    var toCheck: Int?

    static var libraryURL: URL {
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

    func loadScore() throws -> Score { try MusicXMLParser.parse(url: scoreURL) }
    func loadComposition() -> Composition? { try? Composition.decode(Data(contentsOf: compositionURL)) }
    func musicXML() throws -> String { try String(contentsOf: scoreURL, encoding: .utf8) }

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
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return dirs.compactMap { try? dec.decode(Piece.self, from: Data(contentsOf: $0.appending(path: "piece.json"))) }
            .sorted { $0.created > $1.created }
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
        if let original {
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
            p.toCheck = ReviewList.items(score: score, uncertainty: result.composition.map(UncertaintyIndex.init) ?? .empty).count
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
        var p = self
        p.toCheck = remaining
        try? p.save()
    }

    /// "Brass band · 64 bars · Today · 3 notes to check"
    var summary: String {
        var bits: [String] = []
        if let profile { bits.append(profile.shortTitle) }
        if let bars { bits.append(String(localized: "\(bars) bars")) }
        bits.append(created.formatted(.relative(presentation: .named, unitsStyle: .wide)).capitalizedFirst)
        if let toCheck, toCheck > 0 { bits.append(toCheck == 1 ? String(localized: "1 note to check") : String(localized: "\(toCheck) notes to check")) }
        return bits.joined(separator: " · ")
    }
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

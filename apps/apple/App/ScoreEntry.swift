import Foundation
import TranscriptionKit

/// A row in "Your scores": a piece on this device, or a finished score on the paired computer.
struct ScoreEntry: Identifiable, Hashable {
    enum Location: Hashable { case local(Piece), computer(jobID: String) }

    let id: String
    let title: String
    let date: Date
    let profile: SourceProfile?
    let location: Location
    /// Local summary ("Brass band · 64 bars · Today"); computer scores say where they are.
    let summary: String

    var piece: Piece? { if case .local(let p) = location { p } else { nil } }

    static func == (a: ScoreEntry, b: ScoreEntry) -> Bool {
        a.id == b.id && a.title == b.title && a.summary == b.summary
    }
    func hash(into h: inout Hasher) { h.combine(id) }

    /// Local pieces and the computer's finished runs, newest first. A computer run already
    /// opened here is shown once, and re-runs of one recording collapse to the latest.
    static func merge(pieces: [Piece], jobs: [CompanionService.Job]) -> [ScoreEntry] {
        let local = pieces.map { p in
            ScoreEntry(id: p.id.uuidString, title: p.title, date: p.created, profile: p.profile, location: .local(p), summary: p.summary)
        }
        let downloaded = Set(pieces.compactMap(\.remoteJobID))
        var seenAudio = Set<String>()
        var remote: [ScoreEntry] = []
        for j in jobs.sorted(by: { ($0.created ?? 0) > ($1.created ?? 0) }) where j.status == "succeeded" && j.outputs.contains(ArtifactKind.musicXML.engineName) {
            if let audio = j.audioID, !seenAudio.insert(audio).inserted { continue }
            guard !downloaded.contains(j.id) else { continue }
            let date = Date(timeIntervalSince1970: j.created ?? 0)
            let profile = j.profile.flatMap(SourceProfile.init(rawValue:))
            let when = date.formatted(.relative(presentation: .named, unitsStyle: .wide)).capitalizedFirst
            let summary = ([profile?.shortTitle, when, String(localized: "On your computer")] as [String?]).compactMap { $0 }.joined(separator: " · ")
            remote.append(ScoreEntry(id: "job:\(j.id)", title: j.title ?? j.id, date: date, profile: profile,
                                     location: .computer(jobID: j.id), summary: summary))
        }
        return (local + remote).sorted { $0.date > $1.date }
    }
}

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
            ScoreEntry(id: p.id.uuidString, title: p.displayTitle, date: p.created, profile: p.profile, location: .local(p), summary: p.summary)
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
            remote.append(ScoreEntry(id: "job:\(j.id)", title: ScoreTitles.display(j.title ?? "", made: date), date: date, profile: profile,
                                     location: .computer(jobID: j.id), summary: summary))
        }
        let all = (local + remote).sorted { $0.date > $1.date }
        // two scores with the same title: the time tells them apart
        let counts = Dictionary(all.map { ($0.title, 1) }, uniquingKeysWith: +)
        return all.map { e in
            guard (counts[e.title] ?? 0) > 1 else { return e }
            let time = e.date.formatted(.dateTime.hour().minute())
            return ScoreEntry(id: e.id, title: e.title, date: e.date, profile: e.profile, location: e.location, summary: time + " · " + e.summary)
        }
    }
}


/// Score titles people can tell apart.
enum ScoreTitles {
    /// "Recording, 26 Sep 19:02"
    static func recording(at date: Date) -> String {
        String(localized: "Recording, \(date.formatted(.dateTime.day().month(.abbreviated))) \(date.formatted(.dateTime.hour().minute()))")
    }

    /// The given title, or "Recording, <date>" when it's empty or only a timestamp
    /// ("20260815_155324", as recorders and phones name files). A timestamp in the name is read.
    static func display(_ title: String, made: Date) -> String {
        let t = title.trimmingCharacters(in: .whitespaces)
        guard t.isEmpty || isTimestamp(t) else { return t }
        return recording(at: timestampDate(t) ?? made)
    }

    static func isTimestamp(_ s: String) -> Bool {
        s.range(of: #"^[0-9][0-9 _.:T-]{5,}$"#, options: .regularExpression) != nil
    }

    static func timestampDate(_ s: String) -> Date? {
        let digits = s.filter(\.isNumber)
        guard digits.count >= 12 else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyyMMddHHmm"
        return f.date(from: String(digits.prefix(12)))
    }

    /// "Today", "Yesterday", "Tuesday", then "26 Sep".
    static func day(_ date: Date) -> String {
        let cal = Calendar.current
        if cal.isDateInToday(date) { return String(localized: "Today") }
        if cal.isDateInYesterday(date) { return String(localized: "Yesterday") }
        if let d = cal.dateComponents([.day], from: date, to: Date()).day, d < 7 { return date.formatted(.dateTime.weekday(.wide)).capitalizedFirst }
        return date.formatted(.dateTime.day().month(.abbreviated))
    }
}

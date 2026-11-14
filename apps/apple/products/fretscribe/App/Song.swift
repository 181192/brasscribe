import Foundation
import TabKit
import TranscriptionKit

/// One song with its tab on this device: `Application Support/Fretscribe/Songs/<id>/`, holding the tab as the
/// computer wrote it (`tab.musicxml`, `tab.json`), the notes it heard (`composition.json`) and `song.json`.
/// The recording itself is kept by practice (`PracticeRecordings`), by the song's job.
struct TabSong: Identifiable, Hashable, Codable {
    var id: UUID
    var title: String
    var created: Date
    /// The job on the computer the tab came from; nil for one that has none.
    var jobID: String?
    /// The preset it was written for ("bass-4-standard").
    var preset: String?
    /// Notes marked "?", as the tab draws them.
    var toCheck: Int
    /// Notes under a "!": they have no place on the instrument.
    var noPlace: Int
    /// The recording it was made from, when the app was given it (a new recording, an opened file).
    var recording: URL?

    var folder: URL { Self.root.appending(path: id.uuidString, directoryHint: .isDirectory) }
    var musicXMLURL: URL { folder.appending(path: "tab.musicxml") }
    var tabURL: URL { folder.appending(path: "tab.json") }

    func musicXML() throws -> Data { try Data(contentsOf: musicXMLURL) }

    /// The tab's data, when the computer gave it.
    func tab() -> TabData? {
        (try? Data(contentsOf: tabURL)).flatMap { try? JSONDecoder().decode(TabData.self, from: $0) }
    }

    /// Where songs are kept; `SCRIBE_SONGS` moves it (tests).
    static var root: URL {
        if let dir = ProcessInfo.processInfo.environment["SCRIBE_SONGS"] { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL.applicationSupportDirectory.appending(path: "Fretscribe/Songs", directoryHint: .isDirectory)
    }

    /// Every song on this device, newest first. A folder that can't be read is left out.
    static func loadAll() -> [TabSong] {
        let dirs = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        return dirs.compactMap { d in
            (try? Data(contentsOf: d.appending(path: "song.json"))).flatMap { try? JSONDecoder().decode(TabSong.self, from: $0) }
        }.sorted { $0.created > $1.created }
    }

    /// A new song from a finished job: its MusicXML, and its tab data when there is one.
    static func create(title: String, jobID: String?, musicXML: Data, tab: Data?, recording: URL?) throws -> TabSong {
        let data = tab.flatMap { try? JSONDecoder().decode(TabData.self, from: $0) }
        // The tab's own two numbers: what it marks "?" and what it puts under a "!".
        let marks = SongMarks.of(musicXML: musicXML, tab: data)
        var song = TabSong(id: UUID(), title: title, created: Date(), jobID: jobID, preset: data?.preset,
                           toCheck: marks.doubtful, noPlace: marks.noPlace, recording: nil)
        try FileManager.default.createDirectory(at: song.folder, withIntermediateDirectories: true)
        try musicXML.write(to: song.musicXMLURL)
        if let tab { try tab.write(to: song.tabURL) }
        song.recording = recording
        try song.save()
        return song
    }

    func save() throws {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try JSONEncoder().encode(self).write(to: folder.appending(path: "song.json"), options: .atomic)
    }

    func delete() { try? FileManager.default.removeItem(at: folder) }
}

/// A tab's marks: what is in doubt, and what has no place on the instrument.
enum SongMarks {
    /// A note below this confidence is marked "?" (the core's doubt threshold).
    static let doubt = 0.4

    /// The marks as the tab draws them: a note under a "!" is not also a "?", and a note the page folds into another
    /// is neither. Every screen that counts them counts these.
    static func of(musicXML: Data, tab: TabData?) -> TabMarks {
        TabMarks.of(TabIndex.parse(musicXML: musicXML), tab: tab)
    }

    /// A saved song's marks: the tab's own, as its sheet draws them.
    static func of(_ song: TabSong) -> TabMarks? { TabSheet.read(song)?.marks }
}

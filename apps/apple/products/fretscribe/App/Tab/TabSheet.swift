import Foundation
import TabKit

/// What the tab screen reads of tab.json beyond `TabData`: the instrument (its tuning, frets and capo), the tempo,
/// the layout, and which notes are out of the instrument's range.
struct TabDetails: Decodable, Sendable {
    struct Instrument: Decodable, Sendable {
        struct Tuning: Decodable, Sendable {
            struct Open: Decodable, Sendable {
                var openPitch: Int
                enum CodingKeys: String, CodingKey { case openPitch = "open_pitch" }
            }
            var name: String?
            /// Highest first, as the tab's lines are.
            var strings: [Open]
        }
        var tuning: Tuning?
        var frets: Int?
        var capo: Int?
    }
    struct Note: Decodable, Sendable {
        var outOfRange: Bool?
        enum CodingKeys: String, CodingKey { case outOfRange = "out_of_range" }
    }

    var preset: String?
    var instrument: Instrument?
    var tempoBpm: Double?
    /// "tab", "tab-and-notation" or "notation".
    var layout: String?
    var notes: [Note]?

    enum CodingKeys: String, CodingKey { case preset, instrument, tempoBpm = "tempo_bpm", layout, notes }
}

/// How the page is written: tab alone, tab with notation, or notation alone.
enum TabLayoutKind: String, Sendable {
    case tab
    case tabAndNotation = "tab-and-notation"
    case notation
}

/// A tab ready to show: the page, what the page says of its own notes, the data when the computer gave it, and the marks.
struct TabSheet: Sendable {
    var musicXML: String
    var index: TabIndex
    var data: TabData?
    var details: TabDetails?
    var marks: TabMarks

    init(musicXML: String, data: TabData?, details: TabDetails?) {
        self.musicXML = musicXML
        index = TabIndex.parse(musicXML: musicXML)
        self.data = data
        self.details = details
        marks = TabMarks.of(index, tab: data, details: details)
    }

    /// Reads a song's page and data from its folder; nil when the page can't be read.
    static func read(_ song: TabSong) -> TabSheet? {
        guard let xml = try? song.musicXML() else { return nil }
        let json = try? Data(contentsOf: song.tabURL)
        return TabSheet(musicXML: String(decoding: xml, as: UTF8.self), data: song.tab(),
                        details: json.flatMap { try? JSONDecoder().decode(TabDetails.self, from: $0) })
    }

    var layout: TabLayoutKind {
        if let id = details?.layout, let l = TabLayoutKind(rawValue: id) { return l }
        if index.tabStaff == nil { return .notation }
        return index.staves > 1 ? .tabAndNotation : .tab
    }

    /// The instrument and tuning id the tab was written for, from its preset ("bass-4-standard").
    var preset: (kind: FrettedInstrument, tuning: String)? {
        guard let id = details?.preset ?? data?.preset else { return nil }
        return Self.ofPreset(id)
    }

    static func ofPreset(_ id: String) -> (kind: FrettedInstrument, tuning: String)? {
        for kind in FrettedInstrument.allCases {
            for tuning in kind.tunings where kind.preset(tuning) == id { return (kind, tuning) }
        }
        return nil
    }

    /// The tuning's id ("drop-d") when the preset gives one; else the name the data or the page gives.
    var tuning: String {
        preset?.tuning ?? details?.instrument?.tuning?.name ?? index.tuningName ?? FrettedInstrument.standardTuning
    }

    var capo: Int { details?.instrument?.capo ?? index.capo }

    /// Quarter notes a minute.
    var tempo: Int? { details?.tempoBpm.map { Int($0.rounded()) } ?? index.tempo }

    /// Each column's mark as the page is told of it: where it stands, and its notes.
    var spots: [TabMarkSpot] { marks.columns.map(\.spot) }
}

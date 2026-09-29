import BrasscribeCore
import Foundation
import ScoreKit
import TranscriptionKit

/// What the player plays: the answer to "What do you play?". Saved on this device.
enum SeatChoice: Equatable, Sendable {
    /// Never answered, or "Not now": everything behaves as before seats (Solo Cornet is "your part").
    case notSet
    /// "I conduct or listen": no part is yours; scores open on every part.
    case conductor
    /// A core seat id, and the clef it is read in when that isn't the brass-band default.
    case seat(String, reads: String?)

    var id: String? { if case .seat(let id, _) = self { id } else { nil } }
    var reads: String? { if case .seat(_, let r) = self { r } else { nil } }

    static let seatKey = "seat", readsKey = "seatReads"

    /// One string for a piece to keep (`parse` reads it back): "" not set, "none" conductor, "id[:reads]".
    var encoded: String {
        switch self {
        case .notSet: return ""
        case .conductor: return "none"
        case .seat(let id, let reads): return reads.map { "\(id):\($0)" } ?? id
        }
    }

    /// The saved answer. `-seat <id>[:bass]` and `-seat none` set it for tests and screenshots.
    static var stored: SeatChoice {
        if let i = LaunchOptions.args.firstIndex(of: "-seat"), i + 1 < LaunchOptions.args.count {
            return parse(LaunchOptions.args[i + 1])
        }
        let d = UserDefaults.standard
        return decode(d.string(forKey: seatKey), reads: d.string(forKey: readsKey))
    }

    static func parse(_ arg: String) -> SeatChoice {
        let bits = arg.split(separator: ":").map(String.init)
        return decode(bits.first, reads: bits.count > 1 ? bits[1] : nil)
    }

    static func decode(_ seat: String?, reads: String?) -> SeatChoice {
        switch seat {
        case nil, "": return .notSet
        case "none": return .conductor
        case let id?: return Seats.info(id) == nil ? .notSet : .seat(id, reads: reads)
        }
    }

    func save(to d: UserDefaults = .standard) {
        switch self {
        case .notSet: d.removeObject(forKey: Self.seatKey); d.removeObject(forKey: Self.readsKey)
        case .conductor: d.set("none", forKey: Self.seatKey); d.removeObject(forKey: Self.readsKey)
        case .seat(let id, let reads): d.set(id, forKey: Self.seatKey); d.set(reads, forKey: Self.readsKey)
        }
    }

    /// Settings' value: "1st Baritone · treble clef in B♭", "I conduct or listen" or "Not set".
    var summary: String {
        switch self {
        case .notSet: return String(localized: "Not set")
        case .conductor: return String(localized: "I conduct or listen")
        case .seat(let id, let reads):
            guard let s = Seats.info(id) else { return String(localized: "Not set") }
            let name = Seats.name(s)
            guard s.reads.count > 1 else { return name }
            return "\(name) · \(Seats.readingInline(reads ?? s.reads[0], seat: s))"
        }
    }
}

/// The contest band's seats and instruments, from the core (`seats()`, `instruments()`), with the
/// words the app shows for them.
enum Seats {
    static let all: [SeatInfo] = seats()
    private static let instrumentsByID: [String: InstrumentInfo] =
        Dictionary(BrasscribeCore.instruments().map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })

    static func info(_ id: String) -> SeatInfo? { all.first { $0.id == id } }
    static func info(part name: String) -> SeatInfo? { all.first { $0.name == name } }

    /// The seat's part name in the musician's language (the core's table).
    static func name(_ s: SeatInfo, language: ScoreLanguage = .current) -> String {
        language == .norwegian ? s.nbName : s.name
    }

    /// The seat's lead part in a lineup ("Solo Cornet"), in the musician's language.
    static func leadName(_ lineup: Lineup) -> String { PartNames.display(lineup.lead) }

    // MARK: keys and clefs

    /// The instrument's key as a pitch class: 10 = B♭, 3 = E♭, 0 = C (sounds as written).
    static func keyClass(instrument id: String) -> Int {
        let c = Int(instrumentsByID[id]?.chromatic ?? 0)
        return ((c % 12) + 12) % 12
    }

    /// "B♭" / «B», "E♭" / «Ess»; nil for an instrument at concert pitch.
    static func keyName(instrument id: String) -> String? {
        switch keyClass(instrument: id) {
        case 10: return String(localized: "B♭")
        case 3: return String(localized: "E♭")
        default: return nil
        }
    }

    /// Fifths to add to a concert key to get the key written on the instrument's part.
    static func writtenShift(instrument id: String) -> Int {
        let c = Int(instrumentsByID[id]?.chromatic ?? 0)
        return (((-c * 7) % 12) + 12) % 12
    }

    /// "Treble clef in B♭" / "Bass clef, as it sounds", for the You read choice.
    static func readingTitle(_ reads: String, seat s: SeatInfo) -> String {
        if reads == "bass" { return String(localized: "Bass clef, as it sounds") }
        guard let k = keyName(instrument: s.instrument) else { return String(localized: "Treble clef") }
        return String(localized: "Treble clef in \(k)")
    }

    /// "treble clef in B♭" inside a sentence (Settings' value).
    static func readingInline(_ reads: String, seat s: SeatInfo) -> String {
        if reads == "bass" { return String(localized: "bass clef, as it sounds") }
        guard let k = keyName(instrument: s.instrument) else { return String(localized: "treble clef") }
        return String(localized: "treble clef in \(k)")
    }

    // MARK: the picker's instruments

    /// One tile of "What do you play?": an instrument and the seats it offers.
    struct Instrument: Identifiable, Hashable {
        let id: String
        let title: String
        let detail: String?
        let seats: [SeatInfo]
        /// ♭ read as "flat" (VoiceOver would say "B, E").
        var accessibilityName: String { [title, detail].compactMap { $0 }.joined(separator: " ").spokenFlats }
    }

    /// In the order players look for them: cornets first, percussion last.
    static var instruments: [Instrument] {
        let order = ["bb-cornet", "bb-trumpet", "eb-soprano-cornet", "flugelhorn", "eb-tenor-horn", "baritone", "euphonium",
                     "tenor-trombone", "bass-trombone", "eb-bass", "bb-bass", "drum-kit"]
        let known = Set(order)
        let ids = order + all.map(\.instrument).filter { !known.contains($0) }.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        return ids.compactMap { id in
            let seats = all.filter { $0.instrument == id }
            guard let first = seats.first else { return nil }
            let inEb = keyClass(instrument: id) == 3 ? String(localized: "in E♭") : nil
            // One part: its own name (the core's). Several: the instrument, then Which part?
            switch (id, seats.count) {
            case ("bb-cornet", _): return Instrument(id: id, title: String(localized: "Cornet"), detail: nil, seats: seats)
            case ("bb-trumpet", _): return Instrument(id: id, title: String(localized: "Trumpet"), detail: String(localized: "in B♭"), seats: seats)
            case ("eb-tenor-horn", _): return Instrument(id: id, title: String(localized: "Tenor Horn"), detail: inEb, seats: seats)
            case ("baritone", _): return Instrument(id: id, title: String(localized: "Baritone"), detail: nil, seats: seats)
            case ("tenor-trombone", _): return Instrument(id: id, title: String(localized: "Trombone"), detail: nil, seats: seats)
            case ("eb-soprano-cornet", _): return Instrument(id: id, title: String(localized: "Soprano"), detail: String(localized: "E♭ cornet"), seats: seats)
            default: return Instrument(id: id, title: name(first), detail: nil, seats: seats)
            }
        }
    }

    static func instrument(of seatID: String) -> Instrument? { instruments.first { $0.seats.contains { $0.id == seatID } } }

    // MARK: your part in a lineup

    /// The seat's part in the lineup (the core's table), nil for an unknown seat.
    static func part(_ seatID: String, in lineup: Lineup) -> SeatPart? {
        try? seatPart(lineup: lineup.coreValue, seat: seatID)
    }

    /// "This small band has no 1st Baritone. Your part here is Euphonium, the closest: the same key and
    /// clef." One sentence per lineup, so Norwegian gets its own definite form. Nil when the seat has
    /// its own part.
    static func mappingNotice(seat s: SeatInfo, lineup: Lineup, part: SeatPart, reads: String?) -> String? {
        guard !part.exact else { return nil }
        let seatName = name(s)
        // A seat that takes a lineup part (a trumpet takes the lead): the part is theirs, written for them.
        if let takes = part.takes, part.part == s.name {
            let word = seatName.lowercased(), taken = PartNames.display(takes)
            switch lineup {
            case .fullBand: return String(localized: "The full brass band has no \(word) part. You get the \(taken) part, written for \(word).")
            default: return String(localized: "The small band has no \(word) part. You get the \(taken) part, written for \(word).")
            }
        }
        guard let partName = part.part.map({ PartNames.display($0) }) else {
            switch lineup {
            case .quartet: return String(localized: "The quartet has no percussion part. Brasscribe opens every part.")
            case .minimalBand, .fullBand: return String(localized: "This small band has no percussion part. Brasscribe opens every part.")
            }
        }
        if part.sameKey {
            switch lineup {
            case .quartet: return String(localized: "The quartet has no \(seatName). Your part here is \(partName), the closest: the same key and clef.")
            case .fullBand: return String(localized: "The full brass band has no \(seatName). Your part here is \(partName), the closest: the same key and clef.")
            default: return String(localized: "This small band has no \(seatName). Your part here is \(partName), the closest: the same key and clef.")
            }
        }
        if reads == "bass" {
            switch lineup {
            case .quartet: return String(localized: "The quartet has no \(seatName). Your part here is \(partName), the closest, in bass clef as it sounds.")
            case .fullBand: return String(localized: "The full brass band has no \(seatName). Your part here is \(partName), the closest, in bass clef as it sounds.")
            default: return String(localized: "This small band has no \(seatName). Your part here is \(partName), the closest, in bass clef as it sounds.")
            }
        }
        let key = partKeyName(part.part!) ?? String(localized: "concert pitch")
        switch lineup {
        case .quartet: return String(localized: "The quartet has no \(seatName). Your part here is \(partName), written for \(key).")
        case .fullBand: return String(localized: "The full brass band has no \(seatName). Your part here is \(partName), written for \(key).")
        default: return String(localized: "This small band has no \(seatName). Your part here is \(partName), written for \(key).")
        }
    }

    /// The notice as one line, for the banner above the part: "The small band has no 1st Baritone —
    /// showing Euphonium". The whole sentence opens from it.
    static func mappingShort(seat s: SeatInfo, lineup: Lineup, part: SeatPart) -> String? {
        guard !part.exact else { return nil }
        let seatName = name(s)
        if let takes = part.takes, part.part == s.name {
            let word = seatName.lowercased(), taken = PartNames.display(takes)
            switch lineup {
            case .fullBand: return String(localized: "The full brass band has no \(word) part — \(taken), written for \(word)")
            default: return String(localized: "The small band has no \(word) part — \(taken), written for \(word)")
            }
        }
        guard let partName = part.part.map({ PartNames.display($0) }) else {
            switch lineup {
            case .quartet: return String(localized: "The quartet has no percussion part — showing every part")
            default: return String(localized: "The small band has no percussion part — showing every part")
            }
        }
        switch lineup {
        case .quartet: return String(localized: "The quartet has no \(seatName) — showing \(partName)")
        case .fullBand: return String(localized: "The full brass band has no \(seatName) — showing \(partName)")
        default: return String(localized: "The small band has no \(seatName) — showing \(partName)")
        }
    }

    /// A score not written for the seat (made before the seat was set): the part the seat would take
    /// ("Solo Cornet" for a trumpet), as a plain mapping.
    static func asTaken(_ sp: SeatPart) -> SeatPart { SeatPart(part: sp.takes, exact: false, sameKey: sp.sameKey, takes: nil) }

    /// The key a lineup part is written in: a band seat's instrument, or the quartet's own parts.
    static func partKeyName(_ part: String) -> String? {
        if let s = info(part: part) { return keyName(instrument: s.instrument) }
        switch part {
        case "1st Cornet", "2nd Cornet": return keyName(instrument: "bb-cornet")
        case "Tenor Horn": return keyName(instrument: "eb-tenor-horn")
        default: return nil
        }
    }

    /// Fifths from concert to the part's written key (0 at concert pitch).
    static func partWrittenShift(_ part: String) -> Int {
        if let s = info(part: part) { return writtenShift(instrument: s.instrument) }
        switch part {
        case "1st Cornet", "2nd Cornet": return writtenShift(instrument: "bb-cornet")
        case "Tenor Horn": return writtenShift(instrument: "eb-tenor-horn")
        default: return 0
        }
    }

    /// The clef the player reads: `reads` when they chose one, else the seat's own first, as the core
    /// writes it. The bass trombone reads bass clef at concert pitch with nothing stored.
    static func reading(_ reads: String?, seat: SeatInfo?) -> String? { reads ?? seat?.reads.first }

    /// The seat is percussion (no clef to read): a solo take can't be written for it, since the pitch
    /// trackers' notes from a drummer's take are no drum part.
    static func isPercussion(_ choice: SeatChoice) -> Bool { choice.id.flatMap { info($0) }?.reads.isEmpty == true }

    static var percussionSoloRefused: String {
        String(localized: "Brasscribe can't write down percussion from a solo take yet. Record the band: you get a percussion part when the recording has drums.")
    }

    /// Can the seat carry the tune ("Who plays the tune?")? The core says (melody or solo roles).
    static func canCarryTune(_ s: SeatInfo) -> Bool { s.tune }
}

/// Where a part comes from, as the core derives it (`part_sources`). The words are the same on every
/// screen and platform, and in the PDF.
enum PartSourceKind: String, Sendable {
    case yourRecording = "your-recording"
    case recording
    case arranged
    /// Nothing to play in this arrangement (Percussion without drums, the Soprano Cornet with no climax).
    case empty

    var title: String {
        switch self {
        case .yourRecording: return String(localized: "From your recording")
        case .recording: return String(localized: "From the recording")
        case .arranged: return String(localized: "Arranged from the band's harmony")
        case .empty: return String(localized: "Nothing to play in this arrangement")
        }
    }

    /// The one-sentence explanation the label opens.
    var explanation: String {
        switch self {
        case .yourRecording, .recording: return String(localized: "Brasscribe wrote down the notes it heard for this part.")
        case .arranged: return String(localized: "Nobody played this part on its own in the recording. Brasscribe wrote it from the chords it heard, so it can differ from your printed part.")
        case .empty: return String(localized: "Nothing in the recording gave this part any notes, so it is left empty.")
        }
    }

    /// Record-mic for what was heard, parts for what was arranged.
    var icon: BrasscribeIcon { self == .arranged || self == .empty ? .parts : .recordMic }

    /// Part name → source, for a score's composition. The composition's own record of how it was
    /// arranged is not kept on the device, so the piece's choice (lineup, seat, reading, lead) is
    /// written into it first.
    static func sources(composition: Composition?, output: OutputChoice?) -> [String: PartSourceKind] {
        guard let composition, let data = try? JSONEncoder().encode(composition),
              var obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return [:] }
        var arrangement: [String: Any] = [:]
        if let output {
            arrangement["lineup"] = output.lineup.coreValue
            arrangement["difficulty"] = output.difficulty.rawValue
            if let s = output.seat {
                arrangement["seat"] = s
                if let r = output.reads { arrangement["reads"] = r }
                if let l = output.lead { arrangement["lead"] = l }
            }
        }
        if !arrangement.isEmpty { obj["arrangement"] = arrangement }
        guard let json = try? JSONSerialization.data(withJSONObject: obj),
              let rows = try? partSources(compositionJson: String(decoding: json, as: UTF8.self)) else { return [:] }
        var out: [String: PartSourceKind] = [:]
        for r in rows { if let k = PartSourceKind(rawValue: r.source) { out[r.part] = k } }
        return out
    }
}

extension String {
    /// "E♭ Bass" → "E flat Bass" for speech; Norwegian names have no ♭.
    var spokenFlats: String {
        guard contains("♭") else { return self }
        return replacingOccurrences(of: "♭", with: String(localized: " flat"))
    }
}

import Foundation
import TabKit

/// What the tab screen says: a mark, read to VoiceOver and shown when it is chosen; the tuning chip; the tab as one
/// element; and what the player says of the recording.
enum TabWords {
    /// The app's words are bokmål (the pitch names follow: H, Ess, Ass).
    static var bokmal: Bool { Bundle.main.preferredLocalizations.first?.hasPrefix("nb") == true }

    // MARK: marks

    /// A pitch's name: "D-flat", or in bokmål "Dess".
    static func pitch(_ step: String, _ alter: Int, bokmal: Bool) -> String {
        if !bokmal {
            return step + (alter == 1 ? "-sharp" : alter == -1 ? "-flat" : alter == 2 ? "-double-sharp" : alter == -2 ? "-double-flat" : "")
        }
        let natural = step == "B" ? "H" : step
        switch alter {
        case 1: return natural + "iss"
        case -1: return step == "E" ? "Ess" : step == "A" ? "Ass" : step == "B" ? "B" : step + "ess"
        case 2: return natural + "ississ"
        case -2: return step == "E" ? "Essess" : step == "A" ? "Assass" : step == "B" ? "Bess" : step + "essess"
        default: return natural
        }
    }

    /// "3rd": strings are named by number, 1st the highest, never by a note name (the tuning changes that).
    static func ordinal(_ n: Int) -> String {
        let all = [String(localized: "1st"), String(localized: "2nd"), String(localized: "3rd"), String(localized: "4th"),
                   String(localized: "5th"), String(localized: "6th"), String(localized: "7th"), String(localized: "8th")]
        return all[safe: n - 1] ?? "\(n)"
    }

    /// "Bar 13, beat 2. 3rd string, fret 7, D-flat. Fretscribe isn't sure about this one."
    static func describe(_ column: TabColumn, bokmal: Bool = bokmal) -> String {
        var parts: [String] = []
        parts.append(column.pickup ? String(localized: "The pickup bar, beat \(column.beat).")
                                   : String(localized: "Bar \(column.barNumber), beat \(column.beat)."))
        for n in column.notes {
            switch n.kind {
            case .doubt:
                let name = n.step.map { pitch($0, n.alter, bokmal: bokmal) }
                if let string = n.string, let fret = n.fret {
                    parts.append(fret == 0 ? String(localized: "\(ordinal(string)) string, open, \(name ?? "").")
                                           : String(localized: "\(ordinal(string)) string, fret \(fret), \(name ?? "")."))
                } else if let name {
                    parts.append(name + ".")
                }
                parts.append(String(localized: "Fretscribe isn't sure about this one."))
            case .noPlace:
                let name = n.step.map { pitch($0, n.alter, bokmal: bokmal) } ?? n.name
                let words: String = switch (name, n.why) {
                case (nil, _): String(localized: "A note here has no place on your instrument. Is the tuning right?")
                case (let name?, .tooLow): String(localized: "\(name) is lower than your lowest string. Is the tuning right?")
                case (let name?, .tooHigh): String(localized: "\(name) is higher than your highest fret. Is the tuning right?")
                case (let name?, .other): String(localized: "\(name) has no place on your instrument here. Is the tuning right?")
                }
                parts.append(words)
            }
        }
        return parts.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }.joined(separator: " ")
    }

    // MARK: the header

    /// A tuning's name, as shown or as spoken ("BEAD" and "DADGAD" are read letter by letter). The one tuning of a
    /// baritone ukulele and of a mandolin (`kind`) is named by its strings, lowest first. An id without words of its own
    /// shows as it is.
    static func tuning(_ id: String, spoken: Bool = false, kind: FrettedInstrument? = nil) -> String {
        switch id {
        case "standard":
            switch kind {
            case .ukuleleBaritone: spoken ? String(localized: "D, G, B, E") : String(localized: "D G B E")
            case .mandolin: spoken ? String(localized: "G, D, A, E") : String(localized: "G D A E")
            default: String(localized: "Standard")
            }
        case "eb-standard": String(localized: "E-flat standard (half a step down)")
        case "d-standard": String(localized: "D standard (a whole step down)")
        case "c-standard": String(localized: "C standard (two whole steps down)")
        case "drop-d": String(localized: "Drop D")
        case "drop-c": String(localized: "Drop C")
        case "drop-b": String(localized: "Drop B")
        case "dadgad": spoken ? String(localized: "D, A, D, G, A, D") : String(localized: "DADGAD")
        case "open-g": String(localized: "Open G")
        case "open-d": String(localized: "Open D")
        case "open-e": String(localized: "Open E")
        case "bead": spoken ? String(localized: "B, E, A, D") : String(localized: "BEAD")
        case "drop-a": String(localized: "Drop A")
        case "high-g": String(localized: "High G")
        case "low-g": String(localized: "Low G")
        default: id
        }
    }

    static func capo(_ fret: Int) -> String { fret > 0 ? String(localized: "capo \(fret)") : String(localized: "no capo") }

    /// The tuning chip as it is shown: "Standard · no capo".
    static func chip(_ sheet: TabSheet) -> String {
        String(localized: "\(tuning(sheet.tuning, kind: sheet.preset?.kind)) · \(capo(sheet.capo))")
    }

    /// The tuning chip as it is read: "Tuning: Standard, no capo".
    static func chipName(_ sheet: TabSheet) -> String {
        String(localized: "Tuning: \(tuning(sheet.tuning, spoken: true, kind: sheet.preset?.kind)), \(capo(sheet.capo))")
    }

    static func tempo(_ bpm: Int) -> String { String(localized: "♩ = \(bpm)") }
    static func tempoSpoken(_ bpm: Int) -> String { String(localized: "\(bpm) beats a minute") }

    /// "2 notes marked ? · Check them", under the chip.
    static func markedLine(_ n: Int) -> String {
        n == 1 ? String(localized: "\(n) note marked ? · Check it") : String(localized: "\(n) notes marked ? · Check them")
    }

    static func noPlaceLine(_ n: Int) -> String {
        n == 1 ? String(localized: "\(n) note with no place") : String(localized: "\(n) notes with no place")
    }

    static func marked(_ n: Int) -> String {
        n == 1 ? String(localized: "\(n) note marked ?") : String(localized: "\(n) notes marked ?")
    }

    static func bars(_ n: Int) -> String { n == 1 ? String(localized: "\(n) bar") : String(localized: "\(n) bars") }

    static func layout(_ layout: TabLayoutKind) -> String {
        switch layout {
        case .tab: String(localized: "Tab")
        case .tabAndNotation: String(localized: "Tab and notation")
        case .notation: String(localized: "Notation")
        }
    }

    /// The tab as one element: "Bass line. Tab. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?.
    /// 1 note with no place."
    static func summary(title: String, _ sheet: TabSheet) -> String {
        let parts: [String?] = [
            title.isEmpty ? nil : title,
            layout(sheet.layout),
            chipName(sheet),
            sheet.tempo.map(tempoSpoken),
            bars(sheet.index.bars),
            sheet.marks.doubtful > 0 ? marked(sheet.marks.doubtful) : nil,
            sheet.marks.noPlace > 0 ? noPlaceLine(sheet.marks.noPlace) : nil,
        ]
        return parts.compactMap { $0 }.joined(separator: ". ") + "."
    }

    // MARK: the player

    /// Where the song is: "Bar 13, beat 2", or "Pickup bar, beat 1"; empty when it is nowhere yet.
    static func place(_ measure: TabMeasure?, beat: Int) -> String {
        guard let measure else { return "" }
        return measure.pickup ? String(localized: "Pickup bar, beat \(beat)") : String(localized: "Bar \(measure.number), beat \(beat)")
    }

    /// What the player says instead of its controls, when it has no recording to play: nil when it plays.
    static func says(_ state: RecordingState, follows: Bool, canFetch: Bool) -> String? {
        if !follows { return String(localized: "Fretscribe can't follow the recording in this tab. You can still read it.") }
        switch state {
        case .here, .looking: return nil
        case .getting: return String(localized: "Getting the recording from your computer…")
        case .gone: return String(localized: "Your computer doesn't have the recording any more. You can still read the tab.")
        case .noAnswer: return String(localized: "The recording didn't come. Is your computer on?")
        case .updateApp:
            return String(localized: "Update this app. Bandroom on your computer is newer than this app, and they only work together when both are up to date.")
        case .updateComputer:
            return String(localized: "Update Bandroom on your computer. This app is newer than Bandroom there, and they only work together when both are up to date.")
        case .noRoom: return String(localized: "There is no room on this device for the recording. You can still read the tab.")
        case .tooLarge: return String(localized: "The recording is too large to keep on this device. You can still read the tab.")
        case .unplayable: return String(localized: "This device can't play the recording. You can still read the tab.")
        case .notHere:
            return canFetch ? String(localized: "The recording is not on this device.")
                            : String(localized: "The recording is not on this device. Connect to your computer to get it. You can still read the tab.")
        }
    }

    /// The recording can be asked for again: it is not here, or the last try did not get through.
    static func offersFetch(_ state: RecordingState) -> Bool { state == .notHere || state == .noAnswer || state == .noRoom }

    /// The repeat chip's words, which are its name: "Repeat bars", "Repeating 3", "Repeating 3–6".
    static func repeatChip(_ bars: RepeatBars?, number: (Int) -> String) -> String {
        guard let bars else { return String(localized: "Repeat bars") }
        return bars.first == bars.last ? String(localized: "Repeating \(number(bars.first))")
                                       : String(localized: "Repeating \(number(bars.first))–\(number(bars.last))")
    }
}

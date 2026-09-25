import Foundation

public enum PitchMode: String, Sendable, CaseIterable {
    case written, concert
}

/// Language for spoken score descriptions. Norwegian uses its own note names
/// (H for B natural, B for B-flat, -iss/-ess suffixes).
public enum ScoreLanguage: String, Sendable, CaseIterable {
    case english = "en", norwegian = "nb"

    public static var current: ScoreLanguage {
        let code = Locale.preferredLanguages.first?.prefix(2) ?? "en"
        return (code == "nb" || code == "no" || code == "nn") ? .norwegian : .english
    }
}

/// Per-note transcription confidence carried over to the arranged parts.
///
/// Confidence is measured only on the transcribed source voices in the Composition. An
/// arranged note inherits it when a source note sounds the same pitch class at the same
/// time; everything else is treated as certain. The talking score says "uncertain" only
/// for inherited low confidence.
public struct UncertaintyIndex: Sendable {
    public static let threshold = 0.7
    /// (composition tick, pitch class) -> lowest confidence at that onset
    let byOnset: [Int: [Int: Double]]
    let ticksPerBeat: Int

    public init(composition: Composition) {
        var m: [Int: [Int: Double]] = [:]
        for v in composition.voices {
            for n in v.notes where n.confidence < 1 {
                let pc = ((n.pitch % 12) + 12) % 12
                m[n.start, default: [:]][pc] = min(m[n.start]?[pc] ?? 1, n.confidence)
            }
        }
        byOnset = m
        ticksPerBeat = composition.ticksPerBeat
    }

    public static let empty = UncertaintyIndex()
    private init() { byOnset = [:]; ticksPerBeat = 24 }

    /// Confidence for an arranged note (1 when no source note matches).
    public func confidence(startTick: Int, concertPitch: Int) -> Double {
        let t = Int((Double(startTick) * Double(ticksPerBeat) / Double(Score.ticksPerQuarter)).rounded())
        return byOnset[t]?[((concertPitch % 12) + 12) % 12] ?? 1
    }

    public func isUncertain(_ note: ScoreNote) -> Bool {
        guard let p = note.midiPitch, case .pitched = note.kind else { return false }
        return confidence(startTick: note.startTick, concertPitch: p) < Self.threshold
    }

    public var isEmpty: Bool { byOnset.isEmpty }
}

/// Text descriptions of a score for screen readers and the talking-score export:
/// "Bar 12, beat 1: E-flat 5, quarter note, uncertain".
public struct TalkingScore: Sendable {
    public var score: Score
    public var language: ScoreLanguage
    public var pitchMode: PitchMode
    public var uncertainty: UncertaintyIndex

    public init(score: Score, language: ScoreLanguage = .current, pitchMode: PitchMode = .written,
                uncertainty: UncertaintyIndex = .empty) {
        self.score = score; self.language = language; self.pitchMode = pitchMode; self.uncertainty = uncertainty
    }

    // MARK: vocabulary

    var nb: Bool { language == .norwegian }

    public func noteName(_ p: SpelledPitch) -> String {
        if nb {
            let base: String
            switch (p.step, p.alter) {
            case ("B", -1): return "B \(p.octave)"
            case ("B", 0): base = "H"
            case ("B", let a): base = "H" + suffixNB(a)
            case ("E", -1): return "Ess \(p.octave)"
            case ("A", -1): return "Ass \(p.octave)"
            case (let s, let a): base = s + suffixNB(a)
            }
            return "\(base) \(p.octave)"
        }
        let acc: String
        switch p.alter {
        case -2: acc = "-double-flat"
        case -1: acc = "-flat"
        case 1: acc = "-sharp"
        case 2: acc = "-double-sharp"
        default: acc = ""
        }
        return "\(p.step)\(acc) \(p.octave)"
    }

    private func suffixNB(_ a: Int) -> String {
        switch a {
        case -2: return "essess"
        case -1: return "ess"
        case 1: return "iss"
        case 2: return "ississ"
        default: return ""
        }
    }

    public func durationName(type: String?, dots: Int, ticks: Int) -> String {
        let t = type ?? Self.guessType(ticks: ticks, dots: dots)
        let en = ["whole": "whole note", "half": "half note", "quarter": "quarter note", "eighth": "eighth note",
                  "16th": "sixteenth note", "32nd": "thirty-second note", "64th": "sixty-fourth note", "breve": "double whole note"]
        let no = ["whole": "helnote", "half": "halvnote", "quarter": "fjerdedelsnote", "eighth": "åttendedelsnote",
                  "16th": "sekstendedelsnote", "32nd": "trettitodelsnote", "64th": "sekstifiredelsnote", "breve": "dobbel helnote"]
        let base = (nb ? no : en)[t] ?? t
        switch dots {
        case 0: return base
        case 1: return (nb ? "punktert " : "dotted ") + base
        default: return (nb ? "dobbeltpunktert " : "double-dotted ") + base
        }
    }

    static func guessType(ticks: Int, dots: Int) -> String {
        let q = Double(ticks) / Double(Score.ticksPerQuarter) / (dots == 1 ? 1.5 : dots >= 2 ? 1.75 : 1)
        switch q {
        case 3...: return "whole"
        case 1.5...: return "half"
        case 0.75...: return "quarter"
        case 0.375...: return "eighth"
        case 0.1875...: return "16th"
        default: return "32nd"
        }
    }

    public func drumName(_ key: Int) -> String {
        let en: [Int: String] = [35: "bass drum", 36: "bass drum", 37: "side stick", 38: "snare", 40: "snare",
                                 41: "floor tom", 43: "floor tom", 45: "tom", 47: "tom", 48: "high tom", 50: "high tom",
                                 42: "closed hi-hat", 44: "pedal hi-hat", 46: "open hi-hat", 49: "crash cymbal",
                                 51: "ride cymbal", 53: "ride bell"]
        let no: [Int: String] = [35: "stortromme", 36: "stortromme", 37: "kantslag", 38: "skarptromme", 40: "skarptromme",
                                 41: "gulvtam", 43: "gulvtam", 45: "tam", 47: "tam", 48: "høy tam", 50: "høy tam",
                                 42: "lukket hihat", 44: "pedal-hihat", 46: "åpen hihat", 49: "crashcymbal",
                                 51: "ridecymbal", 53: "ride-klokke"]
        return (nb ? no : en)[key] ?? (nb ? "slagverk" : "percussion")
    }

    public func pitch(of note: ScoreNote, in part: Part) -> String? {
        switch note.kind {
        case .rest: return nil
        case .unpitched: return drumName(note.midiPitch ?? 0)
        case .pitched(let written):
            if pitchMode == .written || part.transposeSemitones == 0 { return noteName(written) }
            return noteName(SpelledPitch.spelling(midi: note.midiPitch ?? written.midi, fifths: part.concertFifths))
        }
    }

    // MARK: descriptions

    public func barLabel(_ index: Int) -> String {
        (nb ? "Takt " : "Bar ") + (score.measures.indices.contains(index) ? score.measures[index].number : "\(index + 1)")
    }

    public func beatLabel(_ beat: Double) -> String {
        let whole = beat.rounded(.down)
        let frac = beat - whole
        let b = Int(whole)
        let word = nb ? "slag" : "beat"
        if frac < 0.01 { return "\(word) \(b)" }
        if abs(frac - 0.5) < 0.01 { return nb ? "\(word) \(b) og" : "\(word) \(b) and" }
        return String(format: "%@ %.2f", word, beat)
    }

    /// One phrase per onset in the bar: "beat 1: E-flat 5, quarter note, uncertain".
    public func events(part: Part, measureIndex: Int) -> [String] {
        let notes = part.notes(inMeasure: measureIndex)
        guard !notes.isEmpty else { return [nb ? "tom takt" : "empty bar"] }
        let m = score.measures[measureIndex]
        if notes.allSatisfy(\.isRest) {
            return [nb ? "pause hele takten" : "rest for the whole bar"]
        }
        var groups: [(Int, [ScoreNote])] = []
        for n in notes {
            if let last = groups.last, last.0 == n.startTick { groups[groups.count - 1].1.append(n) }
            else { groups.append((n.startTick, [n])) }
        }
        return groups.map { tick, ns in
            let beat = 1 + Double(tick - m.startTick) / Double(m.beatTicks)
            let head = ns[0]
            if head.isRest {
                return "\(beatLabel(beat)): \(nb ? "pause" : "rest"), \(durationName(type: head.type, dots: head.dots, ticks: head.durTicks))"
            }
            let pitches = ns.compactMap { pitch(of: $0, in: part) }.joined(separator: nb ? " og " : " and ")
            var s = "\(beatLabel(beat)): \(pitches), \(durationName(type: head.type, dots: head.dots, ticks: head.durTicks))"
            if head.tieStop { s += nb ? ", bundet fra forrige" : ", tied from previous" }
            if ns.contains(where: uncertainty.isUncertain) { s += nb ? ", usikker" : ", uncertain" }
            return s
        }
    }

    /// Full spoken description of one bar of one part.
    public func describe(part: Part, measureIndex: Int) -> String {
        "\(barLabel(measureIndex)), \(part.name). " + events(part: part, measureIndex: measureIndex).joined(separator: ". ") + "."
    }

    /// Plain-text talking score of the whole piece: a heading per part, a line per bar.
    public func text(parts: [Part]? = nil) -> String {
        var out = "\(score.title)\n"
        out += nb ? "Tempo \(Int(score.tempoBPM)) slag per minutt. \(score.measures.count) takter.\n"
                  : "Tempo \(Int(score.tempoBPM)) beats per minute. \(score.measures.count) bars.\n"
        out += pitchMode == .written ? (nb ? "Skrevet toneart.\n" : "Written pitch.\n")
                                     : (nb ? "Klingende tonehøyde.\n" : "Concert pitch.\n")
        for p in parts ?? score.parts {
            out += "\n## \(p.name)\n"
            for i in score.measures.indices {
                out += "\(barLabel(i)): " + events(part: p, measureIndex: i).joined(separator: "; ") + "\n"
            }
        }
        return out
    }
}

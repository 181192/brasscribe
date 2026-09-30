import Foundation

public enum MusicXMLError: Error, Equatable, CustomStringConvertible {
    case notPartwise
    case malformed(String)

    public var description: String {
        switch self {
        case .notPartwise: return "not a score-partwise MusicXML document"
        case .malformed(let s): return "malformed MusicXML: \(s)"
        }
    }
}

/// Reads uncompressed score-partwise MusicXML into a `Score`.
///
/// Covers what the brasscribe arranger writes and common exports: multiple parts,
/// `<chord>`, `<backup>`/`<forward>`, ties, transposing instruments
/// (`<chromatic>` + `<octave-change>`), unpitched percussion, per-part `<divisions>`
/// and `<sound tempo>`. Grace notes and cue notes are not played (cue notes still take their time).
/// Dynamic marks, hairpins and accents give each note its velocity (`Dynamics`).
///
/// Values that would make the score unplayable (a non-finite or huge alteration, a beat type that is not
/// a power of two, more than 255 beats in a bar, huge divisions or durations, a part with no bars) throw
/// `.malformed`, so a broken file is refused on import instead of crashing playback or export. Tempo marks
/// outside `tempoRange` are ignored.
public enum MusicXMLParser {
    public static func parse(_ data: Data) throws -> Score {
        let d = Delegate()
        let p = XMLParser(data: data)
        p.shouldResolveExternalEntities = false
        p.delegate = d
        guard p.parse() else {
            if let e = d.error { throw e }
            throw MusicXMLError.malformed(p.parserError?.localizedDescription ?? "parse failed")
        }
        if let e = d.error { throw e }
        return try d.build()
    }

    public static func parse(url: URL) throws -> Score { try parse(Data(contentsOf: url)) }

    /// Tempo marks (quarter notes per minute) the parser keeps; others are ignored.
    public static let tempoRange: ClosedRange<Double> = 4...1000
    /// Largest `<divisions>` accepted.
    static let maxDivisions = 1_000_000
    /// Longest note, forward or backup, in quarter notes.
    static let maxDurationQuarters = 1024
    /// Longest part, in quarter notes.
    static let maxScoreQuarters = 100_000

    /// Semitones from a trilled note up to its auxiliary: the next letter up, with the accidental-mark's
    /// alteration, else the key signature's (accidentals earlier in the bar are not read, as the arranger writes it).
    public static func trillSemitones(_ p: SpelledPitch, accidentalMark: String?, fifths: Int) -> Int {
        let steps = ["C", "D", "E", "F", "G", "A", "B"]
        let i = steps.firstIndex(of: p.step) ?? 0
        let auxStep = steps[(i + 1) % 7]
        let marks = ["sharp": 1, "natural": 0, "flat": -1, "double-sharp": 2, "sharp-sharp": 2, "flat-flat": -2]
        let alter = accidentalMark.flatMap { marks[$0] } ?? SpelledPitch.keyAlter(step: auxStep, fifths: fifths)
        let aux = SpelledPitch(step: auxStep, alter: alter, octave: p.octave + (i == 6 ? 1 : 0))
        return aux.midi - p.midi
    }

    /// General MIDI drum key for an unpitched note, inverting the arranger's drum map
    /// (display position on a five-line percussion staff plus notehead).
    public static func drumKey(displayStep: String, displayOctave: Int, notehead: String) -> Int {
        switch (displayStep, displayOctave, notehead) {
        case ("F", 4, _), ("E", 4, _): return 36
        case ("C", 5, "x"): return 37
        case ("C", 5, _): return 38
        case ("A", 4, _): return 43
        case ("D", 5, _): return 47
        case ("E", 5, _): return 50
        case ("G", 5, "circle-x"): return 46
        case ("G", 5, _): return 42
        case ("D", 4, _): return 44
        case ("A", 5, _): return 49
        case ("F", 5, "diamond"): return 53
        case ("F", 5, _): return 51
        default: return 56
        }
    }
}

private final class Delegate: NSObject, XMLParserDelegate {
    struct PartInfo {
        var id = "", name = "", abbreviation = "", instrumentName = "", instrumentSound = ""
        var midiProgram: Int?, midiChannel = 1
        /// `<midi-unpitched>` (1-based) of each `<midi-instrument>`: the drum a note naming that instrument plays.
        var unpitched: [String: Int] = [:]
        var midiInstrument: String?
    }
    struct RawNote {
        var isRest = false, isChord = false, isGrace = false, isCue = false
        var step = "", alter = 0, octave = 4
        var unpitched = false, displayStep = "", displayOctave = 4, notehead = "normal"
        var duration = 0, type: String?, dots = 0, tieStart = false, tieStop = false
        var hasPitch = false
        var accent = 0
        var trill = false, trillAccidental: String?, staccato = false
        var instrument: String?
    }
    struct RawMeasure { var number = "", start = 0, maxPos = 0, beats = 4, beatType = 4, fifths = 0 }

    var error: MusicXMLError?
    var title = "", movementTitle = ""
    var partInfos: [String: PartInfo] = [:]
    var partOrder: [String] = []
    var currentInfo: PartInfo?
    var tempos: [Int: Double] = [:]
    var directions: [Score.Direction] = []
    var partDynamics: [String: [Int: String]] = [:]
    var partWedges: [String: [Wedge]] = [:]
    var openWedges: [String: (Wedge.Kind, Int)] = [:] // wedge number -> kind, start tick (current part)
    var mark = Dynamics.defaultMark // the dynamic in effect, in document order
    var firstPart: String?
    var currentTick: Int { partTick + toTicks(pos) }

    // Per-part parse state
    var partMeasures: [String: [RawMeasure]] = [:]
    var partNotes: [String: [ScoreNote]] = [:]
    var partTranspose: [String: Int] = [:]
    var partPercussion: [String: Bool] = [:]
    var partFifths: [String: Int] = [:]
    var partMarked: Set<String> = []
    var curPart: String?
    var divisions = 1
    var pos = 0 // in divisions within the current measure
    var lastNoteStart = 0
    var measure = RawMeasure()
    var measureIndex = -1
    var partTick = 0 // tick of the current measure start
    var beats = 4, beatType = 4, fifths = 0
    var chromatic = 0, octaveChange = 0
    var note: RawNote?
    var inBackup = false, inForward = false, inTranspose = false
    var moveDuration = 0
    var text = ""
    var stack: [String] = []

    func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes a: [String: String] = [:]) {
        stack.append(name)
        text = ""
        switch name {
        case "score-timewise":
            error = .notPartwise; parser.abortParsing()
        case "score-part":
            currentInfo = PartInfo(id: a["id"] ?? "P\(partOrder.count + 1)")
        case "midi-instrument":
            currentInfo?.midiInstrument = a["id"]
        case "instrument" where note != nil:
            note?.instrument = a["id"]
        case "part":
            let id = a["id"] ?? "P\(partMeasures.count + 1)"
            curPart = id
            if firstPart == nil { firstPart = id }
            partMeasures[id] = []
            partNotes[id] = []
            divisions = 1; beats = 4; beatType = 4; fifths = 0; chromatic = 0; octaveChange = 0
            measureIndex = -1; partTick = 0
            mark = Dynamics.defaultMark; openWedges = [:]
        case "measure":
            measureIndex += 1
            measure = RawMeasure(number: a["number"] ?? "\(measureIndex + 1)", start: partTick)
            pos = 0; lastNoteStart = 0
        case "note":
            note = RawNote()
            if a["color"] != nil, let p = curPart { partMarked.insert(p) }
        case "notehead":
            if a["color"] != nil, let p = curPart { partMarked.insert(p) }
        case "rest": note?.isRest = true
        case "chord": note?.isChord = true
        case "grace": note?.isGrace = true
        case "cue": note?.isCue = true
        case "unpitched": note?.unpitched = true
        case "pitch": note?.hasPitch = true
        case "dot": note?.dots += 1
        case "tie":
            if a["type"] == "start" { note?.tieStart = true }
            if a["type"] == "stop" { note?.tieStop = true }
        case "backup": inBackup = true; moveDuration = 0
        case "forward": inForward = true; moveDuration = 0
        case "transpose": inTranspose = true; chromatic = 0; octaveChange = 0
        case "sound":
            if let t = a["tempo"], let v = Double(t), MusicXMLParser.tempoRange.contains(v), tempos[currentTick] == nil {
                tempos[currentTick] = v
            }
        case _ where Dynamics.isMark(name) && stack.dropLast().last == "dynamics":
            if let part = curPart {
                partDynamics[part, default: [:]][note == nil ? currentTick : partTick + toTicks(note!.isChord ? lastNoteStart : pos)] = name
                mark = name
            }
        case "trill-mark" where stack.dropLast().last == "ornaments": note?.trill = true
        case "staccato" where stack.dropLast().last == "articulations": note?.staccato = true
        case "accent", "strong-accent":
            if stack.dropLast().last == "articulations", let n = note { note?.accent = max(n.accent, Dynamics.accentSteps[name] ?? 0) }
        case "wedge":
            guard let part = curPart else { break }
            let number = a["number"] ?? "1"
            switch a["type"] {
            case "crescendo": openWedges[number] = (.crescendo, currentTick)
            case "diminuendo": openWedges[number] = (.diminuendo, currentTick)
            case "stop":
                if let (kind, start) = openWedges.removeValue(forKey: number), currentTick > start {
                    partWedges[part, default: []].append(Wedge(kind: kind, startTick: start, stopTick: currentTick))
                }
            default: break
            }
        default: break
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) { text += string }

    func parser(_ parser: XMLParser, didEndElement name: String, namespaceURI: String?, qualifiedName qName: String?) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let parent = stack.count >= 2 ? stack[stack.count - 2] : ""
        defer { stack.removeLast(); text = "" }

        if var info = currentInfo {
            switch name {
            case "part-name": info.name = t
            case "part-abbreviation": info.abbreviation = t
            case "instrument-name": if info.instrumentName.isEmpty { info.instrumentName = t }
            case "instrument-sound": if info.instrumentSound.isEmpty { info.instrumentSound = t }
            case "midi-program": info.midiProgram = Int(t).flatMap { (1...128).contains($0) ? $0 : nil }
            case "midi-channel": info.midiChannel = Int(t) ?? 1
            case "midi-unpitched": if let id = info.midiInstrument, let k = Int(t) { info.unpitched[id] = k }
            case "score-part":
                partInfos[info.id] = info; partOrder.append(info.id); currentInfo = nil; return
            default: break
            }
            currentInfo = info
            return
        }

        switch name {
        case "work-title": title = t
        case "words" where curPart == firstPart && !t.isEmpty && t != "?":
            directions.append(.init(tick: currentTick, kind: .words, text: t))
        case "rehearsal" where curPart == firstPart && !t.isEmpty:
            directions.append(.init(tick: currentTick, kind: .rehearsal, text: t))
        case "movement-title": movementTitle = t
        case "divisions":
            let d = Int(t) ?? 1
            guard d <= MusicXMLParser.maxDivisions else { return fail(parser, "divisions \(t)") }
            divisions = max(1, d)
        case "fifths":
            fifths = Int(t) ?? 0
            if let p = curPart, partFifths[p] == nil { partFifths[p] = fifths }
        case "beats":
            let terms = t.split(separator: "+").compactMap { Int($0) }
            guard terms.allSatisfy({ (0...255).contains($0) }) else { return fail(parser, "beats \(t)") }
            let b = terms.reduce(0, +)
            guard b <= 255 else { return fail(parser, "beats \(t)") }
            beats = b > 0 ? b : 4
        case "beat-type":
            // a note value: 1, 2, 4, 8, …
            let bt = Int(t) ?? 4
            guard (1...1024).contains(bt), bt & (bt - 1) == 0 else { return fail(parser, "beat-type \(t)") }
            beatType = bt
        case "chromatic":
            guard inTranspose else { break }
            let c = Int(t) ?? 0
            guard (-48...48).contains(c) else { return fail(parser, "chromatic \(t)") }
            chromatic = c
        case "octave-change":
            guard inTranspose else { break }
            let o = Int(t) ?? 0
            guard (-8...8).contains(o) else { return fail(parser, "octave-change \(t)") }
            octaveChange = o
        case "transpose": inTranspose = false
        case "sign": if t == "percussion", let p = curPart { partPercussion[p] = true }
        case "step": if parent == "pitch" { note?.step = t }
        case "alter" where parent == "pitch":
            let v = Double(t) ?? 0
            guard v.isFinite, abs(v) <= 2 else { return fail(parser, "alter \(t)") }
            note?.alter = Int(v.rounded())
        case "octave" where parent == "pitch":
            let o = Int(t) ?? 4
            guard (0...9).contains(o) else { return fail(parser, "octave \(t)") }
            note?.octave = o
        case "accidental-mark" where parent == "ornaments": note?.trillAccidental = t
        case "display-step": note?.displayStep = t
        case "display-octave": note?.displayOctave = Int(t) ?? 4
        case "notehead": note?.notehead = t
        case "type": if parent == "note" { note?.type = t }
        case "duration":
            let d = Int(t) ?? 0
            guard d >= 0, d <= divisions * MusicXMLParser.maxDurationQuarters else { return fail(parser, "duration \(t)") }
            if inBackup || inForward { moveDuration = d } else { note?.duration = d }
        case "backup":
            pos = max(0, pos - moveDuration); inBackup = false
        case "forward":
            pos += moveDuration; measure.maxPos = max(measure.maxPos, pos); inForward = false
            guard pos <= divisions * MusicXMLParser.maxScoreQuarters else { return fail(parser, "bar too long") }
        case "note":
            if let n = note { addNote(n) }
            note = nil
            guard pos <= divisions * MusicXMLParser.maxScoreQuarters else { return fail(parser, "bar too long") }
        case "attributes":
            measure.beats = beats; measure.beatType = beatType; measure.fifths = fifths
            if let p = curPart { partTranspose[p] = chromatic + 12 * octaveChange }
        case "measure":
            measure.beats = beats; measure.beatType = beatType; measure.fifths = fifths
            if let p = curPart {
                partMeasures[p, default: []].append(measure)
                let nominal = beats * divisions * 4 / max(1, beatType)
                let len = measure.maxPos > 0 ? measure.maxPos : nominal
                partTick += toTicks(len)
                guard partTick <= MusicXMLParser.maxScoreQuarters * Score.ticksPerQuarter else { return fail(parser, "score too long") }
            }
        case "part": curPart = nil
        default: break
        }
    }

    func toTicks(_ d: Int) -> Int { d * Score.ticksPerQuarter / divisions }

    /// Stops the parse with `.malformed`; the first failure wins.
    func fail(_ parser: XMLParser, _ why: String) {
        if error == nil { error = .malformed(why) }
        parser.abortParsing()
    }

    func addNote(_ n: RawNote) {
        guard let p = curPart, !n.isGrace else { return }
        let start = n.isChord ? lastNoteStart : pos
        if !n.isChord {
            lastNoteStart = pos
            pos += n.duration
            measure.maxPos = max(measure.maxPos, pos)
        }
        // a cue note takes its time in the bar but is not played
        if n.isCue { return }
        let kind: ScoreNote.Kind
        var midi: Int?
        if n.isRest {
            kind = .rest
        } else if n.unpitched {
            kind = .unpitched(displayStep: n.displayStep, displayOctave: n.displayOctave, notehead: n.notehead)
            // the instrument's <midi-unpitched> when the note names one, else the arranger's drum map by position
            if let id = n.instrument, let k = partInfos[p]?.unpitched[id], (1...128).contains(k) {
                midi = k - 1
            } else {
                midi = MusicXMLParser.drumKey(displayStep: n.displayStep, displayOctave: n.displayOctave, notehead: n.notehead)
            }
        } else {
            let sp = SpelledPitch(step: n.step, alter: n.alter, octave: n.octave)
            kind = .pitched(written: sp)
            midi = sp.midi + chromatic + 12 * octaveChange
        }
        var trill = 0
        if n.trill, case .pitched(let sp) = kind { trill = MusicXMLParser.trillSemitones(sp, accidentalMark: n.trillAccidental, fifths: fifths) }
        partNotes[p, default: []].append(ScoreNote(
            kind: kind, measureIndex: measureIndex, startTick: partTick + toTicks(start),
            durTicks: toTicks(n.duration), type: n.type, dots: n.dots, isChordTone: n.isChord,
            tieStart: n.tieStart, tieStop: n.tieStop, midiPitch: midi, dynamic: mark, accent: n.accent,
            trill: trill, staccato: n.staccato))
    }

    /// Each note's velocity: its mark, moved by any hairpin it starts in, plus its accent.
    static func withVelocities(_ notes: [ScoreNote], wedges: [Wedge], marks: [Int: String]) -> [ScoreNote] {
        var out = notes
        let order = out.indices.sorted { out[$0].startTick < out[$1].startTick }
        for i in order {
            let t = out[i].startTick
            var v = Double(Dynamics.velocity(mark: out[i].dynamic))
            for w in wedges where t >= w.startTick {
                let by = Double(w.kind == .crescendo ? Dynamics.step : -Dynamics.step)
                let end = target(of: w, marks: marks)
                if t >= w.stopTick {
                    // with no mark at its end, the music stays a step louder or softer until the next mark
                    let next = marks.keys.filter { $0 >= w.stopTick }.min() ?? .max
                    if end == nil, t < next { v += by }
                    continue
                }
                let startMark = order.first { out[$0].startTick >= w.startTick }.map { out[$0].dynamic } ?? out[i].dynamic
                let v0 = Double(Dynamics.velocity(mark: startMark))
                let v1 = end.map { Double(Dynamics.velocity(mark: $0)) } ?? v0 + by
                v = v0 + (v1 - v0) * Double(t - w.startTick) / Double(w.stopTick - w.startTick)
            }
            out[i].velocity = Dynamics.clamp(Int(v.rounded()) + out[i].accent * Dynamics.step)
        }
        return out
    }

    /// The first mark at or up to a bar after a hairpin's end.
    static func target(of w: Wedge, marks: [Int: String]) -> String? {
        marks.filter { $0.key >= w.stopTick && $0.key <= w.stopTick + 4 * Score.ticksPerQuarter }.min { $0.key < $1.key }?.value
    }

    func build() throws -> Score {
        let ids = partOrder.filter { partMeasures[$0] != nil } + partMeasures.keys.filter { !partOrder.contains($0) }.sorted()
        guard let first = ids.first, let raw = partMeasures[first] else { throw MusicXMLError.malformed("no parts") }
        guard !raw.isEmpty else { throw MusicXMLError.malformed("no bars") }
        var measures: [Measure] = []
        for (i, m) in raw.enumerated() {
            let next = i + 1 < raw.count ? raw[i + 1].start : nil
            let len = next.map { $0 - m.start } ?? (m.beats * Score.ticksPerQuarter * 4 / max(1, m.beatType))
            measures.append(Measure(number: m.number, startTick: m.start, lengthTicks: len,
                                    beats: m.beats, beatType: m.beatType, fifths: m.fifths))
        }
        if let last = measures.last, let lastEnd = partNotes.values.flatMap({ $0 }).map(\.endTick).max(),
           lastEnd > last.startTick + last.lengthTicks {
            measures[measures.count - 1].lengthTicks = lastEnd - last.startTick
        }
        for id in ids { partNotes[id] = Self.withVelocities(partNotes[id] ?? [], wedges: partWedges[id] ?? [], marks: partDynamics[id] ?? [:]) }
        let parts = ids.map { id -> Part in
            let info = partInfos[id] ?? PartInfo(id: id, name: id)
            let perc = partPercussion[id] ?? false || info.instrumentSound.hasPrefix("drum") || info.midiChannel == 10
            return Part(id: id, name: info.name, abbreviation: info.abbreviation, instrumentName: info.instrumentName,
                        instrumentSound: info.instrumentSound, midiProgram: info.midiProgram,
                        midiChannel: info.midiChannel, transposeSemitones: partTranspose[id] ?? 0,
                        isPercussion: perc, writtenFifths: partFifths[id] ?? 0, notes: partNotes[id] ?? [],
                        dynamics: partDynamics[id] ?? [:], wedges: partWedges[id] ?? [], measureFifths: partMeasures[id]?.map(\.fifths) ?? [],
                        hasMarks: partMarked.contains(id))
        }
        var tempoList = tempos.sorted { $0.key < $1.key }.map { Score.Tempo(tick: $0.key, bpm: $0.value) }
        if let first = tempoList.first, first.tick > 0 { tempoList.insert(.init(tick: 0, bpm: first.bpm), at: 0) }
        return Score(title: title.isEmpty ? movementTitle : title, parts: parts, measures: measures, tempos: tempoList,
                     directions: directions.sorted { $0.tick < $1.tick })
    }
}

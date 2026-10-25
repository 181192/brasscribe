import Foundation

/// One written piece of a note in tab.musicxml. A note is one piece, or several tied ones when it crosses a
/// beat or a bar line, and it is written on each staff of a pair.
public struct TabPiece: Equatable, Sendable {
    /// The note's place in the tab's `notes` (the `<?fretted-note N?>` instruction).
    public var note: Int
    /// 0 is the first staff of the part.
    public var staff: Int
    /// The measure, counted from 0 in the order they are written (a pickup is the first).
    public var bar: Int
    /// The measure's printed number: 0 for a pickup.
    public var barNumber: String
    /// From the start of the measure, in `TabIndex.ticks` to a quarter note.
    public var onset: Int
    /// Sounding MIDI pitch.
    public var pitch: Int
    public var step: String
    public var alter: Int
    /// 1 is the top line; nil on a notation staff.
    public var string: Int?
    public var fret: Int?
    /// Where the note starts: the piece no tie comes into.
    public var first: Bool
    /// The `<?fretted-confidence?>` of a doubtful note, on its first piece.
    public var confidence: Double?
    /// The beat it starts in, 1 the first, by the time signature in force there; in a pickup, the beat of the full bar it leads into.
    public var beat: Int
    /// In a pickup: a first measure shorter than its time signature.
    public var pickup: Bool

    public init(note: Int, staff: Int, bar: Int, barNumber: String, onset: Int, pitch: Int, step: String, alter: Int,
                string: Int?, fret: Int?, first: Bool, confidence: Double?, beat: Int = 1, pickup: Bool = false) {
        self.note = note; self.staff = staff; self.bar = bar; self.barNumber = barNumber; self.onset = onset
        self.pitch = pitch; self.step = step; self.alter = alter; self.string = string; self.fret = fret
        self.first = first; self.confidence = confidence; self.beat = beat; self.pickup = pickup
    }
}

/// One written measure: its printed number, how long it is and how its beats are counted.
public struct TabMeasure: Equatable, Sendable {
    /// The printed number: 0 for a pickup.
    public var number: String
    /// In `TabIndex.ticks` to a quarter note: a full bar of its time signature, or what a pickup holds.
    public var length: Int
    /// Beats in a full bar of the time signature in force.
    public var beats: Int
    /// One beat, in `TabIndex.ticks`.
    public var beatTicks: Int
    /// A first measure shorter than its time signature.
    public var pickup: Bool

    public init(number: String, length: Int, beats: Int, beatTicks: Int, pickup: Bool = false) {
        self.number = number; self.length = length; self.beats = beats; self.beatTicks = beatTicks; self.pickup = pickup
    }

    /// The beat that starts at or before `tick` of this measure, 1 the first; in a pickup, the beat of the full bar it leads into.
    public func beatAt(_ tick: Int) -> Int {
        let beat = (max(tick, 0) + (pickup ? beats * beatTicks - length : 0)) / beatTicks + 1
        return min(max(beat, 1), beats)
    }
}

/// The boxed "! D1" above a column: the names of the notes that have no place there.
public struct TabNoPlace: Equatable, Sendable {
    public var staff: Int
    public var bar: Int
    public var barNumber: String
    public var onset: Int
    public var names: [String]
    public var beat: Int
    public var pickup: Bool

    public init(staff: Int, bar: Int, barNumber: String, onset: Int, names: [String], beat: Int = 1, pickup: Bool = false) {
        self.staff = staff; self.bar = bar; self.barNumber = barNumber; self.onset = onset; self.names = names
        self.beat = beat; self.pickup = pickup
    }
}

/// tab.musicxml as the tab view needs it: which drawn note is which note of the tab's data. The core says
/// so in a processing instruction on every note piece (core/targets/fretted/README.md, The note index);
/// alphaTab drops those when it reads the file, so they are read here, with each piece's measure, start
/// and string, and a drawn note is found again by those.
public struct TabIndex: Sendable {
    /// alphaTab's ticks to a quarter note: onsets are kept in them, so they compare with a beat's start.
    public static let ticks = 960

    public let pieces: [TabPiece]
    public let noPlace: [TabNoPlace]
    /// Measures written.
    public let bars: Int
    public let staves: Int
    /// The staff with the TAB clef; nil in the notation layout.
    public let tabStaff: Int?
    /// The words over the first measure: "Drop D: D A D G B E, Capo 3".
    public let header: String?
    /// Quarter notes a minute, as the first measure says; nil when it does not.
    public let tempo: Int?
    /// The measures in the order they are written; `bars` of them.
    public let measures: [TabMeasure]
    private let byNote: [Int: [TabPiece]]

    public init(pieces: [TabPiece], noPlace: [TabNoPlace], bars: Int, staves: Int, tabStaff: Int?, header: String?,
                tempo: Int? = nil, measures: [TabMeasure] = []) {
        self.pieces = pieces; self.noPlace = noPlace; self.bars = bars; self.staves = staves; self.tabStaff = tabStaff
        self.header = header; self.tempo = tempo; self.measures = measures
        byNote = Dictionary(grouping: pieces, by: \.note)
    }

    /// The pieces of `note` in the order they are written; empty for a note the document does not have.
    public func of(_ note: Int) -> [TabPiece] { byNote[note] ?? [] }

    /// The staff the marks stand on: the tab staff, or the notation staff when it is the only one.
    public var markStaff: Int { tabStaff ?? 0 }

    /// The capo's fret, as the header says it; 0 without one.
    public var capo: Int {
        guard let header, let m = Self.capoPattern.firstMatch(in: header, range: NSRange(header.startIndex..., in: header)),
              let r = Range(m.range(at: 1), in: header) else { return 0 }
        return Int(header[r]) ?? 0
    }

    /// The tuning's name, as the header says it ("Drop D").
    public var tuningName: String? {
        guard let header, let colon = header.firstIndex(of: ":") else { return nil }
        let name = header[..<colon].trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? nil : name
    }

    // MARK: - For the renderer

    private static let capoPattern = try! NSRegularExpression(pattern: #"\bCapo (\d+)"#)
    private static let markDirection = try! NSRegularExpression(
        pattern: #"<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>\s*(?:\?|![^<]*)</words>(?:(?!</direction>).)*?</direction>\s*"#,
        options: .dotMatchesLineSeparators)
    private static let noteColour = try! NSRegularExpression(pattern: ##"(<note(?:head)?\b[^>]*?)\s+color="#[0-9A-Fa-f]{6,8}""##)
    private static let wordsDirection = try! NSRegularExpression(
        pattern: #"<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>([^<]*)</words>(?:(?!</direction>).)*?</direction>\s*"#,
        options: .dotMatchesLineSeparators)

    /// `musicXML` without the "?" and "!" words and without the doubt colour: the view draws its marks from
    /// the data, and would otherwise show them twice. For the renderer only; the file itself is kept as it is.
    public static func withoutMarks(_ musicXML: String) -> String {
        let s = NSMutableString(string: musicXML)
        markDirection.replaceMatches(in: s, range: NSRange(location: 0, length: s.length), withTemplate: "")
        noteColour.replaceMatches(in: s, range: NSRange(location: 0, length: s.length), withTemplate: "$1")
        return s as String
    }

    /// `musicXML` for the renderer: without its marks (`withoutMarks`) and without the words over the first
    /// measure (the tuning, the strings and the capo). The screen's header says those, and on the page a mark
    /// over the first notes would stand on them.
    public static func forRenderer(_ musicXML: String, header: String?) -> String {
        let bare = withoutMarks(musicXML) as NSString
        guard let header else { return bare as String }
        for m in wordsDirection.matches(in: bare as String, range: NSRange(location: 0, length: bare.length))
        where bare.substring(with: m.range(at: 1)).trimmingCharacters(in: .whitespacesAndNewlines) == header {
            return bare.replacingCharacters(in: m.range, with: "")
        }
        return bare as String
    }

    // MARK: - Reading

    private static let steps: [String: Int] = ["C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11]

    /// How long `measure` is, in divisions: as far as its notes reach.
    private static func lengthOf(_ measure: TabXML) -> Int {
        var pos = 0
        var end = 0
        for c in measure.children {
            switch c.name {
            case "backup": pos -= c.int("duration") ?? 0
            case "forward": pos += c.int("duration") ?? 0
            case "note": if c.child("chord") == nil && c.child("grace") == nil { pos += c.int("duration") ?? 0 }
            default: break
            }
            end = max(end, pos)
        }
        return end
    }

    /// Reads the first part of `musicXML`. A document that is not MusicXML gives an empty index.
    public static func parse(musicXML: String) -> TabIndex {
        parse(musicXML: Data(musicXML.utf8))
    }

    /// Reads the first part of `musicXML`. A document that is not MusicXML gives an empty index.
    public static func parse(musicXML: Data) -> TabIndex {
        guard let part = TabXML.document(musicXML)?.child("part") else {
            return TabIndex(pieces: [], noPlace: [], bars: 0, staves: 1, tabStaff: nil, header: nil)
        }
        var pieces: [TabPiece] = []
        var noPlace: [TabNoPlace] = []
        var divisions = 1
        var staves = 1
        var tabStaff: Int?
        var header: String?
        var tempo: Int?
        var beats = 4
        var beatTicks = ticks
        let measures = part.children("measure")
        var written: [TabMeasure] = []
        for (bar, measure) in measures.enumerated() {
            let n = measure.attribute("number")
            let number = n.isEmpty ? String(bar + 1) : n
            // The time signature and the divisions of this measure are in force from its start.
            if let a = measure.child("attributes") {
                if let d = a.int("divisions"), d > 0 { divisions = d }
                if let b = a.int("time", "beats"), b > 0 { beats = b }
                if let t = a.int("time", "beat-type"), t > 0 { beatTicks = ticks * 4 / t }
            }
            var pos = 0
            var last = 0
            let div = divisions
            func inTicks(_ p: Int) -> Int { p * ticks / div }
            // A pickup is shorter than a bar: its notes are counted in the beats of the bar they lead into.
            let length = inTicks(lengthOf(measure))
            let full = beats * beatTicks
            let pickup = bar == 0 && length >= 1 && length < full
            let (beatTicksHere, lengthHere) = (beatTicks, length)
            func beatAt(_ onset: Int) -> Int { (onset + (pickup ? full - lengthHere : 0)) / beatTicksHere + 1 }
            written.append(TabMeasure(number: number, length: pickup ? length : full, beats: beats, beatTicks: beatTicks, pickup: pickup))
            for el in measure.children {
                switch el.name {
                case "attributes":
                    if let d = el.int("divisions"), d > 0 { divisions = d }
                    if let s = el.int("staves") { staves = max(staves, s) }
                    if let b = el.int("time", "beats"), b > 0 { beats = b }
                    if let t = el.int("time", "beat-type"), t > 0 { beatTicks = ticks * 4 / t }
                    for clef in el.children("clef") where clef.text("sign") == "TAB" {
                        tabStaff = (Int(clef.attribute("number")) ?? 1) - 1
                    }
                case "backup": pos -= el.int("duration") ?? 0
                case "forward": pos += el.int("duration") ?? 0
                case "direction":
                    let staff = (el.int("staff") ?? 1) - 1
                    for type in el.children("direction-type") {
                        for words in type.children("words") {
                            let text = words.textContent.trimmingCharacters(in: .whitespacesAndNewlines)
                            if text == "?" { continue }
                            if text.hasPrefix("!") && words.attribute("enclosure") == "rectangle" {
                                let names = text.dropFirst().trimmingCharacters(in: .whitespacesAndNewlines)
                                    .split(separator: " ").map(String.init)
                                noPlace.append(TabNoPlace(staff: staff, bar: bar, barNumber: number, onset: inTicks(pos), names: names,
                                                          beat: beatAt(inTicks(pos)), pickup: pickup))
                            } else if header == nil && bar == 0 && !text.isEmpty {
                                header = text
                            }
                        }
                    }
                    if tempo == nil && bar == 0, let t = el.child("sound").flatMap({ Double($0.attribute("tempo")) }) {
                        tempo = Int((t + 0.5).rounded(.down))
                    }
                case "note":
                    let chord = el.child("chord") != nil
                    let grace = el.child("grace") != nil
                    let onset = chord ? last : pos
                    if !chord && !grace { last = pos; pos += el.int("duration") ?? 0 }
                    guard let index = el.instruction("fretted-note").flatMap({ Int($0) }),
                          let pitch = el.child("pitch"), let step = pitch.text("step"), let octave = pitch.int("octave") else { continue }
                    let alter = Int(((pitch.text("alter").flatMap { Double($0) } ?? 0) + 0.5).rounded(.down))
                    let technical = el.path("notations", "technical")
                    pieces.append(TabPiece(
                        note: index, staff: (el.int("staff") ?? 1) - 1, bar: bar, barNumber: number, onset: inTicks(onset),
                        pitch: 12 * (octave + 1) + (steps[step] ?? 0) + alter, step: step, alter: alter,
                        string: technical?.int("string"), fret: technical?.int("fret"),
                        first: !el.children("tie").contains { $0.attribute("type") == "stop" },
                        confidence: el.instruction("fretted-confidence").flatMap { Double($0) },
                        beat: beatAt(inTicks(onset)), pickup: pickup))
                default: break
                }
            }
        }
        return TabIndex(pieces: pieces, noPlace: noPlace, bars: measures.count, staves: staves, tabStaff: tabStaff, header: header,
                        tempo: tempo, measures: written)
    }
}

/// An element of a document read whole: its name, attributes, child elements, text and processing instructions.
/// Only as much of a DOM as the index reads.
final class TabXML {
    let name: String
    let attributes: [String: String]
    private(set) var children: [TabXML] = []
    /// The processing instructions directly inside this element, as (target, data).
    private(set) var instructions: [(String, String)] = []

    init(name: String, attributes: [String: String]) {
        self.name = name
        self.attributes = attributes
    }

    func attribute(_ name: String) -> String { attributes[name] ?? "" }
    func child(_ name: String) -> TabXML? { children.first { $0.name == name } }
    func children(_ name: String) -> [TabXML] { children.filter { $0.name == name } }
    func path(_ names: String...) -> TabXML? { names.reduce(Optional(self)) { $0?.child($1) } }
    func text(_ names: String...) -> String? {
        names.reduce(Optional(self)) { $0?.child($1) }?.textContent.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    func int(_ names: String...) -> Int? {
        guard let t = names.reduce(Optional(self), { $0?.child($1) }) else { return nil }
        return Int(t.textContent.trimmingCharacters(in: .whitespacesAndNewlines))
    }
    func instruction(_ target: String) -> String? {
        instructions.first { $0.0 == target }?.1.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The text of this element and of everything in it, in document order.
    var textContent: String {
        var out = ""
        collect(into: &out)
        return out
    }

    private var order: [Either] = []
    private enum Either { case text(String), element(TabXML) }

    private func collect(into out: inout String) {
        for part in order {
            switch part {
            case .text(let t): out += t
            case .element(let e): e.collect(into: &out)
            }
        }
    }

    fileprivate func append(_ child: TabXML) { children.append(child); order.append(.element(child)) }
    fileprivate func append(text: String) {
        if case .text(let t)? = order.last { order[order.count - 1] = .text(t + text) } else { order.append(.text(text)) }
    }
    fileprivate func append(instruction target: String, data: String) { instructions.append((target, data)) }

    /// The root element of `data`; nil when it is not a well-formed document. No external entity or DTD is read.
    static func document(_ data: Data) -> TabXML? {
        let reader = Reader()
        let parser = XMLParser(data: data)
        parser.shouldResolveExternalEntities = false
        parser.externalEntityResolvingPolicy = .never
        parser.shouldProcessNamespaces = false
        parser.delegate = reader
        guard parser.parse() else { return nil }
        return reader.root
    }

    private final class Reader: NSObject, XMLParserDelegate {
        var root: TabXML?
        var open: [TabXML] = []

        func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?, qualifiedName: String?,
                    attributes: [String: String] = [:]) {
            let node = TabXML(name: name, attributes: attributes)
            if let parent = open.last { parent.append(node) } else if root == nil { root = node }
            open.append(node)
        }

        func parser(_ parser: XMLParser, didEndElement name: String, namespaceURI: String?, qualifiedName: String?) {
            _ = open.popLast()
        }

        func parser(_ parser: XMLParser, foundCharacters string: String) { open.last?.append(text: string) }

        func parser(_ parser: XMLParser, foundCDATA block: Data) { open.last?.append(text: String(decoding: block, as: UTF8.self)) }

        func parser(_ parser: XMLParser, foundProcessingInstructionWithTarget target: String, data: String?) {
            open.last?.append(instruction: target, data: data ?? "")
        }
    }
}

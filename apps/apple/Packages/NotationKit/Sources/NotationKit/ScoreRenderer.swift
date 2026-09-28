import CoreGraphics
import Foundation
import ScoreKit
import SVGRender

/// Engraves a MusicXML score with Verovio and hands out natively drawable pages.
///
/// - Show all / show one: pass a set of part ids; other parts are removed from the
///   MusicXML before Verovio sees it.
/// - Written / concert: Verovio's `transposeToSoundingPitch`.
/// - Cursor: Verovio's timemap maps quarter-note positions to sounding note ids and
///   measure ids; `measureIDs` lists measure ids in score order across pages.
public final class ScoreRenderer: @unchecked Sendable {
    public struct Layout: Equatable, Sendable {
        /// Page width in points at zoom 1.
        public var width: CGFloat
        /// Zoom, 1 = 100 %. Verovio scale is 40 × zoom.
        public var zoom: CGFloat
        public var parts: Set<String>?
        public var pitch: PitchMode
        /// Page height in points at the chosen zoom (content is split into pages this tall).
        public var height: CGFloat
        /// A fixed number of bars on every system (the music stand). The score is then engraved
        /// as one long page, and the stand pages through its systems itself.
        public var barsPerSystem: Int?

        public init(width: CGFloat = 820, zoom: CGFloat = 1, parts: Set<String>? = nil, pitch: PitchMode = .written, height: CGFloat = 1160,
                    barsPerSystem: Int? = nil) {
            self.width = width; self.zoom = zoom; self.parts = parts; self.pitch = pitch; self.height = height
            self.barsPerSystem = barsPerSystem
        }
    }

    public struct Page: @unchecked Sendable {
        public let number: Int
        public let svg: SVGDocument
        /// Measure ids on this page in order.
        public let measureIDs: [String]
        /// Staff ids per measure (top to bottom = displayed parts in score order).
        public let staves: [String: [String]]
        /// Note ids per staff id.
        public let notesByStaff: [String: [String]]
        /// The five staff lines per staff id (the staff's own frame also covers its notes).
        public let staffLines: [String: CGRect]
        /// Systems top to bottom: the system's frame (everything drawn in it) and its measure ids.
        public var systems: [System] = []
    }

    public struct System: Sendable, Equatable {
        public let frame: CGRect
        public let measureIDs: [String]

        public init(frame: CGRect, measureIDs: [String]) { self.frame = frame; self.measureIDs = measureIDs }
    }

    public let musicXML: String
    /// What one engraving published: replaced whole when `apply` finishes, so a reader on any
    /// thread sees either the previous layout or the new one, never half of each.
    public struct Engraving: Sendable {
        public var layout = Layout()
        public var pageCount = 0
        public var timemap: [TimemapEntry] = []
        /// Measure ids in score order; index = 0-based bar index.
        public var measureIDs: [String] = []
        /// Bar index by measure id.
        public var measureIndex: [String: Int] = [:]
        public var lastLoadSeconds: Double = 0
    }

    /// The current engraving, read on any thread (the cursor reads it at 20 Hz on the main
    /// thread while `apply` engraves on a background task).
    public var engraving: Engraving { stateLock.withLock { published } }
    public var layout: Layout { engraving.layout }
    public var pageCount: Int { engraving.pageCount }
    public var timemap: [TimemapEntry] { engraving.timemap }
    public var measureIDs: [String] { engraving.measureIDs }
    public var lastLoadSeconds: Double { engraving.lastLoadSeconds }
    /// Notes the arranger flagged as uncertain (document colour), by id, with their level;
    /// filled in as pages are drawn.
    public var uncertainLevels: [String: UncertaintyLevel] { stateLock.withLock { uncertain } }
    public var uncertainNoteIDs: Set<String> { Set(uncertainLevels.keys) }

    private let toolkit: VerovioToolkit
    private var pages: [Int: Page] = [:]
    /// Serialises Verovio (not thread-safe) and the page cache; held for a whole engraving.
    private let lock = NSLock()
    /// Guards `published` and `uncertain`, only ever for a copy, so readers never wait for Verovio.
    private let stateLock = NSLock()
    private var published = Engraving()
    private var uncertain: [String: UncertaintyLevel] = [:]

    /// Very uncertain notes are written in this colour (confidence below 0.4); any other
    /// note colour means uncertain (0.4–0.7, and the older single-level red).
    public static let veryUncertainColor = (red: 0xB0, green: 0x4A, blue: 0x00)

    /// - Parameter keepQuestionMarks: let Verovio engrave the "?" directions itself (for
    ///   printed pages); on screen the app draws them in the note colour instead.
    public init?(musicXML: String, keepQuestionMarks: Bool = false, resourcePath: String? = VerovioToolkit.defaultResourcePath()) {
        guard let tk = VerovioToolkit(resourcePath: resourcePath) else { return nil }
        toolkit = tk
        self.musicXML = keepQuestionMarks ? musicXML : Self.removingQuestionMarks(musicXML)
    }

    /// The MusicXML without any uncertainty marking: no "?" directions and no note colours.
    public static func removingUncertainty(_ xml: String) -> String {
        let plain = removingQuestionMarks(xml)
        guard let re = try? NSRegularExpression(pattern: ##"\s(?:color|fill)="#[0-9A-Fa-f]{6}""##) else { return plain }
        return re.stringByReplacingMatches(in: plain, range: NSRange(plain.startIndex..., in: plain), withTemplate: "")
    }

    /// The MusicXML carries a "?" words direction at each uncertain attack. The app draws
    /// that mark itself, in the note's colour and boxed when very uncertain, so Verovio's
    /// ink copy is removed to keep one mark per note.
    public static func removingQuestionMarks(_ xml: String) -> String {
        guard xml.contains(">?</words>") else { return xml }
        let pattern = #"<direction\b[^>]*>(?:(?!</direction>)[\s\S])*?<words\b[^>]*>\?</words>(?:(?!</direction>)[\s\S])*?</direction>\s*"#
        guard let re = try? NSRegularExpression(pattern: pattern) else { return xml }
        return re.stringByReplacingMatches(in: xml, range: NSRange(xml.startIndex..., in: xml), withTemplate: "")
    }

    /// The level a document note colour stands for.
    public static func level(of color: CGColor) -> UncertaintyLevel {
        guard let c = color.converted(to: CGColorSpace(name: CGColorSpace.sRGB)!, intent: .defaultIntent, options: nil)?.components,
              c.count >= 3 else { return .uncertain }
        let v = veryUncertainColor
        let d = abs(c[0] * 255 - CGFloat(v.red)) + abs(c[1] * 255 - CGFloat(v.green)) + abs(c[2] * 255 - CGFloat(v.blue))
        return d < 40 ? .veryUncertain : .uncertain
    }

    /// (Re)engrave for a layout. Returns false if Verovio could not read the score.
    @discardableResult
    public func apply(_ l: Layout) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let t0 = Date()
        pages = [:]
        let scale = max(10, min(160, Int(40 * l.zoom)))
        // Verovio page units are tenths of a mm at scale 100; the SVG comes out at
        // pageWidth × scale / 100 px, so ask for a width that lands on the view width.
        let pageWidth = Int(l.width * 100 / CGFloat(scale))
        let fixed = l.barsPerSystem.map { max(1, $0) }
        toolkit.setOptions([
            "pageWidth": max(500, pageWidth), "pageHeight": fixed != nil ? 60000 : max(1000, Int(l.height * 100 / CGFloat(scale))),
            "adjustPageHeight": true,
            "scale": scale, "pageMarginLeft": 50, "pageMarginRight": 50, "pageMarginTop": 50, "pageMarginBottom": 50,
            "breaks": fixed != nil ? "encoded" : "auto", "font": "Leipzig", "svgHtml5": false, "svgBoundingBoxes": false,
            "transposeToSoundingPitch": l.pitch == .concert, "header": "none", "footer": "none",
            "condense": l.parts?.count == 1 ? "none" : "auto", "justifyVertically": false,
        ])
        var xml = l.parts.map { MusicXMLFilter.keepingParts($0, in: musicXML) } ?? musicXML
        if let fixed {
            xml = Self.breakingSystems(every: fixed, in: xml)
            // one part on the stand: its name is in the stand's own band, so the staff starts at the margin
            if l.parts?.count == 1 {
                xml = xml.replacingOccurrences(of: #"<part-(name|abbreviation)\b[^>]*>[^<]*</part-(name|abbreviation)>"#,
                                               with: "<part-$1></part-$1>", options: .regularExpression)
            }
        }
        guard toolkit.loadData(xml) else { return false }
        var e = Engraving(layout: l, pageCount: toolkit.pageCount, timemap: toolkit.timemap())
        var seen = Set<String>()
        e.measureIDs = e.timemap.compactMap(\.measureOn).filter { seen.insert($0).inserted }
        e.measureIndex = Dictionary(uniqueKeysWithValues: e.measureIDs.enumerated().map { ($1, $0) })
        e.lastLoadSeconds = Date().timeIntervalSince(t0)
        stateLock.withLock { published = e; uncertain = [:] }
        return true
    }

    /// The MusicXML with a system break before every `n`th bar of every part, and no other
    /// system or page breaks.
    public static func breakingSystems(every n: Int, in xml: String) -> String {
        var s = xml.replacingOccurrences(of: #"\snew-(system|page)="yes""#, with: "", options: .regularExpression)
        guard n > 0, let re = try? NSRegularExpression(pattern: #"<part\b[^>]*>|<measure\b[^>/]*>"#) else { return s }
        var out = "", last = s.startIndex, bar = 0
        for m in re.matches(in: s, range: NSRange(s.startIndex..., in: s)) {
            guard let r = Range(m.range, in: s) else { continue }
            out += s[last..<r.upperBound]
            last = r.upperBound
            if s[r].hasPrefix("<part") { bar = 0; continue }
            if bar > 0, bar % n == 0 { out += #"<print new-system="yes"/>"# }
            bar += 1
        }
        out += s[last...]
        s = out
        return s
    }

    public func page(_ n: Int) -> Page? {
        lock.lock(); defer { lock.unlock() }
        if let p = pages[n] { return p }
        guard n >= 1, n <= engraving.pageCount, let doc = try? SVGDocument(svg: toolkit.renderToSVG(page: n)) else { return nil }
        var staves: [String: [String]] = [:]
        var notes: [String: [String]] = [:]
        var seenStaff = Set<String>(), seenNote = Set<String>()
        var lines: [String: CGRect] = [:]
        var levels: [String: UncertaintyLevel] = [:]
        for op in doc.ops {
            if let last = op.owners.last, let path = op.path {
                let id = doc.ids[Int(last)]
                if doc.classes[id] == "staff" { lines[id] = (lines[id] ?? .null).union(path.boundingBoxOfPath) }
            }
            var measure: String?, staff: String?
            for o in op.owners {
                let id = doc.ids[Int(o)]
                switch doc.classes[id] {
                case "measure": measure = id
                case "staff": staff = id
                case "note":
                    if let staff, seenNote.insert(id).inserted { notes[staff, default: []].append(id) }
                    if let c = op.color, levels[id] == nil { levels[id] = Self.level(of: c) }
                default: break
                }
            }
            if let measure, let staff, seenStaff.insert(staff).inserted { staves[measure, default: []].append(staff) }
        }
        var p = Page(number: n, svg: doc, measureIDs: doc.ids(ofClass: "measure"), staves: staves, notesByStaff: notes, staffLines: lines)
        p.systems = Self.systems(in: doc, measureIDs: p.measureIDs)
        pages[n] = p
        stateLock.withLock { uncertain.merge(levels) { old, _ in old } }
        return p
    }

    /// Systems top to bottom, each with the measures whose frame sits inside it.
    static func systems(in doc: SVGDocument, measureIDs: [String]) -> [System] {
        let frames = doc.ids(ofClass: "system").compactMap { doc.frames[$0] }.sorted { $0.minY < $1.minY }
        return frames.map { f in
            System(frame: f, measureIDs: measureIDs.filter { id in doc.frames[id].map { f.contains(CGPoint(x: $0.midX, y: $0.midY)) } ?? false })
        }
    }

    public func renderAllPages() -> [Page] { (1...max(1, pageCount)).compactMap(page) }

    /// One part's bars `first...last` (1-based printed order) on a single strip, for Check the notes.
    public static func snippet(musicXML: String, partID: String, bars: ClosedRange<Int>, width: CGFloat, pitch: PitchMode = .written,
                               resourcePath: String? = VerovioToolkit.defaultResourcePath()) -> Page? {
        guard let tk = VerovioToolkit(resourcePath: resourcePath) else { return nil }
        let scale = 40
        tk.setOptions([
            "pageWidth": max(500, Int(width * 100 / CGFloat(scale))), "pageHeight": 60000, "adjustPageHeight": true, "scale": scale,
            "pageMarginLeft": 20, "pageMarginRight": 20, "pageMarginTop": 20, "pageMarginBottom": 20,
            "breaks": "none", "font": "Leipzig", "svgHtml5": false, "header": "none", "footer": "none",
            "transposeToSoundingPitch": pitch == .concert,
        ])
        let xml = MusicXMLFilter.keepingParts([partID], in: removingQuestionMarks(musicXML))
        guard tk.loadData(xml) else { return nil }
        tk.select(["measureRange": "\(bars.lowerBound)-\(bars.upperBound)"])
        tk.redoLayout()
        guard let doc = try? SVGDocument(svg: tk.renderToSVG(page: 1)) else { return nil }
        var notes: [String: [String]] = [:]
        var lines: [String: CGRect] = [:]
        for op in doc.ops {
            var staff: String?
            for o in op.owners {
                let id = doc.ids[Int(o)]
                switch doc.classes[id] {
                case "staff":
                    staff = id
                    if let path = op.path, o == op.owners.last { lines[id] = (lines[id] ?? .null).union(path.boundingBoxOfPath) }
                case "note": if let staff, !(notes[staff] ?? []).contains(id) { notes[staff, default: []].append(id) }
                default: break
                }
            }
        }
        return Page(number: 1, svg: doc, measureIDs: doc.ids(ofClass: "measure"), staves: [:], notesByStaff: notes, staffLines: lines)
    }

    /// Page holding a measure id.
    public func pageNumber(forMeasure id: String) -> Int {
        lock.lock(); defer { lock.unlock() }
        return toolkit.pageWithElement(id)
    }

    /// Note ids starting at the latest onset at or before `beat`, and that onset's measure.
    public func sounding(atBeat beat: Double) -> (notes: [String], measureIndex: Int) {
        Self.sounding(atBeat: beat, in: engraving)
    }

    static func sounding(atBeat beat: Double, in e: Engraving) -> (notes: [String], measureIndex: Int) {
        let timemap = e.timemap
        var lo = 0, hi = timemap.count - 1, best = -1
        while lo <= hi {
            let mid = (lo + hi) / 2
            if timemap[mid].qstamp <= beat + 1e-6 { best = mid; lo = mid + 1 } else { hi = mid - 1 }
        }
        guard best >= 0 else { return ([], 0) }
        var notes = timemap[best].on ?? []
        // carry notes still held from earlier onsets
        var i = best - 1
        var offs = Set(timemap[best].off ?? [])
        while i >= 0 && i >= best - 32 {
            for id in timemap[i].on ?? [] where !offs.contains(id) { notes.append(id) }
            offs.formUnion(timemap[i].off ?? [])
            i -= 1
        }
        var measure = 0
        for j in stride(from: best, through: 0, by: -1) {
            if let m = timemap[j].measureOn, let idx = e.measureIndex[m] { measure = idx; break }
        }
        return (notes, measure)
    }

    public var verovioVersion: String { VerovioToolkit.version }
}

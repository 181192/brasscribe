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

        public init(width: CGFloat = 820, zoom: CGFloat = 1, parts: Set<String>? = nil, pitch: PitchMode = .written, height: CGFloat = 1160) {
            self.width = width; self.zoom = zoom; self.parts = parts; self.pitch = pitch; self.height = height
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
    }

    public let musicXML: String
    public private(set) var layout = Layout()
    public private(set) var pageCount = 0
    public private(set) var timemap: [TimemapEntry] = []
    /// Measure ids in score order; index = 0-based bar index.
    public private(set) var measureIDs: [String] = []
    /// Notes the arranger flagged as uncertain (document colour), by id, with their level.
    public private(set) var uncertainLevels: [String: UncertaintyLevel] = [:]
    public var uncertainNoteIDs: Set<String> { Set(uncertainLevels.keys) }
    public private(set) var lastLoadSeconds: Double = 0

    private let toolkit: VerovioToolkit
    private var pages: [Int: Page] = [:]
    private let lock = NSLock()

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
        layout = l
        pages = [:]
        let scale = max(10, min(160, Int(40 * l.zoom)))
        // Verovio page units are tenths of a mm at scale 100; the SVG comes out at
        // pageWidth × scale / 100 px, so ask for a width that lands on the view width.
        let pageWidth = Int(l.width * 100 / CGFloat(scale))
        toolkit.setOptions([
            "pageWidth": max(500, pageWidth), "pageHeight": max(1000, Int(l.height * 100 / CGFloat(scale))), "adjustPageHeight": true,
            "scale": scale, "pageMarginLeft": 50, "pageMarginRight": 50, "pageMarginTop": 50, "pageMarginBottom": 50,
            "breaks": "auto", "font": "Leipzig", "svgHtml5": false, "svgBoundingBoxes": false,
            "transposeToSoundingPitch": l.pitch == .concert, "header": "none", "footer": "none",
            "condense": l.parts?.count == 1 ? "none" : "auto", "justifyVertically": false,
        ])
        let xml = l.parts.map { MusicXMLFilter.keepingParts($0, in: musicXML) } ?? musicXML
        guard toolkit.loadData(xml) else { return false }
        pageCount = toolkit.pageCount
        timemap = toolkit.timemap()
        measureIDs = timemap.compactMap(\.measureOn)
        var seen = Set<String>()
        measureIDs = measureIDs.filter { seen.insert($0).inserted }
        uncertainLevels = [:]
        lastLoadSeconds = Date().timeIntervalSince(t0)
        return true
    }

    public func page(_ n: Int) -> Page? {
        lock.lock(); defer { lock.unlock() }
        if let p = pages[n] { return p }
        guard n >= 1, n <= pageCount, let doc = try? SVGDocument(svg: toolkit.renderToSVG(page: n)) else { return nil }
        var staves: [String: [String]] = [:]
        var notes: [String: [String]] = [:]
        var seenStaff = Set<String>(), seenNote = Set<String>()
        var lines: [String: CGRect] = [:]
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
                    if let c = op.color, uncertainLevels[id] == nil { uncertainLevels[id] = Self.level(of: c) }
                default: break
                }
            }
            if let measure, let staff, seenStaff.insert(staff).inserted { staves[measure, default: []].append(staff) }
        }
        let p = Page(number: n, svg: doc, measureIDs: doc.ids(ofClass: "measure"), staves: staves, notesByStaff: notes, staffLines: lines)
        pages[n] = p
        return p
    }

    public func renderAllPages() -> [Page] { (1...max(1, pageCount)).compactMap(page) }

    /// Page holding a measure id.
    public func pageNumber(forMeasure id: String) -> Int {
        lock.lock(); defer { lock.unlock() }
        return toolkit.pageWithElement(id)
    }

    /// Note ids starting at the latest onset at or before `beat`, and that onset's measure.
    public func sounding(atBeat beat: Double) -> (notes: [String], measureIndex: Int) {
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
            if let m = timemap[j].measureOn, let idx = measureIDs.firstIndex(of: m) { measure = idx; break }
        }
        return (notes, measure)
    }

    public var verovioVersion: String { VerovioToolkit.version }
}

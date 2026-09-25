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

        public init(width: CGFloat = 820, zoom: CGFloat = 1, parts: Set<String>? = nil, pitch: PitchMode = .written) {
            self.width = width; self.zoom = zoom; self.parts = parts; self.pitch = pitch
        }
    }

    public struct Page: @unchecked Sendable {
        public let number: Int
        public let svg: SVGDocument
        /// Measure ids on this page in order.
        public let measureIDs: [String]
    }

    public let musicXML: String
    public private(set) var layout = Layout()
    public private(set) var pageCount = 0
    public private(set) var timemap: [TimemapEntry] = []
    /// Measure ids in score order; index = 0-based bar index.
    public private(set) var measureIDs: [String] = []
    /// Notes the arranger flagged as uncertain (document colour), by id.
    public private(set) var uncertainNoteIDs: Set<String> = []
    public private(set) var lastLoadSeconds: Double = 0

    private let toolkit: VerovioToolkit
    private var pages: [Int: Page] = [:]
    private let lock = NSLock()

    public static let uncertaintyColor = "#D0021B"

    public init?(musicXML: String, resourcePath: String? = VerovioToolkit.defaultResourcePath()) {
        guard let tk = VerovioToolkit(resourcePath: resourcePath) else { return nil }
        toolkit = tk
        self.musicXML = musicXML
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
            "pageWidth": max(500, pageWidth), "pageHeight": 60000, "adjustPageHeight": true,
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
        uncertainNoteIDs = []
        lastLoadSeconds = Date().timeIntervalSince(t0)
        return true
    }

    public func page(_ n: Int) -> Page? {
        lock.lock(); defer { lock.unlock() }
        if let p = pages[n] { return p }
        guard n >= 1, n <= pageCount, let doc = try? SVGDocument(svg: toolkit.renderToSVG(page: n)) else { return nil }
        let p = Page(number: n, svg: doc, measureIDs: doc.ids(ofClass: "measure"))
        for (i, op) in doc.ops.enumerated() where op.color != nil {
            _ = i
            for o in op.owners {
                let id = doc.ids[Int(o)]
                if doc.classes[id] == "note" { uncertainNoteIDs.insert(id) }
            }
        }
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

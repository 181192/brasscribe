import CoreGraphics
import CoreText
import Foundation

/// A minimal SVG renderer for engraved notation (the subset Verovio writes): nested
/// `<svg viewBox>`, `<g>`, `<defs>` + `<use>` glyphs, `<path>`, `<polygon>`, `<polyline>`,
/// `<rect>`, `<ellipse>`, `<circle>`, `<line>`, `<text>`/`<tspan>`, `transform`, `fill`,
/// `color`/`currentColor`, `stroke-width`.
///
/// The document is flattened once into a display list of CGPaths in output coordinates
/// (y down, points = SVG px), so drawing a page is a straight loop. Every drawing op
/// remembers the ids of the elements it belongs to, which gives
/// - bounding boxes per id (`frames`) for accessibility elements and hit testing, and
/// - per-id colour overrides for the playback cursor and uncertainty marks.
public final class SVGDocument: @unchecked Sendable {
    public struct Op {
        public enum Kind { case fill, stroke(CGFloat), text(CTLine, CGPoint) }
        public let kind: Kind
        public let path: CGPath?
        /// Explicit colour from the document (nil = current colour).
        public let color: CGColor?
        /// Indices into `ids` of the elements (with an id) that contain this op, outermost first.
        public let owners: [Int32]
    }

    public let size: CGSize
    public private(set) var ops: [Op] = []
    public private(set) var ids: [String] = []
    /// Bounding box per element id, in output coordinates.
    public private(set) var frames: [String: CGRect] = [:]
    /// SVG `class` per element id (e.g. `measure`, `staff`, `note`).
    public private(set) var classes: [String: String] = [:]

    public init(data: Data) throws {
        let root = try XMLTree.parse(data)
        guard root.name == "svg" else { throw SVGError.notSVG }
        let w = Self.length(root.attrs["width"]) ?? 100
        let h = Self.length(root.attrs["height"]) ?? 100
        size = CGSize(width: w, height: h)
        var defs: [String: XMLTree.Node] = [:]
        root.walk { n in if let id = n.attrs["id"], n.parentIsDefs { defs[id] = n } }
        var b = Builder(defs: defs)
        root.walk { n in
            if n.name == "style" { for case .text(let css) in n.content { b.registerFonts(css: css) } }
        }
        b.visit(root, ctm: .identity, style: .init(), viewport: size, owners: [])
        ops = b.ops
        ids = b.ids
        frames = b.frames
        classes = b.classes
    }

    public convenience init(svg: String) throws { try self.init(data: Data(svg.utf8)) }

    /// Ids of elements with the given class, in document order.
    public func ids(ofClass cls: String) -> [String] {
        ids.filter { classes[$0]?.split(separator: " ").contains(Substring(cls)) ?? false }
    }

    /// Draw into a context whose user space is y-down and matches `size` (scale the CTM first
    /// to zoom). `highlight` recolours ops belonging to the given ids; `ink` replaces black
    /// (used for dark mode and high contrast).
    /// `visible`, when given, skips everything outside that rectangle (a window onto a long page).
    public func draw(in ctx: CGContext, ink: CGColor = CGColor(gray: 0, alpha: 1),
                     highlight: [String: CGColor] = [:], keepDocumentColors: Bool = true, visible: CGRect? = nil) {
        let hi: [Int32: CGColor] = Dictionary(uniqueKeysWithValues: highlight.compactMap { k, v in
            idIndex[k].map { ($0, v) }
        })
        ctx.saveGState()
        ctx.setLineCap(.butt)
        let bounds = visible == nil ? [] : opBounds
        for (i, op) in ops.enumerated() {
            if let visible, !bounds[i].intersects(visible) { continue }
            var color = keepDocumentColors ? (op.color ?? ink) : ink
            if !hi.isEmpty { for o in op.owners.reversed() { if let c = hi[o] { color = c; break } } }
            switch op.kind {
            case .fill:
                ctx.setFillColor(color)
                ctx.addPath(op.path!)
                ctx.fillPath()
            case .stroke(let w):
                ctx.setStrokeColor(color)
                ctx.setLineWidth(w)
                ctx.addPath(op.path!)
                ctx.strokePath()
            case .text(let line, let pt):
                ctx.saveGState()
                ctx.setFillColor(color)
                ctx.textMatrix = CGAffineTransform(scaleX: 1, y: -1)
                ctx.textPosition = pt
                CTLineDraw(line, ctx)
                ctx.restoreGState()
            }
        }
        ctx.restoreGState()
    }

    /// Each op's bounds (text by its baseline point, padded to a line's height).
    private lazy var opBounds: [CGRect] = ops.map { op in
        switch op.kind {
        case .text(_, let pt): return CGRect(x: pt.x - 200, y: pt.y - 100, width: 400, height: 200)
        case .stroke(let w): return op.path?.boundingBoxOfPath.insetBy(dx: -w, dy: -w) ?? .null
        case .fill: return op.path?.boundingBoxOfPath ?? .null
        }
    }

    private lazy var idIndex: [String: Int32] = Dictionary(uniqueKeysWithValues: ids.enumerated().map { ($1, Int32($0)) })

    static func length(_ s: String?) -> CGFloat? {
        guard let s else { return nil }
        let t = s.trimmingCharacters(in: .letters.union(.whitespaces).union(CharacterSet(charactersIn: "%")))
        return Double(t).map { CGFloat($0) }
    }
}

public enum SVGError: Error { case notSVG, parse(String) }

// MARK: - flattening

struct Style {
    var fill: CGColor?? = nil          // nil = inherit/default(currentColor); .some(nil) = none
    var current: CGColor? = nil        // currentColor from `color`; nil = ink
    var fontSize: CGFloat = 16
    var anchor = "start"
    var fontFamily = "Times"
}

struct Builder {
    let defs: [String: XMLTree.Node]
    var ops: [SVGDocument.Op] = []
    var ids: [String] = []
    var frames: [String: CGRect] = [:]
    var classes: [String: String] = [:]
    var glyphCache: [ObjectIdentifier: CGPath] = [:]

    /// Fonts embedded with @font-face data URLs (Verovio embeds its SMuFL text font).
    var embeddedFonts: [String: CTFontDescriptor] = [:]

    init(defs: [String: XMLTree.Node]) { self.defs = defs }

    mutating func registerFonts(css: String) {
        let quotes = CharacterSet(charactersIn: " '\"")
        var rest = css[...]
        while let r = rest.range(of: "@font-face") {
            rest = rest[r.upperBound...]
            guard let fam = rest.range(of: "font-family:"), let b64 = rest.range(of: "base64,") else { break }
            let famEnd = rest[fam.upperBound...].firstIndex(of: ";") ?? rest.endIndex
            let family = rest[fam.upperBound..<famEnd].trimmingCharacters(in: quotes)
            let dataEnd = rest[b64.upperBound...].firstIndex(where: { $0 == ")" || $0 == "'" || $0 == "\"" }) ?? rest.endIndex
            if let data = Data(base64Encoded: String(rest[b64.upperBound..<dataEnd])),
               let descs = CTFontManagerCreateFontDescriptorsFromData(data as CFData) as? [CTFontDescriptor], let d = descs.first {
                embeddedFonts[family] = d
            }
            rest = rest[dataEnd...]
        }
    }

    mutating func register(_ n: XMLTree.Node, owners: [Int32]) -> [Int32] {
        guard let id = n.attrs["id"] else { return owners }
        ids.append(id)
        if let c = n.attrs["class"] { classes[id] = c }
        return owners + [Int32(ids.count - 1)]
    }

    mutating func addOp(_ op: SVGDocument.Op, bounds: CGRect) {
        ops.append(op)
        guard !bounds.isNull, !bounds.isInfinite else { return }
        for o in op.owners {
            let id = ids[Int(o)]
            frames[id] = frames[id].map { $0.union(bounds) } ?? bounds
        }
    }

    func resolved(_ s: Style) -> CGColor? {
        switch s.fill {
        case .none: return s.current
        case .some(let c): return c ?? nil
        }
    }

    mutating func visit(_ n: XMLTree.Node, ctm: CGAffineTransform, style parent: Style, viewport: CGSize, owners parentOwners: [Int32]) {
        if n.name == "defs" || n.name == "style" || n.name == "desc" || n.name == "title" { return }
        var style = parent
        if let c = n.attrs["color"] { style.current = parseColor(c) ?? style.current }
        if let f = n.attrs["fill"] {
            if f == "none" { style.fill = .some(nil) }
            else if f == "currentColor" { style.fill = nil }
            else if let c = parseColor(f) { style.fill = .some(c) }
        }
        if let fs = n.attrs["font-size"], let v = SVGDocument.length(fs) { style.fontSize = v }
        if let a = n.attrs["text-anchor"] { style.anchor = a }
        if let ff = n.attrs["font-family"] { style.fontFamily = ff }
        var m = ctm
        if let t = n.attrs["transform"] { m = parseTransform(t).concatenating(m) }
        let owners = register(n, owners: parentOwners)

        switch n.name {
        case "svg":
            var vp = viewport
            if n.parent != nil, let vb = n.attrs["viewBox"] {
                let v = numbers(vb)
                if v.count == 4, v[2] > 0, v[3] > 0 {
                    let w = SVGDocument.length(n.attrs["width"]) ?? viewport.width
                    let h = SVGDocument.length(n.attrs["height"]) ?? viewport.height
                    let s = min(w / v[2], h / v[3])
                    m = CGAffineTransform(translationX: -v[0], y: -v[1]).concatenating(CGAffineTransform(scaleX: s, y: s)).concatenating(m)
                    vp = CGSize(width: v[2], height: v[3])
                }
            }
            for c in n.children { visit(c, ctm: m, style: style, viewport: vp, owners: owners) }
        case "g", "a", "symbol":
            for c in n.children { visit(c, ctm: m, style: style, viewport: viewport, owners: owners) }
        case "use":
            let href = (n.attrs["xlink:href"] ?? n.attrs["href"] ?? "").replacingOccurrences(of: "#", with: "")
            guard let target = defs[href] else { return }
            var mm = m
            let x = SVGDocument.length(n.attrs["x"]) ?? 0, y = SVGDocument.length(n.attrs["y"]) ?? 0
            if x != 0 || y != 0 { mm = CGAffineTransform(translationX: x, y: y).concatenating(m) }
            if let p = glyphPath(target) {
                var t = mm
                if let tp = p.copy(using: &t) { emitShape(tp, n: target, style: style, owners: owners, strokeAttr: nil) }
            } else {
                for c in target.children { visit(c, ctm: mm, style: style, viewport: viewport, owners: owners) }
            }
        case "path":
            let p = PathParser.parse(n.attrs["d"] ?? "")
            var t = m
            if let tp = p.copy(using: &t) { emitShape(tp, n: n, style: style, owners: owners, strokeAttr: n.attrs["stroke-width"], scale: m) }
        case "polygon", "polyline":
            let v = numbers(n.attrs["points"] ?? "")
            guard v.count >= 4 else { return }
            let p = CGMutablePath()
            p.move(to: CGPoint(x: v[0], y: v[1]))
            var i = 2
            while i + 1 < v.count { p.addLine(to: CGPoint(x: v[i], y: v[i + 1])); i += 2 }
            if n.name == "polygon" { p.closeSubpath() }
            var t = m
            if let tp = p.copy(using: &t) {
                emitShape(tp, n: n, style: style, owners: owners, strokeAttr: n.attrs["stroke-width"], scale: m, fillOpen: n.name == "polygon")
            }
        case "rect", "ellipse", "circle", "line":
            let a = { (k: String) in SVGDocument.length(n.attrs[k]) ?? 0 }
            let p = CGMutablePath()
            switch n.name {
            case "rect": p.addRect(CGRect(x: a("x"), y: a("y"), width: a("width"), height: a("height")))
            case "ellipse": p.addEllipse(in: CGRect(x: a("cx") - a("rx"), y: a("cy") - a("ry"), width: 2 * a("rx"), height: 2 * a("ry")))
            case "circle": p.addEllipse(in: CGRect(x: a("cx") - a("r"), y: a("cy") - a("r"), width: 2 * a("r"), height: 2 * a("r")))
            default: p.move(to: CGPoint(x: a("x1"), y: a("y1"))); p.addLine(to: CGPoint(x: a("x2"), y: a("y2")))
            }
            var t = m
            if let tp = p.copy(using: &t) {
                emitShape(tp, n: n, style: style, owners: owners, strokeAttr: n.attrs["stroke-width"] ?? (n.name == "line" ? "1" : nil),
                          scale: m, fillOpen: n.name != "line")
            }
        case "text":
            var cursor = CGPoint(x: SVGDocument.length(n.attrs["x"]) ?? 0, y: SVGDocument.length(n.attrs["y"]) ?? 0)
            var runs: [(String, Style, [Int32])] = []
            collectText(n, style: style, owners: owners, into: &runs, isRoot: true)
            let total = runs.reduce(CGFloat(0)) { $0 + CTLineGetTypographicBounds(line($1.0, $1.1), nil, nil, nil) }
            if style.anchor == "end" { cursor.x -= total } else if style.anchor == "middle" { cursor.x -= total / 2 }
            for (s, st, ow) in runs where !s.isEmpty && st.fontSize > 0 {
                let l = line(s, st)
                let w = CTLineGetTypographicBounds(l, nil, nil, nil)
                let origin = cursor.applying(m)
                let scale = sqrt(abs(m.a * m.d - m.b * m.c))
                let sl = scale == 1 ? l : line(s, { var x = st; x.fontSize *= scale; return x }())
                let bounds = CGRect(x: origin.x, y: origin.y - st.fontSize * scale * 0.8, width: w * scale, height: st.fontSize * scale)
                addOp(.init(kind: .text(sl, origin), path: nil, color: resolved(st), owners: ow), bounds: bounds)
                cursor.x += w
            }
        default:
            for c in n.children { visit(c, ctm: m, style: style, viewport: viewport, owners: owners) }
        }
    }

    mutating func collectText(_ n: XMLTree.Node, style: Style, owners: [Int32], into runs: inout [(String, Style, [Int32])], isRoot: Bool) {
        var st = style
        var ow = owners
        if !isRoot {
            if let fs = n.attrs["font-size"], let v = SVGDocument.length(fs) { st.fontSize = v }
            if let f = n.attrs["fill"], let c = parseColor(f) { st.fill = .some(c) }
            if let ff = n.attrs["font-family"] { st.fontFamily = ff }
            ow = register(n, owners: owners)
        }
        for c in n.content {
            switch c {
            case .text(let s):
                let t = s.trimmingCharacters(in: .newlines).replacingOccurrences(of: "\n", with: " ")
                if !t.trimmingCharacters(in: .whitespaces).isEmpty { runs.append((t.trimmingCharacters(in: .whitespaces), st, ow)) }
            case .node(let child):
                if child.name == "tspan" { collectText(child, style: st, owners: ow, into: &runs, isRoot: false) }
            }
        }
    }

    func line(_ s: String, _ st: Style) -> CTLine {
        let family = st.fontFamily.split(separator: ",").first.map { $0.trimmingCharacters(in: .whitespaces) } ?? "Times"
        let name = family == "Times" ? "Times New Roman" : family
        let font = embeddedFonts[family].map { CTFontCreateWithFontDescriptor($0, max(1, st.fontSize), nil) }
            ?? CTFontCreateWithName(name as CFString, max(1, st.fontSize), nil)
        let attr = NSAttributedString(string: s, attributes: [NSAttributedString.Key(kCTFontAttributeName as String): font,
                                                              NSAttributedString.Key(kCTForegroundColorFromContextAttributeName as String): true])
        return CTLineCreateWithAttributedString(attr)
    }

    mutating func emitShape(_ p: CGPath, n: XMLTree.Node, style: Style, owners: [Int32], strokeAttr: String?,
                            scale: CGAffineTransform = .identity, fillOpen: Bool = true) {
        let color = resolved(style)
        let explicitNoFill: Bool = { if case .some(.none) = style.fill { return true }; return n.attrs["fill"] == "none" }()
        let bounds = p.boundingBoxOfPath
        if let sw = strokeAttr.flatMap({ SVGDocument.length($0) }), sw > 0 {
            let s = sqrt(abs(scale.a * scale.d - scale.b * scale.c))
            addOp(.init(kind: .stroke(sw * s), path: p, color: color, owners: owners), bounds: bounds.insetBy(dx: -sw * s / 2, dy: -sw * s / 2))
            // Verovio fills closed shapes and strokes outlines; filling a two-point line is a no-op
            if fillOpen && !explicitNoFill && isClosedOrCurved(n) { addOp(.init(kind: .fill, path: p, color: color, owners: owners), bounds: bounds) }
        } else if !explicitNoFill {
            addOp(.init(kind: .fill, path: p, color: color, owners: owners), bounds: bounds)
        }
    }

    func isClosedOrCurved(_ n: XMLTree.Node) -> Bool {
        if n.name != "path" { return true }
        let d = n.attrs["d"] ?? ""
        return d.contains(where: { "CcQqSsTtZzAa".contains($0) })
    }

    /// A glyph definition that is a single path with a plain transform: flattened once and reused.
    mutating func glyphPath(_ g: XMLTree.Node) -> CGPath? {
        let key = ObjectIdentifier(g)
        if let p = glyphCache[key] { return p }
        let elements = g.name == "path" ? [g] : g.children
        guard elements.count == 1, elements[0].name == "path", elements[0].attrs["stroke-width"] == nil else { return nil }
        let e = elements[0]
        var t = e.attrs["transform"].map(parseTransform) ?? .identity
        if let gt = g.attrs["transform"], g.name != "path" { t = t.concatenating(parseTransform(gt)) }
        guard let p = PathParser.parse(e.attrs["d"] ?? "").copy(using: &t) else { return nil }
        glyphCache[key] = p
        return p
    }
}

// MARK: - attribute parsing

func numbers(_ s: String) -> [CGFloat] {
    var out: [CGFloat] = []
    var sc = NumberScanner(s)
    while let v = sc.next() { out.append(v) }
    return out
}

func parseTransform(_ s: String) -> CGAffineTransform {
    var result = CGAffineTransform.identity
    var rest = s[...]
    while let open = rest.firstIndex(of: "("), let close = rest[open...].firstIndex(of: ")") {
        let name = rest[..<open].trimmingCharacters(in: .whitespaces.union(CharacterSet(charactersIn: ",")))
        let v = numbers(String(rest[rest.index(after: open)..<close]))
        var t = CGAffineTransform.identity
        switch name {
        case "translate": t = CGAffineTransform(translationX: v.first ?? 0, y: v.count > 1 ? v[1] : 0)
        case "scale": t = CGAffineTransform(scaleX: v.first ?? 1, y: v.count > 1 ? v[1] : (v.first ?? 1))
        case "rotate":
            let a = (v.first ?? 0) * .pi / 180
            if v.count == 3 {
                t = CGAffineTransform(translationX: -v[1], y: -v[2]).concatenating(CGAffineTransform(rotationAngle: a))
                    .concatenating(CGAffineTransform(translationX: v[1], y: v[2]))
            } else { t = CGAffineTransform(rotationAngle: a) }
        case "matrix" where v.count == 6: t = CGAffineTransform(a: v[0], b: v[1], c: v[2], d: v[3], tx: v[4], ty: v[5])
        case "skewX": t = CGAffineTransform(a: 1, b: 0, c: tan((v.first ?? 0) * .pi / 180), d: 1, tx: 0, ty: 0)
        case "skewY": t = CGAffineTransform(a: 1, b: tan((v.first ?? 0) * .pi / 180), c: 0, d: 1, tx: 0, ty: 0)
        default: break
        }
        // SVG applies the list left to right onto the element: M = T1 · T2 · …
        result = t.concatenating(result)
        rest = rest[rest.index(after: close)...]
    }
    return result
}

func parseColor(_ s: String) -> CGColor? {
    let t = s.trimmingCharacters(in: .whitespaces).lowercased()
    if t.hasPrefix("#") {
        var hex = String(t.dropFirst())
        if hex.count == 3 { hex = hex.map { "\($0)\($0)" }.joined() }
        guard hex.count == 6, let v = Int(hex, radix: 16) else { return nil }
        return CGColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                       blue: CGFloat(v & 0xFF) / 255, alpha: 1)
    }
    switch t {
    case "black": return nil // the ink colour, so dark mode and high contrast can replace it
    case "white": return CGColor(gray: 1, alpha: 1)
    case "red": return CGColor(srgbRed: 1, green: 0, blue: 0, alpha: 1)
    case "blue": return CGColor(srgbRed: 0, green: 0, blue: 1, alpha: 1)
    case "dodgerblue": return CGColor(srgbRed: 0.12, green: 0.56, blue: 1, alpha: 1)
    case "limegreen": return CGColor(srgbRed: 0.2, green: 0.8, blue: 0.2, alpha: 1)
    default: return nil
    }
}

struct NumberScanner {
    let u: [UInt8]
    var i = 0
    init(_ s: String) { u = Array(s.utf8) }

    mutating func skipSeparators() {
        while i < u.count, u[i] == 32 || u[i] == 44 || u[i] == 10 || u[i] == 13 || u[i] == 9 { i += 1 }
    }

    /// Next number, or nil if the next token is not a number (a command letter or the end).
    mutating func next() -> CGFloat? {
        skipSeparators()
        guard i < u.count else { return nil }
        let start = i
        if u[i] == 43 || u[i] == 45 { i += 1 } // + -
        var sawDot = false, sawDigit = false
        while i < u.count {
            let c = u[i]
            if c >= 48 && c <= 57 { sawDigit = true; i += 1 }
            else if c == 46 && !sawDot { sawDot = true; i += 1 }
            else if (c == 101 || c == 69) && sawDigit { // exponent
                i += 1
                if i < u.count, u[i] == 43 || u[i] == 45 { i += 1 }
            } else { break }
        }
        guard sawDigit else { i = start; return nil }
        return CGFloat(Double(String(decoding: u[start..<i], as: UTF8.self)) ?? 0)
    }

    mutating func command() -> UInt8? {
        skipSeparators()
        guard i < u.count else { return nil }
        let c = u[i]
        if (c >= 65 && c <= 90) || (c >= 97 && c <= 122) { i += 1; return c }
        return nil
    }

    var atEnd: Bool { mutating get { skipSeparators(); return i >= u.count } }
}

enum PathParser {
    static func parse(_ d: String) -> CGPath {
        let p = CGMutablePath()
        var sc = NumberScanner(d)
        var cmd: UInt8 = 77 // M
        var cur = CGPoint.zero, start = CGPoint.zero, lastCtrl: CGPoint?
        var lastCmd: UInt8 = 0
        while !sc.atEnd {
            if let c = sc.command() { cmd = c }
            let rel = cmd >= 97
            let base = rel ? cur : .zero
            func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: base.x + x, y: base.y + y) }
            switch cmd | 0x20 { // lowercase
            case 109: // m
                guard let x = sc.next(), let y = sc.next() else { return p }
                cur = pt(x, y); start = cur; p.move(to: cur)
                cmd = rel ? 108 : 76 // subsequent pairs are lineto
            case 108: // l
                guard let x = sc.next(), let y = sc.next() else { return p }
                cur = pt(x, y); p.addLine(to: cur)
            case 104: // h
                guard let x = sc.next() else { return p }
                cur = CGPoint(x: rel ? cur.x + x : x, y: cur.y); p.addLine(to: cur)
            case 118: // v
                guard let y = sc.next() else { return p }
                cur = CGPoint(x: cur.x, y: rel ? cur.y + y : y); p.addLine(to: cur)
            case 99: // c
                guard let x1 = sc.next(), let y1 = sc.next(), let x2 = sc.next(), let y2 = sc.next(), let x = sc.next(), let y = sc.next() else { return p }
                let c2 = pt(x2, y2)
                cur = pt(x, y); p.addCurve(to: cur, control1: pt(x1, y1), control2: c2); lastCtrl = c2
            case 115: // s
                guard let x2 = sc.next(), let y2 = sc.next(), let x = sc.next(), let y = sc.next() else { return p }
                let c1 = ([99, 115].contains(lastCmd | 0x20) ? lastCtrl.map { CGPoint(x: 2 * cur.x - $0.x, y: 2 * cur.y - $0.y) } : nil) ?? cur
                let c2 = pt(x2, y2)
                cur = pt(x, y); p.addCurve(to: cur, control1: c1, control2: c2); lastCtrl = c2
            case 113: // q
                guard let x1 = sc.next(), let y1 = sc.next(), let x = sc.next(), let y = sc.next() else { return p }
                let c = pt(x1, y1)
                cur = pt(x, y); p.addQuadCurve(to: cur, control: c); lastCtrl = c
            case 116: // t
                guard let x = sc.next(), let y = sc.next() else { return p }
                let c = ([113, 116].contains(lastCmd | 0x20) ? lastCtrl.map { CGPoint(x: 2 * cur.x - $0.x, y: 2 * cur.y - $0.y) } : nil) ?? cur
                cur = pt(x, y); p.addQuadCurve(to: cur, control: c); lastCtrl = c
            case 97: // a — approximated by a line (Verovio does not emit arcs)
                guard sc.next() != nil, sc.next() != nil, sc.next() != nil, sc.next() != nil, sc.next() != nil,
                      let x = sc.next(), let y = sc.next() else { return p }
                cur = pt(x, y); p.addLine(to: cur)
            case 122: // z
                p.closeSubpath(); cur = start
            default:
                return p
            }
            lastCmd = cmd
            if cmd | 0x20 == 122 { continue }
        }
        return p
    }
}

// MARK: - XML tree

final class XMLTree: NSObject, XMLParserDelegate {
    final class Node {
        enum Content { case text(String), node(Node) }
        let name: String
        let attrs: [String: String]
        weak var parent: Node?
        var content: [Content] = []
        var children: [Node] { content.compactMap { if case .node(let n) = $0 { return n } else { return nil } } }
        var parentIsDefs: Bool { parent?.name == "defs" }
        init(name: String, attrs: [String: String], parent: Node?) { self.name = name; self.attrs = attrs; self.parent = parent }
        func walk(_ f: (Node) -> Void) { f(self); for c in children { c.walk(f) } }
    }

    var stack: [Node] = []
    var root: Node?

    static func parse(_ data: Data) throws -> Node {
        let t = XMLTree()
        let p = XMLParser(data: data)
        p.delegate = t
        p.shouldProcessNamespaces = false
        guard p.parse(), let r = t.root else { throw SVGError.parse(p.parserError?.localizedDescription ?? "empty") }
        return r
    }

    func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?, qualifiedName: String?, attributes: [String: String]) {
        let n = Node(name: name, attrs: attributes, parent: stack.last)
        if let top = stack.last { top.content.append(.node(n)) } else { root = n }
        stack.append(n)
    }

    func parser(_ parser: XMLParser, didEndElement name: String, namespaceURI: String?, qualifiedName: String?) { stack.removeLast() }

    func parser(_ parser: XMLParser, foundCharacters s: String) {
        guard let top = stack.last else { return }
        if case .text(let prev)? = top.content.last {
            top.content[top.content.count - 1] = .text(prev + s)
        } else { top.content.append(.text(s)) }
    }
}

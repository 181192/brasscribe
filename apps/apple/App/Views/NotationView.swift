import NotationKit
import ScoreKit
import SVGRender
import SwiftUI

/// The engraved score, drawn natively from Verovio's SVG with the score tokens, with one
/// accessibility element per part per bar (label = talking-score description), rotors for
/// bars, parts and uncertain notes, and custom actions to play or loop a bar.
struct NotationView: View {
    @Bindable var model: PracticeModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.horizontalSizeClass) private var hsize
    @Environment(AppModel.self) private var app
    @Namespace private var rotorNS
    @State private var lastScrolledBar = -1

    /// The first page scrolls to the very top, so the part view's header shows with it.
    private func target(_ page: Int) -> String {
        page == model.pages.first?.number ? "page-top" : "page-\(page)"
    }

    var body: some View {
        GeometryReader { geo in
            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    LazyVStack(spacing: BrasscribeDesign.Space.s3) {
                        // the part view's header scrolls with the music, so it never takes the score's room
                        VStack(alignment: .leading, spacing: 0) {
                            if hsize == .compact {
                                StatusLine(model: model, toCheck: model.toCheck, wide: false) { app.path.append(.review(model.piece)) }
                            }
                            PartHeader(model: model)
                        }
                        .padding(.top, BrasscribeDesign.Space.s1)
                        .id("page-top")
                        ForEach(model.pages, id: \.number) { page in
                            PageView(model: model, page: page, rotorNS: rotorNS)
                                .id("page-\(page.number)")
                        }
                    }
                    .padding(.vertical, BrasscribeDesign.Space.s2)
                    // The pages are engraved to this width. Pinning it here keeps the
                    // fixed-width pages from raising the window's minimum size.
                    .frame(width: max(0, geo.size.width), alignment: .topLeading)
                    .clipped()
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(Text("Score pages"))
                }
                .background(Color.Brasscribe.bg)
                .accessibilityIdentifier("scoreArea")
                .onAppear {
                    // Engrave once the width is known; phones open on the musician's own
                    // part, which is readable at that width.
                    model.viewWidth = geo.size.width - 16
                    if hsize == .compact, model.shownPart == nil, !model.openedOnMyPart, LaunchOptions.screen != "score" {
                        model.openedOnMyPart = true
                        model.shownPart = model.myPart
                    } else {
                        model.relayout()
                    }
                }
                .onChange(of: geo.size.width) { _, w in
                    if abs(w - 16 - model.viewWidth) > 40 { model.viewWidth = w - 16; model.relayout() }
                }
                .onChange(of: model.layoutVersion) { _, _ in
                    // after (re)engraving, show the current bar
                    DispatchQueue.main.async { proxy.scrollTo(target(model.pageNumber(forBar: model.currentBar)), anchor: .top) }
                }
                .onChange(of: model.pages.count) { _, _ in
                    // pages arrive one by one: once the current bar's page is here, show it
                    let page = model.pageNumber(forBar: model.currentBar)
                    guard page != lastScrolledBar, model.pages.contains(where: { $0.number == page }) else { return }
                    lastScrolledBar = page
                    DispatchQueue.main.async { proxy.scrollTo(target(page), anchor: .top) }
                }
                .onChange(of: model.currentBar) { _, bar in
                    let page = model.pageNumber(forBar: bar)
                    guard page != lastScrolledBar else { return }
                    lastScrolledBar = page
                    withAnimation(BrasscribeDesign.Motion.animation(BrasscribeDesign.Motion.slow, reduceMotion: reduceMotion)) {
                        proxy.scrollTo(target(page), anchor: .top)
                    }
                }
            }
        }
        // the score scrolls; it never asks the window to be as tall (or wide) as a page
        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
        .overlay {
            if model.pages.isEmpty {
                ProgressView(String(localized: "Laying out the pages…"))
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Score"))
        .accessibilityRotor(Text("Bars")) {
            ForEach(Array(model.score.measures.indices), id: \.self) { i in
                AccessibilityRotorEntry(Text(model.barLabel(i)), id: "\(i)-0", in: rotorNS)
            }
        }
        .accessibilityRotor(Text("Parts")) {
            ForEach(Array(model.displayedParts.enumerated()), id: \.offset) { k, p in
                AccessibilityRotorEntry(Text(p.displayName), id: "\(model.currentBar)-\(k)", in: rotorNS)
            }
        }
        .accessibilityRotor(Text("Uncertain notes")) {
            ForEach(uncertainEntries, id: \.self) { key in
                AccessibilityRotorEntry(Text(rotorLabel(key)), id: key, in: rotorNS)
            }
        }
    }

    private var uncertainEntries: [String] {
        var out: [String] = []
        for i in model.score.measures.indices {
            for (k, p) in model.displayedParts.enumerated() where p.notes(inMeasure: i).contains(where: model.uncertainty.isUncertain) {
                out.append("\(i)-\(k)")
            }
        }
        return out
    }

    private func rotorLabel(_ key: String) -> String {
        let bits = key.split(separator: "-").compactMap { Int($0) }
        guard bits.count == 2, model.displayedParts.indices.contains(bits[1]) else { return key }
        return "\(model.barLabel(bits[0])), \(model.displayedParts[bits[1]].name)"
    }
}

/// One engraved page, drawn in a single Canvas in this order:
/// 1. the bar band: the loop tint, else the cursor-bar tint, else the ad lib tint (tints
///    never stack; in high contrast there are no tints, only outlines);
/// 2. the notation in ink, with uncertain notes in their colour;
/// 3. the loop brackets and the "Loop 12–13" label;
/// 4. a "?" above each uncertain note, boxed when very uncertain, in the note's colour;
/// 5. the 3 pt playback cursor across the whole system.
private struct PageView: View {
    @Bindable var model: PracticeModel
    let page: ScoreRenderer.Page
    let rotorNS: Namespace.ID
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let doc = page.svg
        let barIndex: [String: Int] = Dictionary(uniqueKeysWithValues: (model.renderer?.measureIDs ?? []).enumerated().map { ($1, $0) })
        let paint = ScorePaint(model: model, highContrast: contrast == .increased)
        ZStack(alignment: .topLeading) {
            Canvas(opaque: false, rendersAsynchronously: false) { ctx, _ in
                paint.draw(page, in: ctx)
            }
            .frame(width: doc.size.width, height: doc.size.height)
            .accessibilityHidden(true)

            ForEach(page.measureIDs, id: \.self) { mid in
                if let bar = barIndex[mid], let mf = doc.frames[mid] {
                    ForEach(Array((page.staves[mid] ?? []).enumerated()), id: \.offset) { k, staffID in
                        if let sf = doc.frames[staffID], model.displayedParts.indices.contains(k) {
                            StaffElement(model: model, bar: bar, part: model.displayedParts[k], partIndex: k,
                                         frame: sf.union(CGRect(x: mf.minX, y: sf.minY, width: mf.width, height: sf.height)),
                                         rotorNS: rotorNS)
                        }
                    }
                }
            }
        }
        .frame(width: doc.size.width, height: doc.size.height)
        .background(Color.Brasscribe.bg)
    }

    /// The band behind one bar: the bar's width, from the top staff line of the system to
    /// the bottom one.
    nonisolated static func band(_ measureID: String, doc: SVGDocument, page: ScoreRenderer.Page) -> CGRect? {
        guard let mf = doc.frames[measureID] else { return nil }
        let staves = (page.staves[measureID] ?? []).compactMap { page.staffLines[$0] }
        guard let top = staves.map(\.minY).min(), let bottom = staves.map(\.maxY).max() else { return nil }
        let minX = max(mf.minX, staves.map(\.minX).min() ?? mf.minX)
        let maxX = min(mf.maxX, staves.map(\.maxX).max() ?? mf.maxX)
        return CGRect(x: minX, y: top, width: max(0, maxX - minX), height: bottom - top)
    }
}

/// Everything drawn on a page, in order (see PageView), for the score view and the music stand.
/// `visible` limits the notation to the part of the page on screen.
struct ScorePaint {
    let barIndex: [String: Int]
    let levels: [String: UncertaintyLevel]
    let sounding: Set<String>
    let current: Int
    let loop: ClosedRange<Int>?
    let adLib: [ClosedRange<Int>]
    let highContrast: Bool
    let loopLabel: String?

    @MainActor init(model: PracticeModel, highContrast: Bool) {
        barIndex = Dictionary(uniqueKeysWithValues: (model.renderer?.measureIDs ?? []).enumerated().map { ($1, $0) })
        levels = model.renderer?.uncertainLevels ?? [:]
        sounding = model.soundingNotes
        current = model.currentBar
        let loop: ClosedRange<Int>? = model.looping ? min(model.loopFrom, model.loopTo)...max(model.loopFrom, model.loopTo) : nil
        self.loop = loop
        adLib = model.freeTimeBars
        self.highContrast = highContrast
        loopLabel = loop.map { l in
            l.count == 1 ? String(localized: "Repeat \(l.lowerBound + 1)") : String(localized: "Repeat \(l.lowerBound + 1)–\(l.upperBound + 1)")
        }
    }

    func draw(_ page: ScoreRenderer.Page, in ctx: GraphicsContext, visible: CGRect? = nil) {
        let doc = page.svg
        var bars: [(bar: Int, rect: CGRect)] = []
        for mid in page.measureIDs {
            guard let bar = barIndex[mid], let r = PageView.band(mid, doc: doc, page: page) else { continue }
            bars.append((bar, r))
            let inLoop = loop?.contains(bar) == true
            let inAdLib = adLib.contains { $0.contains(bar) }
            if highContrast {
                if !inLoop, bar == current || inAdLib {
                    ctx.stroke(Path(r), with: .color(.Brasscribe.staff),
                               style: StrokeStyle(lineWidth: 1, dash: bar == current ? [] : [4, 3]))
                }
            } else if inLoop {
                ctx.fill(Path(r), with: .color(.Brasscribe.loopTint))
            } else if bar == current {
                ctx.fill(Path(r), with: .color(.Brasscribe.cursorTint))
            } else if inAdLib {
                ctx.fill(Path(r), with: .color(.Brasscribe.adlibTint))
            }
        }

        let env = ctx.environment
        let ink = Color.Brasscribe.ink.resolve(in: env).cgColor
        let uncertain = Color.Brasscribe.uncertain.resolve(in: env).cgColor
        let very = Color.Brasscribe.veryUncertain.resolve(in: env).cgColor
        var highlight: [String: CGColor] = [:]
        for (id, level) in levels { highlight[id] = level == .veryUncertain ? very : uncertain }
        ctx.withCGContext { cg in doc.draw(in: cg, ink: ink, highlight: highlight, keepDocumentColors: false, visible: visible) }

        if let l = loop {
            let arm: CGFloat = 6
            for (bar, r) in bars where bar == l.lowerBound || bar == l.upperBound {
                var p = Path()
                if bar == l.lowerBound {
                    p.move(to: CGPoint(x: r.minX + arm, y: r.minY)); p.addLine(to: CGPoint(x: r.minX, y: r.minY))
                    p.addLine(to: CGPoint(x: r.minX, y: r.maxY)); p.addLine(to: CGPoint(x: r.minX + arm, y: r.maxY))
                    if let loopLabel {
                        ctx.draw(Text(loopLabel).font(.caption.weight(.semibold)).foregroundStyle(Color.Brasscribe.loopEdge),
                                 at: CGPoint(x: r.minX + 2, y: r.minY - 16), anchor: .bottomLeading)
                    }
                }
                if bar == l.upperBound {
                    p.move(to: CGPoint(x: r.maxX - arm, y: r.minY)); p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
                    p.addLine(to: CGPoint(x: r.maxX, y: r.maxY)); p.addLine(to: CGPoint(x: r.maxX - arm, y: r.maxY))
                }
                ctx.stroke(p, with: .color(.Brasscribe.loopEdge), lineWidth: BrasscribeDesign.Score.loopEdgeWidth)
            }
        }

        for (staffID, notes) in page.notesByStaff {
            guard let lines = page.staffLines[staffID] ?? doc.frames[staffID] else { continue }
            let space = max(3, lines.height / 4)
            let size = space * BrasscribeDesign.Score.markSizeStaffSpaces
            for id in notes {
                guard let level = levels[id], let f = doc.frames[id] else { continue }
                let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Brasscribe.uncertain
                let bottom = min(lines.minY, f.minY) - space * 0.5
                let center = CGPoint(x: f.midX, y: bottom - size * 0.6)
                ctx.draw(Text(verbatim: "?").font(.system(size: size, weight: .bold)).foregroundStyle(color), at: center)
                if level == .veryUncertain {
                    let box = CGRect(x: center.x - size * 0.45, y: center.y - size * 0.62, width: size * 0.9, height: size * 1.24)
                    ctx.stroke(Path(roundedRect: box, cornerRadius: 1.5), with: .color(color), lineWidth: max(1.5, size / 11))
                }
            }
        }

        if let (_, r) = bars.first(where: { $0.bar == current }) {
            let xs = sounding.compactMap { doc.frames[$0]?.midX }.filter { $0 >= r.minX && $0 <= r.maxX }
            let x = xs.min() ?? r.minX + 6
            let w = BrasscribeDesign.Score.cursorWidth
            ctx.fill(Path(CGRect(x: x - w / 2, y: r.minY - 4, width: w, height: r.height + 8)), with: .color(.Brasscribe.cursor))
        }
    }
}

private struct StaffElement: View {
    @Bindable var model: PracticeModel
    let bar: Int
    // The part itself, not an index: picking one part shrinks displayedParts while these views are still alive.
    let part: Part
    let partIndex: Int
    let frame: CGRect
    let rotorNS: Namespace.ID

    var body: some View {
        Rectangle()
            .fill(Color.clear)
            .contentShape(Rectangle())
            .frame(width: max(8, frame.width), height: max(8, frame.height))
            .position(x: frame.midX, y: frame.midY)
            .onTapGesture { model.goToBar(bar) }
            .accessibilityElement()
            .accessibilityLabel(Text(model.describe(partID: part.id, bar: bar)))
            .accessibilityAddTraits(bar == model.currentBar ? [.isSelected, .isButton] : .isButton)
            .accessibilityHint(Text("Double-tap to move playback here."))
            .accessibilityAction { model.goToBar(bar) }
            .accessibilityAction(named: Text("Play this bar")) { model.goToBar(bar); if !model.isPlaying { model.togglePlay() } }
            .accessibilityAction(named: Text("Loop this bar")) { model.loopFrom = bar; model.loopTo = bar; model.setLoop(true) }
            .accessibilityAction(named: Text("Listen to the original")) { model.listen(toBar: bar, original: true) }
            .accessibilityRotorEntry(id: "\(bar)-\(partIndex)", in: rotorNS)
            .accessibilityIdentifier("staff-\(bar)-\(partIndex)")
    }
}

import NotationKit
import ScoreKit
import SVGRender
import SwiftUI

/// Colour-blind-safe palette (Okabe–Ito) with contrast ≥ 3:1 against the page in both
/// appearances; high contrast switches to pure ink.
struct NotationPalette {
    let ink: CGColor
    let paper: Color
    let cursor: CGColor
    let cursorBox: Color
    let uncertain: CGColor
    let uncertainMark: Color

    static func make(dark: Bool, highContrast: Bool) -> NotationPalette {
        if dark {
            return NotationPalette(ink: CGColor(gray: 1, alpha: 1), paper: Color(white: highContrast ? 0 : 0.1),
                                   cursor: CGColor(srgbRed: 0.34, green: 0.71, blue: 0.91, alpha: 1), cursorBox: Color(red: 0.34, green: 0.71, blue: 0.91),
                                   uncertain: CGColor(srgbRed: 1, green: 0.62, blue: 0.29, alpha: 1), uncertainMark: Color(red: 1, green: 0.62, blue: 0.29))
        }
        return NotationPalette(ink: CGColor(gray: 0, alpha: 1), paper: .white,
                               cursor: CGColor(srgbRed: 0, green: 0.447, blue: 0.698, alpha: 1), cursorBox: Color(red: 0, green: 0.447, blue: 0.698),
                               uncertain: CGColor(srgbRed: 0.835, green: 0.369, blue: 0, alpha: 1), uncertainMark: Color(red: 0.835, green: 0.369, blue: 0))
    }
}

/// The engraved score, drawn natively from Verovio's SVG, with one accessibility element
/// per part per bar (label = talking-score description), rotors for bars, parts and
/// uncertain notes, and custom actions to play or loop a bar.
struct NotationView: View {
    @Bindable var model: PracticeModel
    @Environment(\.colorScheme) private var scheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var rotorNS
    @State private var lastScrolledBar = -1

    var body: some View {
        let palette = NotationPalette.make(dark: scheme == .dark, highContrast: contrast == .increased)
        GeometryReader { geo in
            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    LazyVStack(spacing: 12) {
                        ForEach(model.pages, id: \.number) { page in
                            PageView(model: model, page: page, palette: palette, rotorNS: rotorNS)
                                .id("page-\(page.number)")
                        }
                    }
                    .padding(.vertical, 8)
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(Text("Score pages"))
                }
                .background(palette.paper)
                .onAppear { model.viewWidth = geo.size.width - 16 }
                .onChange(of: geo.size.width) { _, w in
                    if abs(w - 16 - model.viewWidth) > 40 { model.viewWidth = w - 16; model.relayout() }
                }
                .onChange(of: model.layoutVersion) { _, _ in
                    // after (re)engraving, show the current bar
                    DispatchQueue.main.async { proxy.scrollTo("page-\(model.pageNumber(forBar: model.currentBar))", anchor: .top) }
                }
                .onChange(of: model.currentBar) { _, bar in
                    let page = model.pageNumber(forBar: bar)
                    guard page != lastScrolledBar else { return }
                    lastScrolledBar = page
                    let id = "page-\(page)"
                    if reduceMotion { proxy.scrollTo(id, anchor: .top) } else { withAnimation(.easeInOut(duration: 0.25)) { proxy.scrollTo(id, anchor: .top) } }
                }
            }
        }
        .overlay {
            if model.pages.isEmpty {
                ProgressView(String(localized: "Engraving the score…"))
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
                AccessibilityRotorEntry(Text(p.name), id: "\(model.currentBar)-\(k)", in: rotorNS)
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

private struct PageView: View {
    @Bindable var model: PracticeModel
    let page: ScoreRenderer.Page
    let palette: NotationPalette
    let rotorNS: Namespace.ID

    var body: some View {
        let doc = page.svg
        let barIndex: [String: Int] = Dictionary(uniqueKeysWithValues: (model.renderer?.measureIDs ?? []).enumerated().map { ($1, $0) })
        let uncertainIDs = model.renderer?.uncertainNoteIDs ?? []
        let sounding = model.soundingNotes
        let current = model.currentBar
        ZStack(alignment: .topLeading) {
            Canvas(opaque: false, rendersAsynchronously: false) { ctx, size in
                var highlight: [String: CGColor] = [:]
                for id in uncertainIDs { highlight[id] = palette.uncertain }
                for id in sounding { highlight[id] = palette.cursor }
                ctx.withCGContext { cg in doc.draw(in: cg, ink: palette.ink, highlight: highlight, keepDocumentColors: false) }
            }
            .frame(width: doc.size.width, height: doc.size.height)
            .accessibilityHidden(true)

            // Uncertainty shape: an open diamond above each flagged note (colour is never the only cue).
            ForEach(page.notesByStaff.values.flatMap { $0 }.filter { uncertainIDs.contains($0) }, id: \.self) { id in
                if let f = doc.frames[id] {
                    Diamond().stroke(palette.uncertainMark, lineWidth: 1.5)
                        .frame(width: 7, height: 7)
                        .position(x: f.midX, y: f.minY - 7)
                        .accessibilityHidden(true)
                }
            }

            ForEach(page.measureIDs, id: \.self) { mid in
                if let bar = barIndex[mid], let mf = doc.frames[mid] {
                    // cursor: outlined box around the current bar (shape plus colour)
                    if bar == current {
                        RoundedRectangle(cornerRadius: 3)
                            .stroke(palette.cursorBox, lineWidth: 2.5)
                            .background(RoundedRectangle(cornerRadius: 3).fill(palette.cursorBox.opacity(0.08)))
                            .frame(width: mf.width + 6, height: mf.height + 6)
                            .position(x: mf.midX, y: mf.midY)
                            .accessibilityHidden(true)
                    }
                    ForEach(Array((page.staves[mid] ?? []).enumerated()), id: \.offset) { k, staffID in
                        if let sf = doc.frames[staffID], model.displayedParts.indices.contains(k) {
                            StaffElement(model: model, bar: bar, partIndex: k, frame: sf.union(CGRect(x: mf.minX, y: sf.minY, width: mf.width, height: sf.height)),
                                         rotorNS: rotorNS)
                        }
                    }
                }
            }
        }
        .frame(width: doc.size.width, height: doc.size.height)
        .background(palette.paper)
    }
}

private struct StaffElement: View {
    @Bindable var model: PracticeModel
    let bar: Int
    let partIndex: Int
    let frame: CGRect
    let rotorNS: Namespace.ID

    var body: some View {
        let part = model.displayedParts[partIndex]
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

struct Diamond: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.midY))
        p.addLine(to: CGPoint(x: r.midX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX, y: r.midY))
        p.closeSubpath()
        return p
    }
}

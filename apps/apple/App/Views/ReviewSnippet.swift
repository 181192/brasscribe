import NotationKit
import ScoreKit
import SVGRender
import SwiftUI

/// The bar under review, drawn on its staff with the neighbouring bar for context: the
/// part engraved on its own, cropped to the bar, with the note being checked ringed in ink
/// and every uncertain note in its colour with its "?".
struct BarSnippet: View {
    let piece: Piece
    let partID: String
    let bar: Int
    let tick: Int

    @State private var crop: Crop?

    struct Crop {
        let doc: SVGDocument
        let rect: CGRect
        let lines: CGRect
        let target: CGRect?
        let levels: [String: UncertaintyLevel]
        let notes: [String]
    }

    var body: some View {
        Group {
            if let crop {
                Canvas { ctx, size in
                    let scale = min(size.width / crop.rect.width, size.height / crop.rect.height)
                    let dx = (size.width - crop.rect.width * scale) / 2
                    ctx.translateBy(x: dx - crop.rect.minX * scale, y: -crop.rect.minY * scale)
                    ctx.scaleBy(x: scale, y: scale)
                    ctx.clip(to: Path(crop.rect))
                    let env = ctx.environment
                    let ink = Color.Brasscribe.ink.resolve(in: env).cgColor
                    let u = Color.Brasscribe.uncertain.resolve(in: env).cgColor
                    let v = Color.Brasscribe.veryUncertain.resolve(in: env).cgColor
                    var hi: [String: CGColor] = [:]
                    for (id, l) in crop.levels { hi[id] = l == .veryUncertain ? v : u }
                    ctx.withCGContext { cg in crop.doc.draw(in: cg, ink: ink, highlight: hi, keepDocumentColors: false) }
                    let space = max(3, crop.lines.height / 4)
                    let size = space * BrasscribeDesign.Score.markSizeStaffSpaces
                    for id in crop.notes {
                        guard let level = crop.levels[id], let f = crop.doc.frames[id] else { continue }
                        let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Brasscribe.uncertain
                        let center = CGPoint(x: f.midX, y: min(crop.lines.minY, f.minY) - space * 0.5 - size * 0.6)
                        ctx.draw(Text(verbatim: "?").font(.system(size: size, weight: .bold)).foregroundStyle(color), at: center)
                        if level == .veryUncertain {
                            let box = CGRect(x: center.x - size * 0.45, y: center.y - size * 0.62, width: size * 0.9, height: size * 1.24)
                            ctx.stroke(Path(roundedRect: box, cornerRadius: 1.5), with: .color(color), lineWidth: max(1.5, size / 11))
                        }
                    }
                    if let t = crop.target {
                        ctx.stroke(Path(roundedRect: t.insetBy(dx: -3, dy: -3), cornerRadius: 3), with: .color(.Brasscribe.focus),
                                   lineWidth: BrasscribeDesign.Score.focusWidth)
                    }
                }
                .frame(height: 120)
                .accessibilityHidden(true)
            } else {
                Color.clear.frame(height: 120)
                    .overlay { ProgressView().controlSize(.small) }
                    .accessibilityHidden(true)
            }
        }
        .task(id: "\(partID)-\(bar)-\(tick)") { crop = await Self.make(piece: piece, partID: partID, bar: bar, tick: tick) }
    }

    /// One engraving per part, kept while the review is open.
    @MainActor private static var engraved: [String: ScoreRenderer] = [:]

    /// Drop the engravings of a piece after its notes change.
    @MainActor static func forget(_ piece: Piece) {
        engraved = engraved.filter { !$0.key.hasPrefix(piece.id.uuidString) }
    }

    @MainActor static func make(piece: Piece, partID: String, bar: Int, tick: Int) async -> Crop? {
        let key = "\(piece.id)-\(partID)"
        let r: ScoreRenderer
        if let have = engraved[key] {
            r = have
        } else {
            guard let xml = try? piece.musicXML() else { return nil }
            let made: ScoreRenderer? = await Task.detached {
                guard let r = ScoreRenderer(musicXML: PartNames.localized(xml)),
                      r.apply(ScoreRenderer.Layout(width: 900, zoom: 1, parts: [partID], pitch: .written, height: 100_000)) else { return nil }
                return r
            }.value
            guard let made else { return nil }
            engraved[key] = made
            r = made
        }
        guard r.measureIDs.indices.contains(bar) else { return nil }
        let mid = r.measureIDs[bar]
        let n = r.pageNumber(forMeasure: mid)
        guard let page = r.page(max(1, n)), let mf = page.svg.frames[mid] else { return nil }
        let staff = page.staves[mid]?.first
        let lines = staff.flatMap { page.staffLines[$0] } ?? mf
        // the bar and its neighbour on the same line
        var rect = mf
        if let i = page.measureIDs.firstIndex(of: mid) {
            let next = page.measureIDs.indices.contains(i + 1) ? page.svg.frames[page.measureIDs[i + 1]] : nil
            if let next, abs(next.midY - mf.midY) < mf.height / 2 { rect = rect.union(next) }
            else if i > 0, let prev = page.svg.frames[page.measureIDs[i - 1]], abs(prev.midY - mf.midY) < mf.height / 2 { rect = rect.union(prev) }
        }
        let space = lines.height / 4
        rect = CGRect(x: rect.minX - space, y: lines.minY - space * 5, width: rect.width + space * 2, height: lines.height + space * 9)
        let onset = Set(r.sounding(atBeat: Double(tick) / Double(Score.ticksPerQuarter)).notes)
        let notes = staff.flatMap { page.notesByStaff[$0] } ?? []
        let target = notes.first { onset.contains($0) && (page.svg.frames[$0].map { mf.contains(CGPoint(x: $0.midX, y: mf.midY)) } ?? false) }
            .flatMap { page.svg.frames[$0] }
        return Crop(doc: page.svg, rect: rect, lines: lines, target: target, levels: r.uncertainLevels, notes: notes)
    }
}

/// "Change note…": the likely alternatives for the note being checked (a semitone or an
/// octave either way). The change goes into the recording's notes, and the score is
/// arranged again on this device.
struct ChangeNoteSheet: View {
    let current: String
    let options: [(delta: Int, title: String)]
    let apply: (Int) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(options, id: \.delta) { o in
                        Button { apply(o.delta); dismiss() } label: {
                            HStack {
                                Text(o.title).foregroundStyle(Color.Brasscribe.text)
                                Spacer()
                                Image(systemName: BrasscribeIcon.open.systemName).foregroundStyle(Color.Brasscribe.textMuted)
                            }
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                } header: {
                    Text("It's written as \(current) now. Choose what you hear.")
                } footer: {
                    Text("The parts are arranged again with the new note. Nothing else changes.")
                }
            }
            .navigationTitle(Text("Change note"))
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
        .presentationDetents([.medium])
        #if os(macOS)
        .frame(minWidth: 420, minHeight: 360)
        #endif
    }
}

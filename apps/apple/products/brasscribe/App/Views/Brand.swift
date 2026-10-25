import ScoreKit
import SVGRender
import SwiftUI

// Brasscribe's own pieces: the display face, the mark and the lockup, the score's marks of doubt and the review's
// selected row. The brand shows only through the tokens (design/brands/brasscribe/dist/apple), the one button shape,
// the display face and the mark.

/// The icons the shared Play screens draw: Brasscribe's.
typealias PlayIcon = BrasscribeIcon

extension Font.Brasscribe {
    /// Instrument Serif for screen titles of 28 pt and up (scales with Dynamic Type).
    static func display(_ size: CGFloat = 40, italic: Bool = false) -> Font {
        .custom(italic ? "InstrumentSerif-Italic" : "InstrumentSerif-Regular", size: max(28, size), relativeTo: .largeTitle)
    }
}

/// A display headline, optionally ending in the brass italic ("Turn a recording into *a score.*").
struct DisplayTitle: View {
    let text: String
    var emphasis: String?
    var size: CGFloat = 40

    var body: some View {
        Group {
            if let emphasis {
                // the whole line carries the display face, so the space between the two parts is display-sized too
                Text("\(Text(text)) \(Text(emphasis).font(Font.Brasscribe.display(size, italic: true)).foregroundStyle(Color.Scribe.brandText))")
                    .font(Font.Brasscribe.display(size))
            } else {
                Text(text).font(Font.Brasscribe.display(size))
            }
        }
        .foregroundStyle(Color.Scribe.text)
        .accessibilityAddTraits(.isHeader)
        .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: the mark

/// The Brasscribe mark (design/brands/brasscribe/brand/logo/mark.svg), drawn in brass or ink. Decorative.
struct BrandMark: View {
    var size: CGFloat = 28
    var color: Color = .Scribe.brand
    private static let doc: SVGDocument? = Bundle.main.url(forResource: "mark", withExtension: "svg")
        .flatMap { try? Data(contentsOf: $0) }.flatMap { try? SVGDocument(data: $0) }

    var body: some View {
        Canvas { ctx, sz in
            guard let doc = Self.doc else { return }
            let ink = color.resolve(in: ctx.environment).cgColor
            ctx.withCGContext { cg in
                cg.scaleBy(x: sz.width / doc.size.width, y: sz.height / doc.size.height)
                doc.draw(in: cg, ink: ink, keepDocumentColors: false)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// Mark + "Brasscribe" + brass italic "Play".
struct Lockup: View {
    var product = true
    var body: some View {
        HStack(spacing: Space.s2) {
            BrandMark(size: 24)
            Text("\(Text(verbatim: "Brasscribe").font(.custom("InstrumentSerif-Regular", size: 24, relativeTo: .title2)))\(product ? Text("\(Text(verbatim: " "))\(Text(verbatim: "Play").font(.custom("InstrumentSerif-Italic", size: 24, relativeTo: .title2)).foregroundStyle(Color.Scribe.brandText))") : Text(verbatim: ""))")
                .foregroundStyle(Color.Scribe.text)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(verbatim: product ? "Brasscribe Play" : "Brasscribe"))
        .accessibilityAddTraits(.isHeader)
    }
}

// MARK: uncertainty

/// The score's "?" (uncertain) and boxed "?" (very uncertain), in the note colour.
struct UncertainMark: View {
    let level: UncertaintyLevel
    @ScaledMetric(relativeTo: .body) private var size: CGFloat = 17
    var body: some View {
        let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Scribe.uncertain
        Text(verbatim: "?")
            .font(.body.weight(.bold))   // Dynamic Type; the frame below scales with it
            .foregroundStyle(color)
            .frame(width: size * 1.1, height: size * 1.3)
            .overlay {
                if level == .veryUncertain {
                    RoundedRectangle(cornerRadius: 2).strokeBorder(color, lineWidth: 1.5)
                }
            }
            .accessibilityHidden(true)
    }
}

/// "? Uncertain   [?] Very uncertain", shown on Review and on the score.
struct UncertaintyLegend: View {
    var body: some View {
        ViewThatFits {
            HStack(spacing: Space.s5) { items }
            VStack(alignment: .leading, spacing: Space.s2) { items }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Notes Brasscribe isn't sure about have a “?” above them. A boxed “?” means very unsure."))
    }

    @ViewBuilder private var items: some View {
        HStack(spacing: Space.s2) { UncertainMark(level: .uncertain); caption(Text("Brasscribe wasn't sure")) }
        HStack(spacing: Space.s2) { UncertainMark(level: .veryUncertain); caption(Text("Very unsure")) }
    }

    /// On the Mac in the page's muted text: left to the list it is in, a caption takes the system's colour, and the
    /// Mac's list is on the page's surface. The iPad's list is the system's, with its colours.
    @ViewBuilder private func caption(_ text: Text) -> some View {
        #if os(macOS)
        text.foregroundStyle(Color.Scribe.textMuted)
        #else
        text
        #endif
    }
}

/// The selected row of the review's note list (design/brands/brasscribe/system.md: selection is `selection-tint`
/// with a 1 px `selection-edge`), under the page's text colour. The system highlight fills with the
/// tint instead (primary, near black in light), under text that keeps its own colour.
enum SelectedRow {
    static let fill = Color.Brasscribe.selectionTint
    static let edge = Color.Brasscribe.selectionEdge
    static let text = Color.Scribe.text

    /// The row background: this for the selected row, the list's own for the rest.
    static func background(_ selected: Bool) -> AnyView? {
        guard selected else { return nil }
        return AnyView(
            RoundedRectangle(cornerRadius: Radius.sm)
                .fill(fill)
                .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(edge, lineWidth: 1))
        )
    }

    /// The same in a list on a ground of the page's: a row that is not selected has no ground of its own, so it
    /// lies on the list's (the system's row ground is not one of the page's colours).
    static func backgroundOnPage(_ selected: Bool) -> AnyView { background(selected) ?? AnyView(Color.clear) }
}

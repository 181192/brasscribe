import ScoreKit
import SVGRender
import SwiftUI

// The brand shows only through the tokens (design/dist/apple), the one button shape, the
// display face and the mark. Everything here is built from those; screens use these
// pieces instead of their own colours or shapes.

typealias Space = BrasscribeDesign.Space
typealias Radius = BrasscribeDesign.Radius

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
                Text("\(Text(text)) \(Text(emphasis).font(Font.Brasscribe.display(size, italic: true)).foregroundStyle(Color.Brasscribe.brassText))")
                    .font(Font.Brasscribe.display(size))
            } else {
                Text(text).font(Font.Brasscribe.display(size))
            }
        }
        .foregroundStyle(Color.Brasscribe.text)
        .accessibilityAddTraits(.isHeader)
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// Small caps section label ("YOUR SCORES").
struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text.uppercased(with: .current))
            .font(Font.Brasscribe.caption.weight(.semibold))
            .kerning(0.6)
            .foregroundStyle(Color.Brasscribe.textMuted)
            .accessibilityAddTraits(.isHeader)
    }
}

// MARK: buttons

private var buttonHeight: CGFloat {
    #if os(iOS)
    52
    #else
    44
    #endif
}

/// The one primary button per screen: ink on light, paper on dark, 12 pt corners.
struct PrimaryButtonStyle: ButtonStyle {
    var fullWidth = false
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Font.Brasscribe.label)
            .foregroundStyle(Color.Brasscribe.onPrimary)
            .modifier(OneLineLabel(fullWidth: fullWidth))
            .padding(.horizontal, Space.s5)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: buttonHeight)
            .background(Color.Brasscribe.primary.opacity(configuration.isPressed ? 0.8 : 1), in: RoundedRectangle(cornerRadius: Radius.md))
            .opacity(enabled ? 1 : 0.4)
            .contentShape(RoundedRectangle(cornerRadius: Radius.md))
    }
}

/// Secondary (tonal) and outline buttons, in the warm neutrals.
struct SecondaryButtonStyle: ButtonStyle {
    var outline = false
    var fullWidth = false
    var minHeight: CGFloat?
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Font.Brasscribe.label)
            .foregroundStyle(outline ? Color.Brasscribe.text : Color.Brasscribe.onSecondary)
            .modifier(OneLineLabel(fullWidth: fullWidth))
            .padding(.horizontal, Space.s4)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: minHeight ?? buttonHeight)
            .background {
                RoundedRectangle(cornerRadius: Radius.md)
                    .fill(outline ? Color.clear : Color.Brasscribe.secondary)
                    .overlay { if outline { RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1) } }
                    .opacity(configuration.isPressed ? 0.7 : 1)
            }
            .opacity(enabled ? 1 : 0.4)
            .contentShape(RoundedRectangle(cornerRadius: Radius.md))
    }
}

/// "Listen to this bar" / "Stop": both labels take up the space, so switching never moves or resizes the button.
struct ListenStopLabel: View {
    var playing: Bool
    var listenText: LocalizedStringKey = "Listen to this bar"
    var body: some View {
        ZStack {
            Label(listenText, systemImage: BrasscribeIcon.listenBar.systemName).opacity(playing ? 0 : 1)
            Label("Stop", systemImage: BrasscribeIcon.stop.systemName).opacity(playing ? 1 : 0)
        }
        .accessibilityElement(children: .ignore)
    }
}

/// On the Mac a button's label keeps one line at its full width: a row too narrow for it wraps the
/// row instead ("Can-cel" and "Co…" never happen). Touch screens keep wrapping for large text.
struct OneLineLabel: ViewModifier {
    var fullWidth = false
    func body(content: Content) -> some View {
        #if os(macOS)
        content.lineLimit(1).fixedSize(horizontal: !fullWidth, vertical: false)
        #else
        content
        #endif
    }
}

/// Plain text buttons (Cancel, Skip, Finish later), at least 44 pt tall.
struct PlainButtonStyle44: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .modifier(OneLineLabel())
            .font(Font.Brasscribe.label)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, Space.s3)
            .frame(minHeight: 44)
            .contentShape(Rectangle())
            .opacity(configuration.isPressed ? 0.6 : 1)
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var primary: PrimaryButtonStyle { PrimaryButtonStyle() }
    static var primaryWide: PrimaryButtonStyle { PrimaryButtonStyle(fullWidth: true) }
}
extension ButtonStyle where Self == SecondaryButtonStyle {
    static var tonal: SecondaryButtonStyle { SecondaryButtonStyle() }
    static var outline: SecondaryButtonStyle { SecondaryButtonStyle(outline: true) }
}
extension ButtonStyle where Self == PlainButtonStyle44 {
    static var plainText: PlainButtonStyle44 { PlainButtonStyle44() }
}

/// Practice chips (Count-in, Metronome, Mute my part…): outlined when off; when on, a tonal
/// fill, an ink border and a ✓. Ink fill is kept for Play alone. 48 pt tall.
struct ChipToggleStyle: ToggleStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: Space.s2) {
                if configuration.isOn { Image(systemName: "checkmark").font(.body.weight(.bold)) }
                configuration.label
            }
            .font(Font.Brasscribe.label)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, Space.s3)
            .frame(minHeight: 48)
            .frame(maxWidth: .infinity)
            .background {
                RoundedRectangle(cornerRadius: Radius.md)
                    .fill(configuration.isOn ? Color.Brasscribe.secondary : Color.clear)
                    .overlay {
                        RoundedRectangle(cornerRadius: Radius.md)
                            .strokeBorder(configuration.isOn ? Color.Brasscribe.text : Color.Brasscribe.borderStrong,
                                          lineWidth: configuration.isOn ? 1.5 : 1)
                    }
            }
            .contentShape(RoundedRectangle(cornerRadius: Radius.md))
            .opacity(enabled ? 1 : 0.4)
        }
        .buttonStyle(.plain)
        .accessibilityRepresentation { Toggle(isOn: configuration.$isOn) { configuration.label } }
    }
}

extension ToggleStyle where Self == ChipToggleStyle {
    static var chip: ChipToggleStyle { ChipToggleStyle() }
}

/// A chip that opens a menu (Speed, Loop on the phone). Looks like an off chip.
struct ChipLabel: View {
    let title: String
    let systemImage: String
    var active = false
    /// A chip that opens a menu: no ✓ (it isn't a switch), a chevron instead. The tonal fill still
    /// says something inside is on.
    var menu = false
    var body: some View {
        HStack(spacing: Space.s2) {
            if active && !menu { Image(systemName: "checkmark").font(.body.weight(.bold)) }
            Image(systemName: systemImage)
            Text(title).monospacedDigit()
            if menu { Image(systemName: "chevron.down").font(.caption.weight(.semibold)).accessibilityHidden(true) }
        }
        .font(Font.Brasscribe.label)
        .foregroundStyle(Color.Brasscribe.text)
        .padding(.horizontal, Space.s3)
        .frame(minHeight: 48)
        .frame(maxWidth: .infinity)
        .background {
            RoundedRectangle(cornerRadius: Radius.md)
                .fill(active ? Color.Brasscribe.secondary : Color.clear)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(active ? Color.Brasscribe.text : Color.Brasscribe.borderStrong, lineWidth: active ? 1.5 : 1)
                }
        }
        .contentShape(RoundedRectangle(cornerRadius: Radius.md))
    }
}

/// A segmented choice in the warm greys: the chosen segment is raised with an edge. No
/// accent colour, so it never reads as the primary. Each segment is at least 44 pt tall.
struct Segmented<Value: Hashable>: View {
    let label: String
    @Binding var selection: Value
    let options: [(value: Value, title: String)]
    /// Fall back to one segment per row when the row doesn't fit. Off for short labels that
    /// always fit (the fallback's measuring leaves an empty node for the audit to flag).
    var wraps = true
    @Environment(\.dynamicTypeSize) private var typeSize

    /// At the largest text sizes the segments stack, one per row, so none wraps or squeezes.
    private var stacked: Bool { typeSize >= .accessibility1 }

    var body: some View {
        if stacked {
            segments(vertical: true)
        } else if !wraps {
            segments(vertical: false)
        } else {
            ViewThatFits(in: .horizontal) {
                segments(vertical: false)
                segments(vertical: true)
            }
        }
    }

    private func segments(vertical: Bool) -> some View {
        let layout = vertical ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2)) : AnyLayout(HStackLayout(spacing: 2))
        return layout {
            ForEach(Array(options.enumerated()), id: \.offset) { _, o in
                let on = o.value == selection
                Button { selection = o.value } label: {
                    Text(o.title)
                        .font(on ? Font.Brasscribe.label : Font.Brasscribe.body)
                        .foregroundStyle(on ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
                        .padding(.horizontal, Space.s3)
                        .frame(maxWidth: vertical ? .infinity : nil, minHeight: 44, alignment: .leading)
                        .background {
                            if on {
                                RoundedRectangle(cornerRadius: Radius.sm).fill(Color.Brasscribe.surfaceRaised)
                                    .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(Color.Brasscribe.borderStrong))
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? [.isSelected] : [])
            }
        }
        .padding(2)
        .background(Color.Brasscribe.secondary, in: RoundedRectangle(cornerRadius: Radius.md))
        .fixedSize(horizontal: !vertical, vertical: true)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(label))
    }
}

// MARK: surfaces

/// A 40 pt icon well in `secondary`, for list rows and cards.
struct IconWell: View {
    let systemName: String
    var tint: Color = .Brasscribe.text
    @ScaledMetric(relativeTo: .body) private var size: CGFloat = 40
    var body: some View {
        Image(systemName: systemName)
            .font(.body.weight(.medium))
            .foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(Color.Brasscribe.secondary, in: RoundedRectangle(cornerRadius: Radius.sm))
            .accessibilityHidden(true)
    }
}

struct CardModifier: ViewModifier {
    var padding: CGFloat = Space.s4
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        content
            .padding(padding)
            // the shadow sits on the card's shape only, never on the text inside it
            .background(RoundedRectangle(cornerRadius: Radius.lg).fill(Color.Brasscribe.surfaceRaised)
                .shadow(color: scheme == .dark ? .clear : .black.opacity(0.04), radius: 2, y: 1))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(Color.Brasscribe.border, lineWidth: 1))
    }
}

/// A tinted notice with an icon (info, or the computer it runs on).
struct NoticeBox: View {
    let systemImage: String
    let text: String
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Space.s3) {
            Image(systemName: systemImage).accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Font.Brasscribe.body)
        .foregroundStyle(Color.Brasscribe.text)
        .padding(Space.s4)
        .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
        .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.border))
        .accessibilityElement(children: .combine)
    }
}

/// Small helper line with an icon (streaming tip, where it runs).
struct HelperLine: View {
    let systemImage: String
    let text: String
    var body: some View {
        Label { Text(text).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: systemImage) }
            .font(Font.Brasscribe.callout)
            .foregroundStyle(Color.Brasscribe.textMuted)
            .accessibilityElement(children: .combine)
    }
}

/// Where a flow page's actions go. On the Mac they follow the content, trailing in its column
/// (design/system.md §2: "Bottom right of the content, after Cancel"), so a tall window never leaves
/// them far below it. On iPhone and iPad they sit in a band at the bottom of the screen.
enum PageActions {
    static var followContent: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }
}

/// A row of actions, trailing: secondary first, the primary last. Where the row doesn't fit, the
/// buttons stack, trailing, so no label wraps or truncates.
struct ActionRow<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: Space.s3) { Spacer(minLength: 0); content }
            VStack(alignment: .trailing, spacing: Space.s2) { content }
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
    }
}

/// A column beside the content, with a hairline between (the Mac's parts list).
struct SidePanel<Panel: View>: ViewModifier {
    let shown: Bool
    let width: CGFloat
    let panel: Panel

    func body(content: Content) -> some View {
        HStack(spacing: 0) {
            content.frame(maxWidth: .infinity)
            if shown {
                Divider().overlay(Color.Brasscribe.border)
                panel.frame(width: width).frame(maxHeight: .infinity)
            }
        }
    }
}

extension View {
    func sidePanel<P: View>(shown: Bool, width: CGFloat, @ViewBuilder _ panel: () -> P) -> some View {
        modifier(SidePanel(shown: shown, width: width, panel: panel()))
    }

    /// iPhone and iPad: the page's actions in a band at the bottom of the screen. On the Mac the page
    /// puts them after its content instead (`PageActions.followContent`).
    @ViewBuilder func bottomActions<A: View>(@ViewBuilder _ actions: () -> A) -> some View {
        if PageActions.followContent { self } else { safeAreaInset(edge: .bottom) { actions() } }
    }

    /// For a control docked under a page with `safeAreaInset(edge: .bottom)`: on the Mac, VoiceOver reaches what is
    /// docked in an inset before the content above it (the accessibility navigation order), so it is sent after it.
    func afterTheContentItIsDockedUnder() -> some View {
        #if os(macOS)
        accessibilitySortPriority(-1)
        #else
        self
        #endif
    }

    func card(padding: CGFloat = Space.s4) -> some View { modifier(CardModifier(padding: padding)) }

    /// The page background and the reading column (at most 720 pt, centred).
    func readingColumn() -> some View {
        frame(maxWidth: BrasscribeDesign.Size.contentMaxWidth, alignment: .leading)
            .frame(maxWidth: .infinity)
    }

    func pageBackground() -> some View { background(Color.Brasscribe.bg.ignoresSafeArea()) }
}

// MARK: the mark

/// The Brasscribe mark (design/brand/logo/mark.svg), drawn in brass or ink. Decorative.
struct BrandMark: View {
    var size: CGFloat = 28
    var color: Color = .Brasscribe.brass
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
            Text("\(Text(verbatim: "Brasscribe").font(.custom("InstrumentSerif-Regular", size: 24, relativeTo: .title2)))\(product ? Text(verbatim: " ") + Text(verbatim: "Play").font(.custom("InstrumentSerif-Italic", size: 24, relativeTo: .title2)).foregroundStyle(Color.Brasscribe.brassText) : Text(verbatim: ""))")
                .foregroundStyle(Color.Brasscribe.text)
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
        let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Brasscribe.uncertain
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
        HStack(spacing: Space.s2) { UncertainMark(level: .uncertain); Text("Brasscribe wasn't sure") }
        HStack(spacing: Space.s2) { UncertainMark(level: .veryUncertain); Text("Very unsure") }
    }
}

extension View {
    /// Menu pickers: ink text on iOS (they take the tint); the Mac pop-up button keeps its own
    /// label colour, which a custom tint only dims.
    @ViewBuilder func menuTint() -> some View {
        #if os(iOS)
        tint(Color.Brasscribe.text)
        #else
        foregroundStyle(Color.Brasscribe.text)
        #endif
    }
}

/// Percent in the user's locale: "75%" in English, "75 %" in Norwegian.
func percentText(_ value: Double) -> String { (value / 100).formatted(.percent.precision(.fractionLength(0))) }

/// The selected row of the review's note list (design/system.md: selection is `selection-tint`
/// with a 1 px `selection-edge`), under the page's text colour. The system highlight fills with the
/// tint instead (primary, near black in light), under text that keeps its own colour.
enum SelectedRow {
    static let fill = Color.Brasscribe.selectionTint
    static let edge = Color.Brasscribe.selectionEdge
    static let text = Color.Brasscribe.text

    /// The row background: this for the selected row, the list's own for the rest.
    static func background(_ selected: Bool) -> AnyView? {
        guard selected else { return nil }
        return AnyView(
            RoundedRectangle(cornerRadius: Radius.sm)
                .fill(fill)
                .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(edge, lineWidth: 1))
        )
    }
}

import SwiftUI

// The pieces every Play app's screens are built from: the neutral roles every brand's tokens have (`ScribeDesign`,
// `Color.Scribe`, `Font.Scribe`) and the one button shape. A product's own face, mark and colours are in the product.

typealias Space = ScribeDesign.Space
typealias Radius = ScribeDesign.Radius

/// Small caps section label ("YOUR SCORES").
struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text.uppercased(with: .current))
            .font(Font.Scribe.caption.weight(.semibold))
            .kerning(0.6)
            .foregroundStyle(Color.Scribe.textMuted)
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
            .font(Font.Scribe.label)
            .foregroundStyle(Color.Scribe.onPrimary)
            .modifier(OneLineLabel(fullWidth: fullWidth))
            .padding(.horizontal, Space.s5)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: buttonHeight)
            .background(Color.Scribe.primary.opacity(configuration.isPressed ? 0.8 : 1), in: RoundedRectangle(cornerRadius: Radius.md))
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
            .font(Font.Scribe.label)
            .foregroundStyle(outline ? Color.Scribe.text : Color.Scribe.onSecondary)
            .modifier(OneLineLabel(fullWidth: fullWidth))
            .padding(.horizontal, Space.s4)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: minHeight ?? buttonHeight)
            .background {
                RoundedRectangle(cornerRadius: Radius.md)
                    .fill(outline ? Color.clear : Color.Scribe.secondary)
                    .overlay { if outline { RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Scribe.borderStrong, lineWidth: 1) } }
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
            Label(listenText, systemImage: PlayIcon.listenBar.systemName).opacity(playing ? 0 : 1)
            Label("Stop", systemImage: PlayIcon.stop.systemName).opacity(playing ? 1 : 0)
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
            .font(Font.Scribe.label)
            .foregroundStyle(Color.Scribe.text)
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
            .font(Font.Scribe.label)
            .foregroundStyle(Color.Scribe.text)
            .padding(.horizontal, Space.s3)
            .frame(minHeight: 48)
            .frame(maxWidth: .infinity)
            .background {
                RoundedRectangle(cornerRadius: Radius.md)
                    .fill(configuration.isOn ? Color.Scribe.secondary : Color.clear)
                    .overlay {
                        RoundedRectangle(cornerRadius: Radius.md)
                            .strokeBorder(configuration.isOn ? Color.Scribe.text : Color.Scribe.borderStrong,
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
        .font(Font.Scribe.label)
        .foregroundStyle(Color.Scribe.text)
        .padding(.horizontal, Space.s3)
        .frame(minHeight: 48)
        .frame(maxWidth: .infinity)
        .background {
            RoundedRectangle(cornerRadius: Radius.md)
                .fill(active ? Color.Scribe.secondary : Color.clear)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(active ? Color.Scribe.text : Color.Scribe.borderStrong, lineWidth: active ? 1.5 : 1)
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
                        .font(on ? Font.Scribe.label : Font.Scribe.body)
                        .foregroundStyle(on ? Color.Scribe.text : Color.Scribe.textMuted)
                        .padding(.horizontal, Space.s3)
                        .frame(maxWidth: vertical ? .infinity : nil, minHeight: 44, alignment: .leading)
                        .background {
                            if on {
                                RoundedRectangle(cornerRadius: Radius.sm).fill(Color.Scribe.surfaceRaised)
                                    .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(Color.Scribe.borderStrong))
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? [.isSelected] : [])
            }
        }
        .padding(2)
        .background(Color.Scribe.secondary, in: RoundedRectangle(cornerRadius: Radius.md))
        .fixedSize(horizontal: !vertical, vertical: true)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(label))
    }
}

// MARK: surfaces

/// A 40 pt icon well in `secondary`, for list rows and cards.
struct IconWell: View {
    let systemName: String
    var tint: Color = .Scribe.text
    @ScaledMetric(relativeTo: .body) private var size: CGFloat = 40
    var body: some View {
        Image(systemName: systemName)
            .font(.body.weight(.medium))
            .foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(Color.Scribe.secondary, in: RoundedRectangle(cornerRadius: Radius.sm))
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
            .background(RoundedRectangle(cornerRadius: Radius.lg).fill(Color.Scribe.surfaceRaised)
                .shadow(color: scheme == .dark ? .clear : .black.opacity(0.04), radius: 2, y: 1))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(Color.Scribe.border, lineWidth: 1))
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
        .font(Font.Scribe.body)
        .foregroundStyle(Color.Scribe.text)
        .padding(Space.s4)
        .background(Color.Scribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
        .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Scribe.border))
        .accessibilityElement(children: .combine)
    }
}

/// Small helper line with an icon (streaming tip, where it runs).
struct HelperLine: View {
    let systemImage: String
    let text: String
    var body: some View {
        Label { Text(text).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: systemImage) }
            .font(Font.Scribe.callout)
            .foregroundStyle(Color.Scribe.textMuted)
            .accessibilityElement(children: .combine)
    }
}

/// Where a flow page's actions go. On the Mac they follow the content, trailing in its column
/// (design/brands/brasscribe/system.md §2: "Bottom right of the content, after Cancel"), so a tall window never leaves
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
                Divider().overlay(Color.Scribe.border)
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

    /// A larger system control on the Mac, where a slider is 16 pt high at the regular size; iPhone and iPad draw
    /// theirs large enough to touch.
    func macControlSize(_ size: ControlSize) -> some View {
        #if os(macOS)
        controlSize(size)
        #else
        self
        #endif
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
        frame(maxWidth: ScribeDesign.Size.contentMaxWidth, alignment: .leading)
            .frame(maxWidth: .infinity)
    }

    func pageBackground() -> some View { background(Color.Scribe.bg.ignoresSafeArea()) }
}

extension View {
    /// Menu pickers: ink text on iOS (they take the tint); the Mac pop-up button keeps its own
    /// label colour, which a custom tint only dims.
    @ViewBuilder func menuTint() -> some View {
        #if os(iOS)
        tint(Color.Scribe.text)
        #else
        foregroundStyle(Color.Scribe.text)
        #endif
    }
}

/// Percent in the user's locale: "75%" in English, "75 %" in Norwegian.
func percentText(_ value: Double) -> String { (value / 100).formatted(.percent.precision(.fractionLength(0))) }

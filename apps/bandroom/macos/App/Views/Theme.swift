import AppKit
import SwiftUI

// Bandroom's small layer over the design tokens (design/system.md, design/server-app.md §7 sizes).

/// Text size for the whole app. macOS has no system text size for third-party windows, so Bandroom has
/// its own setting (server-app.md §9, 1.4.4).
enum TextSize: String, CaseIterable, Identifiable {
    case standard, large, larger
    var id: String { rawValue }
    var scale: CGFloat {
        switch self {
        case .standard: 1
        case .large: 1.18
        case .larger: 1.36
        }
    }
}

private struct TextScaleKey: EnvironmentKey { static let defaultValue: CGFloat = 1 }

extension EnvironmentValues {
    var textScale: CGFloat {
        get { self[TextScaleKey.self] }
        set { self[TextScaleKey.self] = newValue }
    }
}

enum BRStyle {
    /// Popover heading: "Brasscribe on Kalli's MacBook".
    case heading
    case body
    case bodyStrong
    case callout
    case caption
    /// "NOW", "THIS COMPUTER".
    case sectionLabel
    case mono
    /// The six-digit pairing code.
    case code
    /// The four-digit match number.
    case matchCode
    /// Serif window titles (desktop sheets and the pair window).
    case display

    func font(_ s: CGFloat) -> Font {
        switch self {
        case .heading: .system(size: 16 * s, weight: .semibold)
        case .body: .system(size: 15 * s)
        case .bodyStrong: .system(size: 15 * s, weight: .semibold)
        case .callout: .system(size: 14 * s)
        case .caption: .system(size: 13 * s)
        case .sectionLabel: .system(size: 12 * s, weight: .semibold)
        case .mono: .system(size: 13 * s, design: .monospaced)
        case .code: .system(size: 40 * s, weight: .bold, design: .rounded).monospacedDigit()
        case .matchCode: .system(size: 34 * s, weight: .bold, design: .rounded).monospacedDigit()
        case .display: .custom("InstrumentSerif-Regular", size: 38 * s, relativeTo: .largeTitle)
        }
    }
}

private struct BRFontModifier: ViewModifier {
    @Environment(\.textScale) private var scale
    let style: BRStyle
    func body(content: Content) -> some View {
        content.font(style.font(scale)).tracking(style == .sectionLabel ? 0.6 : (style == .code || style == .matchCode ? 2 : 0))
    }
}

extension View {
    func brFont(_ style: BRStyle) -> some View { modifier(BRFontModifier(style: style)) }

    /// A card: raised surface, hairline edge, 12 pt corners (system.md §5 Cards).
    func card(padding: CGFloat = 12) -> some View {
        self.padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md))
            .overlay(RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md).strokeBorder(Color.Brasscribe.border))
    }
}

/// 2 px focus ring in `focus` with a 2 px gap (system.md §5 Focus). Custom button styles lose the system
/// ring on macOS, so the styles draw this one.
private struct FocusRing: ViewModifier {
    @Environment(\.isFocused) private var focused
    let radius: CGFloat
    func body(content: Content) -> some View {
        content.overlay(
            RoundedRectangle(cornerRadius: radius + 2)
                .strokeBorder(Color.Brasscribe.focus, lineWidth: 2)
                .padding(-4)
                .opacity(focused ? 1 : 0)
        )
    }
}

enum BRButtonKind { case primary, secondary, outline, plain }

/// The one button shape: 36 pt tall in the popover (the pointer idiom), 12 pt corners.
struct BRButtonStyle: ButtonStyle {
    var kind: BRButtonKind
    var fullWidth = false
    var height: CGFloat = 36
    @Environment(\.textScale) private var scale
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        let radius = BrasscribeDesign.Radius.md
        return configuration.label
            .font(.system(size: 15 * scale, weight: kind == .plain ? .medium : .semibold))
            .lineLimit(2)
            .multilineTextAlignment(.center)
            .padding(.horizontal, kind == .plain ? 6 : 14)
            .frame(minHeight: height * max(1, scale * 0.95))
            .frame(maxWidth: fullWidth ? .infinity : nil)
            .foregroundStyle(foreground)
            .background {
                switch kind {
                case .primary: RoundedRectangle(cornerRadius: radius).fill(Color.Brasscribe.primary)
                case .secondary: RoundedRectangle(cornerRadius: radius).fill(Color.Brasscribe.secondary)
                case .outline:
                    RoundedRectangle(cornerRadius: radius).fill(Color.Brasscribe.surfaceRaised)
                        .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
                case .plain: Color.clear
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: radius))
            .opacity(configuration.isPressed ? 0.8 : (enabled ? 1 : 0.45))
            .modifier(FocusRing(radius: radius))
    }

    private var foreground: Color {
        switch kind {
        case .primary: Color.Brasscribe.onPrimary
        case .secondary: Color.Brasscribe.onSecondary
        case .outline, .plain: Color.Brasscribe.text
        }
    }
}

extension ButtonStyle where Self == BRButtonStyle {
    static var brPrimary: BRButtonStyle { BRButtonStyle(kind: .primary, fullWidth: true) }
    static var brSecondary: BRButtonStyle { BRButtonStyle(kind: .secondary) }
    static var brOutline: BRButtonStyle { BRButtonStyle(kind: .outline) }
    static var brPlain: BRButtonStyle { BRButtonStyle(kind: .plain) }
}

/// The Brasscribe mark (design/brand/logo/mark.svg), drawn from its 64-unit path.
struct MarkShape: Shape {
    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 64
        let ox = rect.midX - 32 * s, oy = rect.midY - 32 * s
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: ox + x * s, y: oy + y * s) }
        var path = Path()
        let k: CGFloat = 4.5 * 0.5523
        path.move(to: p(9.5, 10))
        path.addCurve(to: p(14, 5.5), control1: p(9.5, 10 - k), control2: p(14 - k, 5.5))
        path.addCurve(to: p(18.5, 10), control1: p(14 + k, 5.5), control2: p(18.5, 10 - k))
        path.addLine(to: p(18.5, 31))
        path.addCurve(to: p(50.5, 15), control1: p(29.5, 31), control2: p(41.5, 26))
        path.addCurve(to: p(54.5, 16), control1: p(52, 13.5), control2: p(54.5, 14))
        path.addLine(to: p(54.5, 26))
        path.addCurve(to: p(18.5, 59), control1: p(54.5, 45), control2: p(39.5, 58))
        path.addLine(to: p(9.5, 59))
        path.closeSubpath()
        path.move(to: p(18.5, 41))
        path.addLine(to: p(18.5, 51))
        path.addCurve(to: p(44.5, 31), control1: p(31.5, 49.5), control2: p(40.5, 42))
        path.addCurve(to: p(18.5, 41), control1: p(37.5, 37), control2: p(28.5, 40.5))
        path.closeSubpath()
        return path
    }
}

struct Mark: View {
    var size: CGFloat = 20
    var color: Color = Color.Brasscribe.text
    var body: some View {
        MarkShape().fill(color, style: FillStyle(eoFill: true))
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

/// Section labels: "NOW", "THIS COMPUTER". Headings for VoiceOver.
struct SectionLabel: View {
    let text: LocalizedStringKey
    var body: some View {
        Text(text)
            .textCase(.uppercase)
            .brFont(.sectionLabel)
            .foregroundStyle(Color.Brasscribe.textMuted)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The brass progress bar: the one working brand moment (system.md §5).
struct BrassProgress: View {
    let fraction: Double
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.Brasscribe.secondary)
                Capsule().fill(Color.Brasscribe.brass).frame(width: max(6, geo.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: 6)
        .accessibilityHidden(true)
    }
}

/// Neutral 3-segment meter; never brass or a status colour (§7.5).
struct Meter: View {
    let level: Int
    var body: some View {
        HStack(spacing: 3) {
            ForEach(1...3, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2)
                    .fill(i <= level ? Color.Brasscribe.textMuted : Color.clear)
                    .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(Color.Brasscribe.textMuted, lineWidth: 1))
                    .frame(width: 14, height: 7)
            }
        }
        .accessibilityHidden(true)
    }
}

/// A disclosure with a visible triangle and a full-width hit area, collapsed by default.
struct Disclosure<Content: View>: View {
    let title: LocalizedStringKey
    @Binding var isExpanded: Bool
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                isExpanded.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "arrowtriangle.right.fill")
                        .font(.system(size: 9))
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                    Text(title).brFont(.bodyStrong)
                    Spacer(minLength: 0)
                }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.Brasscribe.text)
            .accessibilityValue(isExpanded ? Text("Expanded") : Text("Collapsed"))
            if isExpanded { content.padding(.bottom, 8) }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md))
        .overlay(RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md).strokeBorder(Color.Brasscribe.border))
    }
}

extension NSImage {
    /// The menu-bar image: the mark plus a shape badge per state (§6.1). A template image, so it follows
    /// the menu bar's colour; the state never depends on colour.
    static func menuBarIcon(badge: MenuBadge) -> NSImage {
        let size = NSSize(width: 20, height: 18)
        let image = NSImage(size: size, flipped: true) { rect in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            let markRect = CGRect(x: 0, y: 0, width: 18, height: 18)
            ctx.addPath(MarkShape().path(in: markRect).cgPath)
            ctx.setFillColor(NSColor.black.cgColor)
            ctx.fillPath(using: .evenOdd)
            guard badge != .none else { return true }
            let badgeRect = CGRect(x: 10.5, y: 8.5, width: 9.5, height: 9.5)
            // Cut a gap around the badge so it reads as a separate shape.
            ctx.setBlendMode(.clear)
            ctx.fillEllipse(in: badgeRect.insetBy(dx: -1.2, dy: -1.2))
            ctx.setBlendMode(.normal)
            badge.draw(in: badgeRect, ctx: ctx)
            return true
        }
        image.isTemplate = true
        return image
    }
}

enum MenuBadge: Equatable {
    case none, dots, pie(step: Int), triangle, square, circularArrow, crossCircle, downArrow

    func draw(in r: CGRect, ctx: CGContext) {
        ctx.setFillColor(NSColor.black.cgColor)
        ctx.setStrokeColor(NSColor.black.cgColor)
        switch self {
        case .none: break
        case .dots:
            let d: CGFloat = 2.4
            for i in 0..<3 {
                ctx.fillEllipse(in: CGRect(x: r.minX + CGFloat(i) * 3.4, y: r.maxY - d - 0.5, width: d, height: d))
            }
        case .pie(let step):
            ctx.setLineWidth(1.2)
            ctx.strokeEllipse(in: r.insetBy(dx: 0.6, dy: 0.6))
            if step > 0 {
                let c = CGPoint(x: r.midX, y: r.midY)
                ctx.move(to: c)
                let start = -CGFloat.pi / 2
                ctx.addArc(center: c, radius: r.width / 2, startAngle: start, endAngle: start + 2 * .pi * CGFloat(step) / 8, clockwise: false)
                ctx.closePath()
                ctx.fillPath()
            }
        case .triangle:
            ctx.move(to: CGPoint(x: r.midX, y: r.minY))
            ctx.addLine(to: CGPoint(x: r.maxX, y: r.maxY))
            ctx.addLine(to: CGPoint(x: r.minX, y: r.maxY))
            ctx.closePath()
            ctx.fillPath()
            ctx.setBlendMode(.clear)
            ctx.fill(CGRect(x: r.midX - 0.6, y: r.minY + 3.2, width: 1.2, height: 3.2))
            ctx.fill(CGRect(x: r.midX - 0.6, y: r.maxY - 1.9, width: 1.2, height: 1.1))
            ctx.setBlendMode(.normal)
        case .square:
            ctx.fill(r.insetBy(dx: 1, dy: 1))
        case .circularArrow:
            ctx.setLineWidth(1.5)
            let c = CGPoint(x: r.midX, y: r.midY)
            ctx.addArc(center: c, radius: r.width / 2 - 1, startAngle: -.pi / 3, endAngle: 1.5 * .pi, clockwise: false)
            ctx.strokePath()
            let tip = CGPoint(x: c.x + (r.width / 2 - 1) * cos(-.pi / 3), y: c.y + (r.width / 2 - 1) * sin(-.pi / 3))
            ctx.move(to: CGPoint(x: tip.x + 2.4, y: tip.y - 0.6))
            ctx.addLine(to: CGPoint(x: tip.x - 0.4, y: tip.y - 2.6))
            ctx.addLine(to: CGPoint(x: tip.x - 0.6, y: tip.y + 1.6))
            ctx.closePath()
            ctx.fillPath()
        case .crossCircle:
            ctx.fillEllipse(in: r)
            ctx.setBlendMode(.clear)
            ctx.setLineWidth(1.4)
            let i = r.insetBy(dx: 2.8, dy: 2.8)
            ctx.move(to: CGPoint(x: i.minX, y: i.minY)); ctx.addLine(to: CGPoint(x: i.maxX, y: i.maxY))
            ctx.move(to: CGPoint(x: i.maxX, y: i.minY)); ctx.addLine(to: CGPoint(x: i.minX, y: i.maxY))
            ctx.strokePath()
            ctx.setBlendMode(.normal)
        case .downArrow:
            ctx.setLineWidth(1.5)
            ctx.move(to: CGPoint(x: r.midX, y: r.minY)); ctx.addLine(to: CGPoint(x: r.midX, y: r.maxY - 1))
            ctx.strokePath()
            ctx.move(to: CGPoint(x: r.minX + 1, y: r.midY + 0.5))
            ctx.addLine(to: CGPoint(x: r.midX, y: r.maxY))
            ctx.addLine(to: CGPoint(x: r.maxX - 1, y: r.midY + 0.5))
            ctx.strokePath()
        }
    }
}

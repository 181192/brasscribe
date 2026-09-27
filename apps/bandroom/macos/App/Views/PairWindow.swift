import BandroomKit
import CoreImage.CIFilterBuiltins
import SwiftUI

/// Pair a phone (design/server-app.md §3.4, mockups/png/server-pair-*). The code works while this window is
/// open, and only once.
struct PairWindow: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismissWindow) private var dismissWindow
    @State private var helpOpen = false
    @AccessibilityFocusState private var pairedFocused: Bool

    private var pairing: PairingModel { app.pairing }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Pair a phone")
                .brFont(.display)
                .foregroundStyle(Color.Brasscribe.text)
                .accessibilityAddTraits(.isHeader)
            Text("Do this once for each phone or tablet. It stays paired.")
                .brFont(.body).foregroundStyle(Color.Brasscribe.textMuted)
                .padding(.bottom, 20)

            HStack(alignment: .top, spacing: 28) {
                VStack(alignment: .leading, spacing: 18) {
                    ways
                    statusBox
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                qr
            }

            Disclosure(title: "Phone doesn't show this computer?", isExpanded: $helpOpen) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Check that both are on the same Wi-Fi.").brFont(.callout)
                    if let a = pairing.address {
                        Text("Or type this address in Brasscribe on the phone: \(a.ip), port \(a.port)")
                            .brFont(.callout)
                            .textSelection(.enabled)
                            .accessibilityLabel(Text("Or type this address in Brasscribe on the phone: \(Strings.addressForVoiceOver(a.ip)), port \(a.port)"))
                    }
                }
            }
            .padding(.top, 18)

            Divider().padding(.vertical, 16)
            HStack {
                Button { Task { await pairing.pairAnother() } } label: { Text("Pair another phone") }
                    .buttonStyle(.brOutline)
                    .disabled(pairing.phase != .open)
                Spacer()
                Button { dismissWindow(id: "pair") } label: { Text("Done") }
                    .buttonStyle(BRButtonStyle(kind: .primary))
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, 32)
        .padding(.vertical, 28)
        .frame(minWidth: 720, idealWidth: 860, maxWidth: 1000)
        .background(Color.Brasscribe.bg)
        .foregroundStyle(Color.Brasscribe.text)
        .sheet(item: Binding(get: { app.monitor.requests.first }, set: { _ in })) { r in
            AllowCard(request: r).frame(width: 320).padding(8)
        }
        .onAppear {
            app.isPairWindowOpen = true
            Task { await pairing.open() }
        }
        .onDisappear {
            app.isPairWindowOpen = false
            Task { await pairing.close() }
        }
        .onChange(of: pairing.pairedDevice) { _, name in
            guard let name else { return }
            AccessibilityNotification.Announcement(String(localized: "\(name) is paired.")).post()
            pairedFocused = true
        }
        .onChange(of: pairing.isLockedOut) { _, locked in
            if locked { AccessibilityNotification.Announcement(String(localized: "Too many wrong codes. Wait a moment, or allow the phone here.")).post() }
        }
    }

    private var ways: some View {
        VStack(alignment: .leading, spacing: 16) {
            WayRow(n: 1) {
                Text("On the phone, open Brasscribe › Settings › Your computer and choose **Brasscribe on \(pairing.host ?? app.hostName)**. Then allow it here.")
            }
            WayRow(n: 2) { Text("Or scan the QR code with the phone's camera.") }
            WayRow(n: 3) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Or type this code on the phone:")
                    if let code = pairing.code, let shown = pairing.displayCode {
                        Text(shown)
                            .brFont(.code)
                            .textSelection(.enabled)
                            .accessibilityLabel(Text(Strings.codeForVoiceOver(code)))
                    } else {
                        Text("––– –––").brFont(.code).foregroundStyle(Color.Brasscribe.textMuted).accessibilityHidden(true)
                    }
                }
            }
        }
        .brFont(.body)
    }

    @ViewBuilder private var statusBox: some View {
        if let name = pairing.pairedDevice {
            HStack(spacing: 10) {
                Image(systemName: "checkmark.circle").foregroundStyle(Color.Brasscribe.success).accessibilityHidden(true)
                Text("\(name) is paired.").brFont(.body)
            }
            .card(padding: 14)
            .accessibilityElement(children: .combine)
            .accessibilityFocused($pairedFocused)
        } else if pairing.isLockedOut {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "info.circle").accessibilityHidden(true)
                Text("Too many wrong codes. Wait a moment, or allow the phone here.").brFont(.body)
            }
            .card(padding: 14)
        } else if pairing.phase == .unavailable {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Color.Brasscribe.warning).accessibilityHidden(true)
                Text("Brasscribe isn't running. Start it from the menu bar, then pair.").brFont(.body)
            }
            .card(padding: 14)
        } else {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Mark(size: 16)
                    Text("Waiting for a phone…").brFont(.bodyStrong)
                }
                Text("This code works while this window is open, and only once.")
                    .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md))
            .overlay(RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md).strokeBorder(Color.Brasscribe.border))
            .accessibilityElement(children: .combine)
        }
    }

    private var qr: some View {
        VStack(alignment: .leading, spacing: 8) {
            QRPlate(payload: pairing.uri)
                .frame(width: 260, height: 260)
                .accessibilityElement()
                .accessibilityLabel(Text("QR code for pairing with Brasscribe on \(pairing.host ?? app.hostName). It holds the same code: \(pairing.displayCode ?? "")."))
                .accessibilityAddTraits(.isImage)
            Text("Scan with the camera, or in Brasscribe on the phone.")
                .brFont(.caption).foregroundStyle(Color.Brasscribe.textMuted)
                .frame(width: 260, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct WayRow<Content: View>: View {
    let n: Int
    @ViewBuilder var content: Content
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 14) {
            Text("\(n)")
                .font(.system(size: 14, weight: .semibold))
                .frame(width: 26, height: 26)
                .overlay(Circle().strokeBorder(Color.Brasscribe.text, lineWidth: 1.5))
                .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
                .accessibilityHidden(true)
            content.fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// The QR code is always black on a white plate, with a 4-module quiet zone and a 1 px border, in every
/// theme (§9 High contrast).
struct QRPlate: View {
    let payload: String?
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md).fill(Color.white)
            RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.md).strokeBorder(Color.black.opacity(0.35), lineWidth: 1)
            if let payload, let image = QRCode.image(payload) {
                GeometryReader { geo in
                    let modules = CGFloat(image.width)
                    // Whole pixels per module, leaving at least 4 modules of white round the code.
                    let unit = floor(min(geo.size.width, geo.size.height) / (modules + 8))
                    Image(decorative: image, scale: 1)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: unit * modules, height: unit * modules)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            } else {
                ProgressView().controlSize(.small).tint(.black)
            }
        }
        .environment(\.colorScheme, .light)
    }
}

enum QRCode {
    /// One pixel per module, no quiet zone (the plate adds it).
    static func image(_ text: String) -> CGImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let out = filter.outputImage else { return nil }
        // CoreImage adds a 1-module margin; crop it off.
        let cropped = out.cropped(to: out.extent.insetBy(dx: 1, dy: 1))
        return CIContext().createCGImage(cropped, from: cropped.extent)
    }
}

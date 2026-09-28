import BandroomKit
import SwiftUI

/// Phones and tablets, inside the panel with a Back button (design/server-app.md §8).
struct PhonesView: View {
    @Environment(AppModel.self) private var app
    @State private var removing: DeviceInfo?
    @State private var techOpen = false
    @FocusState private var focus: FocusTarget?
    @AccessibilityFocusState private var voFocus: FocusTarget?

    enum FocusTarget: Hashable { case back, heading, row(String) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                app.panelPage = .status
            } label: {
                Label("Back", systemImage: "chevron.left")
            }
            .buttonStyle(.brPlain)
            .focused($focus, equals: .back)
            .keyboardShortcut(.cancelAction)

            Text("Phones and tablets")
                .brFont(.heading)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($voFocus, equals: .heading)

            let devices = app.monitor.devices
            if devices.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("No phones yet. Pair a phone to make full-band scores from it.").brFont(.body)
                    Button { app.openWindow("pair") } label: { Label("Pair a phone", systemImage: "iphone") }
                        .buttonStyle(.brPrimary)
                }
            } else {
                VStack(spacing: 0) {
                    ForEach(devices) { d in
                        row(d)
                        if d.id != devices.last?.id { Divider() }
                    }
                }
                .card(padding: 4)
                Disclosure(title: "Details for the band's tech person", isExpanded: $techOpen) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(devices) { d in
                            Text("\(d.name): \(d.deviceId) · \(d.platform) · paired \(d.pairedAt)")
                                .brFont(.mono).textSelection(.enabled)
                        }
                    }
                }
            }
        }
        .padding(14)
        .foregroundStyle(Color.Brasscribe.text)
        .onAppear { focus = .back }
        .overlay { if let removing { confirmRemove(removing) } }
    }

    private func row(_ d: DeviceInfo) -> some View {
        HStack(spacing: 10) {
            Image(systemName: d.isTablet ? "ipad" : "iphone")
                .font(.system(size: 18))
                .frame(width: 36, height: 36)
                .background(Color.Brasscribe.secondary, in: RoundedRectangle(cornerRadius: 8))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(d.name).brFont(.bodyStrong)
                Text(Strings.lastUsed(d)).brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted)
            }
            .accessibilityElement(children: .combine)
            Spacer()
            Button { removing = d } label: { Text("Remove") }
                .buttonStyle(BRButtonStyle(kind: .plain, height: 44))
                .accessibilityLabel(Text("Remove \(d.name)"))
                .focused($focus, equals: .row(d.id))
        }
        .padding(.horizontal, 8)
        .frame(minHeight: 60)
    }

    private func confirmRemove(_ d: DeviceInfo) -> some View {
        ZStack {
            Color.Brasscribe.scrim.ignoresSafeArea().onTapGesture { removing = nil }
            VStack(spacing: 12) {
                Text("Remove \(d.name)?").brFont(.bodyStrong).multilineTextAlignment(.center)
                Text("It can't send recordings here until it is paired again. Scores already on it stay.")
                    .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted).multilineTextAlignment(.center)
                HStack {
                    Button { removing = nil } label: { Text("Cancel") }.buttonStyle(.brOutline).keyboardShortcut(.cancelAction)
                    Button { remove(d) } label: { Text("Remove") }
                        .buttonStyle(BRButtonStyle(kind: .primary))
                }
            }
            .padding(16)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: BrasscribeDesign.Radius.lg).strokeBorder(Color.Brasscribe.border))
            .padding(20)
            .accessibilityAddTraits(.isModal)
        }
    }

    /// Focus goes to the next row, or to the heading when the list is empty (§8).
    private func remove(_ d: DeviceInfo) {
        let list = app.monitor.devices
        let next = list.firstIndex(of: d).flatMap { i in list.indices.contains(i + 1) ? list[i + 1] : (i > 0 ? list[i - 1] : nil) }
        removing = nil
        Task {
            try? await app.monitor.removeDevice(d.deviceId)
            if let next {
                focus = .row(next.id)
            } else {
                voFocus = .heading
            }
        }
    }
}

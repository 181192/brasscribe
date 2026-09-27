import AppKit
import BandroomKit
import SwiftUI

/// First run: one window, four steps, one decision per step (design/server-app.md §3.2).
struct SetupView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismissWindow) private var dismissWindow
    @State private var step = 0
    @State private var pasteOpen = false
    @State private var key = ""
    @State private var keySaved = HuggingFaceKey.read() != nil
    @State private var startAtLogin = true

    private let steps: [LocalizedStringKey] = ["Check this computer", "Accept one licence", "Download", "Ready"]

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            VStack(alignment: .leading, spacing: 10) {
                Mark(size: 32, color: Color.Brasscribe.brass).padding(.bottom, 10)
                ForEach(steps.indices, id: \.self) { i in
                    HStack(spacing: 8) {
                        Image(systemName: i < step ? "checkmark.circle.fill" : (i == step ? "circle.inset.filled" : "circle"))
                            .accessibilityHidden(true)
                        Text(steps[i]).brFont(i == step ? .bodyStrong : .body)
                    }
                    .foregroundStyle(i <= step ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(i == step ? .isSelected : [])
                }
                Spacer()
            }
            .padding(24)
            .frame(width: 230, alignment: .leading)
            .frame(maxHeight: .infinity)
            .background(Color.Brasscribe.brassTint)

            VStack(alignment: .leading, spacing: 16) {
                switch step {
                case 0: checkComputer
                case 1: licence
                case 2: download
                default: ready
                }
            }
            .padding(32)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(minWidth: 760, minHeight: 500)
        .background(Color.Brasscribe.bg)
        .foregroundStyle(Color.Brasscribe.text)
    }

    // MARK: 1

    private var checkComputer: some View {
        let free = app.host?.diskFreeGB ?? 0
        let enough = free >= 15 || app.host == nil
        return VStack(alignment: .leading, spacing: 16) {
            Text("Make scores on this computer").brFont(.display)
            Text("Brasscribe does the heavy work here, so your phones and tablets can make scores for the whole band. Recordings stay on your own devices.")
                .brFont(.body).fixedSize(horizontal: false, vertical: true)
            checkRow("cpu", "\(HostSampler.chipName()) · \(String(localized: "Fast: uses the graphics chip"))")
            checkRow(enough ? "internaldrive" : "exclamationmark.triangle.fill",
                     enough ? String(localized: "Needs about 15 GB · \(free) GB free")
                            : String(localized: "Not enough space: needs about 15 GB, \(free) GB free"))
            checkRow("wifi", String(localized: "Internet: needed once, for the downloads"))
            Spacer()
            HStack {
                Spacer()
                Button { step = 1 } label: { Text("Continue") }
                    .buttonStyle(BRButtonStyle(kind: .primary, height: 40)).keyboardShortcut(.defaultAction)
            }
        }
    }

    private func checkRow(_ symbol: String, _ text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).frame(width: 22).accessibilityHidden(true)
            Text(text).brFont(.body)
        }
        .card(padding: 12)
    }

    // MARK: 2

    private var licence: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Accept one licence").brFont(.display)
            Text("The band writer, MuScriptor, is shared by its makers for non-commercial use (CC BY-NC 4.0). Each person accepts it with their own free Hugging Face account.")
                .brFont(.body).fixedSize(horizontal: false, vertical: true)
            Text("1. Sign in and choose **Agree** on the MuScriptor page.").brFont(.body)
            Text("2. Come back here. Brasscribe downloads it for you.").brFont(.body)
            HStack(spacing: 12) {
                Button { NSWorkspace.shared.open(URL(string: "https://huggingface.co/MuScriptor/muscriptor-medium")!) } label: {
                    Text("Read the licence")
                }
                .buttonStyle(.brPlain)
                Button { NSWorkspace.shared.open(URL(string: "https://huggingface.co/settings/tokens/new?tokenType=read")!) } label: {
                    Text("Get an access key on Hugging Face")
                }
                .buttonStyle(.brOutline)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("Access key from Hugging Face").brFont(.bodyStrong)
                HStack {
                    SecureField(text: $key, prompt: Text(verbatim: "hf_…")) { Text("Access key from Hugging Face") }
                        .textFieldStyle(.roundedBorder)
                    Button { key = NSPasteboard.general.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? key } label: {
                        Text("Paste")
                    }
                    .buttonStyle(.brOutline)
                }
                if keySaved {
                    Label("The key is saved in your Keychain.", systemImage: "checkmark.circle")
                        .brFont(.callout)
                }
            }
            Spacer()
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 4) {
                    Button { step = 2 } label: { Text("Skip for now") }.buttonStyle(.brPlain)
                    Text("Without it, Brasscribe can't write down a full band. You can add it later.")
                        .brFont(.caption).foregroundStyle(Color.Brasscribe.textMuted)
                }
                Spacer()
                Button {
                    if !key.isEmpty { keySaved = HuggingFaceKey.save(key) }
                    step = 2
                } label: { Text("Continue") }
                    .buttonStyle(BRButtonStyle(kind: .primary, height: 40))
                    .keyboardShortcut(.defaultAction)
                    .disabled(key.isEmpty && !keySaved)
            }
        }
    }

    // MARK: 3

    private var download: some View {
        let phase = app.bootstrapper.phase
        return VStack(alignment: .leading, spacing: 14) {
            Text("Downloading what Brasscribe needs").brFont(.display)
            BrassProgress(fraction: Double(app.bootstrapper.percent) / 100)
                .accessibilityElement()
                .accessibilityLabel(Text("Downloading what Brasscribe needs"))
                .accessibilityValue(Text("\(app.bootstrapper.percent)%"))
            Text("\(app.bootstrapper.percent)%").brFont(.callout)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(["Listening tools", "Band writer (MuScriptor)", "Instrument separator", "Beat finder"], id: \.self) { item in
                    Label(LocalizedStringKey(item), systemImage: phase == .done ? "checkmark.circle" : "arrow.down.circle").brFont(.body)
                }
            }
            if case .failed(let why) = phase {
                ProblemCard(title: String(localized: "The download stopped"), why: why, symbol: "exclamationmark.triangle.fill",
                            tint: Color.Brasscribe.warning)
            }
            Text("You can close this window. Brasscribe keeps downloading and tells you when it's ready.")
                .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted)
            Spacer()
            HStack {
                Spacer()
                if phase == .done {
                    Button { step = 3 } label: { Text("Continue") }
                        .buttonStyle(BRButtonStyle(kind: .primary, height: 40)).keyboardShortcut(.defaultAction)
                } else if case .failed = phase {
                    Button { run() } label: { Text("Try again") }.buttonStyle(BRButtonStyle(kind: .primary, height: 40))
                } else {
                    Button { dismissWindow(id: "setup") } label: { Text("Close window") }.buttonStyle(.brOutline)
                }
            }
        }
        .onAppear { if phase == .idle { run() } }
    }

    private func run() {
        let config = app.supervisor.configuration
        let bundled = Bundle.main.resourceURL?.appending(path: "workspace")
        Task { await app.bootstrapper.run(configuration: config, bundledWorkspace: bundled) }
    }

    // MARK: 4

    private var ready: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Brasscribe is ready").brFont(.display)
            Text("It runs quietly in the menu bar. Look for the Brasscribe mark at the top of the screen.").brFont(.body)
            Toggle(isOn: $startAtLogin) { Text("Start when I log in").brFont(.body) }
                .toggleStyle(.switch)
            Text("Next, your Mac asks whether Brasscribe may find devices on your network. Choose **Allow** so phones can connect.")
                .brFont(.callout).fixedSize(horizontal: false, vertical: true)
            Spacer()
            HStack {
                Spacer()
                Button { finish(); dismissWindow(id: "setup") } label: { Text("Done") }.buttonStyle(.brOutline)
                Button { finish(); dismissWindow(id: "setup"); app.openWindow?("pair") } label: { Text("Pair a phone") }
                    .buttonStyle(BRButtonStyle(kind: .primary, height: 40)).keyboardShortcut(.defaultAction)
            }
        }
    }

    private func finish() {
        app.finishSetup(startAtLogin: startAtLogin)
    }
}

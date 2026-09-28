import AppKit
import BandroomKit
import SwiftUI

/// First run: one window, four steps, one decision per step (design/server-app.md §3.2).
struct SetupView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismissWindow) private var dismissWindow
    @State private var step = 0
    /// Went straight to the downloads ("Finish setting up" after the first run): only what is missing.
    @State private var finishing = false
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
        .frame(minWidth: 760, minHeight: 520)
        .background(Color.Brasscribe.bg)
        .foregroundStyle(Color.Brasscribe.text)
        .onDisappear { app.isSetupWindowOpen = false }
        .onAppear {
            app.isSetupWindowOpen = true
            // Finish setting up: straight to what is left. The band writer without a key starts at the licence.
            guard app.setupComplete else { return }
            finishing = true
            let missing = app.models.missing
            step = missing.contains(.bandWriter) && !keySaved && !app.downloader.isActive ? 1 : 2
        }
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
            Text("Brasscribe uses the key only to download the band writer from Hugging Face, and keeps it in your Keychain.")
                .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted).fixedSize(horizontal: false, vertical: true)
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
                    if !key.isEmpty {
                        keySaved = HuggingFaceKey.save(key.trimmingCharacters(in: .whitespacesAndNewlines))
                        app.huggingFaceKeyChanged()
                    }
                    if case .failed = app.downloader.phase { app.downloader.resume() }
                    step = 2
                } label: { Text("Continue") }
                    .buttonStyle(BRButtonStyle(kind: .primary, height: 40))
                    .keyboardShortcut(.defaultAction)
                    .disabled(key.isEmpty && !keySaved)
            }
        }
    }

    // MARK: 3

    /// What this step fetches: the engine's own tools on the first run, then only the missing models.
    private var items: [ModelComponent] {
        let d = app.downloader
        return d.components.isEmpty || d.phase == .idle ? app.models.missing : d.components
    }

    private var download: some View {
        let boot = app.bootstrapper.phase
        let d = app.downloader
        let needsTools = !finishing
        let fraction: Double = needsTools
            ? (boot == .done ? 0.3 + 0.7 * d.fraction : Double(app.bootstrapper.percent) / 100 * 0.3)
            : d.fraction
        return VStack(alignment: .leading, spacing: 14) {
            Text("Downloading what Brasscribe needs").brFont(.display)
            BrassProgress(fraction: fraction)
                .accessibilityElement()
                .accessibilityLabel(Text("Downloading what Brasscribe needs"))
                .accessibilityValue(Text("\(Int(fraction * 100))%"))
            Text(progressLine(fraction: fraction)).brFont(.callout)
            VStack(alignment: .leading, spacing: 6) {
                if needsTools {
                    itemRow(String(localized: "Listening tools"), size: nil, state: toolsState)
                }
                ForEach(items, id: \.self) { c in
                    itemRow(Strings.componentItem(c), size: c.totalBytes, state: state(of: c))
                }
            }
            if case .failed(let why) = boot {
                ProblemCard(title: String(localized: "The download stopped"), why: why, symbol: "exclamationmark.triangle.fill",
                            tint: Color.Brasscribe.warning)
            }
            if case .failed(let e) = d.phase { downloadProblem(e) }
            if items.contains(where: { $0 != .bandWriter }) {
                Text("The separators have no stated licence, so Brasscribe doesn't pass them on: this Mac downloads them from where their makers publish them.")
                    .brFont(.caption).foregroundStyle(Color.Brasscribe.textMuted).fixedSize(horizontal: false, vertical: true)
            }
            Text("You can close this window. Brasscribe keeps downloading and tells you when it's ready.")
                .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted)
            Spacer()
            HStack {
                if d.phase == .downloading || d.phase == .checking {
                    Button { d.pause() } label: { Text("Pause") }.buttonStyle(.brOutline)
                } else if d.phase == .paused {
                    Button { d.resume() } label: { Text("Resume") }.buttonStyle(.brOutline)
                }
                Spacer()
                if (boot == .done || finishing) && (d.phase == .done || items.isEmpty) {
                    Button { step = 3 } label: { Text("Continue") }
                        .buttonStyle(BRButtonStyle(kind: .primary, height: 40)).keyboardShortcut(.defaultAction)
                } else if case .failed = boot {
                    Button { run() } label: { Text("Try again") }.buttonStyle(BRButtonStyle(kind: .primary, height: 40))
                } else if case .failed = d.phase {
                    if boot == .done || finishing {
                        // Carry on without what failed; the popover says what is missing (§6.2).
                        Button { step = 3 } label: { Text("Continue without it") }.buttonStyle(.brPlain)
                    }
                    Button { d.resume() } label: { Text("Try again") }.buttonStyle(BRButtonStyle(kind: .primary, height: 40))
                } else {
                    Button { dismissWindow(id: "setup") } label: { Text("Close window") }.buttonStyle(.brOutline)
                }
            }
        }
        .onAppear { if (boot == .idle && !finishing) || (finishing && !d.isActive && d.phase != .paused) { run() } }
    }

    private enum ItemState { case waiting, active, done, failed }

    private var toolsState: ItemState {
        switch app.bootstrapper.phase {
        case .done: .done
        case .failed: .failed
        case .idle: .waiting
        default: .active
        }
    }

    private func state(of c: ModelComponent) -> ItemState {
        let d = app.downloader
        if !app.models.missing.contains(c) || d.finished.contains(c) { return .done }
        // Held back (the key or the licence) after the rest came.
        if case .failed = d.phase, d.current == nil, d.components.contains(c) { return .failed }
        if d.current == c {
            if case .failed = d.phase { return .failed }
            return d.phase == .downloading ? .active : .waiting
        }
        return .waiting
    }

    private func itemRow(_ title: String, size: Int64?, state: ItemState) -> some View {
        let symbol = switch state {
        case .waiting: "circle"
        case .active: "arrow.down.circle"
        case .done: "checkmark.circle"
        case .failed: "exclamationmark.triangle"
        }
        let word = switch state {
        case .waiting: String(localized: "Waiting")
        case .active: String(localized: "Downloading")
        case .done: String(localized: "Done")
        case .failed: String(localized: "Stopped")
        }
        return HStack(spacing: 8) {
            Image(systemName: symbol).frame(width: 20).accessibilityHidden(true)
            Text(title).brFont(.body)
            if let size { Text("\(Strings.gigabytes(size)) GB").brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted) }
            Spacer()
            Text(word).brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted)
        }
        .accessibilityElement(children: .combine)
    }

    /// "3.1 of 9.8 GB · about 12 min left", "Paused · 3.1 of 9.8 GB".
    private func progressLine(fraction: Double) -> String {
        let d = app.downloader
        guard d.bytesTotal > 0, d.phase != .idle else {
            return String(localized: "\(Int(fraction * 100))%")
        }
        let amount = String(localized: "\(Strings.gigabytes(d.bytesDone)) of \(Strings.gigabytes(d.bytesTotal)) GB")
        if d.phase == .paused { return String(localized: "Paused · \(amount)") }
        if let m = d.minutesLeft { return String(localized: "\(amount) · about \(m) min left") }
        return amount
    }

    /// Each reason in its own words, with the one thing that fixes it.
    @ViewBuilder private func downloadProblem(_ e: DownloadError) -> some View {
        let warn = Color.Brasscribe.warning
        switch e {
        case .keyMissing:
            ProblemCard(title: String(localized: "The band writer needs your Hugging Face access key"),
                        why: String(localized: "Add the key, then try again. The separators download without it."),
                        symbol: "key", tint: warn)
            Button { step = 1 } label: { Text("Add an access key") }.buttonStyle(.brOutline)
        case .keyRefused:
            ProblemCard(title: String(localized: "Hugging Face didn't accept the access key"),
                        why: String(localized: "The key may have been deleted or have expired."), symbol: "key", tint: warn)
            Button { step = 1 } label: { Text("Paste a new key") }.buttonStyle(.brOutline)
        case .licenceNotAccepted:
            ProblemCard(title: String(localized: "Accept the licence on Hugging Face, then try again"),
                        why: String(localized: "Signed in, but the licence isn't accepted yet. Choose **Agree** on the MuScriptor page."),
                        symbol: "doc.text", tint: warn)
            Button { NSWorkspace.shared.open(ModelComponent.bandWriter.page) } label: { Text("Open the MuScriptor page") }
                .buttonStyle(.brOutline)
        case .notEnoughSpace(let needed, let free):
            ProblemCard(title: String(localized: "Not enough space"),
                        why: String(localized: "The downloads need about \(Strings.gigabytes(needed)) GB; \(Strings.gigabytes(free)) GB is free."),
                        symbol: "internaldrive", tint: warn)
            Button { app.openStorageSettings() } label: { Text("Free up space…") }.buttonStyle(.brOutline)
        case .checksumMismatch:
            ProblemCard(title: String(localized: "A download arrived damaged"),
                        why: String(localized: "Brasscribe deleted it. Try again to fetch it afresh."),
                        symbol: "exclamationmark.triangle.fill", tint: warn)
        case .http, .network:
            ProblemCard(title: String(localized: "The download stopped"),
                        why: String(localized: "Check the internet connection, then try again. It continues where it stopped."),
                        symbol: "wifi.exclamationmark", tint: warn)
        case .disk(let why):
            ProblemCard(title: String(localized: "Brasscribe couldn't save the download"), why: why,
                        symbol: "exclamationmark.triangle.fill", tint: warn)
        }
    }

    private func run() {
        if finishing {
            app.downloadMissing()
            return
        }
        let config = app.supervisor.configuration
        let bundled = Bundle.main.resourceURL?.appending(path: "workspace")
        Task {
            await app.bootstrapper.run(configuration: config, bundledWorkspace: bundled)
            if app.bootstrapper.phase == .done { app.downloadMissing() }
        }
    }

    // MARK: 4

    private var ready: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Brasscribe is ready").brFont(.display)
            Text("It runs quietly in the menu bar. Look for the Brasscribe mark at the top of the screen.").brFont(.body)
            Text("Don't see it? On a MacBook it can hide behind the camera notch. Open Brasscribe from Launchpad any time.")
                .brFont(.callout).foregroundStyle(Color.Brasscribe.textMuted).fixedSize(horizontal: false, vertical: true)
            Toggle(isOn: $startAtLogin) { Text("Start when I log in").brFont(.body) }
                .toggleStyle(.switch)
            Text("Next, your Mac asks whether Brasscribe may find devices on your network. Choose **Allow** so phones can connect.")
                .brFont(.callout).fixedSize(horizontal: false, vertical: true)
            Spacer()
            HStack {
                Spacer()
                Button { finish(); dismissWindow(id: "setup") } label: { Text("Done") }.buttonStyle(.brOutline)
                Button { finish(); dismissWindow(id: "setup"); app.openWindow("pair") } label: { Text("Pair a phone") }
                    .buttonStyle(BRButtonStyle(kind: .primary, height: 40)).keyboardShortcut(.defaultAction)
            }
        }
    }

    private func finish() {
        app.finishSetup(startAtLogin: startAtLogin)
    }
}

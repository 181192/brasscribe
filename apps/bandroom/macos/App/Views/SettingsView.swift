import BandroomKit
import SwiftUI

/// Settings (design/shared/server-app.md §4): Start when I log in · Where downloads are kept · Hugging Face access ·
/// Sheet music from pictures (the reader that is fetched only when asked for here) · Appearance (design/brands/brasscribe/system.md §10) · Text size · About.
struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.colorSchemeContrast) private var contrast
    @AppStorage("textSize") private var textSize: TextSize = .standard
    @AppStorage(AppearanceChoice.defaultsKey) private var appearance: AppearanceChoice = .system
    @AppStorage("engineCheckout") private var checkout = ""
    @State private var shownName = ""

    var body: some View {
        Form {
            Section {
                Toggle("Start when I log in", isOn: Binding(get: { app.loginItemEnabled }, set: { app.setLoginItem($0) }))
                Toggle("Show in the Dock", isOn: Binding(get: { app.showInDock }, set: { app.showInDock = $0 }))
                Text("For when the Brasscribe mark is hidden in the menu bar, for example behind the camera notch.")
                    .font(.caption).foregroundStyle(Color.Scribe.textMuted)
            }
            if app.offersCustomComputerName {
                Section("Name shown to phones") {
                    TextField("Name shown to phones", text: $shownName, prompt: Text(verbatim: app.systemComputerName))
                        .onSubmit { app.setCustomComputerName(shownName) }
                    HStack {
                        Text("Phones list this Mac as “Brasscribe on \(app.shownComputerName)”.")
                            .font(.caption).foregroundStyle(Color.Scribe.textMuted)
                        Spacer()
                        Button("Use this name") { app.setCustomComputerName(shownName) }
                            .disabled(shownName.trimmingCharacters(in: .whitespaces) == app.customComputerName)
                    }
                }
                .onAppear { shownName = app.customComputerName }
            }
            Section("Where downloads are kept") {
                LabeledContent("Data folder") {
                    Text(app.paths.data.path.replacingOccurrences(of: NSHomeDirectory(), with: "~")).textSelection(.enabled)
                        .foregroundStyle(Color.Scribe.textMuted)
                }
            }
            if app.bandWriterLeftOut {
                Section("Full-band scores") {
                    Text("A score for a full band needs one more download (\(Strings.gigabytes(ModelComponent.bandWriter.totalBytes)) GB) and a free Hugging Face account.")
                        .font(.caption).foregroundStyle(Color.Scribe.textMuted)
                    Button("Set up full-band scores") { app.wantBandWriter(); app.openWindow("setup") }
                }
            } else {
                Section("Hugging Face access") {
                    Button("Sign in again…") { app.openWindow("setup") }
                }
            }
            Section("Sheet music from pictures") {
                // What it is, its licence and where it comes from, before the button that fetches it.
                Text("Phones can send a picture or a PDF of printed sheet music and get a score or a tab back. That takes a reader, homr, which is not part of Brasscribe: it is free software under the AGPL-3.0 licence.")
                    .fixedSize(horizontal: false, vertical: true)
                Text("Brasscribe doesn't pass it on: this Mac downloads it from PyPI and from homr's releases on GitHub (about \(Strings.gigabytes(SheetReader.downloadBytes)) GB) and runs it as a separate program.")
                    .font(.caption).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                switch app.readerState {
                case .notInstalled:
                    if !app.canInstallReader {
                        Text("Brasscribe is still being set up. The reader can be installed once that is done.")
                            .font(.caption).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                    }
                case .installing:
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small).accessibilityHidden(true)
                        Text("Installing the reader… This takes a few minutes.").fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                case .installed:
                    Text("The reader is installed. Phones can send pictures of sheet music now.")
                        .fixedSize(horizontal: false, vertical: true)
                case .failed(let why):
                    Text(Strings.readerFailure(why)).fixedSize(horizontal: false, vertical: true)
                }
                HStack {
                    Button("Read about homr and its licence") { NSWorkspace.shared.open(SheetReader.page) }
                    Spacer()
                    switch app.readerState {
                    case .notInstalled: Button("Install the reader") { app.installReader() }.disabled(!app.canInstallReader)
                    case .failed: Button("Try again") { app.installReader() }.disabled(!app.canInstallReader)
                    case .installing, .installed: EmptyView()
                    }
                }
            }
            Section("Appearance") {
                Picker("Appearance", selection: $appearance) {
                    Text("Match system").tag(AppearanceChoice.system)
                    Text("Light").tag(AppearanceChoice.light)
                    Text("Dark").tag(AppearanceChoice.dark)
                }
                .pickerStyle(.radioGroup)
                .labelsHidden() // the section title shows the name; VoiceOver still reads it once
                .onChange(of: appearance) { _, choice in choice.apply() }
                // Increase Contrast wins: the choice stays, and AppKit uses the high-contrast colours in either mode.
                if contrast == .increased {
                    Text("Increase contrast is on, so Brasscribe uses its high-contrast colours.")
                        .font(.caption).foregroundStyle(Color.Scribe.textMuted)
                }
            }
            Section("Text size") {
                Picker("Text size", selection: $textSize) {
                    Text("Standard").tag(TextSize.standard)
                    Text("Large").tag(TextSize.large)
                    Text("Larger").tag(TextSize.larger)
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()
            }
            Section("About") {
                // The licences of what Bandroom ships, in the program that opens text files on this Mac.
                Button("Third-party licences") { app.openLicences() }
            }
            Section("Details for the band's tech person") {
                TextField("Engine from a checkout (folder with pixi.toml)", text: $checkout)
                Text("Takes effect the next time Brasscribe starts.").font(.caption).foregroundStyle(Color.Scribe.textMuted)
            }
        }
        .formStyle(.grouped)
        // On the page's ground, with the notes in its muted text: the system's secondary colour on the window's own
        // ground is too faint in the light appearance. The rows' own fills are the system's (a grouped form draws
        // them whatever ground a row is given); the screen catalogue measures every text on them.
        .scrollContentBackground(.hidden)
        .frame(width: 480)
        .padding(.vertical, 8)
        .background(Color.Scribe.bg)
    }
}

extension AppearanceChoice {
    /// Applies at once to every window and the menu-bar panel; nil follows the system.
    @MainActor func apply() {
        NSApp.appearance = appearanceName.flatMap { NSAppearance(named: $0) }
    }
}

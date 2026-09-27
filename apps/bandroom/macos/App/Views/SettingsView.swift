import BandroomKit
import SwiftUI

/// Settings (design/server-app.md §4): Start when I log in · Where downloads are kept · Hugging Face access ·
/// Appearance (design/system.md §10) · Text size · About.
struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.colorSchemeContrast) private var contrast
    @AppStorage("textSize") private var textSize: TextSize = .standard
    @AppStorage(AppearanceChoice.defaultsKey) private var appearance: AppearanceChoice = .system
    @AppStorage("engineCheckout") private var checkout = ""

    var body: some View {
        Form {
            Section {
                Toggle("Start when I log in", isOn: Binding(get: { app.loginItemEnabled }, set: { app.setLoginItem($0) }))
            }
            Section("Where downloads are kept") {
                LabeledContent("Data folder") {
                    Text(app.paths.data.path.replacingOccurrences(of: NSHomeDirectory(), with: "~")).textSelection(.enabled)
                }
            }
            Section("Hugging Face access") {
                Button("Sign in again…") { app.openWindow?("setup") }
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
                        .font(.caption).foregroundStyle(.secondary)
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
            Section("Details for the band's tech person") {
                TextField("Engine from a checkout (folder with pixi.toml)", text: $checkout)
                Text("Takes effect the next time Brasscribe starts.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .padding(.vertical, 8)
    }
}

extension AppearanceChoice {
    /// Applies at once to every window and the menu-bar panel; nil follows the system.
    @MainActor func apply() {
        NSApp.appearance = appearanceName.flatMap { NSAppearance(named: $0) }
    }
}

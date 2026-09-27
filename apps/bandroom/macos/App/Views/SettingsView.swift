import BandroomKit
import SwiftUI

/// Settings (design/server-app.md §4): Start when I log in · Where downloads are kept · Hugging Face access ·
/// Text size · About.
struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @AppStorage("textSize") private var textSize: TextSize = .standard
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
            Section("Text size") {
                Picker("Text size", selection: $textSize) {
                    Text("Standard").tag(TextSize.standard)
                    Text("Large").tag(TextSize.large)
                    Text("Larger").tag(TextSize.larger)
                }
                .pickerStyle(.radioGroup)
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

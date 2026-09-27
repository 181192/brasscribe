import OnDeviceKit
import SwiftUI
import TranscriptionKit

/// Settings, grouped: your computer (connection and pairing), on this device, keyboard, and about.
/// Technical details (the address, the listening files' address) sit behind a disclosure.
struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var status: String?
    @State private var busy = false
    @State private var modelTick = 0
    @AppStorage("singleKeyShortcuts") private var singleKeys = true
    @AppStorage(StandSettings.followKey) private var standTurnPages = true
    @AppStorage(StandSettings.keepControlsKey) private var standKeepControls = false

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            Form {
                YourComputerSection()

                Section {
                    Toggle(isOn: $app.soloOnDevice) { Text("Write down solos on this device") }
                    LabeledContent { Text(modelStatus) } label: { Text("Listening files") }
                    Button("Download the listening files") { Task { await downloadModels() } }
                        .disabled(busy || ModelStore.shared.missing.isEmpty)
                    Button("Remove the listening files", role: .destructive) { ModelStore.shared.removeAll(); modelTick += 1 }
                    if let status { Text(status).font(Font.Brasscribe.callout) }
                    DisclosureGroup {
                        TextField(text: $app.modelDownloadURL) { Text("Download address") }
                            .textContentType(.URL)
                            .autocorrectionDisabled()
                    } label: { Text("Details for the band's tech person") }
                } header: { Text("On this device") } footer: {
                    Text("One instrument on its own can be written down here, with nothing sent anywhere. The listening files (about 6 MB) are downloaded once.")
                }

                Section {
                    Toggle(isOn: $standTurnPages) { Text("Turn the pages while playing") }
                        .accessibilityIdentifier("settingStandTurnPages")
                    Toggle(isOn: $standKeepControls) { Text("Keep the stand controls visible") }
                        .accessibilityIdentifier("settingStandKeepControls")
                } header: { Text("Display") } footer: {
                    VStack(alignment: .leading, spacing: Space.s1) {
                        Text("Page turners and pedals work when they send arrow keys or Page Up and Page Down. Space starts and stops the music.")
                        #if os(iOS)
                        if UIDevice.current.userInterfaceIdiom == .pad {
                            Text("To keep a tablet one way up, use the rotation lock in Control Centre (iPad) or Quick Settings (Android).")
                        }
                        #endif
                    }
                }

                Section {
                    Toggle(isOn: $singleKeys) { Text("Single-key shortcuts") }
                } header: { Text("Keyboard") } footer: {
                    Text("Space plays and pauses, the arrow keys move by bar, F opens the music stand, and L, C, M, A and O switch the practice controls. Turn this off if you use speech control or a switch.")
                }

                Section {
                    HStack(spacing: Space.s3) {
                        Lockup()
                        Spacer()
                        Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
                            .foregroundStyle(Color.Brasscribe.textMuted)
                    }
                    .listRowBackground(Color.Brasscribe.brassTint)
                    NavigationLink { LicenceView() } label: { Text("Instrument Serif (SIL Open Font License 1.1)") }
                    Text("Notation engraved with Verovio (LGPL-3.0), included as an unmodified dynamic framework.")
                    Text("Baseline sounds: MuseScore General SoundFont (MIT), downloaded separately.")
                } header: { Text("About") }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .background(Color.Brasscribe.bg)
            .navigationTitle(Text("Settings"))
            #if os(iOS)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            #endif
        }
        .frame(minWidth: 480, minHeight: 520)
    }

    var modelStatus: String {
        _ = modelTick
        let missing = ModelStore.shared.missing
        if missing.isEmpty { return String(localized: "Ready") }
        let mb = missing.reduce(0) { $0 + $1.sizeMB }
        return String(localized: "\(Int(mb.rounded())) MB to download")
    }

    func downloadModels() async {
        busy = true; defer { busy = false; modelTick += 1 }
        ModelStore.shared.remoteBase = URL(string: app.modelDownloadURL)
        do { try await ModelStore.shared.prepareAll(); status = String(localized: "The listening files are ready.") }
        catch { status = String(localized: "The listening files couldn't be downloaded. Check the connection and try again.") }
    }
}

/// The display face's licence, shown in About.
struct LicenceView: View {
    var body: some View {
        ScrollView {
            Text(licence).font(.footnote.monospaced()).textSelection(.enabled).padding(Space.s5)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .pageBackground()
        .navigationTitle(Text(verbatim: "Instrument Serif"))
    }

    private var licence: String {
        Bundle.main.url(forResource: "OFL", withExtension: "txt").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? ""
    }
}

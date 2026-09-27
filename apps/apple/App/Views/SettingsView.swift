import OnDeviceKit
import SwiftUI
import TranscriptionKit

/// Settings, grouped: your computer (pairing), on this device, keyboard, and about.
/// Technical details (the address, the listening files' address) sit behind a disclosure.
struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var code = ""
    @State private var status: String?
    @State private var busy = false
    @State private var modelTick = 0
    @State private var browser = EngineBrowser()
    @AppStorage("singleKeyShortcuts") private var singleKeys = true

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            Form {
                Section {
                    ForEach(browser.engines) { engine in
                        Button { Task { await choose(engine) } } label: {
                            Label(engine.name, systemImage: BrasscribeIcon.computer.systemName)
                        }
                        .disabled(busy)
                    }
                    if browser.engines.isEmpty {
                        Text("Looking for Brasscribe on your network…").foregroundStyle(Color.Brasscribe.textMuted)
                    }
                    TextField(text: $code) { Text("Six-digit code") }
                        .textContentType(.oneTimeCode)
                        #if os(iOS)
                        .keyboardType(.numberPad)
                        #endif
                    Button("Pair") { Task { await pair() } }.disabled(code.count != 6 || busy)
                    Button("Check the connection") { Task { await check() } }.disabled(busy)
                    if let status { Text(status).font(Font.Brasscribe.callout) }
                    DisclosureGroup {
                        Text("On the computer, start Brasscribe with “brasscribe serve --lan”. It shows the pairing code, and this device finds it on the same network.")
                            .font(Font.Brasscribe.callout)
                        if let problem = browser.problem {
                            Text(problem).font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
                        }
                        TextField(text: $app.companionURL) { Text("Address") }
                            .textContentType(.URL)
                            .autocorrectionDisabled()
                    } label: { Text("Details for the band's tech person") }
                } header: { Text("Brasscribe on your computer") } footer: {
                    Text("Open Brasscribe on your computer. When it's on the same network it's listed here: choose it, then type the six digits it shows.")
                }

                Section {
                    Toggle(isOn: $app.soloOnDevice) { Text("Write down solos on this device") }
                    LabeledContent { Text(modelStatus) } label: { Text("Listening files") }
                    Button("Download the listening files") { Task { await downloadModels() } }
                        .disabled(busy || ModelStore.shared.missing.isEmpty)
                    Button("Remove the listening files", role: .destructive) { ModelStore.shared.removeAll(); modelTick += 1 }
                    DisclosureGroup {
                        TextField(text: $app.modelDownloadURL) { Text("Download address") }
                            .textContentType(.URL)
                            .autocorrectionDisabled()
                    } label: { Text("Details for the band's tech person") }
                } header: { Text("On this device") } footer: {
                    Text("One instrument on its own can be written down here, with nothing sent anywhere. The listening files (about 6 MB) are downloaded once.")
                }

                Section {
                    Toggle(isOn: $singleKeys) { Text("Single-key shortcuts") }
                } header: { Text("Keyboard") } footer: {
                    Text("Space plays and pauses, the arrow keys move by bar, and L, C, M, A and O switch the practice controls. Turn this off if you use speech control or a switch.")
                }

                Section {
                    Toggle(isOn: Binding(get: { UserDefaults.standard.bool(forKey: "useDemoService") },
                                         set: { UserDefaults.standard.set($0, forKey: "useDemoService") })) {
                        Text("Use the demo instead of a computer")
                    }
                    .disabled(app.fixtureDirectory == nil)
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
        .onAppear { browser.start() }
        .onDisappear { browser.stop() }
    }

    func choose(_ engine: EngineBrowser.Engine) async {
        busy = true; defer { busy = false }
        do {
            let url = try await browser.resolve(engine)
            app.companionURL = url.absoluteString
            status = String(localized: "Found \(engine.name). Type the six digits it shows to pair.")
        } catch { status = String(localized: "\(engine.name) didn't answer. Check that it's still open.") }
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

    func pair() async {
        busy = true; defer { busy = false }
        let svc = CompanionService(baseURL: URL(string: app.companionURL) ?? URL(string: "http://localhost:8765")!)
        do {
            #if os(iOS)
            let name = UIDevice.current.name
            #else
            let name = Host.current().localizedName ?? "Mac"
            #endif
            app.companionToken = try await svc.pair(code: code, deviceName: name)
            status = String(localized: "Paired. Recordings can now be written down on your computer.")
        } catch { status = String(localized: "That didn't work. Check the six digits, and that the computer is on the same network.") }
    }

    func check() async {
        busy = true; defer { busy = false }
        let svc = CompanionService(baseURL: URL(string: app.companionURL) ?? URL(string: "http://localhost:8765")!, token: app.companionToken)
        do {
            let h = try await svc.health()
            status = String(localized: "Connected to Brasscribe \(h.version) on \(h.device).")
        } catch { status = String(localized: "Brasscribe on your computer can't be reached. Check that it's open, and on the same network.") }
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

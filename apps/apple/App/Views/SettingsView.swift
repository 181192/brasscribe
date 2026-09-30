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
    @AppStorage(AppearanceSetting.key) private var appearance = AppearanceSetting.system.rawValue
    @AppStorage(PinkUnlock.key) private var pinkUnlocked = false
    @State private var justUnlocked = false
    @Environment(\.colorSchemeContrast) private var contrast
    @AppStorage(StandSettings.followKey) private var standTurnPages = true
    @AppStorage(StandSettings.keepControlsKey) private var standKeepControls = false

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            Form {
                Section {
                    NavigationLink {
                        WhatDoYouPlayView(mode: .settings, initial: app.seat) { answer in
                            if let answer { app.seat = answer }
                        }
                        .navigationTitle(Text("What you play"))
                    } label: {
                        LabeledContent { Text(app.seat.summary) } label: {
                            Label { Text("What you play") } icon: { Image(systemName: BrasscribeIcon.parts.systemName) }
                        }
                    }
                    .accessibilityIdentifier("settingWhatYouPlay")
                } header: { Text("Your instrument") } footer: {
                    Text("New scores open on your part. Scores you already have keep the part you chose for them.")
                }

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
                    Picker(selection: $appearance) {
                        ForEach(AppearanceSetting.options(pinkUnlocked: pinkUnlocked || AppearanceSetting.storedIsPink(appearance))) { a in
                            Text(a.title).tag(a.rawValue)
                        }
                    } label: { Text("Appearance") }
                    .pickerStyle(.inline)
                    .accessibilityIdentifier("settingAppearance")
                    if contrast == .increased {
                        // Increase Contrast wins: the choice stays, with the high-contrast colours in either mode
                        Text("Increase contrast is on, so Brasscribe uses its high-contrast colours.")
                            .font(Font.Brasscribe.callout)
                            .foregroundStyle(Color.Brasscribe.textMuted)
                    }
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
                        VersionButton(unlocked: $pinkUnlocked, justUnlocked: $justUnlocked)
                    }
                    .listRowBackground(Color.Brasscribe.brassTint)
                    if justUnlocked {
                        Text("🎺 Pink unlocked")
                            .font(Font.Brasscribe.callout)
                            .foregroundStyle(Color.Brasscribe.text)
                            .accessibilityIdentifier("pinkUnlocked")
                            .listRowBackground(Color.Brasscribe.brassTint)
                            .task {
                                try? await Task.sleep(for: .seconds(4))
                                justUnlocked = false
                            }
                    }
                    NavigationLink { LicenceView() } label: { Text("Instrument Serif (SIL Open Font License 1.1)") }
                    Text("Notation engraved with Verovio (LGPL-3.0), included as an unmodified dynamic framework.")
                    Text("Band sounds built from VSCO 2 Community Edition (CC0), the University of Iowa Musical Instrument Samples and MS Basic (MIT).")
                } header: { Text("About") }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .background(Color.Brasscribe.bg)
            .navigationTitle(Text("Settings"))
            #if os(iOS)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            #else
            // a Mac sheet has no title bar: the title above the form, Done below it
            .safeAreaInset(edge: .top, spacing: 0) {
                DisplayTitle(text: String(localized: "Settings"), size: 30)
                    .padding(.horizontal, Space.s5)
                    .padding(.top, Space.s5)
                    .padding(.bottom, Space.s1)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.Brasscribe.bg)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                HStack {
                    Spacer()
                    Button { dismiss() } label: { Text("Done") }
                        .buttonStyle(.primary)
                        .keyboardShortcut(.defaultAction)
                        .accessibilityIdentifier("settingsDone")
                        .layoutProbe("settingsDone")
                }
                .padding(.horizontal, Space.s5)
                .padding(.vertical, Space.s3)
                .background(Color.Brasscribe.bg)
                .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
            }
            #endif
        }
        #if os(macOS)
        // the form's own height, up to 90 % of the screen; past that it scrolls
        .sheetSize(minWidth: 520, idealWidth: 600, maxWidth: 680, minHeight: 360)
        #endif
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

/// The version in About. It looks like plain text, but activating it five times in a row unlocks
/// Pink in Appearance (design/system.md §10): by tap, click, VoiceOver, Switch Control or the
/// keyboard. On the Mac, Option-activating it unlocks at once. The unlock is shown under the row and
/// announced once.
struct VersionButton: View {
    @Binding var unlocked: Bool
    @Binding var justUnlocked: Bool
    @State private var counter = UnlockCounter()

    private var version: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "" }

    var body: some View {
        Button(action: activate) {
            Text(verbatim: version).foregroundStyle(Color.Brasscribe.textMuted)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text("Version \(version)"))
        .accessibilityIdentifier("aboutVersion")
        .onAppear { counter = UnlockCounter(unlocked: unlocked) }
    }

    private func activate() {
        #if os(macOS)
        let now = NSEvent.modifierFlags.contains(.option) ? counter.unlockNow() : counter.activate()
        #else
        let now = counter.activate()
        #endif
        guard now else { return }
        unlocked = true
        justUnlocked = true
        AccessibilityNotification.Announcement(String(localized: "🎺 Pink unlocked")).post()
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

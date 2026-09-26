import OnDeviceKit
import SwiftUI
import TranscriptionKit
#if os(macOS)
import AudioCapture
#endif

struct LevelMeter: View {
    let level: Float
    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(.quaternary)
                Capsule().fill(level > 0.9 ? Color.orange : Color.accentColor)
                    .frame(width: g.size.width * CGFloat(min(1, level)))
            }
        }
        .frame(height: 10)
        .accessibilityElement()
        .accessibilityLabel(Text("Input level"))
        .accessibilityValue(Text("\(Int(min(1, level) * 100)) percent"))
    }
}

struct MicRecordView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var rec = MicRecorder()
    @State private var error: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text(rec.isRecording ? String(localized: "Recording…") : String(localized: "Play when you're ready."))
                    .font(.title2)
                Text(Duration.seconds(rec.seconds).formatted(.time(pattern: .minuteSecond)))
                    .font(.system(.largeTitle, design: .monospaced))
                    .accessibilityLabel(Text("Recorded \(Int(rec.seconds)) seconds"))
                LevelMeter(level: rec.level).frame(maxWidth: 360)
                if rec.permissionDenied {
                    Text("Microphone access is off. Turn it on in Settings to record.").foregroundStyle(.red)
                }
                if let error { Text(error).foregroundStyle(.red) }
                Button {
                    if rec.isRecording {
                        if let url = rec.stop() {
                            if rec.peak < 0.001 { app.alert = .silence } else {
                                dismiss()
                                app.acceptRecording(url, title: String(localized: "Recording \(Date().formatted(date: .abbreviated, time: .shortened))"))
                            }
                        }
                    } else {
                        Task { do { try await rec.start() } catch { self.error = error.localizedDescription } }
                    }
                } label: {
                    Label(rec.isRecording ? String(localized: "Stop") : String(localized: "Record"),
                          systemImage: rec.isRecording ? "stop.circle.fill" : "record.circle")
                        .font(.title)
                        .frame(minWidth: 160, minHeight: 44)
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.space, modifiers: [])
            }
            .padding()
            .formStyle(.grouped)
            .navigationTitle(Text("Record"))
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { rec.stop(); dismiss() } } }
        }
        .frame(minWidth: 420, minHeight: 360)
    }
}

#if os(macOS)
/// Records what this Mac is playing (all sound, or one app) through a Core Audio process tap.
struct CaptureView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var apps: [AudioApp] = []
    @State private var choice: String = "system"
    @State private var recorder: ProcessTapRecorder?
    @State private var seconds: Double = 0
    @State private var level: Float = 0
    @State private var error: String?
    let timer = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationStack {
            Form {
                Picker(selection: $choice) {
                    Text("Everything playing on this Mac").tag("system")
                    ForEach(apps) { a in
                        Text(a.isPlaying ? "\(a.bundleID) (playing)" : a.bundleID).tag(a.bundleID)
                    }
                } label: { Text("Record from") }
                .disabled(recorder != nil)
                Text("Protected (DRM) playback, as in some streaming apps, can't be recorded; you'll hear it but the recording stays silent.")
                    .font(.caption).foregroundStyle(.secondary)
                LabeledContent { Text(Duration.seconds(seconds).formatted(.time(pattern: .minuteSecond))).monospacedDigit() } label: { Text("Recorded") }
                LevelMeter(level: level)
                if let error { Text(error).foregroundStyle(.red) }
                Button(recorder == nil ? String(localized: "Start recording") : String(localized: "Stop")) { toggle() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.space, modifiers: [])
            }
            .padding()
            .formStyle(.grouped)
            .navigationTitle(Text("Record this Mac"))
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { _ = try? recorder?.stop(); dismiss() } } }
            .onAppear { apps = ProcessTapRecorder.audioApps() }
            .onReceive(timer) { _ in
                if let r = recorder { seconds = r.elapsedSeconds; level = r.currentPeak }
            }
        }
        .frame(minWidth: 480, minHeight: 360)
    }

    func toggle() {
        if let r = recorder {
            do {
                let result = try r.stop()
                recorder = nil
                if result.isSilent { app.alert = .silence; return }
                dismiss()
                app.acceptRecording(result.url, title: String(localized: "Recording \(Date().formatted(date: .abbreviated, time: .shortened))"))
            } catch { self.error = "\(error)" }
            return
        }
        let url = FileManager.default.temporaryDirectory.appending(path: "capture-\(UUID().uuidString).wav")
        let r = ProcessTapRecorder(source: choice == "system" ? .system : .app(bundleID: choice), outputURL: url)
        do { try r.start(); recorder = r } catch { self.error = "\(error)" }
    }
}
#endif

struct SettingsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var code = ""
    @State private var status: String?
    @State private var busy = false
    @State private var browser = EngineBrowser()

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            Form {
                Section {
                    ForEach(browser.engines) { engine in
                        Button { Task { await choose(engine) } } label: { Label(engine.name, systemImage: "desktopcomputer") }
                            .disabled(busy)
                    }
                    if browser.engines.isEmpty {
                        Text(browser.problem ?? String(localized: "Looking for Brasscribe on your network…"))
                            .foregroundStyle(.secondary)
                    }
                    TextField(text: $app.companionURL) { Text("Address") }
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                    TextField(text: $code) { Text("Pairing code") }
                        .textContentType(.oneTimeCode)
                    Button("Pair") { Task { await pair() } }.disabled(code.count != 6 || busy)
                    Button("Check connection") { Task { await check() } }.disabled(busy)
                    if let status { Text(status).font(.callout) }
                } header: { Text("Your computer") } footer: {
                    Text("Start Brasscribe on your computer with “brasscribe serve --lan”. When it is on the same network it is listed here; choose it and type the six-digit code it shows.")
                }
                Section {
                    Toggle(isOn: $app.soloOnDevice) { Text("Transcribe solos on this device") }
                    TextField(text: $app.modelDownloadURL) { Text("Model download address") }
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                    LabeledContent {
                        Text(modelStatus)
                    } label: { Text("Models") }
                    Button("Download models") { Task { await downloadModels() } }
                        .disabled(busy || ModelStore.shared.missing.isEmpty)
                    Button("Remove downloaded models", role: .destructive) { ModelStore.shared.removeAll(); modelTick += 1 }
                } header: { Text("On this device") } footer: {
                    Text("Pitch and beat models (about 40 MB) are downloaded once and not included in the app.")
                }
                Section {
                    Toggle(isOn: Binding(get: { UserDefaults.standard.bool(forKey: "useDemoService") },
                                         set: { UserDefaults.standard.set($0, forKey: "useDemoService") })) {
                        Text("Use the demo instead of a computer")
                    }
                    .disabled(app.fixtureDirectory == nil)
                }
                Section {
                    Text("Notation engraved with Verovio (LGPL-3.0), included as an unmodified dynamic framework.")
                    Text("Baseline sounds: MuseScore General SoundFont (MIT), downloaded separately.")
                } header: { Text("About") }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Settings"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onAppear { browser.start() }
            .onDisappear { browser.stop() }
        }
        .frame(minWidth: 460, minHeight: 420)
    }

    func choose(_ engine: EngineBrowser.Engine) async {
        busy = true; defer { busy = false }
        do {
            let url = try await browser.resolve(engine)
            app.companionURL = url.absoluteString
            status = String(localized: "Found at \(url.absoluteString). Type the six-digit code to pair.")
        } catch { status = error.localizedDescription }
    }

    @State private var modelTick = 0

    var modelStatus: String {
        _ = modelTick
        let missing = ModelStore.shared.missing
        if missing.isEmpty { return String(localized: "Ready") }
        let mb = missing.reduce(0) { $0 + $1.sizeMB }
        return String(localized: "\(missing.count) to download (\(Int(mb.rounded())) MB)")
    }

    func downloadModels() async {
        busy = true; defer { busy = false; modelTick += 1 }
        ModelStore.shared.remoteBase = URL(string: app.modelDownloadURL)
        do { try await ModelStore.shared.prepareAll(); status = String(localized: "Models ready.") }
        catch { status = "\(error)" }
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
            status = String(localized: "Paired.")
        } catch { status = error.localizedDescription }
    }

    func check() async {
        busy = true; defer { busy = false }
        let svc = CompanionService(baseURL: URL(string: app.companionURL) ?? URL(string: "http://localhost:8765")!, token: app.companionToken)
        do {
            let h = try await svc.health()
            status = String(localized: "Connected to Brasscribe \(h.version) (\(h.device)).")
        } catch { status = error.localizedDescription }
    }
}

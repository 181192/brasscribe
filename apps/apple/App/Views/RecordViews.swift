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
                Capsule().fill(Color.Brasscribe.secondary)
                Capsule().fill(level > 0.9 ? Color.Brasscribe.warning : Color.Brasscribe.text)
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
                    Text("Microphone access is off. Turn it on in Settings to record.").foregroundStyle(Color.Brasscribe.error)
                }
                if let error { Text(error).foregroundStyle(Color.Brasscribe.error) }
                Button {
                    if rec.isRecording {
                        if let url = rec.stop() {
                            if rec.peak < 0.001 { app.show(.silence) } else {
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
                .buttonStyle(.primary)
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
                Text("Streaming apps usually block recording. You hear the music, but the recording stays silent.")
                    .font(.caption).foregroundStyle(.secondary)
                LabeledContent { Text(Duration.seconds(seconds).formatted(.time(pattern: .minuteSecond))).monospacedDigit() } label: { Text("Recorded") }
                LevelMeter(level: level)
                if let error { Text(error).foregroundStyle(Color.Brasscribe.error) }
                Button(recorder == nil ? String(localized: "Start recording") : String(localized: "Stop")) { toggle() }
                    .buttonStyle(.primary)
                    .keyboardShortcut(.space, modifiers: [])
            }
            .padding()
            .formStyle(.grouped)
            .navigationTitle(Text("Record what's playing"))
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
                if result.isSilent { app.show(.silence); return }
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

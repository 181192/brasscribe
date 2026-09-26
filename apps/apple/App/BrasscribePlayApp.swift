import ScoreKit
import SwiftUI
import TranscriptionKit

@main
struct BrasscribePlayApp: App {
    @State private var app = AppModel()
    #if os(macOS)
    @NSApplicationDelegateAdaptor(MacLaunch.self) private var launch
    #endif

    init() {
        if ProcessInfo.processInfo.arguments.contains("-reset") {
            try? FileManager.default.removeItem(at: Piece.libraryURL)
            UserDefaults.standard.removeObject(forKey: "useDemoService")
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(app)
                .tint(Color.Brasscribe.primary)
                .onOpenURL { url in Task { await app.accept(url: url) } }
        }
        #if os(macOS)
        .defaultSize(width: 1280, height: 900)
        // always open a fresh window; a restored "no windows" state left the UI tests with none
        .restorationBehavior(.disabled)
        .commands { PlaybackCommands() }
        #endif
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        NavigationStack(path: $app.path) {
            HomeView()
                .navigationDestination(for: Route.self) { r in
                    switch r {
                    case .transcribe(let id): TranscribeView(jobID: id)
                    case .review(let p): ReviewView(piece: p)
                    case .score(let p): ScoreScreen(piece: p)
                    }
                }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Brasscribe Play"))
        .sheet(item: $app.pending) { src in SourceSheet(source: src) }
        .sheet(isPresented: $app.showRecorder) { MicRecordView() }
        .sheet(isPresented: $app.showSettings) { SettingsView() }
        #if os(macOS)
        .sheet(isPresented: $app.showCapture) { CaptureView() }
        #endif
        .alert(item: $app.alert) { a in
            Alert(title: Text(a.title), message: Text(a.message), dismissButton: .default(Text("OK")))
        }
        .onAppear {
            if ProcessInfo.processInfo.arguments.contains("-open-demo-score") { openDemoScore() }
            // UI tests: start from a recording as if it had just been imported
            if let a = ProcessInfo.processInfo.environment["BRASSCRIBE_OPEN_AUDIO"], FileManager.default.fileExists(atPath: a) {
                app.acceptRecording(URL(fileURLWithPath: a), title: URL(fileURLWithPath: a).deletingPathExtension().lastPathComponent)
            }
        }
    }

    /// UI tests and screenshots: import the fixture straight into a piece and open it.
    private func openDemoScore() {
        guard let dir = app.fixtureDirectory else { FileHandle.standardError.write(Data("open-demo-score: no fixture directory\n".utf8)); return }
        do {
            let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
            let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
            let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
            let p = try Piece.create(title: "Mikkel", profile: .orchestraWithSoloist, result: result, original: app.originalForFixture,
                                     video: app.videoForFixture, fixtureDirectory: dir)
            app.refresh()
            app.path = [.score(p)]
        } catch {
            FileHandle.standardError.write(Data("open-demo-score: \(error)\n".utf8))
        }
    }
}

#if os(macOS)
/// Menu commands mirror the transport shortcuts so they are discoverable and documented.
/// On macOS these menu items carry the shortcuts, so they work wherever keyboard focus is.
struct PlaybackCommands: Commands {
    @FocusedValue(\.practice) private var model

    var body: some Commands {
        CommandMenu(Text("Playback")) {
            Button("Play or pause") { model?.togglePlay() }.keyboardShortcut(.space, modifiers: [])
            Button("Previous bar") { model?.previousBar() }.keyboardShortcut(.leftArrow, modifiers: [])
            Button("Next bar") { model?.nextBar() }.keyboardShortcut(.rightArrow, modifiers: [])
            Divider()
            Button("Loop current bar") { model?.toggleLoopCurrentBar() }.keyboardShortcut("l", modifiers: [])
            Button("Slower") { model?.changeSpeed(by: -5) }.keyboardShortcut(",", modifiers: [])
            Button("Faster") { model?.changeSpeed(by: 5) }.keyboardShortcut(".", modifiers: [])
            Divider()
            Button("Count-in") { model?.countIn.toggle() }.keyboardShortcut("c", modifiers: [])
            Button("Metronome") { model?.metronome.toggle() }.keyboardShortcut("m", modifiers: [])
            Button("Play along") { model?.playAlong.toggle() }.keyboardShortcut("a", modifiers: [])
            Button("Original or score") { model?.hearOriginal.toggle() }.keyboardShortcut("o", modifiers: [])
        }
    }
}
#endif

struct PracticeKey: FocusedValueKey { typealias Value = PracticeModel }
extension FocusedValues {
    var practice: PracticeModel? {
        get { self[PracticeKey.self] }
        set { self[PracticeKey.self] = newValue }
    }
}

#if os(macOS)

/// SwiftUI opens the first window only once the app is active. Launched in the background
/// (from a script, or relaunched by a UI test) it stayed windowless, so activate at launch.
final class MacLaunch: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        // If still no window (activation can be refused for background launches), ask the
        // WindowGroup for one through the standard New Window action.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            if !NSApp.windows.contains(where: { $0.isVisible && $0.canBecomeMain }) {
                NSApp.sendAction(#selector(NSResponder.newWindowForTab(_:)), to: nil, from: nil)
            }
        }
    }
}
#endif

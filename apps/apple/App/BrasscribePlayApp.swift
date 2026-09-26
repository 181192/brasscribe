import ScoreKit
import SwiftUI
import TranscriptionKit

@main
struct BrasscribePlayApp: App {
    @State private var app = AppModel()

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
                .tint(Palette.accent)
                .onOpenURL { url in Task { await app.accept(url: url) } }
        }
        #if os(macOS)
        .defaultSize(width: 1280, height: 900)
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
            FileHandle.standardError.write(Data("root appeared \(ProcessInfo.processInfo.arguments)\n".utf8))
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
struct PlaybackCommands: Commands {
    var body: some Commands {
        CommandMenu(Text("Playback")) {
            Text("Play or pause: Space")
            Text("Previous / next bar: ← / →")
            Text("Loop current bar: L")
            Text("Slower / faster: [ / ]")
            Text("Count-in: C · Metronome: M · Play along: A")
            Text("Original / score: O")
        }
    }
}
#endif

/// Accent with at least 4.5:1 contrast against light and dark bars (the system blue on a
/// grey toolbar fails the accessibility audit on iPad).
enum Palette {
    static let accent = Color(light: Color(red: 0.0, green: 0.33, blue: 0.72), dark: Color(red: 0.45, green: 0.72, blue: 1.0))
}

extension Color {
    init(light: Color, dark: Color) {
        #if os(iOS)
        self.init(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
        #else
        self.init(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(dark) : NSColor(light) })
        #endif
    }
}

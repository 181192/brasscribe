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
                .onOpenURL { url in Task { await app.accept(url: url) } }
        }
        #if os(macOS)
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
        }
    }

    /// UI tests and screenshots: import the fixture straight into a piece and open it.
    private func openDemoScore() {
        guard let dir = app.fixtureDirectory,
              let xml = try? Data(contentsOf: dir.appending(path: "brass-band.musicxml")) else { return }
        let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
        let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
        if let p = try? Piece.create(title: "Mikkel", profile: .orchestraWithSoloist, result: result, original: app.originalForFixture,
                                     video: app.videoForFixture, fixtureDirectory: dir) {
            app.refresh()
            app.path = [.score(p)]
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

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
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-reset") {
            try? FileManager.default.removeItem(at: Piece.libraryURL)
            UserDefaults.standard.removeObject(forKey: "useDemoService")
        }
        if args.contains("-skip-first-run") { UserDefaults.standard.set(true, forKey: "firstRunDone") }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(app)
                .tint(Color.Brasscribe.primary)
                .preferredColorScheme(LaunchOptions.colorScheme)
                .onOpenURL { url in Task { await app.accept(url: url) } }
        }
        #if os(macOS)
        .defaultSize(width: 1280, height: 900)
        // always open a fresh window; a restored "no windows" state left the UI tests with none
        .restorationBehavior(.disabled)
        .commands { PlaybackCommands() }
        #endif

        #if os(macOS)
        Settings {
            SettingsView()
                .environment(app)
                .tint(Color.Brasscribe.primary)
                .preferredColorScheme(LaunchOptions.colorScheme)
        }
        #endif
    }
}

/// Launch arguments for tests and screenshots.
enum LaunchOptions {
    static let args = ProcessInfo.processInfo.arguments

    /// `-appearance dark` / `-appearance light`
    static var colorScheme: ColorScheme? {
        guard let i = args.firstIndex(of: "-appearance"), i + 1 < args.count else { return nil }
        return args[i + 1] == "dark" ? .dark : .light
    }

    /// `-screen home|source|transcribing|review|score|part|export|first-run|error`
    static var screen: String? {
        guard let i = args.firstIndex(of: "-screen"), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize

    /// iPhone: one stack. iPad and Mac: the library in a sidebar next to the stack.
    private var split: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        @Bindable var app = app
        Group {
            if split {
                NavigationSplitView {
                    LibrarySidebar()
                        .navigationSplitViewColumnWidth(min: 240, ideal: BrasscribeDesign.Size.sidebarWidth, max: 340)
                } detail: {
                    flow
                }
            } else {
                flow
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(verbatim: "Brasscribe Play"))
        .scoreOptionDialogs()
        .sheet(isPresented: $app.showRecorder) { MicRecordView() }
        #if os(iOS)
        .sheet(isPresented: $app.showSettings) { SettingsView() }
        #endif
        #if os(macOS)
        .sheet(isPresented: $app.showCapture) { CaptureView() }
        #endif
        .sheet(isPresented: $app.showFirstRun) { FirstRunView() }
        .onAppear {
            if !UserDefaults.standard.bool(forKey: "firstRunDone") || LaunchOptions.screen == "first-run" { app.showFirstRun = true }
            if LaunchOptions.args.contains("-open-demo-score") { openDemoScore() }
            // UI tests: start from a recording as if it had just been imported
            if let a = ProcessInfo.processInfo.environment["BRASSCRIBE_OPEN_AUDIO"], FileManager.default.fileExists(atPath: a) {
                app.acceptRecording(URL(fileURLWithPath: a), title: URL(fileURLWithPath: a).deletingPathExtension().lastPathComponent)
            }
            if let s = LaunchOptions.screen { ScreenshotScenes.open(s, app: app, openScore: openDemoScore) }
        }
    }

    private var flow: some View {
        @Bindable var app = app
        return NavigationStack(path: $app.path) {
            HomeView()
                .navigationDestination(for: Route.self) { r in
                    switch r {
                    case .source(let s): SourceView(source: s)
                    case .transcribe(let id): TranscribeView(jobID: id)
                    case .review(let p): ReviewView(piece: p)
                    case .score(let p): ScoreScreen(piece: p)
                    case .problem(let p): ProblemView(problem: p)
                    }
                }
        }
    }

    /// UI tests and screenshots: import the fixture straight into a piece and open it.
    @discardableResult
    private func openDemoScore() -> Piece? {
        guard let dir = app.fixtureDirectory else { FileHandle.standardError.write(Data("open-demo-score: no fixture directory\n".utf8)); return nil }
        do {
            let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
            let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
            let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
            let p = try Piece.create(title: "Mikkel", profile: .orchestraWithSoloist, result: result, original: app.originalForFixture,
                                     video: app.videoForFixture, fixtureDirectory: dir)
            app.refresh()
            app.path = [.score(p)]
            return p
        } catch {
            FileHandle.standardError.write(Data("open-demo-score: \(error)\n".utf8))
            return nil
        }
    }
}

/// iPad and Mac sidebar: the lockup, "Open a recording" and the scores.
struct LibrarySidebar: View {
    @Environment(AppModel.self) private var app

    private var selection: Binding<String?> {
        Binding(get: {
            for r in app.path.reversed() {
                switch r {
                case .score(let p), .review(let p): return p.id.uuidString
                default: continue
                }
            }
            return nil
        }, set: { id in
            if let id, let entry = app.scores.first(where: { $0.id == id }) { app.open(entry) }
        })
    }

    var body: some View {
        List(selection: selection) {
            Button { app.goHome() } label: {
                Label("Open a recording", systemImage: BrasscribeIcon.importFile.systemName)
            }
            .accessibilityIdentifier("sidebarHome")
            Section {
                if app.scores.isEmpty {
                    Text("Your scores appear here.").foregroundStyle(Color.Brasscribe.textMuted)
                }
                ForEach(app.scores) { entry in
                    HStack(spacing: Space.s1) {
                        Label(entry.title, systemImage: entry.piece == nil ? BrasscribeIcon.computer.systemName : BrasscribeIcon.score.systemName)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        if app.openingScore == entry.id { ProgressView().controlSize(.small) }
                        ScoreOptionsMenu(entry: entry)
                    }
                    .tag(entry.id)
                    .contextMenu { ScoreOptionItems(entry: entry) }
                    .accessibilityIdentifier("sidebar-\(entry.title)")
                }
            } header: { Text("Your scores") }
        }
        .task { await app.refreshComputerScores() }
        .safeAreaInset(edge: .top) {
            HStack { Lockup(); Spacer() }
                .padding(.horizontal, Space.s4)
                .padding(.vertical, Space.s2)
        }
        .navigationTitle(Text(verbatim: "Brasscribe Play"))
        #if os(macOS)
        .toolbar(removing: .title)
        #endif
    }
}

#if os(macOS)
/// Menu commands mirror the transport shortcuts so they are discoverable and documented.
/// On macOS these menu items carry the shortcuts, so they work wherever keyboard focus is.
/// They are off when no score is open, so the keys reach the screen that is.
struct PlaybackCommands: Commands {
    @FocusedValue(\.practice) private var model
    @AppStorage("singleKeyShortcuts") private var singleKeys = true

    private func key(_ k: KeyEquivalent) -> KeyboardShortcut? { singleKeys ? KeyboardShortcut(k, modifiers: []) : nil }

    var body: some Commands {
        CommandMenu(Text("Playback")) {
            Group {
                Button("Play or pause") { model?.togglePlay() }.keyboardShortcut(key(.space))
                Button("Previous bar") { model?.previousBar() }.keyboardShortcut(key(.leftArrow))
                Button("Next bar") { model?.nextBar() }.keyboardShortcut(key(.rightArrow))
                Divider()
                Button("Loop this bar") { model?.toggleLoopCurrentBar() }.keyboardShortcut(key("l"))
                Button("Slower") { model?.changeSpeed(by: -5) }.keyboardShortcut(key(","))
                Button("Faster") { model?.changeSpeed(by: 5) }.keyboardShortcut(key("."))
                Divider()
                Button("Count-in") { model?.countIn.toggle() }.keyboardShortcut(key("c"))
                Button("Metronome") { model?.metronome.toggle() }.keyboardShortcut(key("m"))
                Button("Mute my part") { model?.playAlong.toggle() }.keyboardShortcut(key("a"))
                Button("Band or recording") { model?.hearOriginal.toggle() }.keyboardShortcut(key("o"))
            }
            .disabled(model == nil)
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

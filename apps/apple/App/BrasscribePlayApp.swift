import Network
import PlaybackKit
import ScoreKit
import SwiftUI
import TranscriptionKit

struct BrasscribePlayApp: App {
    @State private var app = AppModel()
    #if os(macOS)
    @NSApplicationDelegateAdaptor(MacLaunch.self) private var launch
    #else
    @UIApplicationDelegateAdaptor(OrientationLock.self) private var orientation
    #endif

    init() {
        // the in-process audio units, registered once on the main thread before any score opens
        PlaybackEngine.prepare()
        let args = ProcessInfo.processInfo.arguments
        if args.contains("-reset") {
            try? FileManager.default.removeItem(at: Piece.libraryURL)
        }
        if args.contains("-skip-first-run") { UserDefaults.standard.set(true, forKey: "firstRunDone") }
        // the palette before the first frame, so Pink never flashes the standard colours
        BrasscribePalette.shared.isPink = AppearanceSetting.isPink(stored: UserDefaults.standard.string(forKey: AppearanceSetting.key))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(app)
                .appAppearance()
                .onOpenURL { url in
                    if url.scheme?.lowercased() == "brasscribe" {
                        if let link = PairingLink(url: url) { app.openPairingLink(link) }
                    } else {
                        Task { await app.accept(url: url) }
                    }
                }
        }
        #if os(macOS)
        .defaultSize(WindowFit.defaultSize(visible: NSScreen.main?.visibleFrame ?? CGRect(x: 0, y: 0, width: 1440, height: 900)))
        // always open a fresh window; a restored "no windows" state left the UI tests with none
        .restorationBehavior(.disabled)
        .commands { PlaybackCommands() }
        #endif

    }
}

/// Settings → Appearance: match the system (the default), or always light or dark. Stored per
/// device. Increase Contrast still applies on top of either. Pink light and Pink dark (design/system.md
/// §10) are hidden until Pink is unlocked from About; they are Light and Dark with the Pink palette.
enum AppearanceSetting: String, CaseIterable, Identifiable {
    case system, light, dark
    case pinkLight = "pink-light"
    case pinkDark = "pink-dark"
    static let key = "appearance"
    /// The one Pink choice of earlier versions, which followed the system's light or dark.
    static let legacyPink = "pink"
    var id: String { rawValue }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light, .pinkLight: .light
        case .dark, .pinkDark: .dark
        }
    }

    var isPink: Bool { self == .pinkLight || self == .pinkDark }

    var title: String {
        switch self {
        case .system: String(localized: "Match system")
        case .light: String(localized: "Light")
        case .dark: String(localized: "Dark")
        case .pinkLight: String(localized: "Pink light")
        case .pinkDark: String(localized: "Pink dark")
        }
    }

    /// The options the picker lists: Pink light and Pink dark only once Pink is unlocked.
    static func options(pinkUnlocked: Bool) -> [AppearanceSetting] {
        pinkUnlocked ? allCases : allCases.filter { !$0.isPink }
    }

    /// The scheme to apply: a test's `-appearance` wins, then the setting.
    static func scheme(stored: String) -> ColorScheme? {
        if let forced = LaunchOptions.appearance { return forced.scheme }
        return (AppearanceSetting(rawValue: stored) ?? .system).colorScheme
    }

    /// Whether the Pink palette applies: a test's `-appearance` wins, then the setting.
    static func isPink(stored: String?) -> Bool {
        if let forced = LaunchOptions.appearance { return forced.pink }
        return storedIsPink(stored)
    }

    /// Whether a stored value is a Pink choice, the earlier single "pink" included.
    static func storedIsPink(_ stored: String?) -> Bool {
        stored == legacyPink || stored.flatMap(AppearanceSetting.init(rawValue:))?.isPink == true
    }

    /// What an earlier version's "pink" becomes: Pink dark while the system is dark, else Pink light;
    /// nil for every other value. An earlier version reads the new values as Match system.
    static func migrated(stored: String?, systemDark: Bool?) -> String? {
        guard stored == legacyPink else { return nil }
        return (systemDark == true ? AppearanceSetting.pinkDark : .pinkLight).rawValue
    }
}

/// Unlocking Pink from About. The flag is kept on this device next to `appearance`; a stored Pink
/// choice counts as unlocked, so the choice is never left without its option.
enum PinkUnlock {
    static let key = "pinkUnlocked"

    static func isUnlocked(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: key) || AppearanceSetting.storedIsPink(defaults.string(forKey: AppearanceSetting.key))
    }

    static func unlock(_ defaults: UserDefaults = .standard) { defaults.set(true, forKey: key) }
}

/// Counts activations of the version in About: five in a row, each within `window` seconds of the
/// one before, unlock Pink. A longer pause starts the count again. Once unlocked it stays unlocked
/// and never reports the unlock a second time.
struct UnlockCounter {
    var threshold = 5
    var window: TimeInterval = 1.5
    private(set) var count = 0
    private(set) var unlocked: Bool
    private var last: Date?

    init(unlocked: Bool = false) { self.unlocked = unlocked }

    /// Records one activation at `now`; true only for the one that unlocks.
    mutating func activate(at now: Date = Date()) -> Bool {
        guard !unlocked else { return false }
        if let last, now.timeIntervalSince(last) > window { count = 0 }
        last = now
        count += 1
        guard count >= threshold else { return false }
        unlocked = true
        return true
    }

    /// Unlocks at once (Option-click on the Mac); true only when that is new.
    mutating func unlockNow() -> Bool {
        guard !unlocked else { return false }
        unlocked = true
        return true
    }
}

/// Applies the Appearance setting to a window or a sheet; it changes at once when the setting does.
/// The tint is set here too, so it follows the palette. An earlier version's "pink" follows the
/// system until it is shown, then becomes Pink light or Pink dark to match it.
struct AppAppearance: ViewModifier {
    @AppStorage(AppearanceSetting.key) private var stored = AppearanceSetting.system.rawValue
    @Environment(\.colorScheme) private var systemScheme
    func body(content: Content) -> some View {
        content
            .tint(Color.Scribe.primary)
            .preferredColorScheme(AppearanceSetting.scheme(stored: stored))
            .onChange(of: stored, initial: true) { _, value in
                // the old "pink" asks for no scheme, so the one seen here is still the system's
                if let migrated = AppearanceSetting.migrated(stored: value, systemDark: systemScheme == .dark) {
                    PinkUnlock.unlock()
                    stored = migrated
                    return
                }
                let pink = AppearanceSetting.isPink(stored: value)
                if BrasscribePalette.shared.isPink != pink { BrasscribePalette.shared.isPink = pink }
            }
    }
}

extension View {
    func appAppearance() -> some View { modifier(AppAppearance()) }
}

/// Launch arguments for tests and screenshots.
enum LaunchOptions {
    static let args = ProcessInfo.processInfo.arguments

    /// `-appearance light|dark|pink-light|pink-dark`: the scheme, and whether the Pink palette applies.
    static var appearance: (scheme: ColorScheme, pink: Bool)? {
        guard let i = args.firstIndex(of: "-appearance"), i + 1 < args.count else { return nil }
        return parseAppearance(args[i + 1])
    }

    static func parseAppearance(_ value: String) -> (scheme: ColorScheme, pink: Bool) {
        switch value {
        case "dark": (.dark, false)
        case "pink-light", "pink": (.light, true)
        case "pink-dark": (.dark, true)
        default: (.light, false)
        }
    }

    /// The scheme a test's `-appearance` forces, if any.
    static var colorScheme: ColorScheme? { appearance?.scheme }

    /// `-screen home|source|transcribing|review|review-listening|score|part|export|first-run|error`
    static var screen: String? {
        guard let i = args.firstIndex(of: "-screen"), i + 1 < args.count else { return nil }
        return args[i + 1]
    }

    /// `-stand-bars N`: a fixed number of bars per system on the music stand (UI tests use 1 to get pages).
    static var standBars: Int? {
        guard let i = args.firstIndex(of: "-stand-bars"), i + 1 < args.count else { return nil }
        return Int(args[i + 1])
    }

    /// `-stand-assistive`: behave as if a screen reader were running (the stand controls stay).
    static var standAssistive: Bool { args.contains("-stand-assistive") }

    /// `-stand-ignore-keyboard`: a simulator's hardware keyboard does not keep the stand controls (the auto-hide test).
    static var standIgnoreKeyboard: Bool { args.contains("-stand-ignore-keyboard") }

    /// `-connection connected|reconnecting|offline|needs-pairing`: show that connection state without
    /// talking to a computer (screenshots and UI tests).
    static var connection: ConnectionState? {
        guard let i = args.firstIndex(of: "-connection"), i + 1 < args.count else { return nil }
        let name = "Brasscribe on Studio Mac"
        switch args[i + 1] {
        case "connected": return .connected(serverName: name)
        case "reconnecting": return .reconnecting(serverName: name)
        case "needs-pairing": return .needsPairing(serverName: name)
        case "offline": return .offline
        default: return nil
        }
    }
}

/// Keeps the heartbeat to the computer running while the app is in front, and checks at once when the
/// network changes.
struct ConnectionLifecycle: ViewModifier {
    @Environment(AppModel.self) private var app
    @Environment(\.scenePhase) private var phase
    @State private var path = NetworkPathWatcher()

    func body(content: Content) -> some View {
        content
            .announcesConnectionChanges(app.connection)
            .onChange(of: phase, initial: true) { _, p in
                if let staged = LaunchOptions.connection {
                    guard !app.connection.staged else { return }
                    let record = staged == .offline ? nil
                        : EngineRecord(serverID: "7f3a9c2e", serverName: "Brasscribe on Studio Mac", deviceID: "d-41b2", token: "staged",
                                       lastAddress: "http://192.0.2.20:8765", lastOK: Date().addingTimeInterval(-12))
                    app.connection.stage(staged, record: record)
                    return
                }
                switch p {
                case .active: app.connection.resume()
                case .background: app.connection.suspend()
                default: break
                }
            }
            .onChange(of: path.generation) { _, _ in app.connection.poke() }
            .task { path.start() }
    }
}

/// Counts network path changes (Wi-Fi joined, lost, switched).
@MainActor @Observable
final class NetworkPathWatcher {
    private(set) var generation = 0
    @ObservationIgnored private var monitor: NWPathMonitor?
    @ObservationIgnored private var updates = 0

    func start() {
        guard monitor == nil else { return }
        let m = NWPathMonitor()
        m.pathUpdateHandler = { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                // the first update only reports the current path
                self.updates += 1
                if self.updates > 1 { self.generation += 1 }
            }
        }
        m.start(queue: .main)
        monitor = m
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    @State private var columns: NavigationSplitViewVisibility = .all

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
                LibrarySplit(columns: $columns) { flow }
                #if os(iOS)
                // on iPad the library steps aside while a score is open; the sidebar button brings it back
                .onChange(of: app.path.isEmpty) { _, home in columns = home ? .all : .detailOnly }
                // the music stand has the whole window
                .onChange(of: app.standOpen) { _, open in columns = open || !app.path.isEmpty ? .detailOnly : .all }
                #endif
            } else {
                flow
            }
        }
        #if os(iOS)
        // the music stand hides the status bar and the home indicator for the whole scene (a split view on iPad)
        .statusBarHidden(app.standOpen)
        .persistentSystemOverlays(app.standOpen ? .hidden : .automatic)
        #endif
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(verbatim: "Brasscribe Play"))
        .modifier(ConnectionLifecycle())
        .scoreOptionDialogs()
        .sheet(isPresented: $app.showRecorder) { MicRecordView().appAppearance() }
        .sheet(isPresented: $app.showSettings) { SettingsView().appAppearance() }
        #if os(macOS)
        .sheet(isPresented: $app.showCapture) { CaptureView().appAppearance() }
        #endif
        .sheet(isPresented: $app.showFirstRun) { FirstRunView().appAppearance() }
        .task {
            // after the split view's navigation stack is in place, or the first path is dropped
            try? await Task.sleep(for: .milliseconds(100))
            if !UserDefaults.standard.bool(forKey: "firstRunDone") || LaunchOptions.screen == "first-run"
                || LaunchOptions.screen?.hasPrefix("what-do-you-play") == true { app.showFirstRun = true }
            if LaunchOptions.args.contains("-open-fixture-score") { openFixtureScore() }
            // UI tests: start from a recording as if it had just been imported
            if let a = ProcessInfo.processInfo.environment["BRASSCRIBE_OPEN_AUDIO"], FileManager.default.fileExists(atPath: a) {
                app.acceptRecording(URL(fileURLWithPath: a), title: URL(fileURLWithPath: a).deletingPathExtension().lastPathComponent)
            }
            if let s = LaunchOptions.screen { ScreenshotScenes.open(s, app: app, openScore: openFixtureScore) }
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
                    case .output(let p): OutputView(piece: p)
                    case .score(let p): ScoreScreen(piece: p)
                    case .problem(let p): ProblemView(problem: p)
                    }
                }
        }
    }

    /// UI tests and screenshots: import the fixture straight into a piece and open it.
    @discardableResult
    private func openFixtureScore() -> Piece? {
        guard let dir = app.fixtureDirectory else { FileHandle.standardError.write(Data("open-fixture-score: no fixture directory\n".utf8)); return nil }
        do {
            let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
            let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
            let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
            let p = try Piece.create(title: comp?.title ?? dir.lastPathComponent, profile: .brassBand, result: result, original: app.originalForFixture,
                                     video: app.videoForFixture, fixtureDirectory: dir)
            app.refresh()
            app.path = [.score(p)]
            return p
        } catch {
            FileHandle.standardError.write(Data("open-fixture-score: \(error)\n".utf8))
            return nil
        }
    }
}

/// iPad and Mac sidebar: the lockup, "Open a recording" and the scores. Plain buttons, not
/// a selection list: a sidebar selection resets the detail column's navigation stack.
struct LibrarySidebar: View {
    @Environment(AppModel.self) private var app

    private var openPiece: UUID? {
        for r in app.path.reversed() {
            switch r {
            case .score(let p), .review(let p), .output(let p): return p.id
            default: continue
            }
        }
        return nil
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s1) {
                Lockup().padding(.horizontal, Space.s3).padding(.bottom, Space.s4)
                row(title: String(localized: "Open a recording"), icon: BrasscribeIcon.importFile.systemName,
                    selected: app.path.isEmpty) { app.goHome() }
                    .accessibilityIdentifier("sidebarHome")
                SectionLabel(String(localized: "Your scores"))
                    .padding(.horizontal, Space.s3).padding(.top, Space.s5).padding(.bottom, Space.s1)
                if app.scores.isEmpty {
                    Text("Your scores appear here.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                        .padding(.horizontal, Space.s3)
                }
                ForEach(app.scores) { entry in
                    HStack(spacing: Space.s1) {
                        row(title: entry.title, icon: entry.piece == nil ? BrasscribeIcon.computer.systemName : BrasscribeIcon.score.systemName,
                            selected: entry.piece?.id == openPiece && openPiece != nil) { app.open(entry) }
                            .scoreRowFocus(entry.id)
                            .accessibilityIdentifier("sidebar-\(entry.title)")
                        if app.openingScore == entry.id { ProgressView().controlSize(.small) }
                        ScoreOptionsMenu(entry: entry)
                    }
                    // the identifiers sit on the row and on its menu: one here would override both
                    .contextMenu { ScoreOptionItems(entry: entry) }
                }
            }
            .padding(Space.s3)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Color.Scribe.surface)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Library"))
        .task { await app.refreshComputerScores() }
        .navigationTitle(Text(verbatim: "Brasscribe Play"))
        #if os(macOS)
        .toolbar(removing: .title)
        #endif
    }

    private func row(title: String, icon: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(selected ? Font.Scribe.headline : Font.Scribe.body)
                .foregroundStyle(Color.Scribe.text)
                .padding(.horizontal, Space.s3)
                .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                .background(selected ? Color.Scribe.surfaceRaised : Color.clear, in: RoundedRectangle(cornerRadius: Radius.sm))
                .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(selected ? Color.Scribe.border : Color.clear))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
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
                // in the music stand the arrows turn pages (menu shortcuts fire before the view's keys)
                Button("Previous bar") { model?.previousBarOrPage() }.keyboardShortcut(key(.leftArrow))
                Button("Next bar") { model?.nextBarOrPage() }.keyboardShortcut(key(.rightArrow))
                Divider()
                Button("Loop this bar") { model?.toggleLoopCurrentBar() }.keyboardShortcut(key("l"))
                Button("Slower") { model?.changeSpeed(by: -5) }.keyboardShortcut(key(","))
                Button("Faster") { model?.changeSpeed(by: 5) }.keyboardShortcut(key("."))
                Divider()
                Button("Count-in") { model?.countIn.toggle() }.keyboardShortcut(key("c"))
                Button("Metronome") { model?.metronome.toggle() }.keyboardShortcut(key("m"))
                Button("Mute my part") { model?.playAlong.toggle() }.keyboardShortcut(key("a")).disabled(model?.myPart == nil)
                Button("Band or recording") { model?.hearOriginal.toggle() }.keyboardShortcut(key("o"))
            }
            .disabled(model == nil)
        }
        // View › Music Stand (F). The green button and ⌃⌘F stay the window's own full screen.
        CommandGroup(before: .toolbar) {
            Button("Music Stand") { model?.toggleStand() }
                .keyboardShortcut(key("f"))
                .disabled(model == nil)
            Divider()
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
    private var placed: NSObjectProtocol?
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
        // UI tests (-ui-test-window): a fixed frame inside the main screen's visible area, clear of
        // the Dock and the menu bar, so a click never lands outside the app.
        if ProcessInfo.processInfo.arguments.contains("-ui-test-window") {
            placed = NotificationCenter.default.addObserver(forName: NSWindow.didBecomeMainNotification, object: nil, queue: .main) { n in
                guard let w = n.object as? NSWindow, let screen = NSScreen.main ?? NSScreen.screens.first else { return }
                MainActor.assumeIsolated { WindowMinimum.keep(w) }
                if w.styleMask.contains(.fullScreen) { w.toggleFullScreen(nil) }
                let v = screen.visibleFrame.insetBy(dx: 20, dy: 20)
                let size = CGSize(width: min(1200, v.width), height: min(820, v.height))
                let frame = CGRect(x: v.midX - size.width / 2, y: v.midY - size.height / 2, width: size.width, height: size.height)
                if w.frame != frame { w.setFrame(frame, display: true) }
            }
        } else {
            // Every window stays whole on its own screen, clear of the Dock and the menu bar: when it
            // first shows or is restored (a frame saved on a larger display), and when it moves to
            // another screen.
            // After a zoom or a live resize ends, a window that reaches under the Dock is pulled back.
            for name in [NSWindow.didBecomeMainNotification, NSWindow.didChangeScreenNotification,
                         NSWindow.didEndLiveResizeNotification, NSWindow.didResizeNotification] {
                fitting.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { n in
                    guard let w = n.object as? NSWindow else { return }
                    // while the pointer drags an edge the window follows it; it is fitted when the drag ends
                    if n.name == NSWindow.didResizeNotification, w.inLiveResize { return }
                    MainActor.assumeIsolated {
                        WindowMinimum.keep(w)
                        ZoomToVisibleFrame.install(on: w)
                        Self.fit(w)
                    }
                })
            }
        }
    }

    private var fitting: [NSObjectProtocol] = []

    @MainActor static func fit(_ w: NSWindow) {
        guard w.canBecomeMain, !w.styleMask.contains(.fullScreen), let screen = w.screen ?? NSScreen.main else { return }
        // the one minimum of the main window, whichever screen it shows
        if w.minSize.width < WindowFit.minimumWindow.width || w.minSize.height < WindowFit.minimumWindow.height {
            w.minSize = WindowFit.minimumWindow
        }
        let f = WindowFit.clamp(w.frame, into: screen.visibleFrame, minSize: minFrameSize(w))
        if f != w.frame { w.setFrame(f, display: true, animate: false) }
    }

    /// The window's minimum (`WindowFit.minimumWindow`), or its content's when that is larger, as a frame size.
    @MainActor static func minFrameSize(_ w: NSWindow) -> CGSize {
        let content = w.frameRect(forContentRect: CGRect(origin: .zero, size: w.contentMinSize)).size
        return CGSize(width: max(w.minSize.width, content.width), height: max(w.minSize.height, content.height))
    }
}

/// Zoom fills the window's own screen's visible frame, not the whole screen under the Dock. It sits
/// in front of SwiftUI's own window delegate and passes every other message on to it.
final class ZoomToVisibleFrame: NSObject, NSWindowDelegate {
    private weak var inner: NSWindowDelegate?
    @MainActor private static var proxies: [ObjectIdentifier: ZoomToVisibleFrame] = [:]

    private init(inner: NSWindowDelegate?) { self.inner = inner }

    @MainActor static func install(on w: NSWindow) {
        guard w.canBecomeMain, !(w.delegate is ZoomToVisibleFrame) else { return }
        let proxy = ZoomToVisibleFrame(inner: w.delegate)
        proxies[ObjectIdentifier(w)] = proxy
        w.delegate = proxy
        // closed windows let their proxies go
        proxies = proxies.filter { key, _ in NSApp.windows.contains { ObjectIdentifier($0) == key } }
        proxies[ObjectIdentifier(w)] = proxy
    }

    func windowWillUseStandardFrame(_ window: NSWindow, defaultFrame newFrame: NSRect) -> NSRect {
        let own = inner?.windowWillUseStandardFrame?(window, defaultFrame: newFrame) ?? newFrame
        guard let screen = window.screen ?? NSScreen.main else { return own }
        let fitted = MainActor.assumeIsolated {
            WindowFit.standardFrame(visible: screen.visibleFrame, minSize: MacLaunch.minFrameSize(window))
        }
        return WindowFit.overflows(own, screen.visibleFrame) ? fitted : own
    }

    // everything else goes to SwiftUI's delegate
    override func responds(to aSelector: Selector!) -> Bool {
        super.responds(to: aSelector) || (inner?.responds(to: aSelector) ?? false)
    }

    override func forwardingTarget(for aSelector: Selector!) -> Any? {
        if let inner, inner.responds(to: aSelector) { return inner }
        return super.forwardingTarget(for: aSelector)
    }
}
#endif

import AppKit
import BandroomKit
import SwiftUI
import UserNotifications

/// The app; `AppEntry` starts it.
struct BandroomApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @AppStorage("textSize") private var textSize: TextSize = .standard

    var body: some Scene {
        let app = delegate.model
        MenuBarExtra {
            PanelRoot(isMenuBar: true)
                .environment(app)
                .environment(\.textScale, textSize.scale)
        } label: {
            MenuBarLabel().environment(app)
        }
        .menuBarExtraStyle(.window)

        // The same content as a normal window, for when the menu-bar icon is hidden (§3.3).
        Window(Text("Brasscribe on this Mac"), id: "main") {
            PanelRoot(isMenuBar: false)
                .background(Color.Scribe.bg)
                .environment(app)
                .environment(\.textScale, textSize.scale)
        }
        .windowResizability(.contentSize)
        .defaultPosition(.topTrailing)

        Window(Text("Pair a phone"), id: "pair") {
            PairWindow()
                .environment(app)
                .environment(\.textScale, textSize.scale)
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)

        Window(Text("Set up Brasscribe"), id: "setup") {
            SetupView()
                .environment(app)
                .environment(\.textScale, textSize.scale)
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)

        Settings {
            SettingsView()
                .environment(app)
        }
    }
}

/// The panel, with the hooks it needs: window opening, and "is it open" for the polling cadence.
struct PanelRoot: View {
    @Environment(AppModel.self) private var app
    @Environment(\.openWindow) private var openWindow
    let isMenuBar: Bool
    @State private var contentHeight: CGFloat = 400

    var body: some View {
        // Width fixed at 360, height to fit; past 80 % of the screen height it scrolls (§4).
        let maxHeight = (NSScreen.main?.visibleFrame.height ?? 900) * 0.8
        ScrollView {
            VStack(spacing: 0) {
                if !isMenuBar && app.showHiddenIconNotice {
                    HiddenIconNotice().padding([.horizontal, .top], 14)
                }
                StatusPanel()
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
        }
            .scrollBounceBehavior(.basedOnSize)
            .frame(width: 360, height: min(contentHeight, maxHeight))
            .background(Color.Scribe.bg)
            .background(WindowKeyObserver { key in
                if app.monitor.isPanelOpen != key { app.log("panel \(isMenuBar ? "popover" : "window") \(key ? "open: polling every 5 s" : "closed: polling every 30 s")") }
                app.monitor.isPanelOpen = key
                if !key && isMenuBar { app.panelPage = .status }
            })
            .onAppear { app.opener.attach { openWindow(id: $0) } }
    }
}

/// Shown once in the "Brasscribe on this Mac" window when the menu-bar mark looks hidden (§3.3).
struct HiddenIconNotice: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "menubar.rectangle").font(.system(size: 16)).foregroundStyle(Color.Scribe.textMuted)
                    .accessibilityHidden(true)
                Text("The Brasscribe mark may be hidden behind the camera notch. Open Brasscribe from Launchpad any time, or make room in System Settings › Menu Bar.")
                    .brFont(.callout).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                Button { app.openMenuBarSettings() } label: { Text("Open Menu Bar settings") }.buttonStyle(.brOutline)
                if !app.showInDock {
                    Button { app.showInDock = true } label: { Text("Show in the Dock") }.buttonStyle(.brOutline)
                }
                Spacer(minLength: 0)
                Button { app.hiddenIconNoticeDismissed = true } label: { Text("Got it") }.buttonStyle(.brPlain)
            }
        }
        .card(padding: 12)
        .accessibilityElement(children: .contain)
    }
}

struct MenuBarLabel: View {
    @Environment(AppModel.self) private var app
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let state = app.displayState
        let tooltip = Strings.tooltip(state, connected: app.monitor.status?.onlineDevices ?? 0)
        Image(nsImage: .menuBarIcon(badge: badge(state)))
            .accessibilityLabel(Text(tooltip))
            .help(Text(tooltip))
            .task {
                app.opener.attach { openWindow(id: $0) }
                if ProcessInfo.processInfo.environment["BANDROOM_OPEN"] != nil {
                    for id in ProcessInfo.processInfo.environment["BANDROOM_OPEN"]!.split(separator: ",") {
                        openWindow(id: String(id))
                    }
                    NSApp.activate()
                }
            }
    }

    private func badge(_ s: DisplayState) -> MenuBadge {
        switch s {
        case .running: .none
        case .busy(let n): .pie(step: DisplayState.pieStep(percent: n))
        case .attention: .triangle
        case .stopped: .square
        case .starting: .dots
        case .updating: .circularArrow
        case .error: .crossCircle
        case .settingUp: .downArrow
        }
    }
}

/// Reports whether the hosting window is key: the menu-bar panel is open while its window is key.
struct WindowKeyObserver: NSViewRepresentable {
    let onChange: (Bool) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = ObserverView()
        view.onChange = onChange
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? ObserverView)?.onChange = onChange
    }

    final class ObserverView: NSView {
        var onChange: ((Bool) -> Void)?
        private var tokens: [NSObjectProtocol] = []

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            tokens.forEach(NotificationCenter.default.removeObserver)
            tokens = []
            guard let window else { return }
            let center = NotificationCenter.default
            for (name, key) in [(NSWindow.didBecomeKeyNotification, true), (NSWindow.didResignKeyNotification, false),
                                (NSWindow.willCloseNotification, false)] {
                tokens.append(center.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { self?.onChange?(key) }
                })
            }
            onChange?(window.isKeyWindow)
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    let model = AppModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Settings › Appearance, before any window shows (BANDROOM_APPEARANCE still wins, for screenshots).
        AppearanceChoice.current().apply()
        model.applyDockPolicy()
        model.launch()
        Notifier.setUp(delegate: self)
    }

    /// Opening the app again from Finder, Launchpad, Spotlight or the Dock shows the panel as a window (§3.3),
    /// or the setup window while the first run isn't finished. Always, even when another window is open: the
    /// menu-bar mark may be hidden behind the notch.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        model.log("reopened from Finder, Launchpad or the Dock")
        model.reopen()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.quit()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async
        -> UNNotificationPresentationOptions { [.banner, .sound] }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let info = response.notification.request.content.userInfo
        let action = response.actionIdentifier
        guard let id = info["request_id"] as? String else { return }
        let request = PairRequestInfo(requestId: id, name: info["name"] as? String ?? "", platform: info["platform"] as? String ?? "",
                                      matchCode: info["match_code"] as? String ?? "", createdAt: "")
        await MainActor.run {
            switch action {
            case "allow": Task { _ = await self.model.decide(request, approve: true) }
            case "deny": Task { _ = await self.model.decide(request, approve: false) }
            default: self.model.openWindow("pair")
            }
        }
    }
}

/// Reads the status item's window: SwiftUI's MenuBarExtra doesn't hand out its NSStatusItem, but its button
/// lives in an NSStatusBarWindow of this app.
@MainActor
enum MenuBarReader {
    static func read() -> StatusItemVisibility.Reading {
        let window = NSApp.windows.first { String(describing: type(of: $0)).contains("StatusBarWindow") }
        let screens = NSScreen.screens
        let notches: [CGRect] = screens.compactMap { s in
            guard let left = s.auxiliaryTopLeftArea, let right = s.auxiliaryTopRightArea, right.minX > left.maxX else { return nil }
            return CGRect(x: left.maxX, y: min(left.minY, right.minY), width: right.minX - left.maxX,
                          height: max(left.height, right.height))
        }
        return StatusItemVisibility.Reading(frame: window?.frame, occlusionVisible: window?.occlusionState.contains(.visible) ?? false,
                                            screens: screens.map(\.frame), notches: notches)
    }
}

import AppKit
import BandroomKit
import SwiftUI
import UserNotifications

@main
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
            ScrollView { PanelRoot(isMenuBar: false) }
                .frame(minWidth: 360, idealWidth: 360, maxWidth: 480, minHeight: 300)
                .background(Color.Brasscribe.bg)
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

    var body: some View {
        StatusPanel()
            .frame(width: 360)
            .background(Color.Brasscribe.bg)
            .background(WindowKeyObserver { key in
                app.monitor.isPanelOpen = key
                if !key && isMenuBar { app.panelPage = .status }
            })
            .onAppear {
                app.openWindow = { id in
                    NSApp.activate()
                    openWindow(id: id)
                }
            }
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
                app.openWindow = { id in
                    NSApp.activate()
                    openWindow(id: id)
                }
                app.launch()
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
        switch ProcessInfo.processInfo.environment["BANDROOM_APPEARANCE"] {
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        default: break
        }
        Notifier.setUp(delegate: self)
    }

    /// Opening the app again from Launchpad or Spotlight shows the panel as a window (§3.3).
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        model.openWindow?("main")
        return true
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
            default: self.model.openWindow?("pair")
            }
        }
    }
}

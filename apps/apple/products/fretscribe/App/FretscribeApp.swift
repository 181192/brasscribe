import SwiftUI
import TranscriptionKit
#if os(macOS)
import AppKit
#endif

/// Starts the app, or on the Mac, when it hosts the unit tests, an app with no window: the screen catalogue renders
/// every screen off screen, and the Mac stays the user's.
@main
enum AppEntry {
    static func main() {
        #if os(macOS)
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil {
            UnitTestHost.main()
            return
        }
        #endif
        FretscribeApp.main()
    }
}

#if os(macOS)
/// No window, no Dock icon, never activated.
struct UnitTestHost: App {
    @NSApplicationDelegateAdaptor(UnitTestHostDelegate.self) private var delegate
    var body: some Scene { Settings { EmptyView() } }
}

final class UnitTestHostDelegate: NSObject, NSApplicationDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) { NSApp.setActivationPolicy(.accessory) }
}
#endif

/// The icons the shared Play screens draw: Fretscribe's.
typealias PlayIcon = FretscribeIcon

/// The other app of the family a pairing link may be meant for.
let siblingApps = [SiblingApp(name: "Brasscribe Play", scheme: "brasscribe")]

struct FretscribeApp: App {
    @State private var model = FretscribeModel()

    init() {
        if LaunchOptions.reset { try? FileManager.default.removeItem(at: TabSong.root) }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model).playHost(model)
                .preferredColorScheme(LaunchOptions.colorScheme)
                .pairingLinks(appName: "Fretscribe", ownScheme: "fretscribe", siblings: siblingApps) { link in
                    model.pendingLink = link
                    model.showSettings = true
                } other: { url in
                    Task { await model.accept(url: url) }
                }
        }
        #if os(macOS)
        .defaultSize(WindowFit.defaultSize(visible: NSScreen.main?.visibleFrame ?? CGRect(x: 0, y: 0, width: 1440, height: 900)))
        .restorationBehavior(.disabled)
        #endif
    }
}

import SwiftUI

/// Starts the app, or on the Mac, when it hosts the unit tests, an app with no window: the
/// layout tests render every screen off screen, and the Mac stays the user's.
@main
enum AppEntry {
    static func main() {
        #if os(macOS)
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil {
            UnitTestHost.main()
            return
        }
        #endif
        BrasscribePlayApp.main()
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

import AppKit
import SwiftUI

/// Starts the app, or, in a Debug build that hosts the unit tests (the screen catalogue, `Tests/`), a host
/// with no menu-bar item, no window and no engine of its own: the tests draw the views off screen, and the
/// Mac, its menu bar and an installed Bandroom's engine stay the user's.
@main
enum AppEntry {
    static func main() {
        #if DEBUG
        if TestHost.isHostingTests {
            TestHost.isolate()
            UnitTestHost.main()
            return
        }
        #endif
        BandroomApp.main()
    }
}

#if DEBUG
/// The test host: its own data and logs folders, canned engine answers (`DemoEngine`), never the user's
/// settings. `AppModel` refuses to start under the tests without all three, so a test can never reach the
/// installed Bandroom's engine (`launch()` stops a stray engine it finds in its data folder) or its settings.
enum TestHost {
    static var isHostingTests: Bool { ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil }

    /// The data and logs of the tests, under the temporary folder. The same folder every run: Settings shows it, and a
    /// screenshot must not change from one run to the next.
    static var root: URL {
        FileManager.default.temporaryDirectory.appending(path: "bandroom-tests", directoryHint: .isDirectory)
    }

    /// Before anything else runs: the environment `AppModel` reads.
    static func isolate() {
        setenv("BANDROOM_DEMO", "busy", 1)
        setenv("BRASSCRIBE_DATA", root.appending(path: "data").path, 1)
        setenv("BRASSCRIBE_LOGS", root.appending(path: "logs").path, 1)
        setenv("BANDROOM_NO_LOGIN_ITEM", "1", 1)
        for name in ["BRASSCRIBE_CHECKOUT", "HF_TOKEN", "BANDROOM_OPEN", "BANDROOM_APPEARANCE", "BANDROOM_DEMO_REQUEST"] { unsetenv(name) }
    }

    /// Stops the test run unless the model is isolated: demo engine, data and logs under `root`, settings not the app's.
    static func requireIsolated(environment: [String: String], data: URL, logs: URL, defaults: UserDefaults) {
        guard isHostingTests else { return }
        let inRoot = { (url: URL) in url.standardizedFileURL.path.hasPrefix(root.standardizedFileURL.path + "/") }
        guard environment["BANDROOM_DEMO"] != nil, inRoot(data), inRoot(logs), defaults !== UserDefaults.standard else {
            fatalError("Under the tests, AppModel needs BANDROOM_DEMO, data and logs under \(root.path) and a defaults store of "
                       + "its own (TestHost); otherwise it could stop the installed Bandroom's engine or change its settings.")
        }
    }
}

/// No window, no menu-bar item, no Dock icon, never activated.
struct UnitTestHost: App {
    @NSApplicationDelegateAdaptor(UnitTestHostDelegate.self) private var delegate
    var body: some Scene { Settings { EmptyView() } }
}

final class UnitTestHostDelegate: NSObject, NSApplicationDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) { NSApp.setActivationPolicy(.accessory) }
}
#endif

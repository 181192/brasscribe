import XCTest

#if os(macOS)
/// The Mac window of the website's screenshots: the full score of the fixture (the `score` scene),
/// light and dark, in English and Norwegian, attached to the result as macos[-nb]-score-<look>.png.
/// Only with BRASSCRIBE_SHOTS set (`MAC_VM_SHOTS=1 scripts/mac-vm.sh test-ui SiteScreenshotUITests`);
/// the files come back under build/mac-vm/<run>/…/attachments/.
final class SiteScreenshotUITests: XCTestCase {
    func testScoreWindow() throws {
        guard !(ProcessInfo.processInfo.environment["BRASSCRIBE_SHOTS"] ?? "").isEmpty else { throw XCTSkip("set BRASSCRIBE_SHOTS to take the site screenshots") }
        guard let dir = fixtureDir() else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
        let app = XCUIApplication()
        for nb in [false, true] {
            let lang = nb ? ["-AppleLanguages", "(nb)", "-AppleLocale", "nb_NO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_GB"]
            for look in ["light", "dark"] {
                app.terminate()
                app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-connection", "connected",
                                       "-screen", "score", "-appearance", look] + lang
                app.launchEnvironment["BRASSCRIBE_FIXTURES"] = dir
                app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"
                app.launchForUITest()
                XCTAssertTrue(app.descendants(matching: .any)["scoreArea"].firstMatch.waitForExistence(timeout: 60), "the score shows")
                // the pointer rests on the empty sidebar, so no help tag shows over the parts
                app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.6)).hover()
                sleep(6)
                let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
                shot.name = "macos\(nb ? "-nb" : "")-score-\(look)"
                shot.lifetime = .keepAlways
                add(shot)
            }
        }
    }
}
#endif

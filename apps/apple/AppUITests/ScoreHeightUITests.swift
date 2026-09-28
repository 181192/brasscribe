import XCTest

#if os(iOS)
/// On a phone the music keeps the screen: the score gets at least 55 % of the height inside the safe
/// area and at least two systems, at the default text size and at AX3, and no control sits over it.
final class ScoreHeightUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
        guard UIDevice.current.userInterfaceIdiom == .phone else { throw XCTSkip("the phone layout") }
        guard fixtureDir() != nil else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
    }

    func testScoreKeepsItsShareAtTheDefaultSize() throws { try check(textSize: nil) }

    func testScoreKeepsItsShareAtAX3() throws { try check(textSize: "UICTContentSizeCategoryAccessibilityXXXL") }

    private func check(textSize: String?) throws {
        let app = XCUIApplication()
        app.launchArguments = ["-reset", "-open-fixture-score", "-skip-first-run", "-seat", "1st-baritone"]
        if let textSize { app.launchArguments += ["-UIPreferredContentSizeCategoryName", textSize] }
        app.launchEnvironment["BRASSCRIBE_FIXTURES"] = fixtureDir()
        app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"
        app.launch()

        let screen = app.descendants(matching: .any)["practiceScreen"].firstMatch
        let score = app.descendants(matching: .any)["scoreArea"].firstMatch
        XCTAssertTrue(score.waitForExistence(timeout: 60))
        let staves = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-'"))
        XCTAssertTrue(staves.firstMatch.waitForExistence(timeout: 60))

        // the safe area: from the top of the navigation bar to the bottom of the practice screen
        let nav = app.navigationBars.firstMatch.frame
        let safeTop = nav.isEmpty ? screen.frame.minY : nav.minY
        // a Face ID iPhone keeps 34 pt at the bottom for the home indicator
        let window0 = app.windows.firstMatch.frame
        let safeBottom = screen.frame.maxY >= window0.maxY - 1 ? window0.maxY - 34 : screen.frame.maxY
        let safe = safeBottom - safeTop
        // the score's scroll view runs under the player; what shows ends where the player starts
        let player = app.descendants(matching: .any)["playerArea"].firstMatch.frame
        var area = score.frame
        if !player.isEmpty, player.minY < area.maxY { area.size.height = player.minY - area.minY }
        XCTAssertGreaterThanOrEqual(area.height, 0.55 * safe, "the score keeps 55 % of \(safe) pt, has \(area.height)")

        // at least two systems in sight: staff rows at two heights inside the score
        let rows = Set(staves.allElementsBoundByIndex.map(\.frame).filter { area.contains(CGPoint(x: $0.midX, y: $0.midY)) }.map { Int($0.minY / 20) })
        XCTAssertGreaterThanOrEqual(rows.count, 2, "two systems show")

        // the controls stay off the music and inside the window
        let window = app.windows.firstMatch.frame
        for id in ["partPicker", "viewMenu", "playPause", "speedMenu", "loopToggle", "muteMyPart", "practiceMenu"] {
            let e = app.descendants(matching: .any)[id].firstMatch
            guard e.exists, !e.frame.isEmpty else { continue }
            XCTAssertFalse(e.frame.intersection(area).height > 1, "\(id) sits over the score")
            XCTAssertTrue(window.contains(e.frame) || !window.intersects(e.frame), "\(id) is cut by the screen's edge")
            if !player.isEmpty, player.intersects(e.frame) {
                XCTAssertTrue(player.contains(e.frame), "\(id) is cut by the player's edge")
            }
        }
    }
}
#endif

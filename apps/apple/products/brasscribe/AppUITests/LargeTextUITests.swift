import XCTest

#if os(iOS)
/// On a phone with larger text (XXL and XXXL, below the accessibility sizes) the buttons keep their words on one
/// line and Listen is in view above Finish later, Keep and Skip: Check the notes and Share or print, in English and
/// bokmål. Run on the newest iPhone and on an iPhone SE, the shortest screen (`make test-iphone-small`). The score
/// at XXL is in `ScoreHeightUITests`.
final class LargeTextUITests: XCTestCase {
    private let xxl = "UICTContentSizeCategoryXXL"
    private let xxxl = "UICTContentSizeCategoryXXXL"

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard UIDevice.current.userInterfaceIdiom == .phone else { throw XCTSkip("the phone layout") }
        guard fixtureDir() != nil else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
    }

    /// The screen as the test ends, kept with the results.
    private func picture(_ app: XCUIApplication, _ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }

    private func launch(_ screen: String, textSize: String, nb: Bool) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-reset", "-fixture-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run",
                               "-screen", screen, "-UIPreferredContentSizeCategoryName", textSize]
            + (nb ? ["-AppleLanguages", "(nb)", "-AppleLocale", "nb_NO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_GB"])
        app.launchEnvironment["SCRIBE_FIXTURES"] = fixtureDir()
        app.launchEnvironment["SCRIBE_COMPANION"] = "http://127.0.0.1:1"
        app.launch()
        return app
    }

    /// One line of words: about as high as a button beside it whose words are on one line (the button styles'
    /// padding differs by a few points), its icon in the middle of its height (a label puts its icon by the first
    /// line, so with two the icon sits high, also where the words run out of a button that does not grow), and
    /// inside the window.
    private func oneLine(_ e: XCUIElement, like reference: XCUIElement, in app: XCUIApplication, _ what: String) {
        XCTAssertTrue(e.exists, "\(what) is there")
        XCTAssertLessThanOrEqual(e.frame.height, reference.frame.height + 8, "\(what) has its words on one line (\(e.frame.height) pt high)")
        let icon = e.images.firstMatch.frame
        XCTAssertFalse(icon.isEmpty, "\(what) has its icon")
        XCTAssertEqual(icon.midY, e.frame.midY, accuracy: 2, "\(what) has its words on one line (its icon is by the first of more)")
        XCTAssertTrue(app.windows.firstMatch.frame.contains(e.frame), "\(what) is inside the window")
    }

    // MARK: Check the notes

    func testCheckTheNotesAtXXL() throws { try checkTheNotes(textSize: xxl, nb: false) }
    func testCheckTheNotesAtXXLInBokmal() throws { try checkTheNotes(textSize: xxl, nb: true) }
    func testCheckTheNotesAtXXXLInBokmal() throws { try checkTheNotes(textSize: xxxl, nb: true) }

    private func checkTheNotes(textSize: String, nb: Bool) throws {
        let app = launch("review", textSize: textSize, nb: nb)
        let listen = app.buttons["listenBar"].firstMatch
        XCTAssertTrue(listen.waitForExistence(timeout: 60))
        let keep = app.buttons["keepNext"].firstMatch
        let skip = app.buttons["skipNote"].firstMatch
        let later = app.buttons["openScore"].firstMatch
        XCTAssertTrue(keep.waitForExistence(timeout: 10))
        picture(app, "review-\(textSize)-\(nb ? "nb" : "en")")
        // As the page opens, Listen is whole and in view, above Finish later, Keep and Skip: pinned at the bottom
        // where they leave room for it, or after it on the page (a short phone).
        let window = app.windows.firstMatch.frame
        XCTAssertTrue(window.contains(listen.frame), "Listen is in view (\(listen.frame) in \(window))")
        XCTAssertTrue(listen.isHittable, "Listen can be tapped")
        let band = min(later.frame.minY, keep.frame.minY, skip.frame.minY)
        XCTAssertLessThanOrEqual(listen.frame.maxY, band + 1, "Listen is above Finish later, Keep and Skip")
        // Finish later, Keep and Skip are in view, or a scroll away.
        for _ in 0..<6 where ![later, keep, skip].allSatisfy({ window.contains($0.frame) && $0.isHittable }) {
            app.swipeUp()
        }
        for (e, what) in [(later, "Finish later"), (keep, "Keep"), (skip, "Skip")] {
            XCTAssertTrue(e.isHittable, "\(what) can be reached")
        }
        oneLine(keep, like: listen, in: app, "Keep")
        oneLine(skip, like: listen, in: app, "Skip")
        XCTAssertFalse(keep.frame.intersects(skip.frame), "Keep and Skip do not overlap")
        picture(app, "review-\(textSize)-\(nb ? "nb" : "en")-buttons")
    }

    // MARK: Share or print

    func testShareOrPrintAtXXL() throws { try shareOrPrint(nb: false) }
    func testShareOrPrintAtXXLInBokmal() throws { try shareOrPrint(nb: true) }

    private func shareOrPrint(nb: Bool) throws {
        let app = launch("export", textSize: xxl, nb: nb)
        let print = app.buttons["printExport"].firstMatch
        XCTAssertTrue(print.waitForExistence(timeout: 60))
        picture(app, "export-xxl-\(nb ? "nb" : "en")")
        oneLine(app.buttons["shareExport"].firstMatch, like: print, in: app, "Share")
        oneLine(app.buttons["saveExport"].firstMatch, like: print, in: app, "Save to Files")
    }
}
#endif

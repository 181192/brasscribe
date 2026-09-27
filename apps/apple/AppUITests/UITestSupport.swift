import XCTest

// macOS UI tests drive the real mouse and keyboard. Every click and key goes through these
// helpers: they check that the app is frontmost and that the element is hittable inside the
// app's window, and fail the test instead of clicking anywhere else.

extension XCUIApplication {
    /// Launch with the window at a fixed frame inside the screen's visible area (clear of the
    /// Dock and the menu bar), then wait until it is there and in front.
    func launchForUITest() {
        if !launchArguments.contains("-ui-test-window") { launchArguments.append("-ui-test-window") }
        launch()
        #if os(macOS)
        if !windows.firstMatch.waitForExistence(timeout: 5) {
            activate()
            if !windows.firstMatch.waitForExistence(timeout: 3), state == .runningForeground { typeKey("n", modifierFlags: .command) }
        }
        activate()
        let window = windows.firstMatch
        let hittable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND hittable == true"), object: window)
        XCTAssertEqual(XCTWaiter.wait(for: [hittable], timeout: 10), .completed, "the app window is on screen")
        #endif
    }

    /// Fail unless the app is frontmost (macOS): keys and clicks would reach another app.
    @discardableResult
    func ensureFrontmost(file: StaticString = #filePath, line: UInt = #line) -> Bool {
        #if os(macOS)
        if state != .runningForeground { activate() }
        guard state == .runningForeground else {
            XCTFail("the app is not frontmost; not sending input", file: file, line: line)
            return false
        }
        #endif
        return true
    }

    /// `typeKey`, only while the app is frontmost.
    func safeTypeKey(_ key: String, modifierFlags: XCUIElement.KeyModifierFlags, file: StaticString = #filePath, line: UInt = #line) {
        guard ensureFrontmost(file: file, line: line) else { return }
        typeKey(key, modifierFlags: modifierFlags)
    }
}

extension XCUIElement {
    /// Tap (click on macOS) only when the app is frontmost and the element is hittable inside its window.
    func safeTap(_ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) {
        #if os(macOS)
        guard app.ensureFrontmost(file: file, line: line) else { return }
        guard isHittable else { XCTFail("\(self) is not hittable; not clicking", file: file, line: line); return }
        // menus and menu items live outside the window's frame
        if elementType != .menuItem && elementType != .menu {
            let window = app.windows.firstMatch.frame
            let f = frame
            guard window.contains(CGPoint(x: f.midX, y: f.midY)) else {
                XCTFail("\(self) is outside the app window; not clicking", file: file, line: line)
                return
            }
        }
        #endif
        tap()
    }
}

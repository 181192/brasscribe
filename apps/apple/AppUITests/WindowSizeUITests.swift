#if os(macOS)
import AppKit
import XCTest

/// The Mac window at many sizes: dragged small, medium and past the screen's edge, zoomed with the
/// title bar, Option and the Window menu, and filled. After each the window must lie inside the
/// screen's visible frame (clear of the Dock and the menu bar), and the form screens must not
/// spread their controls over a taller window.
///
/// These resize a real window with a real pointer, so they run only in the macOS VM
/// (scripts/mac-vm.sh test-ui, docs/dev/macos-vm.md) or on a CI runner, never on a desktop in use.
final class WindowSizeUITests: XCTestCase {
    var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = true
        guard Self.inVirtualMachine else {
            throw XCTSkip("window size tests run only in a virtual machine (scripts/mac-vm.sh test-ui)")
        }
        guard let dir = fixtureDir() else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
        app = XCUIApplication()
        app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
        app.launchEnvironment["BRASSCRIBE_FIXTURES"] = dir
        app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"
    }

    override func tearDown() {
        app?.terminate()
        super.tearDown()
    }

    // MARK: - The window stays on the screen

    func testDraggedSizesStayInsideTheVisibleFrame() throws {
        launch()
        let v = visibleFrame
        // small: towards the top-left corner, below the content's minimum
        dragCorner(to: CGPoint(x: window.frame.minX + 200, y: window.frame.minY + 150))
        assertInsideVisibleFrame("dragged to 200 × 150")
        // medium
        dragCorner(to: CGPoint(x: min(window.frame.minX + 900, v.maxX - 10), y: min(window.frame.minY + 680, v.maxY - 10)))
        assertInsideVisibleFrame("dragged to about 900 × 680")
        // past the right edge and down onto the Dock
        dragCorner(to: CGPoint(x: screenFrame.maxX - 2, y: screenFrame.maxY - 2))
        assertInsideVisibleFrame("dragged onto the Dock at the screen's bottom-right corner")
        // and back to a size that fits, from the new position
        dragCorner(to: CGPoint(x: window.frame.minX + 700, y: window.frame.minY + 700))
        assertInsideVisibleFrame("dragged back to about 700 × 700")
    }

    func testZoomStaysInsideTheVisibleFrame() throws {
        launch()
        // the title bar's double-click (the system setting's default is Zoom / Fill)
        titleBar.doubleClick()
        assertInsideVisibleFrame("title bar double-click")
        titleBar.doubleClick()
        assertInsideVisibleFrame("title bar double-click, again")
        // Option and the green button: zoom instead of full screen
        // macOS 26 exposes the green button as the full-screen button; with Option it zooms
        var zoom = window.buttons[XCUIIdentifierZoomWindow]
        if !zoom.waitForExistence(timeout: 3) { zoom = window.buttons[XCUIIdentifierFullScreenWindow] }
        XCTAssertTrue(zoom.waitForExistence(timeout: 3),
                      "the window has a zoom button; its buttons: \(window.buttons.allElementsBoundByIndex.prefix(12).map { "\($0.identifier)/\($0.label)" })")
        if zoom.exists, app.ensureFrontmost() {
            XCUIElement.perform(withKeyModifiers: .option) { zoom.click() }
            assertInsideVisibleFrame("Option-click on the green button")
            XCUIElement.perform(withKeyModifiers: .option) { zoom.click() }
            assertInsideVisibleFrame("Option-click on the green button, again")
        }
    }

    func testWindowMenuSizesStayInsideTheVisibleFrame() throws {
        launch()
        // Window › Zoom, Fill, Center, and the halves where the system has them (macOS 15 and later)
        for item in ["Zoom", "Fill", "Center", "Top", "Bottom", "Left", "Right", "Zoom"] {
            guard windowMenu(item) else { continue }
            assertInsideVisibleFrame("Window › \(item)")
        }
    }

    // MARK: - The score across the sidebar's line, and the window's minimum

    /// The sidebar steps aside below 1000 pt. Across that line, in both directions and after a
    /// title-bar zoom, the score's column lays out at once: it starts at the window's edge with the
    /// sidebar gone and after the sidebar with it shown, never where the other state left it.
    func testScoreRelayoutsAcrossTheSidebarLine() throws {
        app.launchArguments += ["-open-fixture-score"]
        launch()
        // the score's column, by its first control: on macOS 26 the column's own frame runs under
        // the floating sidebar, so its controls tell where it is laid out
        let detail = app.descendants(matching: .any)["partPicker"].firstMatch
        XCTAssertTrue(detail.waitForExistence(timeout: 30), "the score opens")
        guard detail.exists else { return }
        let v = visibleFrame
        func width(_ w: CGFloat, _ what: String) {
            dragCorner(to: CGPoint(x: min(window.frame.minX + w, v.maxX - 4), y: window.frame.maxY - 2))
            assertInsideVisibleFrame(what)
            assertDetailLaidOut(detail, what)
        }
        width(1250, "1250 pt wide")
        width(920, "920 pt wide, below the sidebar's line")
        width(1250, "back to 1250 pt")
        width(930, "930 pt again")
        titleBar.doubleClick()
        settle()
        assertInsideVisibleFrame("title bar zoom from 930 pt")
        assertDetailLaidOut(detail, "title bar zoom from 930 pt")
        titleBar.doubleClick()
        settle()
        assertInsideVisibleFrame("title bar zoom back")
        assertDetailLaidOut(detail, "title bar zoom back")
    }

    /// The window goes down to 900 × 600 and no further, on the score, on the stand and with each
    /// part shown: no part's content raises the minimum (the parts column once grew the window to 1291 × 855).
    func testMinimumWindowOnTheScoreAndEveryPart() throws {
        app.launchArguments += ["-open-fixture-score"]
        launch()
        let picker = app.popUpButtons["partPicker"].firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 30), "the score opens with the part picker")
        assertMinimum("the full score")
        guard picker.exists, app.ensureFrontmost() else { return }
        picker.click()
        let count = picker.menuItems.count
        app.typeKey(.escape, modifierFlags: [])
        XCTAssertGreaterThanOrEqual(count, 19, "All parts and the 18 parts of the band")
        for i in 1..<count {
            guard app.ensureFrontmost() else { return }
            picker.click()
            let item = picker.menuItems.element(boundBy: i)
            guard item.waitForExistence(timeout: 2) else { XCTFail("part \(i) is not in the menu"); continue }
            let title = item.title
            item.click()
            settle()
            assertInsideVisibleFrame("part \(title)")
            assertMinimum("part \(title)")
        }
    }

    func testMinimumWindowOnTheStand() throws {
        app.launchArguments += ["-screen", "stand"]
        launch()
        XCTAssertTrue(app.descendants(matching: .any)["standScore"].firstMatch.waitForExistence(timeout: 30), "the stand opens")
        assertMinimum("the stand")
    }

    // MARK: - Forms keep their size in a taller window

    func testHomeDoesNotStretch() throws {
        launch()
        XCTAssertTrue(app.descendants(matching: .any)["import"].firstMatch.waitForExistence(timeout: 20), "home shows")
        try assertDoesNotStretch("home")
    }

    func testSourceFormDoesNotStretch() throws {
        app.launchArguments += ["-fixture-service", "-fast", "-screen", "source"]
        launch()
        XCTAssertTrue(app.descendants(matching: .any)["transcribe"].firstMatch.waitForExistence(timeout: 20), "What is this? shows")
        try assertDoesNotStretch("source")
    }

    func testOutputFormDoesNotStretch() throws {
        app.launchArguments += ["-screen", "output"]
        launch()
        XCTAssertTrue(app.descendants(matching: .any)["showScore"].firstMatch.waitForExistence(timeout: 30), "How should the score be? shows")
        try assertDoesNotStretch("output")
    }

    func testSettingsSheetDoesNotStretch() throws {
        app.launchArguments += ["-screen", "settings"]
        launch()
        let sheet = app.sheets.firstMatch
        XCTAssertTrue(sheet.waitForExistence(timeout: 20), "Settings shows as a sheet")
        guard sheet.exists else { return }
        // the window's corner, beside the sheet: smallest, then down to the visible frame's bottom
        dragCorner(to: CGPoint(x: window.frame.maxX, y: window.frame.minY + 100))
        let short = window.frame, shortSheet = sheet.frame
        attach("settings-short")
        dragCorner(to: CGPoint(x: window.frame.maxX, y: visibleFrame.maxY - 4))
        let tall = window.frame, tallSheet = sheet.frame
        attach("settings-tall")
        assertInsideVisibleFrame("settings, tall")
        XCTAssertTrue(visibleFrame.insetBy(dx: -1, dy: -1).contains(tallSheet), "the Settings sheet \(tallSheet) stays inside the visible frame \(visibleFrame)")
        let added = tall.height - short.height
        guard added > 100 else { throw XCTSkip("the window did not get taller (\(short.height) → \(tall.height) pt)") }
        // Settings is longer than the screen, so its sheet takes the room it is given, which ends at the
        // window's bottom or at the Dock, and scrolls inside. A sheet whose content fits stops short of
        // both, and must keep its height in a taller window.
        let room = min(tall.maxY, visibleFrame.maxY)
        if tallSheet.maxY < room - 60 {
            XCTAssertLessThan(tallSheet.height - shortSheet.height, max(60, 0.5 * added),
                              "the Settings sheet is \(shortSheet.height) pt in a \(short.height) pt window and \(tallSheet.height) pt in a \(tall.height) pt one")
        }
    }

    // MARK: - Helpers

    static var inVirtualMachine: Bool {
        var value: Int32 = 0
        var size = MemoryLayout<Int32>.size
        return sysctlbyname("kern.hv_vmm_present", &value, &size, nil, 0) == 0 && value == 1
    }

    var window: XCUIElement { app.windows.firstMatch }

    /// The window's title bar, a little in from the top edge, between the traffic lights and the toolbar.
    var titleBar: XCUICoordinate {
        let f = window.frame
        return window.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: f.width / 2, dy: 12))
    }

    /// The screen that shows the window, in XCUITest coordinates (origin at the top-left of the main
    /// screen, y down); AppKit's frames have their origin at the bottom-left, y up.
    private func flipped(_ r: CGRect) -> CGRect {
        let primary = NSScreen.screens.first?.frame ?? .zero
        return CGRect(x: r.minX, y: primary.maxY - r.maxY, width: r.width, height: r.height)
    }

    private var screen: NSScreen? {
        let f = window.exists ? window.frame : .zero
        let center = CGPoint(x: f.midX, y: f.midY)
        return NSScreen.screens.first { flipped($0.frame).contains(center) } ?? NSScreen.screens.first
    }

    var screenFrame: CGRect { flipped(screen?.frame ?? .zero) }
    var visibleFrame: CGRect { flipped(screen?.visibleFrame ?? .zero) }

    func launch() {
        app.launch()
        if !window.waitForExistence(timeout: 10) {
            app.activate()
            if !window.waitForExistence(timeout: 5), app.state == .runningForeground { app.typeKey("n", modifierFlags: .command) }
        }
        app.dismissLocalNetworkPrompt()
        app.activate()
        let hittable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND hittable == true"), object: window)
        XCTAssertEqual(XCTWaiter.wait(for: [hittable], timeout: 15), .completed, "the app window is on screen")
        settle()
        assertInsideVisibleFrame("first window")
    }

    /// Let a resize or zoom animation, and the app's own fitting after it, finish.
    func settle() { Thread.sleep(forTimeInterval: 0.7) }

    /// Drag the window's bottom-right corner to `target` (screen coordinates, y down).
    func dragCorner(to target: CGPoint) {
        guard app.ensureFrontmost() else { return }
        let f = window.frame
        let origin = window.coordinate(withNormalizedOffset: .zero)
        let corner = origin.withOffset(CGVector(dx: f.width - 2, dy: f.height - 2))
        corner.press(forDuration: 0.4, thenDragTo: origin.withOffset(CGVector(dx: target.x - f.minX, dy: target.y - f.minY)))
        settle()
    }

    /// Choose Window › `title` in the menu bar; false when the system has no such item.
    @discardableResult
    func windowMenu(_ title: String) -> Bool {
        guard app.ensureFrontmost() else { return false }
        let menu = app.menuBars.menuBarItems["Window"]
        guard menu.exists else { return false }
        menu.click()
        let item = menu.menuItems[title]
        guard item.waitForExistence(timeout: 2), item.isEnabled else {
            app.typeKey(.escape, modifierFlags: [])
            return false
        }
        item.click()
        settle()
        return true
    }

    /// Dragged as small as it goes, the window is 900 × 600 (a larger minimum means some content raised it).
    func assertMinimum(_ what: String, file: StaticString = #filePath, line: UInt = #line) {
        dragCorner(to: CGPoint(x: window.frame.minX + 300, y: window.frame.minY + 200))
        let f = window.frame
        let ok = abs(f.width - 900) <= 2 && abs(f.height - 600) <= 2
        XCTAssertTrue(ok, "\(what): the smallest window is \(f.width) × \(f.height), not 900 × 600", file: file, line: line)
        assertInsideVisibleFrame("\(what), smallest", file: file, line: line)
        if !ok { attach("minimum-\(what)") }
    }

    /// The score's column matches the sidebar: its first control (`detail`) sits near the window's
    /// left edge when the sidebar is gone, right of the sidebar when it shows, and inside the window.
    func assertDetailLaidOut(_ detail: XCUIElement, _ what: String, file: StaticString = #filePath, line: UInt = #line) {
        let w = window.frame, d = detail.frame
        let side = app.descendants(matching: .any)["sidebarHome"].firstMatch
        let sidebarShown = side.exists && !side.frame.isEmpty && side.isHittable && w.contains(CGPoint(x: side.frame.midX, y: side.frame.midY))
        var ok = d.maxX <= w.maxX + 1 && d.minX >= w.minX - 1
        if sidebarShown {
            let s = side.frame
            ok = ok && d.minX >= s.maxX - 1
            XCTAssertGreaterThanOrEqual(d.minX, s.maxX - 1, "\(what): the score's column \(d) runs under the sidebar (\(s))", file: file, line: line)
        } else {
            // the back button and the margin come first; a sidebar's width (240 pt or more) is stale
            ok = ok && d.minX <= w.minX + 160
            XCTAssertLessThanOrEqual(d.minX, w.minX + 160, "\(what): the sidebar is gone but the score's column still starts \(d.minX - w.minX) pt into the window \(w)", file: file, line: line)
        }
        XCTAssertLessThanOrEqual(d.maxX, w.maxX + 1, "\(what): the score's column \(d) reaches past the window \(w)", file: file, line: line)
        if !ok { attach("stale-\(what)") }
    }

    func assertInsideVisibleFrame(_ what: String, file: StaticString = #filePath, line: UInt = #line) {
        let f = window.frame
        let v = visibleFrame
        let inside = v.insetBy(dx: -1, dy: -1).contains(f)
        XCTAssertTrue(inside, "\(what): the window \(f) reaches past the visible frame \(v) (screen \(screenFrame))", file: file, line: line)
        if !inside { attach("outside-\(what)") }
    }

    /// The window's controls, as frames (buttons, text, fields, pickers), below the title bar.
    private func controlFrames() -> [CGRect] {
        let w = window.frame
        let types: [XCUIElement.ElementType] = [.button, .staticText, .textField, .checkBox, .radioButton, .popUpButton, .segmentedControl, .toggle, .slider]
        var frames: [CGRect] = []
        for t in types {
            for e in window.descendants(matching: t).allElementsBoundByIndex {
                let f = e.frame
                guard !f.isEmpty, f.minY > w.minY + 60, w.contains(CGPoint(x: f.midX, y: f.midY)) else { continue }
                frames.append(f)
            }
        }
        return frames
    }

    /// At its smallest the window's controls take some height; in a window as tall as the screen
    /// allows they must take about the same: a form that follows the window's height is stretched.
    func assertDoesNotStretch(_ screenName: String, file: StaticString = #filePath, line: UInt = #line) throws {
        // smallest: drag the corner up past the content's minimum
        dragCorner(to: CGPoint(x: window.frame.maxX, y: window.frame.minY + 100))
        let short = window.frame
        let before = controlFrames()
        attach("\(screenName)-short")
        _ = windowMenu("Fill") || windowMenu("Zoom")
        if window.frame.height < short.height + 100 {
            dragCorner(to: CGPoint(x: window.frame.maxX, y: visibleFrame.maxY - 4))
        }
        let tall = window.frame
        let after = controlFrames()
        attach("\(screenName)-tall")
        assertInsideVisibleFrame("\(screenName), tall", file: file, line: line)
        let added = tall.height - short.height
        guard added > 100 else { throw XCTSkip("the screen is too short to compare (\(short.height) → \(tall.height) pt)") }
        guard !before.isEmpty, !after.isEmpty else { XCTFail("\(screenName): no controls found", file: file, line: line); return }

        func span(_ fs: [CGRect]) -> CGFloat { (fs.map(\.maxY).max() ?? 0) - (fs.map(\.minY).min() ?? 0) }
        let grew = span(after) - span(before)
        XCTAssertLessThan(grew, max(60, 0.5 * added),
                          "\(screenName): the controls spread over \(span(before)) pt in a \(short.height) pt window and \(span(after)) pt in a \(tall.height) pt one",
                          file: file, line: line)
        // no single control follows the window's height
        for f in after where f.height > 0.4 * tall.height {
            XCTFail("\(screenName): a control is \(f.height) pt tall in a \(tall.height) pt window (\(f))", file: file, line: line)
        }
    }

    func attach(_ name: String) {
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }
}
#endif

import XCTest

/// The music stand (design/music-stand.md): in and out, the controls that stay for assistive
/// technology and the keyboard, and the page keys Bluetooth page turners send.
final class MusicStandUITests: XCTestCase {
    var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard let dir = fixtureDir() else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
        app = XCUIApplication()
        app.launchArguments = ["-reset", "-open-fixture-score", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
        app.launchEnvironment["BRASSCRIBE_FIXTURES"] = dir
        app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"
    }

    override func tearDown() {
        #if os(iOS)
        XCUIDevice.shared.orientation = .portrait
        #endif
        super.tearDown()
    }

    private func launch(_ extra: [String] = []) {
        app.launchArguments += extra
        app.launchForUITest()
    }

    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    /// Open the stand with the toolbar button, once the score is engraved.
    private func enterStand() {
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-'")).firstMatch
            .waitForExistence(timeout: 60), "the score is engraved")
        let button = app.buttons["musicStand"].firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: 10))
        button.safeTap(app)
        XCTAssertTrue(app.buttons["standLeave"].waitForExistence(timeout: 10), "the stand is open")
        XCTAssertTrue(element("standScore").waitForExistence(timeout: 30))
    }

    /// The position line. iOS reports a text's words as its label; the Mac reports them as its value.
    private var position: String {
        let e = element("standPosition")
        return e.label.isEmpty ? (e.value as? String ?? "") : e.label
    }

    /// Waits until the position line satisfies `test`.
    private func waitForPosition(timeout: TimeInterval, _ test: @escaping (String) -> Bool) -> Bool {
        XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in test(self.position) }, object: nil)],
                       timeout: timeout) == .completed
    }

    private func waitFor(_ e: XCUIElement, exists: Bool, timeout: TimeInterval) -> Bool {
        XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == %@", NSNumber(value: exists)), object: e)],
                       timeout: timeout) == .completed
    }

    func testEnterAndLeaveTheStand() throws {
        launch()
        enterStand()
        // the score's own chrome is gone; the persistent band and the layer (paused) are there
        XCTAssertFalse(app.descendants(matching: .any)["partPicker"].exists)
        XCTAssertFalse(app.buttons["playPause"].exists)
        XCTAssertTrue(element("standLayer").exists, "the controls show on entry while paused")
        XCTAssertTrue(position.contains("1"), position)
        XCTAssertEqual(app.buttons["standLeave"].label, "Leave the music stand")
        // Only my part off shows every part, on again shows yours
        let mine = position
        let only = element("standOnlyMine")
        XCTAssertTrue(only.exists)
        only.safeTap(app)
        XCTAssertTrue(waitForPosition(timeout: 30) { $0.contains("All parts") }, "Only my part off: \(position)")
        only.safeTap(app)
        XCTAssertTrue(waitForPosition(timeout: 30) { $0 == mine }, "Only my part on again: \(position)")
        // "Only my part" is on: the part line says it is yours
        XCTAssertTrue(position.contains("(you)"), position)
        app.buttons["standLeave"].safeTap(app)
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 10), "back on the score")
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["standLeave"].exists)
    }

    /// While the music plays the controls hide after 4 s, and a tap on the music brings them back.
    func testControlsHideWhilePlaying() throws {
        launch(["-stand-ignore-keyboard"])
        enterStand()
        app.buttons["standPlay"].safeTap(app)
        XCTAssertTrue(waitFor(element("standLayer"), exists: false, timeout: 10), "the layer hides while playing")
        XCTAssertTrue(app.buttons["standLeave"].exists, "Leave always stays")
        element("standScore").safeTap(app)
        XCTAssertTrue(element("standLayer").waitForExistence(timeout: 5), "a tap shows the controls")
    }

    /// With a screen reader or switch running the controls never hide, not by the timer and not by a tap.
    func testControlsStayWithAssistiveTechnology() throws {
        launch(["-stand-assistive", "-stand-ignore-keyboard"])
        enterStand()
        app.buttons["standPlay"].safeTap(app)
        XCTAssertFalse(waitFor(element("standLayer"), exists: false, timeout: 7), "the layer stays with assistive technology")
        element("standScore").safeTap(app)
        XCTAssertTrue(element("standLayer").exists)
        app.buttons["standPlay"].safeTap(app)
    }

    /// Page turners send arrows or Page Up / Page Down; Home and End go to the first and last page;
    /// Esc leaves. (The iOS simulator's key injection delivers the arrows and letters but not Page Up,
    /// Page Down, Home, End or Esc, so those are checked on the Mac.)
    func testPageKeys() throws {
        #if os(iOS)
        guard UIDevice.current.userInterfaceIdiom == .pad else { throw XCTSkip("hardware-keyboard tests run on iPad and Mac") }
        let (next, previous) = (XCUIKeyboardKey.downArrow, XCUIKeyboardKey.upArrow)
        #else
        let (next, previous) = (XCUIKeyboardKey.pageDown, XCUIKeyboardKey.pageUp)
        #endif
        launch(["-stand-bars", "1"])
        enterStand()
        let first = position
        XCTAssertTrue(first.contains("1"), first)
        // a page turns with a short fade, and the position line follows it
        app.safeTypeKey(next.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 != first }, "the next-page key turns the page: \(position)")
        let second = position
        app.safeTypeKey(previous.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 == first }, "the previous-page key turns back: \(position)")
        app.safeTypeKey(XCUIKeyboardKey.rightArrow.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 == second }, "→ turns the page, not the bar: \(position)")
        app.safeTypeKey(XCUIKeyboardKey.leftArrow.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 == first }, "← turns back: \(position)")
        #if os(macOS)
        app.safeTypeKey(XCUIKeyboardKey.end.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 != first }, "End goes to the last page: \(position)")
        app.safeTypeKey(XCUIKeyboardKey.home.rawValue, modifierFlags: [])
        XCTAssertTrue(waitForPosition(timeout: 5) { $0 == first }, "Home goes to the first page: \(position)")
        #endif
        #if os(macOS)
        app.safeTypeKey(XCUIKeyboardKey.escape.rawValue, modifierFlags: [])
        #else
        app.safeTypeKey("f", modifierFlags: [])  // the simulator's key injection does not deliver Esc either
        #endif
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 10), "Esc (F on iPad) leaves the stand")
        XCTAssertTrue(app.buttons["playPause"].exists, "and only the stand: the score is still open")
    }

    /// Lock rotation keeps the music the way up it was; leaving gives rotation back to the system.
    func testRotationLockHoldsAndLeavingReleasesIt() throws {
        #if os(iOS)
        guard UIDevice.current.userInterfaceIdiom == .phone else { throw XCTSkip("the lock is on phones only") }
        XCUIDevice.shared.orientation = .portrait
        launch(["-stand-ignore-keyboard"])
        enterStand()
        let lock = element("standLock")
        XCTAssertTrue(lock.waitForExistence(timeout: 5))
        lock.safeTap(app)
        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(2)
        let locked = app.windows.firstMatch.frame
        XCTAssertGreaterThan(locked.height, locked.width, "locked upright: the stand does not turn")
        app.buttons["standLeave"].safeTap(app)
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 10))
        XCUIDevice.shared.orientation = .portrait
        sleep(1)
        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(2)
        let free = app.windows.firstMatch.frame
        XCTAssertGreaterThan(free.width, free.height, "after leaving, the app turns with the phone again")
        #else
        throw XCTSkip("the lock is on phones only")
        #endif
    }

    /// F opens the stand from the score (the Mac's View › Music Stand, a keyboard on iPad) and closes it.
    func testFTogglesTheStand() throws {
        #if os(iOS)
        guard UIDevice.current.userInterfaceIdiom == .pad else { throw XCTSkip("hardware-keyboard tests run on iPad and Mac") }
        #endif
        launch()
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 60))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-'")).firstMatch
            .waitForExistence(timeout: 60))
        app.safeTypeKey("f", modifierFlags: [])
        XCTAssertTrue(app.buttons["standLeave"].waitForExistence(timeout: 10), "F opens the stand")
        app.safeTypeKey("f", modifierFlags: [])
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 10), "F leaves it")
    }

    /// "Open on the music stand" in a score's menu opens the score and the stand in one step;
    /// leaving goes back to the library.
    func testOpenOnTheMusicStandFromTheLibrary() throws {
        launch()
        XCTAssertTrue(app.buttons["musicStand"].waitForExistence(timeout: 60))
        #if os(iOS)
        // back to the library (on iPad the sidebar steps aside while a score is open)
        app.navigationBars.buttons.element(boundBy: 0).safeTap(app)
        #endif
        let options = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'options-'")).firstMatch
        XCTAssertTrue(options.waitForExistence(timeout: 10))
        options.safeTap(app)
        let item = app.buttons["Open on the music stand"].firstMatch
        let menuItem = app.menuItems["Open on the music stand"].firstMatch
        if item.waitForExistence(timeout: 3) { item.safeTap(app) } else { XCTAssertTrue(menuItem.waitForExistence(timeout: 3)); menuItem.safeTap(app) }
        XCTAssertTrue(app.buttons["standLeave"].waitForExistence(timeout: 30), "the stand opens")
        app.buttons["standLeave"].safeTap(app)
        XCTAssertTrue(options.waitForExistence(timeout: 10), "back in the library")
    }

    // MARK: screenshots (STAND_SHOTS=<dir>, NB=1 for Norwegian)

    func testScreenshots() throws {
        guard let dir = ProcessInfo.processInfo.environment["STAND_SHOTS"] else { throw XCTSkip("set STAND_SHOTS to take the stand screenshots") }
        let nb = ProcessInfo.processInfo.environment["NB"] == "1"
        let lang = nb ? ["-AppleLanguages", "(nb)", "-AppleLocale", "nb_NO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_GB"]
        let tag = nb ? "-nb" : ""
        #if os(iOS)
        let device = UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone"
        // (scene, orientation, extra arguments): the fixture is 12 bars, so the iPad spread uses 2 bars a system to fill two pages
        let states: [(String, UIDeviceOrientation, [String])] = device == "iphone"
            ? [("stand", .portrait, []), ("stand-hidden", .portrait, []), ("stand-hint", .portrait, []),
               ("stand", .landscapeLeft, []), ("stand-locked", .landscapeLeft, [])]
            : [("stand", .landscapeLeft, []), ("stand-hidden", .landscapeLeft, []), ("stand", .portrait, []),
               ("stand-spread", .landscapeLeft, ["-stand-bars", "2"])]
        #else
        let device = "macos"
        let states: [(String, Int, [String])] = [("stand", 0, []), ("stand-hidden", 0, [])]
        #endif
        for (screen, orientation, extra) in states {
            #if os(iOS)
            XCUIDevice.shared.orientation = orientation
            let hold = orientation == .portrait ? "portrait" : "landscape"
            #else
            _ = orientation
            let hold = "window"
            #endif
            for look in ["light", "dark"] {
                app.terminate()
                app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-connection", "connected",
                                       "-screen", screen == "stand-spread" ? "stand" : screen, "-appearance", look] + lang + extra
                launch()
                XCTAssertTrue(element("standScore").waitForExistence(timeout: 60))
                sleep(6)
                let shot = XCUIScreen.main.screenshot()
                #if os(macOS)
                let image = app.windows.firstMatch.screenshot()
                let png = image.pngRepresentation
                #else
                // the screen is captured in its portrait buffer: turn a landscape shot the way it was held
                let png = orientation == .portrait ? shot.pngRepresentation : Self.turned(shot.image)
                #endif
                let name = "\(device)\(tag)-\(screen)-\(hold)-\(look).png"
                try png.write(to: URL(fileURLWithPath: dir).appending(path: name))
            }
        }
    }

    /// Settings → Appearance changes the whole app at once: Dark, then Light, then back to Match system.
    /// With STAND_SHOTS set, it also saves Settings in both.
    func testAppearanceSetting() throws {
        #if os(iOS)
        let nb = ProcessInfo.processInfo.environment["NB"] == "1"
        app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-connection", "connected",
                               "-screen", "settings"] + (nb ? ["-AppleLanguages", "(nb)", "-AppleLocale", "nb_NO"] : ["-AppleLanguages", "(en)"])
        launch()
        let picker = element("settingAppearance")
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 20))
        for _ in 0..<6 where !(picker.exists && picker.isHittable) { app.swipeUp() }
        XCTAssertTrue(picker.waitForExistence(timeout: 5))
        let names = nb ? ["Mørkt", "Lyst", "Følg systemet"] : ["Dark", "Light", "Match system"]
        let device = UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone"
        for (name, look) in zip(names, ["dark", "light", "system"]) {
            // an inline picker's options are rows; the row's text is enough to tap
            let option = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", name)).firstMatch
            // the form is a lazy list: scroll until the row is on screen
            for _ in 0..<5 where !(option.exists && option.isHittable) { app.swipeUp() }
            XCTAssertTrue(option.exists, name)
            option.safeTap(app)
            sleep(1)
            if let dir = ProcessInfo.processInfo.environment["STAND_SHOTS"], look != "system" {
                let png = XCUIScreen.main.screenshot().pngRepresentation
                try png.write(to: URL(fileURLWithPath: dir).appending(path: "\(device)\(nb ? "-nb" : "")-settings-appearance-\(look).png"))
            }
        }
        #else
        throw XCTSkip("the Mac's Settings are not driven by UI tests here")
        #endif
    }

    #if os(iOS)
    /// The screenshot drawn the way it is shown: the image carries the orientation, its PNG data does not.
    static func turned(_ image: UIImage) -> Data {
        let format = UIGraphicsImageRendererFormat()
        format.scale = image.scale
        return UIGraphicsImageRenderer(size: image.size, format: format).pngData { _ in image.draw(at: .zero) }
    }
    #endif
}

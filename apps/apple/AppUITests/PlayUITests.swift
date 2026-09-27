import XCTest

/// The golden Mikkel output, located from this source file (the simulator and the
/// macOS runner can both read host paths).
func fixtureDir() -> String? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return env }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<6 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c.path }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

func soundFont() -> String? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<6 {
        let c = dir.appending(path: "data/soundfonts/MuseScore_General.sf2")
        if FileManager.default.fileExists(atPath: c.path) { return c.path }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

final class PlayUITests: XCTestCase {
    var app: XCUIApplication!

    /// Launch and make sure there is a window. On macOS a relaunched app is not always
    /// activated, and SwiftUI then opens no window; File > New Window (Cmd-N) opens one.
    func launchApp() {
        app.launch()
        #if os(macOS)
        if !app.windows.firstMatch.waitForExistence(timeout: 5) {
            app.activate()
            if !app.windows.firstMatch.waitForExistence(timeout: 3) { app.typeKey("n", modifierFlags: .command) }
        }
        #endif
    }

    /// Review → confirm "Finish later" when notes are left → "How should the score be?" → Show the score.
    func leaveReview(_ open: XCUIElement) {
        open.tap()
        let finish = app.buttons.matching(NSPredicate(format: "label == 'Finish later'")).firstMatch
        if finish.waitForExistence(timeout: 3) { finish.tap() }
        let show = app.descendants(matching: .any)["showScore"].firstMatch
        XCTAssertTrue(show.waitForExistence(timeout: 10), "How should the score be? follows the review")
        show.tap()
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard let dir = fixtureDir() else { throw XCTSkip("golden Mikkel fixture not found") }
        app = XCUIApplication()
        app.launchArguments = ["-reset", "-open-demo-score", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
        app.launchEnvironment["BRASSCRIBE_FIXTURES"] = dir
        // no computer: scores on a Brasscribe running on this Mac must not leak into the tests
        app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"
        if let sf = soundFont() { app.launchEnvironment["BRASSCRIBE_SOUNDFONT"] = sf }
        // the realistic brass-band tier, when sounds/ and its built instruments are present
        let root = URL(fileURLWithPath: dir).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        if FileManager.default.fileExists(atPath: root.appending(path: "sounds/mapping.json").path) {
            app.launchEnvironment["BRASSCRIBE_SOUNDS"] = root.path
        }
        launchApp()
    }

    /// Loads the Mikkel score, checks the notation exposes bars to VoiceOver, and plays
    /// until the transport has moved past bar 1.
    func testLoadMikkelAndPlayABar() throws {
        let play = app.buttons["playPause"]
        XCTAssertTrue(play.waitForExistence(timeout: 30))
        // bar 1 of the solo cornet (index 1 in the full score, 0 when a phone shows only that part)
        let staff = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-' AND label CONTAINS 'Solo Cornet'")).firstMatch
        if !staff.waitForExistence(timeout: 60) {
            let tree = app.debugDescription
            print("TREE-BEGIN\n\(tree.prefix(20000))\nTREE-END")
            XCTFail("notation should expose bar 1 of the solo cornet")
        }
        XCTAssertTrue(staff.label.contains("Solo Cornet"), staff.label)
        let position = app.descendants(matching: .any)["position"]
        XCTAssertTrue(position.exists)
        XCTAssertEqual(position.value as? String, "1")
        play.tap()
        let moved = NSPredicate { _, _ in (Int(position.value as? String ?? "1") ?? 1) >= 2 }
        wait(for: [XCTNSPredicateExpectation(predicate: moved, object: nil)], timeout: 15)
        play.tap()
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "score-after-playing"
        shot.lifetime = .keepAlways
        add(shot)
    }

    /// Home → "What is this?" → progress → Review → score, with the demo transcription service.
    func testDemoFlowThroughReview() throws {
        app.terminate()
        app.launchArguments = ["-reset", "-demo-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
        launchApp()
        let demo = app.descendants(matching: .any)["demo"].firstMatch
        XCTAssertTrue(demo.waitForExistence(timeout: 20))
        demo.tap()
        let transcribe = app.descendants(matching: .any)["transcribe"].firstMatch
        XCTAssertTrue(transcribe.waitForExistence(timeout: 10))
        XCTAssertFalse(transcribe.isEnabled, "the app never guesses the profile")
        app.descendants(matching: .any)["profile-orchestra-with-soloist"].firstMatch.tap()
        XCTAssertTrue(transcribe.isEnabled)
        transcribe.tap()
        let open = app.descendants(matching: .any)["openScore"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 60), "review should follow the transcription")
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "review"
        shot.lifetime = .keepAlways
        add(shot)
        leaveReview(open)
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 30))
    }

    /// Documented shortcuts: → / ← move by bar, . raises the speed, space plays and pauses.
    func testKeyboardShortcuts() throws {
        #if os(iOS)
        guard UIDevice.current.userInterfaceIdiom == .pad else { throw XCTSkip("hardware-keyboard shortcuts are tested on iPad and Mac") }
        #endif
        let play = app.buttons["playPause"]
        XCTAssertTrue(play.waitForExistence(timeout: 30))
        let position = app.descendants(matching: .any)["position"]
        let speed = app.descendants(matching: .any)["speed"]
        // wait until the score is engraved, so no keystroke lands while the view rebuilds
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-'")).firstMatch
            .waitForExistence(timeout: 60))
        app.typeKey(XCUIKeyboardKey.rightArrow.rawValue, modifierFlags: [])
        app.typeKey(XCUIKeyboardKey.rightArrow.rawValue, modifierFlags: [])
        XCTAssertEqual(position.value as? String, "3")
        app.typeKey(XCUIKeyboardKey.leftArrow.rawValue, modifierFlags: [])
        XCTAssertEqual(position.value as? String, "2")
        app.typeKey(".", modifierFlags: [])
        // iOS reports the slider's accessibility value text, macOS its number
        let raised = NSPredicate { _, _ in
            if let s = speed.value as? String { return s.contains("105") }
            if let n = speed.value as? NSNumber { return n.doubleValue == 105 }
            return false
        }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: raised, object: nil)], timeout: 3), .completed,
                       "\(String(describing: speed.value))")
        app.typeKey(" ", modifierFlags: [])
        XCTAssertTrue(app.buttons["Pause"].waitForExistence(timeout: 5))
        app.typeKey(" ", modifierFlags: [])
        XCTAssertTrue(app.buttons["Play"].waitForExistence(timeout: 5))
    }

    /// A recorded solo becomes a readable part with no computer: on-device models and the core.
    func testOfflineSoloToReadablePart() throws {
        let clip = URL(fileURLWithPath: fixtureDir()!).deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "runs/apple/entertainer-tpt1-30s.wav")
        let models = "/Users/k/private/brasscribe/models/converted"
        guard FileManager.default.fileExists(atPath: clip.path), FileManager.default.fileExists(atPath: models) else {
            throw XCTSkip("needs the URMP clip and models/converted")
        }
        app.terminate()
        app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
        app.launchEnvironment["BRASSCRIBE_OPEN_AUDIO"] = clip.path
        app.launchEnvironment["BRASSCRIBE_MODELS"] = models
        app.launchEnvironment["BRASSCRIBE_COMPANION"] = "http://127.0.0.1:1"   // no computer
        launchApp()
        let solo = app.descendants(matching: .any)["profile-solo"].firstMatch
        XCTAssertTrue(solo.waitForExistence(timeout: 20))
        solo.tap()
        app.descendants(matching: .any)["transcribe"].firstMatch.tap()
        let open = app.descendants(matching: .any)["openScore"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 120), "on-device transcription should reach Review")
        leaveReview(open)
        let staff = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-' AND label CONTAINS 'Solo Cornet'")).firstMatch
        XCTAssertTrue(staff.waitForExistence(timeout: 60))
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "offline-solo-part"
        shot.lifetime = .keepAlways
        add(shot)
    }

    /// The synced video uses the system player, which offers picture in picture.
    func testVideoOffersPictureInPicture() throws {
        let video = URL(fileURLWithPath: fixtureDir()!).deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "runs/apple/mikkel-20s.mp4")
        guard FileManager.default.fileExists(atPath: video.path) else { throw XCTSkip("needs data/runs/apple/mikkel-20s.mp4") }
        app.terminate()
        app.launchEnvironment["BRASSCRIBE_VIDEO"] = video.path
        launchApp()
        let pip = app.buttons["pipButton"]
        XCTAssertTrue(pip.waitForExistence(timeout: 30), "picture-in-picture control")
        let available = NSPredicate { _, _ in pip.isEnabled }
        let r = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: available, object: nil)], timeout: 15)
        #if os(iOS)
        if r != .completed, UIDevice.current.userInterfaceIdiom == .phone {
            throw XCTSkip("the iPhone simulator reports picture in picture as not possible for this player")
        }
        #endif
        XCTAssertEqual(r, .completed)
        pip.tap()
        let started = app.buttons["Stop picture in picture"].waitForExistence(timeout: 10)
        print("PIP available \(pip.isEnabled), started \(started)")
        XCTAssertTrue(started)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "video-pip-control"
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testNextBarAndLoopWithoutDragging() throws {
        let next = app.buttons["nextBar"]
        XCTAssertTrue(next.waitForExistence(timeout: 30))
        next.tap(); next.tap()
        let position = app.descendants(matching: .any)["position"]
        XCTAssertEqual(position.value as? String, "3")
        app.buttons["previousBar"].tap()
        XCTAssertEqual(position.value as? String, "2")
    }

    /// Picking one part shrinks displayedParts while the staff views of the other parts are
    /// still on screen; indexing that array from a staff view crashed the app.
    func testShowOnePartThenAllParts() throws {
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 30))
        let staves = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-'"))
        XCTAssertTrue(staves.firstMatch.waitForExistence(timeout: 60))
        #if os(iOS)
        if UIDevice.current.userInterfaceIdiom == .pad {
            XCTAssertGreaterThan(staves.count, 1, "the full score shows every part")
        }
        #else
        XCTAssertGreaterThan(staves.count, 1, "the full score shows every part")
        #endif

        let picker = app.descendants(matching: .any)["partPicker"].firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 10))
        picker.tap()
        #if os(macOS)
        app.menuItems["Solo Cornet"].tap()
        #else
        app.descendants(matching: .any)["Solo Cornet"].firstMatch.tap()
        #endif

        let solo = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-' AND label CONTAINS 'Solo Cornet'")).firstMatch
        XCTAssertTrue(solo.waitForExistence(timeout: 30), "the solo cornet alone should still engrave")
        XCTAssertEqual(app.state, .runningForeground)

        picker.tap()
    #if os(macOS)
    app.menuItems["All parts"].tap()
    #else
        app.descendants(matching: .any)["All parts"].firstMatch.tap()
    #endif
        XCTAssertTrue(staves.firstMatch.waitForExistence(timeout: 30))
        XCTAssertEqual(app.state, .runningForeground)
    }

    /// Xcode's accessibility audit on the score screen. Issues are recorded, not fatal,
    /// so the report lists them all; the test fails only on missing labels or
    /// unreachable elements.
    func testAccessibilityAudit() throws {
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 30))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-'")).firstMatch.waitForExistence(timeout: 60))
        var issues: [String] = []
        var blocking: [String] = []
        try app.performAccessibilityAudit { issue in
            let line = "AUDIT \(issue.auditType) | \(issue.compactDescription) | \(issue.element?.identifier ?? "") \(issue.element?.label ?? "") type=\(issue.element?.elementType.rawValue ?? 0) frame=\(issue.element?.frame ?? .zero)"
            issues.append(line)
            print(line)
            // Not ours: the system menu bar, and SwiftUI's unlabeled hosting groups: the
            // window group, and on macOS the sidebar and inspector columns (groups as tall as
            // the window). All are listed in the report.
            let window = self.app.windows.firstMatch.frame
            let f = issue.element?.frame ?? .zero
            let systemOwned = issue.element?.elementType == .menuBar || f.minY == 0
                || (issue.element?.elementType == .group && (f.width >= window.width - 1 || f.height >= window.height - 60))
            if (issue.auditType == .sufficientElementDescription || issue.auditType == .hitRegion), !systemOwned {
                blocking.append(line)
            }
            return true
        }
        print("AUDIT total \(issues.count)")
        let a = XCTAttachment(string: issues.joined(separator: "\n"))
        a.name = "accessibility-audit"
        a.lifetime = .keepAlways
        add(a)
        XCTAssertTrue(blocking.isEmpty, blocking.joined(separator: "\n"))
    }
}

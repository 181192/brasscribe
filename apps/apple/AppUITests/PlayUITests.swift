import XCTest

/// The Old Hundredth fixture (apps/fixtures/old-hundredth), located from this source file (the
/// simulator and the macOS runner can both read host paths).
func fixtureDir() -> String? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return env }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<6 {
        let c = dir.appending(path: "apps/fixtures/old-hundredth")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c.path }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// The repository's local data/ folder (not in git).
func dataDir() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<8 {
        let c = dir.appending(path: "data")
        if FileManager.default.fileExists(atPath: c.path) { return c }
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
        app.launchForUITest()
    }

    /// Review → confirm "Finish later" when notes are left → "How should the score be?" → Show the score.
    func leaveReview(_ open: XCUIElement) {
        open.safeTap(app)
        let finish = app.buttons.matching(NSPredicate(format: "label == 'Finish later'")).firstMatch
        if finish.waitForExistence(timeout: 3) { finish.safeTap(app) }
        let show = app.descendants(matching: .any)["showScore"].firstMatch
        XCTAssertTrue(show.waitForExistence(timeout: 10), "How should the score be? follows the review")
        show.safeTap(app)
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard let dir = fixtureDir() else { throw XCTSkip("apps/fixtures/old-hundredth not found") }
        app = XCUIApplication()
        app.launchArguments = ["-reset", "-open-fixture-score", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run"]
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

    /// Loads the fixture score, checks the notation exposes bars to VoiceOver, and plays
    /// until the transport has moved past bar 1.
    func testLoadFixtureScoreAndPlayABar() throws {
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
        play.safeTap(app)
        let moved = NSPredicate { _, _ in (Int(position.value as? String ?? "1") ?? 1) >= 2 }
        wait(for: [XCTNSPredicateExpectation(predicate: moved, object: nil)], timeout: 15)
        play.safeTap(app)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "score-after-playing"
        shot.lifetime = .keepAlways
        add(shot)
    }

    /// "What is this?" → progress → Review → score, with the fixture transcription service.
    func testFixtureFlowThroughReview() throws {
        app.terminate()
        app.launchArguments = ["-reset", "-fixture-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-screen", "source"]
        launchApp()
        let transcribe = app.descendants(matching: .any)["transcribe"].firstMatch
        XCTAssertTrue(transcribe.waitForExistence(timeout: 10))
        XCTAssertFalse(transcribe.isEnabled, "the app never guesses the profile")
        app.descendants(matching: .any)["profile-orchestra-with-soloist"].firstMatch.safeTap(app)
        XCTAssertTrue(transcribe.isEnabled)
        transcribe.safeTap(app)
        let open = app.descendants(matching: .any)["openScore"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 60), "review should follow the transcription")
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "review"
        shot.lifetime = .keepAlways
        add(shot)
        leaveReview(open)
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 30))
    }

    /// "Change note…" → Save stays on the note: "Changed to … (was …)" with Undo, the same place in the
    /// queue; change again keeps "was"; Undo takes the line away; only Keep moves on.
    func testChangeNoteStaysOnTheNote() throws {
        app.terminate()
        app.launchArguments = ["-reset", "-fixture-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-screen", "source"]
        launchApp()
        let transcribe = app.descendants(matching: .any)["transcribe"].firstMatch
        XCTAssertTrue(transcribe.waitForExistence(timeout: 10))
        app.descendants(matching: .any)["profile-orchestra-with-soloist"].firstMatch.safeTap(app)
        transcribe.safeTap(app)
        let position = app.staticTexts["reviewPosition"].firstMatch
        XCTAssertTrue(position.waitForExistence(timeout: 60), "review should follow the transcription")
        let before = shown(position)
        let changed = app.staticTexts["noteChanged"].firstMatch
        // macOS exposes a static text's words as its value, iOS as its label
        func shown(_ e: XCUIElement) -> String { e.label.isEmpty ? (e.value as? String ?? "") : e.label }

        func changeUp() {
            app.buttons["changeNote"].firstMatch.safeTap(app)
            let up = app.buttons["Up a semitone"].firstMatch
            XCTAssertTrue(up.waitForExistence(timeout: 10))
            up.safeTap(app)
            app.buttons["Save"].firstMatch.safeTap(app)
            XCTAssertTrue(changed.waitForExistence(timeout: 20), "the card says what the note was changed to")
        }

        changeUp()
        XCTAssertEqual(shown(position), before, "Save stays on the same note")
        XCTAssertTrue(shown(changed).hasPrefix("Changed to "), shown(changed))
        let was = String(shown(changed)[shown(changed).range(of: "(was ")!.lowerBound...])
        XCTAssertTrue(app.buttons["undoChange"].exists)

        changeUp()
        XCTAssertEqual(shown(position), before)
        XCTAssertTrue(shown(changed).hasSuffix(was), "\(shown(changed)) keeps \(was)")

        app.buttons["undoChange"].firstMatch.safeTap(app)
        let gone = NSPredicate(format: "exists == false")
        wait(for: [XCTNSPredicateExpectation(predicate: gone, object: changed)], timeout: 20)
        XCTAssertEqual(shown(position), before)

        changeUp()
        app.buttons["keepNext"].firstMatch.safeTap(app)
        let total = { (s: String) in Int(s.split(separator: " ")[2]) ?? 0 }
        let fewer = NSPredicate { _, _ in !position.exists || total(shown(position)) == total(before) - 1 }
        wait(for: [XCTNSPredicateExpectation(predicate: fewer, object: nil)], timeout: 20)
        XCTAssertFalse(changed.exists, "the next note is not changed")
    }

    /// Show the score sits on its own band: scrolled to the end, the key buttons are fully above it
    /// and can be pressed, so nothing (and no focused control) is hidden behind it (WCAG 2.4.11).
    func testShowScoreBandLeavesKeyButtonsClear() throws {
        app.terminate()
        app.launchArguments = ["-reset", "-fixture-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-screen", "output"]
        launchApp()
        let show = app.descendants(matching: .any)["showScore"].firstMatch
        XCTAssertTrue(show.waitForExistence(timeout: 20))
        let lower = app.descendants(matching: .any)["keyLower"].firstMatch
        let higher = app.descendants(matching: .any)["keyHigher"].firstMatch
        XCTAssertTrue(higher.waitForExistence(timeout: 5))
        #if os(iOS)
        app.scrollViews.firstMatch.swipeUp()
        app.scrollViews.firstMatch.swipeUp()
        #endif
        // the band starts one spacing step (12 pt) above the button
        let top = show.frame.minY - 12
        for button in [lower, higher] {
            XCTAssertTrue(button.isHittable, "\(button.identifier) can be pressed")
            XCTAssertLessThanOrEqual(button.frame.maxY, top + 0.5, "\(button.identifier) ends above the Show the score band")
        }
        XCTAssertTrue(show.isHittable)
        higher.safeTap(app)
        XCTAssertTrue(show.isHittable)
    }

    /// "Listen to this bar" becomes "Stop" in the same place and size, and Stop ends it.
    func testListenInReviewCanBeStopped() throws {
        app.terminate()
        app.launchArguments = ["-reset", "-fixture-service", "-fast", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-screen", "review"]
        launchApp()
        let listen = app.buttons["listenBar"].firstMatch
        XCTAssertTrue(listen.waitForExistence(timeout: 60))
        XCTAssertEqual(listen.label, "Listen to this bar")
        let frame = listen.frame
        listen.safeTap(app)
        XCTAssertTrue(NSPredicate(format: "label == 'Stop'").evaluate(with: listen) || app.buttons["Stop"].waitForExistence(timeout: 3))
        XCTAssertEqual(listen.frame, frame, "no layout jump")
        listen.safeTap(app)
        let back = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'Listen to this bar'"), object: listen)
        wait(for: [back], timeout: 5)
    }

    /// The connection row: words and an icon, and the way forward for each state.
    func testConnectionRowStates() throws {
        for (arg, text, action) in [("offline", "Not connected", "connectionConnect"), ("needs-pairing", "no longer recognises", "connectionPairAgain"),
                                    ("connected", "Connected to Brasscribe on Studio Mac", nil), ("reconnecting", "Looking for Brasscribe on Studio Mac", nil)] {
            app.terminate()
            app.launchArguments = ["-reset", "-ApplePersistenceIgnoreState", "YES", "-skip-first-run", "-connection", arg]
            launchApp()
            let row = app.descendants(matching: .any)["connectionStatusText"].firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 20), arg)
            XCTAssertTrue(row.label.contains(text), "\(arg): \(row.label)")
            if let action { XCTAssertTrue(app.buttons[action].firstMatch.exists, arg) }
            else { XCTAssertFalse(app.buttons["connectionConnect"].firstMatch.exists, arg) }
        }
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
        app.safeTypeKey(XCUIKeyboardKey.rightArrow.rawValue, modifierFlags: [])
        app.safeTypeKey(XCUIKeyboardKey.rightArrow.rawValue, modifierFlags: [])
        XCTAssertEqual(position.value as? String, "3")
        app.safeTypeKey(XCUIKeyboardKey.leftArrow.rawValue, modifierFlags: [])
        XCTAssertEqual(position.value as? String, "2")
        app.safeTypeKey(".", modifierFlags: [])
        // iOS reports the slider's accessibility value text, macOS its number
        let raised = NSPredicate { _, _ in
            if let s = speed.value as? String { return s.contains("105") }
            if let n = speed.value as? NSNumber { return n.doubleValue == 105 }
            return false
        }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: raised, object: nil)], timeout: 3), .completed,
                       "\(String(describing: speed.value))")
        app.safeTypeKey(" ", modifierFlags: [])
        XCTAssertTrue(app.buttons["Pause"].waitForExistence(timeout: 5))
        app.safeTypeKey(" ", modifierFlags: [])
        XCTAssertTrue(app.buttons["Play"].waitForExistence(timeout: 5))
    }

    /// A recorded solo becomes a readable part with no computer: on-device models and the core.
    func testOfflineSoloToReadablePart() throws {
        guard let clip = dataDir()?.appending(path: "runs/apple/entertainer-tpt1-30s.wav") else { throw XCTSkip("needs data/") }
        let models = ProcessInfo.processInfo.environment["BRASSCRIBE_MODELS"]
            ?? clip.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                .deletingLastPathComponent().appending(path: "models/converted").path
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
        solo.safeTap(app)
        app.descendants(matching: .any)["transcribe"].firstMatch.safeTap(app)
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
        // a test pattern with a tone: ffmpeg -f lavfi -i testsrc2=size=640x360:rate=25 -f lavfi -i sine=frequency=392
        //   -t 20 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest data/runs/apple/test-pattern-20s.mp4
        guard let video = dataDir()?.appending(path: "runs/apple/test-pattern-20s.mp4"), FileManager.default.fileExists(atPath: video.path) else {
            throw XCTSkip("needs data/runs/apple/test-pattern-20s.mp4")
        }
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
        pip.safeTap(app)
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
        next.safeTap(app); next.safeTap(app)
        let position = app.descendants(matching: .any)["position"]
        XCTAssertEqual(position.value as? String, "3")
        app.buttons["previousBar"].safeTap(app)
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
        picker.safeTap(app)
        #if os(macOS)
        app.menuItems["Solo Cornet (you)"].safeTap(app)
        #else
        app.descendants(matching: .any)["Solo Cornet (you)"].firstMatch.safeTap(app)
        #endif

        let solo = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'staff-0-' AND label CONTAINS 'Solo Cornet'")).firstMatch
        XCTAssertTrue(solo.waitForExistence(timeout: 30), "the solo cornet alone should still engrave")
        XCTAssertEqual(app.state, .runningForeground)

        picker.safeTap(app)
    #if os(macOS)
    app.menuItems["All parts"].safeTap(app)
    #else
        app.descendants(matching: .any)["All parts"].firstMatch.safeTap(app)
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
            let line = "AUDIT \(issue.auditType) | \(issue.compactDescription) | \(issue.element?.identifier ?? "") \(issue.element?.label ?? "") type=\(issue.element?.elementType.rawValue ?? 0) frame=\(issue.element?.frame ?? .zero) \(issue.detailedDescription.prefix(200))"
            issues.append(line)
            print(line)
            // Not ours: the system menu bar, a tooltip left up by the resting pointer (AppKit draws
            // `.help` text in a help tag without a description; the text is the button's help),
            // and SwiftUI's unlabeled hosting groups: the window group, and on macOS the sidebar
            // and inspector columns (groups as tall as the window). All are listed in the report.
            let window = self.app.windows.firstMatch.frame
            let f = issue.element?.frame ?? .zero
            let systemOwned = issue.element?.elementType == .menuBar || issue.element?.elementType == .helpTag || f.minY == 0
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

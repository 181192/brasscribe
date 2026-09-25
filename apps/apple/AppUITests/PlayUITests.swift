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

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard let dir = fixtureDir() else { throw XCTSkip("golden Mikkel fixture not found") }
        app = XCUIApplication()
        app.launchArguments = ["-reset", "-open-demo-score"]
        app.launchEnvironment["BRASSCRIBE_FIXTURES"] = dir
        if let sf = soundFont() { app.launchEnvironment["BRASSCRIBE_SOUNDFONT"] = sf }
        app.launch()
    }

    /// Loads the Mikkel score, checks the notation exposes bars to VoiceOver, and plays
    /// until the transport has moved past bar 1.
    func testLoadMikkelAndPlayABar() throws {
        let play = app.buttons["playPause"]
        XCTAssertTrue(play.waitForExistence(timeout: 30))
        let staff = app.descendants(matching: .any)["staff-0-1"]
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

    func testNextBarAndLoopWithoutDragging() throws {
        let next = app.buttons["nextBar"]
        XCTAssertTrue(next.waitForExistence(timeout: 30))
        next.tap(); next.tap()
        let position = app.descendants(matching: .any)["position"]
        XCTAssertEqual(position.value as? String, "3")
        app.buttons["previousBar"].tap()
        XCTAssertEqual(position.value as? String, "2")
    }

    /// Xcode's accessibility audit on the score screen. Issues are recorded, not fatal,
    /// so the report lists them all; the test fails only on missing labels or
    /// unreachable elements.
    func testAccessibilityAudit() throws {
        XCTAssertTrue(app.buttons["playPause"].waitForExistence(timeout: 30))
        XCTAssertTrue(app.descendants(matching: .any)["staff-0-1"].waitForExistence(timeout: 60))
        var issues: [String] = []
        var blocking: [String] = []
        try app.performAccessibilityAudit { issue in
            let line = "AUDIT \(issue.auditType) | \(issue.compactDescription) | \(issue.element?.identifier ?? "") \(issue.element?.label ?? "") type=\(issue.element?.elementType.rawValue ?? 0) frame=\(issue.element?.frame ?? .zero)"
            issues.append(line)
            print(line)
            // Not ours: the system menu bar and SwiftUI's unlabeled window hosting group
            // (a group spanning the whole window). Both are listed in the report.
            let window = self.app.windows.firstMatch.frame
            let systemOwned = issue.element?.elementType == .menuBar || (issue.element?.frame.minY ?? 1) == 0
                || (issue.element?.elementType == .group && (issue.element?.frame.width ?? 0) >= window.width - 1)
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

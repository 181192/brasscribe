import AppKit
@testable import BandroomKit
import XCTest

final class AppearanceTests: XCTestCase {
    private func defaults(_ value: String?) -> UserDefaults {
        let d = UserDefaults(suiteName: "AppearanceTests-\(UUID().uuidString)")!
        if let value { d.set(value, forKey: AppearanceChoice.defaultsKey) }
        return d
    }

    func testMissingOrUnknownValueMatchesSystem() {
        XCTAssertEqual(AppearanceChoice(stored: nil), .system)
        XCTAssertEqual(AppearanceChoice(stored: "sepia"), .system)
        XCTAssertEqual(AppearanceChoice.current(defaults: defaults(nil), environment: [:]), .system)
    }

    func testStoredValuesRoundTrip() {
        for choice in AppearanceChoice.allCases {
            XCTAssertEqual(AppearanceChoice(stored: choice.rawValue), choice)
            XCTAssertEqual(AppearanceChoice.current(defaults: defaults(choice.rawValue), environment: [:]), choice)
        }
    }

    func testAppearanceMapping() {
        XCTAssertNil(AppearanceChoice.system.appearanceName)
        XCTAssertEqual(AppearanceChoice.light.appearanceName, .aqua)
        XCTAssertEqual(AppearanceChoice.dark.appearanceName, .darkAqua)
    }

    func testEnvironmentOverrideWinsForScreenshots() {
        XCTAssertEqual(AppearanceChoice.current(defaults: defaults("light"), environment: ["BANDROOM_APPEARANCE": "dark"]), .dark)
        XCTAssertEqual(AppearanceChoice.current(defaults: defaults("dark"), environment: ["BANDROOM_APPEARANCE": "bogus"]), .dark)
    }
}

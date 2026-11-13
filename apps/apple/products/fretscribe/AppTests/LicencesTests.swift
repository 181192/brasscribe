import Foundation
import Testing
@testable import Fretscribe

/// The file of third-party licences the app ships (licences/dist, written by scripts/licences.py), as About shows it.
@MainActor struct LicencesTests {
    @Test func aFileIsShownAsHeadingsParagraphsAndDividers() {
        let file = "Third-party licences: An app\n\nWhat this is.\n\nContents\n\n- A font (OFL-1.1)\n\n"
            + "\(ThirdPartyLicencesView.rule)\n\nA font\nhttps://example.org/font\nLicence: OFL-1.1\n\nCopyright someone.\n\n"
            + "\(ThirdPartyLicencesView.rule)\n\nLicence text: OFL-1.1\n\nFirst paragraph.\n\nSecond paragraph.\n"
        #expect(ThirdPartyLicencesView.parts(of: file) == [
            .paragraph("What this is."), .heading("Contents"), .paragraph("- A font (OFL-1.1)"),
            .rule, .heading("A font"), .paragraph("https://example.org/font\nLicence: OFL-1.1"), .paragraph("Copyright someone."),
            .rule, .heading("Licence text: OFL-1.1"), .paragraph("First paragraph."), .paragraph("Second paragraph."),
        ])
    }

    @Test func theAppCarriesItsOwnFileWithTheTextsItNames() throws {
        let url = try #require(Bundle.main.url(forResource: "fretscribe-apple", withExtension: "txt"))
        let parts = ThirdPartyLicencesView.parts(of: try String(contentsOf: url, encoding: .utf8))
        #expect(parts.contains(.heading("alphaTab")) && parts.contains(.heading("Licence text: MPL-2.0")))
        #expect(parts.contains { if case .paragraph(let p) = $0 { p.hasPrefix("Mozilla Public License Version 2.0") } else { false } })
    }
}

import AVFoundation
import CoreGraphics
import Foundation
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// Sheet music from a picture, a photo or a PDF: the pages in hand, and what goes wrong in the player's words.
@MainActor
struct SheetMusicTests {
    static let png = Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13])

    func file(_ name: String, _ data: Data) throws -> URL {
        let dir = FileManager.default.temporaryDirectory.appending(path: "sheet-\(UUID().uuidString)", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appending(path: name)
        try data.write(to: url)
        return url
    }

    /// A PDF of `pages` blank pages.
    func pdf(_ name: String, pages: Int) throws -> URL {
        let url = try file(name, Data())
        var box = CGRect(x: 0, y: 0, width: 595, height: 842)
        let ctx = try #require(CGContext(url as CFURL, mediaBox: &box, nil))
        for _ in 0..<pages { ctx.beginPDFPage(nil); ctx.endPDFPage() }
        ctx.closePDF()
        return url
    }

    /// Pages are kept in the order chosen, can be moved and removed, and what is no page is left out and said.
    @Test func thePagesAreKeptInOrderAndWhatIsNoPageIsLeftOut() async throws {
        let list = PageList()
        await list.add([try file("one.png", Self.png), try file("take.wav", Data("RIFF\0\0\0\0WAVEfmt ".utf8)), try pdf("two.pdf", pages: 1)])
        #expect(list.pages.map(\.name) == ["one.png", "two.pdf"])
        #expect(list.status == String(localized: "One file is not a picture or a PDF, so it was left out."))
        list.move(1, by: -1)
        #expect(list.pages.map(\.name) == ["two.pdf", "one.png"])
        #expect(list.status == String(localized: "Page 2 is now page 1."))
        list.move(0, by: -1)
        #expect(list.pages.map(\.name) == ["two.pdf", "one.png"])
        list.remove(0)
        #expect(list.pages.map(\.name) == ["one.png"])
        list.clear()
        #expect(list.pages.isEmpty)
    }

    @Test func noMoreThanFortyPagesAreTaken() async throws {
        let list = PageList()
        let page = try file("p.png", Self.png)
        await list.add(Array(repeating: page, count: Pages.maxPages + 2))
        #expect(list.pages.count == Pages.maxPages)
        #expect(list.status == String(localized: "At most 40 pages can be read at once, every page of a PDF counted. The rest were left out."))
    }

    /// Every page of a PDF counts: a 60-page PDF is stopped on the device, before anything is sent, and a PDF that
    /// cannot be opened is left out with why.
    @Test func everyPageOfAPDFCountsBeforeAnythingIsSent() async throws {
        let list = PageList()
        await list.add([try pdf("hymns.pdf", pages: 60)])
        #expect(list.pages.isEmpty)
        #expect(list.status == String(localized: "At most 40 pages can be read at once, every page of a PDF counted. The rest were left out."))
        await list.add([try pdf("first.pdf", pages: 30), try file("p.png", Self.png), try pdf("second.pdf", pages: 10)])
        #expect(list.pages.map(\.name) == ["first.pdf", "p.png"])
        #expect(list.pageCount == 31)
        await list.add([try file("broken.pdf", Data("%PDF-1.7 and then nothing".utf8))])
        #expect(list.status == String(localized: "A PDF that is locked with a password, or damaged, can't be read, so it was left out."))
        list.clear()
    }

    /// The camera opens when allowed, the system asks the first time, and a refusal leads to Settings with why.
    @Test func aRefusedCameraLeadsToSettings() {
        #expect(CameraAccess.of(.authorized) == .open)
        #expect(CameraAccess.of(.notDetermined) == .ask)
        #expect(CameraAccess.of(.denied) == .refused)
        #expect(CameraAccess.of(.restricted) == .refused)
        #expect(CameraAccess.refusedWords.contains("Settings"))
    }

    /// Every refusal and every failure of a read has its own words, and none is the computer's English.
    @Test func everyRefusalAndFailureIsSaidInTheAppsWords() {
        for refused in Pages.Refused.allCases {
            let e = TranscriptionError.http(415, #"{"code":"\#(refused.rawValue)","detail":"engine words"}"#)
            #expect(PagesWords.of(e) == PagesWords.words(refused))
        }
        for failure in Pages.Failure.allCases {
            let e = TranscriptionError.jobFailed("read: StageFailed: read: \(failure.engineWords)")
            #expect(PagesWords.of(e) == PagesWords.words(failure))
            #expect(PagesWords.title(e) != nil)
        }
        #expect(PagesWords.title(TranscriptionError.jobFailed("read: StageFailed: read: no notes were found on the page"))
                == String(localized: "No notes were found on the page"))
        #expect(PagesWords.of(TranscriptionError.unreachable("down")) == nil)
        #expect(Set(Pages.Refused.allCases.map(PagesWords.words)).count == Pages.Refused.allCases.count)
    }

    /// A picture or a PDF opened or shared goes to the pages, not to "What is this?".
    @Test func aPictureOpenedGoesToThePages() async throws {
        let app = AppModel()
        app.pageList.clear()
        await app.accept(url: try file("Hymn.png", Self.png))
        #expect(app.path == [.pages])
        #expect(app.pageList.pages.map(\.name) == ["Hymn.png"])
        app.pageList.clear()
    }
}

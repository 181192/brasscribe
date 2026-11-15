import CoreGraphics
import Foundation
import Testing
import TabKit
import TranscriptionKit
@testable import Fretscribe

/// Sheet music from a picture, a photo or a PDF, read into a tab for the player's instrument.
@MainActor
struct SheetMusicTests {
    /// The pages are read for the player's instrument, tuning and reading; nothing was recorded, so no recording kind.
    @Test func pagesAreReadForTheInstrument() {
        let fields = FretscribeModel.pageFields(instrument: YourInstrument(.bass5, tuning: "drop-a", reads: .tabAndNotation))
        let sent = Dictionary(uniqueKeysWithValues: fields.map { ($0.name, $0.value) })
        #expect(sent == ["instrument": "bass-5", "tuning": "drop-a", "layout": "tab-and-notation"])
        #expect(FretscribeModel.sheetProfile == "sheet-tab")
    }

    /// A picture opened or shared goes to the pages; a MusicXML file is still refused, with where pictures go.
    @Test func aPictureOpenedGoesToThePages() async throws {
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-sheet-\(UUID().uuidString)")!)
        model.pageList = PageList(folder: FileManager.default.temporaryDirectory.appending(path: "fs-pages-\(UUID().uuidString)"))
        let dir = FileManager.default.temporaryDirectory.appending(path: "fs-sheet-\(UUID().uuidString)", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let page = dir.appending(path: "Riff.pdf")
        var box = CGRect(x: 0, y: 0, width: 595, height: 842)
        let ctx = try #require(CGContext(page as CFURL, mediaBox: &box, nil))
        ctx.beginPDFPage(nil); ctx.endPDFPage(); ctx.closePDF()
        await model.accept(url: page)
        #expect(model.path == [.pages])
        #expect(model.pageList.pages.map(\.name) == ["Riff.pdf"])
        model.pageList.clear()
    }

    /// A tab read from pages says so, and is kept as one.
    @Test func aTabFromPagesIsKeptAsOne() throws {
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-sheet-\(UUID().uuidString)", directoryHint: .isDirectory)
        setenv("SCRIBE_SONGS", songs.path, 1)
        defer { try? FileManager.default.removeItem(at: songs) }
        let song = try TabSong.create(title: "Riff", jobID: "j1", musicXML: Data("<score-partwise/>".utf8), tab: nil, recording: nil, fromPages: true)
        #expect(TabSong.loadAll().first { $0.id == song.id }?.fromPages == true)
    }
}

import Foundation
import Testing
@testable import NotationKit

func goldenDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return URL(fileURLWithPath: env) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

@Test func verovioLoads() throws {
    let tk = try #require(VerovioToolkit())
    #expect(tk.loadData(#"<?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>C</part-name></score-part></part-list><part id="P1"><measure number="1"><note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>"#))
    #expect(tk.pageCount == 1)
    #expect(tk.renderToSVG(page: 1).contains("<svg"))
}

@Test(.enabled(if: goldenDir() != nil)) func dumpMikkelPage() throws {
    let tk = try #require(VerovioToolkit())
    let xml = try String(contentsOf: goldenDir()!.appending(path: "brass-band.musicxml"), encoding: .utf8)
    tk.setOptions(["pageWidth": 2100, "pageHeight": 2970, "scale": 40, "adjustPageHeight": true])
    #expect(tk.loadData(xml))
    #expect(tk.pageCount > 5)
    if let out = ProcessInfo.processInfo.environment["NOTATION_DUMP"] {
        try tk.renderToSVG(page: 1).write(toFile: out, atomically: true, encoding: .utf8)
    }
}

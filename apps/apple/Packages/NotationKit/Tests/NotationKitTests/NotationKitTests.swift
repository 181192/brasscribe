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

/// One mark per note: Verovio's ink "?" is removed, and the note colour gives the level
/// (the app draws the boxed "?" for very uncertain notes).
@Test func uncertainNotesKeepTheirLevelAndLoseTheInkQuestionMark() throws {
    let xml = """
    <?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>C</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
    <direction placement="above"><direction-type><words enclosure="rectangle">?</words></direction-type></direction>
    <note color="#B04A00"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
    <direction placement="above"><direction-type><words>?</words></direction-type></direction>
    <note color="#0063A6"><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
    <note><pitch><step>E</step><octave>5</octave></pitch><duration>2</duration><type>half</type></note>
    </measure></part></score-partwise>
    """
    #expect(!ScoreRenderer.removingQuestionMarks(xml).contains(">?</words>"))
    let r = try #require(ScoreRenderer(musicXML: xml))
    #expect(r.apply(.init()))
    let page = try #require(r.page(1))
    #expect(Set(r.uncertainLevels.values) == [.uncertain, .veryUncertain])
    #expect(r.uncertainLevels.count == 2)
    #expect(page.svg.ids(ofClass: "dir").isEmpty, "no ink question mark left")
    // five lines, four staff spaces of 7.2 px at zoom 1 (Verovio scale 40)
    let lines = try #require(page.staffLines.values.first)
    #expect(abs(lines.height - 28.8) < 2, "\(lines)")
}

private func tiesAndTrills() -> String? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let f = dir.appending(path: "apps/fixtures/ties-and-trills.musicxml")
        if let s = try? String(contentsOf: f, encoding: .utf8) { return s }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// Verovio draws each trill mark (SMuFL ornamentTrill), the accidental-mark above it (sharp, flat) and the wavy
/// line of a trill tied over the barline (apps/fixtures/ties-and-trills.musicxml: per brass part, bars 4-8).
@Test(.enabled(if: tiesAndTrills() != nil)) func trillsShowTheirMarkAccidentalAndWavyLine() throws {
    let tk = try #require(VerovioToolkit())
    #expect(tk.loadData(try #require(tiesAndTrills())))
    let svg = tk.renderToSVG(page: 1)
    let glyphs: [[String]] = svg.matches(of: /<g id="[^"]*" class="trill"[^>]*>(.*?)<\/g>/.dotMatchesNewlines()).map { m in
        String(m.1).matches(of: /href="#(E[0-9A-F]{3})/).map { String($0.1) }
    }
    #expect(glyphs.count == 11)
    #expect(glyphs.allSatisfy { $0.contains("E566") }, "tr")
    #expect(glyphs.filter { $0.contains("E262") }.count == 2, "sharp above bar 6's trill (cornet, trombone)")
    #expect(glyphs.filter { $0.contains("E260") }.count == 2, "flat above bar 7's trill")
    #expect(glyphs.filter { $0.contains("E59D") }.count == 2, "wavy line over the tied trill")
}

@Test(.enabled(if: goldenDir() != nil)) func reviewSnippetShowsOnePartAndTheChosenBars() throws {
    let xml = try String(contentsOf: goldenDir()!.appending(path: "brass-band.musicxml"), encoding: .utf8)
    let page = try #require(ScoreRenderer.snippet(musicXML: xml, partID: "P2", bars: 14...15, width: 640))
    #expect(page.measureIDs.count == 2)
    #expect(page.staffLines.count == 2, "one staff per bar of the one part")
    #expect(page.svg.size.width <= 660)
}

private func oldHundredth() -> String? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<8 {
        let f = dir.appending(path: "apps/fixtures/old-hundredth/brass-band.musicxml")
        if let s = try? String(contentsOf: f, encoding: .utf8) { return s }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// The music stand engraves a fixed number of bars on every system, as one long page that it
/// pages through itself.
@Test(.enabled(if: oldHundredth() != nil)) func standLayoutHasFixedBarsPerSystem() throws {
    let xml = try #require(oldHundredth())
    let r = try #require(ScoreRenderer(musicXML: xml))
    for bars in [3, 4] {
        for parts: Set<String>? in [["P2"], nil] {
            #expect(r.apply(.init(width: 390, zoom: 0.8, parts: parts, height: 700, barsPerSystem: bars)))
            #expect(r.pageCount == 1)
            let page = try #require(r.page(1))
            let counts = page.systems.map(\.measureIDs.count)
            print("STAND \(bars) bars, parts \(parts ?? []): \(page.systems.count) systems \(counts), page \(page.svg.size)")
            #expect(counts.dropLast().allSatisfy { $0 == bars })
            #expect(counts.reduce(0, +) == r.measureIDs.count)
            #expect(page.systems.count >= 2)
            #expect(zip(page.systems, page.systems.dropFirst()).allSatisfy { $0.frame.maxY <= $1.frame.minY + 1 })
        }
    }
    #expect(ScoreRenderer.breakingSystems(every: 2, in: #"<part id="P1"><measure number="1"></measure><measure number="2"><print new-page="yes"/></measure><measure number="3"></measure></part>"#)
        == #"<part id="P1"><measure number="1"></measure><measure number="2"><print/></measure><measure number="3"><print new-system="yes"/></measure></part>"#)
}

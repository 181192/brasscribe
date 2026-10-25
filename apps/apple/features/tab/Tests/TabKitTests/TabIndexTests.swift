import Foundation
import Testing
@testable import TabKit

/// The repository's root, found from this file.
let repositoryRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../../..").standardizedFileURL

/// A fixture's text (apps/fixtures).
func fixtureText(_ name: String) throws -> String { String(decoding: try fixture(name), as: UTF8.self) }

/// A fixture's tab.json.
func fixtureTab(_ name: String) throws -> TabData { try JSONDecoder().decode(TabData.self, from: try fixture("\(name)/tab.json")) }

func count(_ pattern: String, in text: String) -> Int {
    try! NSRegularExpression(pattern: pattern).numberOfMatches(in: text, range: NSRange(text.startIndex..., in: text))
}

/// Which drawn note is which note of the tab's data: the index read from tab.musicxml (`TabIndex`), on the recorded
/// fixtures (apps/fixtures/bass-line and bass-line-marks) and on small documents written here as the core writes them
/// (core/targets/fretted/README.md).
struct TabIndexTests {
    /// A note piece as the core writes it.
    func note(_ index: Int, _ step: String, _ octave: Int, _ duration: Int, _ string: Int? = nil, _ fret: Int? = nil, alter: Int? = nil,
              chord: Bool = false, staff: Int? = nil, tie: String = "", confidence: String? = nil) -> String {
        let ties = tie.split(separator: " ")
        return """
        <note\(confidence != nil ? " color=\"#9A5200\"" : "")>
          \(chord ? "<chord />" : "")
          <pitch><step>\(step)</step>\(alter.map { "<alter>\($0)</alter>" } ?? "")<octave>\(octave)</octave></pitch>
          <duration>\(duration)</duration>
          \(ties.map { "<tie type=\"\($0)\" />" }.joined())
          <voice>1</voice><type>quarter</type>
          \(staff.map { "<staff>\($0)</staff>" } ?? "")
          \(confidence != nil ? "<notehead color=\"#9A5200\">normal</notehead>" : "")
          <notations>
            \(ties.map { "<tied type=\"\($0)\" />" }.joined())
            \(string.map { "<technical><string>\($0)</string><fret>\(fret!)</fret></technical>" } ?? "")
          </notations>
          <?fretted-note \(index)?>
          \(confidence.map { "<?fretted-confidence \($0)?>" } ?? "")
        </note>
        """
    }

    func rest(_ duration: Int, staff: Int? = nil) -> String {
        "<note><rest /><duration>\(duration)</duration><voice>1</voice>\(staff.map { "<staff>\($0)</staff>" } ?? "")</note>"
    }

    func words(_ text: String, staff: Int? = nil, boxed: Bool = false) -> String {
        "<direction placement=\"above\"><direction-type><words\(boxed ? " enclosure=\"rectangle\"" : "")>\(text)</words></direction-type>\(staff.map { "<staff>\($0)</staff>" } ?? "")</direction>"
    }

    func backup(_ duration: Int) -> String { "<backup><duration>\(duration)</duration></backup>" }

    /// A part of `measures` in 4/4 with 24 divisions: a tab staff alone, a notation staff alone, or the pair (notation above).
    func document(_ layout: String, _ measures: String..., first: String = "1", header: String = "Standard: E A D G") -> String {
        let clefs = switch layout {
        case "tab": "<clef><sign>TAB</sign><line>5</line></clef>"
        case "notation": "<clef><sign>F</sign><line>4</line><clef-octave-change>-1</clef-octave-change></clef>"
        default: "<staves>2</staves><clef number=\"1\"><sign>F</sign><line>4</line></clef><clef number=\"2\"><sign>TAB</sign><line>5</line></clef>"
        }
        let attributes = "<attributes><divisions>24</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>\(clefs)</attributes>"
        let body = measures.enumerated().map { i, m in
            let number = i == 0 ? first : String(Int(first)! + i)
            return "<measure number=\"\(number)\">\(i == 0 ? attributes + words(header, staff: layout == "pair" ? 1 : nil) : "")\(m)</measure>"
        }.joined(separator: "\n")
        return """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
        <score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Bass</part-name></score-part></part-list>
        <part id="P1">\(body)</part></score-partwise>
        """
    }

    @Test func theRecordedLineHasEveryNoteOnceWhereItIsWritten() throws {
        let tab = try fixtureTab("bass-line")
        let index = TabIndex.parse(musicXML: try fixtureText("bass-line/tab.musicxml"))
        #expect(index.bars == 15)
        #expect(index.staves == 1)
        #expect(index.tabStaff == 0)
        #expect(index.header == "Standard: E A D G")
        #expect(index.tuningName == "Standard")
        #expect(index.capo == 0)
        #expect(index.tempo == 100)
        // Every note of the data is on the page, once, with the string and fret the data gives it.
        #expect(index.pieces.map(\.note) == Array(tab.notes.indices))
        for (i, n) in tab.notes.enumerated() {
            let pieces = index.of(i)
            try #require(pieces.count == 1, "note \(i)")
            let piece = pieces[0]
            #expect([n.pitch, n.string, n.fret] == [piece.pitch, piece.string, piece.fret], "note \(i)")
            #expect(piece.first)
            #expect(piece.confidence == nil)
            // The line is in 2/4 with 24 ticks to the beat: the bar and the place in it follow from the start.
            #expect(piece.bar == n.start / 48 && piece.onset == (n.start % 48) * TabIndex.ticks / 24, "note \(i)")
        }
        #expect(index.of(3).first?.string == 3)
        #expect(index.noPlace.isEmpty)
    }

    @Test func theLineWithNotesToCheckHasItsNotesAndItsNoPlace() throws {
        let index = TabIndex.parse(musicXML: try fixtureText("bass-line-marks/tab.musicxml"))
        // The doubtful note carries its confidence; the note below the lowest string is a rest with boxed words, and has no index.
        let doubtful = try #require(index.of(5).first?.confidence)
        #expect(abs(doubtful - 0.31) < 1e-9)
        #expect(index.of(12).isEmpty)
        #expect(index.noPlace == [TabNoPlace(staff: 0, bar: 6, barNumber: "7", onset: 960, names: ["D1"], beat: 2)])
        // The last note crosses the beat and the bar line: three tied pieces, all with its index, the first with the confidence.
        let tied = index.of(28)
        #expect(tied.map { [$0.bar, $0.onset] } == [[14, 480], [14, 960], [15, 0]])
        #expect(tied.map(\.first) == [true, false, false])
        #expect(tied.map(\.confidence) == [0.22, nil, nil])
    }

    @Test func singleNotesAndAChordAreFoundByMeasureStartAndString() {
        let xml = document("tab",
            note(0, "E", 1, 24, 4, 0) + words("?") + note(1, "A", 1, 24, 3, 0, confidence: "0.20") + note(2, "E", 2, 24, 2, 2, chord: true, confidence: "0.35") +
                note(3, "D", 2, 24, 2, 0, alter: -1) + rest(24),
            note(4, "G", 1, 96, 4, 3))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.bars == 2)
        #expect(index.pieces.map(\.onset) == [0, 960, 960, 1920, 0])
        #expect(index.pieces.map(\.bar) == [0, 0, 0, 0, 1])
        #expect(index.pieces.map(\.beat) == [1, 2, 2, 3, 1])
        // D-flat is spelled as the page spells it, and sounds a semitone under D.
        let flat = index.of(3)[0]
        #expect(flat.step == "D" && flat.alter == -1 && flat.pitch == 37)
        #expect(index.of(1)[0].confidence == 0.2 && index.of(2)[0].confidence == 0.35)
    }

    @Test func aNoteTiedAcrossTheBarLineIsWrittenInPiecesThatKeepItsIndex() {
        let xml = document("tab",
            rest(72) + words("?") + note(0, "A", 1, 24, 3, 0, tie: "start", confidence: "0.10"),
            note(0, "A", 1, 48, 3, 0, tie: "stop start") + rest(48),
            note(0, "A", 1, 24, 3, 0, tie: "stop") + note(1, "E", 1, 72, 4, 0))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.of(0).map { [$0.bar, $0.onset] } == [[0, 2880], [1, 0], [2, 0]])
        #expect(index.of(0).map(\.first) == [true, false, false])
        #expect(index.of(0)[0].beat == 4)
    }

    @Test func aNoteMovedToTheGridAndSplitIntoPiecesKeepsItsIndex() {
        // The page writes a note that starts between two triplet sixteenths on the grid, as two tied pieces across the beat.
        let xml = document("tab",
            note(0, "E", 1, 20, 4, 0) + words("?") + note(1, "G", 1, 4, 4, 3, tie: "start", confidence: "0.30") +
                note(1, "G", 1, 20, 4, 3, tie: "stop") + rest(52))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.of(1).map(\.onset) == [800, 960])
        #expect(index.of(1).map(\.first) == [true, false])
    }

    @Test func inAPairOfStavesBothStavesAreRead() {
        // Notation above (staff 1), tab below (staff 2). The low D has no place: the notation staff writes it, with its
        // index; the tab staff has a rest and the boxed words.
        let xml = document("pair",
            note(0, "E", 1, 24, staff: 1) + note(1, "D", 1, 24, staff: 1) + note(2, "A", 1, 48, staff: 1, confidence: "0.25") + backup(96) +
                note(0, "E", 1, 24, 4, 0, staff: 2) + words("! D1", staff: 2, boxed: true) + rest(24, staff: 2) + words("?", staff: 2) +
                note(2, "A", 1, 48, 3, 0, staff: 2, confidence: "0.25"))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.staves == 2)
        #expect(index.tabStaff == 1)
        #expect(index.markStaff == 1)
        #expect(index.header == "Standard: E A D G")
        #expect(index.of(0).map(\.staff) == [0, 1])
        #expect(index.of(1).map(\.staff) == [0])
        #expect(index.of(2).map(\.string) == [nil, 3])
        #expect(index.noPlace == [TabNoPlace(staff: 1, bar: 0, barNumber: "1", onset: 960, names: ["D1"], beat: 2)])
    }

    @Test func inTheNotationLayoutTheNotesHaveNoStrings() {
        let xml = document("notation", words("! D1", boxed: true) + note(0, "D", 1, 48) + words("?") + note(1, "A", 1, 48, confidence: "0.25"))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.tabStaff == nil)
        #expect(index.markStaff == 0)
        #expect(index.noPlace.map(\.onset) == [0])
        #expect(index.of(1).map(\.onset) == [1920])
        #expect(index.of(1)[0].string == nil)
    }

    @Test func aPickupIsMeasureNoughtAndBarsAreCountedAsWritten() {
        let xml = document("tab", words("?") + note(0, "E", 1, 24, 4, 0, confidence: "0.10"), note(1, "A", 1, 96, 3, 0),
                           first: "0", header: "Drop D: D A D G, Capo 3")
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.tuningName == "Drop D")
        #expect(index.capo == 3)
        // alphaTab's first bar is the pickup. Its one quarter note is the fourth beat of the bar it leads into.
        let first = index.of(0)[0]
        #expect(first.bar == 0 && first.barNumber == "0")
        #expect(first.pickup)
        #expect(first.beat == 4)
        #expect(index.measures[0] == TabMeasure(number: "0", length: TabIndex.ticks, beats: 4, beatTicks: TabIndex.ticks, pickup: true))
        #expect(!index.of(1)[0].pickup)
        #expect(index.of(1)[0].bar == 1 && index.of(1)[0].barNumber == "1")
    }

    @Test func aBeatIsCountedInTheTimeSignatureInForce() {
        // Two bars of 4/4, then 6/8: the third bar's notes are counted in eighths.
        let six = "<attributes><time><beats>6</beats><beat-type>8</beat-type></time></attributes>"
        let xml = document("tab",
            rest(72) + words("?") + note(0, "E", 1, 24, 4, 0, confidence: "0.10"),
            rest(96),
            six + rest(36) + words("?") + note(1, "A", 1, 36, 3, 0, confidence: "0.10"))
        let index = TabIndex.parse(musicXML: xml)
        #expect(index.pieces.map { [$0.bar, $0.beat] } == [[0, 4], [2, 4]])
        #expect(index.pieces.map(\.pickup) == [false, false])
        #expect(index.measures.map(\.beats) == [4, 4, 6])
        #expect(index.measures[2].length == 3 * TabIndex.ticks)
    }

    @Test func theRendererGetsThePageWithoutItsHeaderWords() throws {
        let xml = try fixtureText("bass-line-marks/tab.musicxml")
        let index = TabIndex.parse(musicXML: xml)
        let page = TabIndex.forRenderer(xml, header: index.header)
        #expect(!page.contains("Standard: E A D G"))
        #expect(page.contains("<metronome>"))
        #expect(count("<direction ", in: xml) - 4 == count("<direction ", in: page))
        #expect(index.pieces == TabIndex.parse(musicXML: page).pieces)
        // Words that are not the header stay.
        let ring = document("tab", words("let ring") + note(0, "E", 1, 96, 4, 0))
        #expect(TabIndex.forRenderer(ring, header: TabIndex.parse(musicXML: ring).header).contains("let ring"))
    }

    @Test func thePageGoesToTheRendererWithoutItsMarks() throws {
        let xml = try fixtureText("bass-line-marks/tab.musicxml")
        let bare = TabIndex.withoutMarks(xml)
        #expect(!bare.contains("<words>?</words>"))
        #expect(!bare.contains("! D1"))
        #expect(!bare.contains("#9A5200"))
        // Only those: the header, the tempo and every note are still there, and it is still a document.
        #expect(bare.contains("<words>Standard: E A D G</words>"))
        #expect(bare.contains("<metronome>"))
        #expect(count(#"<note\b"#, in: xml) == count(#"<note\b"#, in: bare))
        #expect(count("<direction ", in: xml) - 3 == count("<direction ", in: bare))
        let again = TabIndex.parse(musicXML: bare)
        #expect(TabIndex.parse(musicXML: xml).pieces == again.pieces)
        #expect(again.noPlace.isEmpty)
    }

    @Test(arguments: ["", "not xml", "<score-partwise version=\"4.0\"></score-partwise>"])
    func somethingThatIsNotATabGivesAnEmptyIndex(text: String) {
        let index = TabIndex.parse(musicXML: text)
        #expect(index.bars == 0)
        #expect(index.pieces.isEmpty && index.measures.isEmpty)
    }

    @Test func anExternalEntityIsNeverRead() throws {
        let secret = FileManager.default.temporaryDirectory.appending(path: "tab-\(UUID().uuidString).txt")
        try "<words>leaked</words>".write(to: secret, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: secret) }
        let xml = """
        <?xml version="1.0"?>
        <!DOCTYPE score-partwise [<!ENTITY leak SYSTEM "\(secret.absoluteString)">]>
        <score-partwise><part id="P1"><measure number="1"><direction><direction-type><words>&leak;</words></direction-type></direction></measure></part></score-partwise>
        """
        #expect(TabIndex.parse(musicXML: xml).header != "leaked")
    }
}

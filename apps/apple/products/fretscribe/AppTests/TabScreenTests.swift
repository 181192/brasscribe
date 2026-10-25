import CoreGraphics
import Foundation
import SwiftUI
import Testing
import TabKit
import TranscriptionKit
@testable import Fretscribe

/// A fixture beside the apps (apps/fixtures), found from this file.
private func fixture(_ name: String) throws -> Data {
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appending(path: "../../../../fixtures/\(name)").standardizedFileURL
    return try Data(contentsOf: url)
}

/// A fixture's tab as the screen reads it: the page, and the data unless `withData` is false.
private func sheet(_ dir: String, withData: Bool = true) throws -> TabSheet {
    let xml = String(decoding: try fixture("\(dir)/tab.musicxml"), as: UTF8.self)
    let json = try fixture("\(dir)/tab.json")
    return TabSheet(musicXML: xml, data: withData ? try JSONDecoder().decode(TabData.self, from: json) : nil,
                    details: withData ? try JSONDecoder().decode(TabDetails.self, from: json) : nil)
}

@Suite struct TabMarksTests {
    @Test func theDataMarksTwoDoubtsAndANoteBelowTheLowestString() throws {
        let s = try sheet("bass-line-marks")
        #expect(s.marks.doubtful == 2)
        #expect(s.marks.noPlace == 1)
        #expect(s.marks.unplaced == 0)
        #expect(s.marks.columns.map(\.kind) == [.doubt, .noPlace, .doubt])
        #expect(s.marks.doubts == [0, 2])
        #expect(s.marks.columns.map(\.bar) == [2, 6, 14])
        #expect(s.marks.columns[1].notes.first?.why == .tooLow)
    }

    @Test func aMarkIsReadWithItsBarBeatStringFretAndPitch() throws {
        let s = try sheet("bass-line-marks")
        let words = s.marks.columns.map { TabWords.describe($0, bokmal: false) }
        #expect(words == [
            "Bar 3, beat 2. 3rd string, fret 2, B. Fretscribe isn't sure about this one.",
            "Bar 7, beat 2. D1 is lower than your lowest string. Is the tuning right?",
            "Bar 15, beat 1. 4th string, open, E. Fretscribe isn't sure about this one.",
        ])
    }

    @Test func withoutTheDataThePageItselfIsRead() throws {
        let s = try sheet("bass-line-marks", withData: false)
        #expect(s.marks.doubtful == 2)
        #expect(s.marks.noPlace == 1)
        #expect(s.marks.columns.map(\.bar) == [2, 6, 14])
        #expect(TabWords.describe(s.marks.columns[1], bokmal: false)
                == "Bar 7, beat 2. D1 has no place on your instrument here. Is the tuning right?")
    }

    @Test func theGuitarLineHasANoteAboveItsHighestFretAndOneBelowItsLowestString() throws {
        let s = try sheet("guitar-line")
        #expect(s.marks.noPlace == 2)
        #expect(s.marks.doubtful == 1)
        let why = s.marks.columns.flatMap(\.notes).filter { $0.kind == .noPlace }.map(\.why)
        #expect(Set(why) == [.tooHigh, .tooLow])
    }

    @Test func aCleanTabHasNoMarks() throws {
        let s = try sheet("bass-line")
        #expect(s.marks.columns.isEmpty)
        #expect(s.spots.isEmpty)
    }

    @Test func thePageIsToldEachMarkWithItsNotes() throws {
        let s = try sheet("bass-line-marks")
        let first = try #require(s.spots.first)
        #expect(first.bar == 2)
        #expect(first.staff == s.index.markStaff)
        #expect(first.notes == [TabMarkSpot.Note(string: 3, fret: 2, pitchClass: 11, doubt: true)])
        #expect(s.spots[1].notes.allSatisfy { !$0.doubt })
    }

    @Test func pitchNamesInEnglishAndBokmal() {
        #expect(TabWords.pitch("D", -1, bokmal: false) == "D-flat")
        #expect(TabWords.pitch("F", 1, bokmal: false) == "F-sharp")
        #expect(TabWords.pitch("B", 0, bokmal: true) == "H")
        #expect(TabWords.pitch("B", -1, bokmal: true) == "B")
        #expect(TabWords.pitch("E", -1, bokmal: true) == "Ess")
        #expect(TabWords.pitch("A", -1, bokmal: true) == "Ass")
        #expect(TabWords.pitch("F", 1, bokmal: true) == "Fiss")
        #expect(TabWords.pitch("D", -1, bokmal: true) == "Dess")
        #expect(TabWords.ordinal(3) == "3rd")
        #expect(TabWords.ordinal(9) == "9")
    }
}

@Suite struct TabHeaderWordsTests {
    @Test func theChipIsShownShortAndReadWhole() throws {
        let s = try sheet("bass-line-marks")
        #expect(TabWords.chip(s) == "Standard · no capo")
        #expect(TabWords.chipName(s) == "Tuning: Standard, no capo")
        #expect(s.tempo == 100)
        #expect(TabWords.tempo(100) == "♩ = 100")
        #expect(TabWords.tempoSpoken(100) == "100 beats a minute")
        #expect(TabWords.markedLine(2) == "2 notes marked ? · Check them")
        #expect(TabWords.markedLine(1) == "1 note marked ? · Check it")
        #expect(TabWords.noPlaceLine(1) == "1 note with no place")
    }

    @Test func theTabIsOneElementThatSaysWhatItIs() throws {
        #expect(TabWords.summary(title: "Bass line", try sheet("bass-line-marks"))
                == "Bass line. Tab. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?. 1 note with no place.")
        #expect(TabWords.summary(title: "Bass line", try sheet("bass-line"))
                == "Bass line. Tab. Tuning: Standard, no capo. 100 beats a minute. 15 bars.")
    }

    @Test func thePresetNamesTheInstrumentAndTuning() {
        #expect(TabSheet.ofPreset("bass-4-drop-d")! == (FrettedInstrument.bass4, "drop-d"))
        #expect(TabSheet.ofPreset("guitar-standard")! == (FrettedInstrument.guitar6, "standard"))
        #expect(TabSheet.ofPreset("mandolin")! == (FrettedInstrument.mandolin, "standard"))
        #expect(TabSheet.ofPreset("theremin") == nil)
        #expect(TabWords.tuning("standard", kind: .mandolin) == "G D A E")
        #expect(TabWords.tuning("bead") == "BEAD")
        #expect(TabWords.tuning("bead", spoken: true) == "B, E, A, D")
        #expect(TabWords.tuning("Nashville") == "Nashville")
        #expect(TabWords.capo(3) == "capo 3")
    }

    @Test func thePlayerSaysWhatBecameOfTheRecording() {
        #expect(TabWords.says(.here, follows: true, canFetch: true) == nil)
        #expect(TabWords.says(.looking, follows: true, canFetch: true) == nil)
        #expect(TabWords.says(.here, follows: false, canFetch: true) == "Fretscribe can't follow the recording in this tab. You can still read it.")
        #expect(TabWords.says(.notHere, follows: true, canFetch: true) == "The recording is not on this device.")
        #expect(TabWords.says(.notHere, follows: true, canFetch: false)?.hasSuffix("You can still read the tab.") == true)
        #expect(TabWords.offersFetch(.noAnswer))
        #expect(!TabWords.offersFetch(.gone))
        #expect(TabWords.repeatChip(nil) { "\($0 + 1)" } == "Repeat bars")
        #expect(TabWords.repeatChip(RepeatBars(first: 2, last: 2)) { "\($0 + 1)" } == "Repeating 3")
        #expect(TabWords.repeatChip(RepeatBars(first: 2, last: 5)) { "\($0 + 1)" } == "Repeating 3–6")
        #expect(TabWords.place(TabMeasure(number: "13", length: 3840, beats: 4, beatTicks: 960), beat: 2) == "Bar 13, beat 2")
        #expect(TabWords.place(TabMeasure(number: "0", length: 960, beats: 4, beatTicks: 960, pickup: true), beat: 4) == "Pickup bar, beat 4")
    }

    @Test func aFetchTheComputerRefusedIsReadForWhatItIs() {
        let plenty: Int64 = 1 << 40
        #expect(PracticeRecordings.whyNot(TabFetch.error(.http(404, "input")), room: plenty) == .gone)
        #expect(PracticeRecordings.whyNot(TabFetch.error(.http(413, "input")), room: plenty) == .tooLarge)
        #expect(PracticeRecordings.whyNot(TabFetch.error(.interfaceMismatch(.app)), room: plenty) == .updateApp)
        #expect(PracticeRecordings.whyNot(TabFetch.error(.interfaceMismatch(.computer)), room: plenty) == .updateComputer)
        #expect(PracticeRecordings.whyNot(TabFetch.error(.unreachable("off")), room: plenty) == .noAnswer)
    }
}

@Suite struct TabPlacingTests {
    @Test func aSmallMarkGetsATargetOf44PointsCentredOnItsColumn() {
        let f = MarkTarget.frame(TabMarkBox(mark: 0, x: 100, top: 50, bottom: 64, columnBottom: 80, width: 14))
        #expect(f.width == 44 && f.height == 44)
        #expect(f.midX == 100)
        // 30 points from the mark to the numerals' foot, so 7 above and 7 below.
        #expect(f.minY == 43)
    }

    @Test func aTallColumnIsCoveredFromItsMarkDown() {
        let f = MarkTarget.frame(TabMarkBox(mark: 0, x: 100, top: 50, bottom: 64, columnBottom: 150, width: 60))
        #expect(f.minY == 50 && f.height == 100 && f.width == 60)
    }

    @Test func theSizeFollowsTheTextAndTheZoomButABarFitsTheWidth() {
        #expect(TabSize.scale(percent: 100, fontScale: 1, width: 1000) == TabSize.base)
        #expect(TabSize.scale(percent: 200, fontScale: 1, width: 1000) == TabSize.base * 2)
        #expect(TabSize.scale(percent: 400, fontScale: 2, width: 280) == 2)
    }

    @Test func thePageFollowsTheRecordingFromLineToLine() {
        let lines = [TabLine(top: 0, bottom: 100, first: 0, last: 3), TabLine(top: 120, bottom: 220, first: 4, last: 7),
                     TabLine(top: 240, bottom: 340, first: 8, last: 11)]
        let shown = 0.0...300.0
        // Within a line: stays.
        #expect(TabFollow.scrollTarget(now: 2, last: 1, playing: true, moved: false, lines: lines, pageTop: 0, shown: shown) == nil)
        // On to the next line while playing: it goes to the top.
        #expect(TabFollow.scrollTarget(now: 4, last: 3, playing: true, moved: false, lines: lines, pageTop: 0, shown: shown) == 120)
        // Moved by the player to a line out of view.
        #expect(TabFollow.scrollTarget(now: 9, last: 1, playing: false, moved: true, lines: lines, pageTop: 0, shown: shown) == 240)
        // Moved to a line in view: stays.
        #expect(TabFollow.scrollTarget(now: 5, last: 1, playing: false, moved: true, lines: lines, pageTop: 0, shown: shown) == nil)
        #expect(TabFollow.scrollTarget(now: 40, last: 1, playing: true, moved: true, lines: lines, pageTop: 0, shown: shown) == nil)
    }

    @Test func coloursAreCSS() {
        #expect(TabColours.css(Color.Resolved(red: 1, green: 0, blue: 0.5, opacity: 1)) == "#ff0080")
        #expect(TabColours.css(Color.Resolved(red: 0, green: 0, blue: 0, opacity: 0.2)) == "#00000033")
    }

    @Test func highContrastHasNoWash() {
        let env = EnvironmentValues()
        #expect(TabColours.palette(in: env, highContrast: false).cursorTint != nil)
        #expect(TabColours.palette(in: env, highContrast: true).cursorTint == nil)
        #expect(TabColours.palette(in: env).ink.hasPrefix("#"))
    }
}

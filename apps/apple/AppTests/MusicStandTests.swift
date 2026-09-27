import Foundation
import NotationKit
import ScoreKit
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// The auto-hide rule of design/music-stand.md §4.2: only while the music plays, and never while
/// a screen reader, switch access, the keyboard or the setting needs the controls.
@Test func standAutoHidesOnlyWhilePlayingAndNothingNeedsTheControls() {
    func hides(playing: Bool = true, voiceOver: Bool = false, switchControl: Bool = false, keyboard: Bool = false,
               focus: Bool = false, keep: Bool = false) -> Bool {
        MusicStand.autoHides(playing: playing, voiceOver: voiceOver, switchControl: switchControl, fullKeyboardAccess: keyboard,
                             focusInLayer: focus, keepVisible: keep)
    }
    #expect(hides())
    #expect(!hides(playing: false))
    #expect(!hides(voiceOver: true))
    #expect(!hides(switchControl: true))
    #expect(!hides(keyboard: true))
    #expect(!hides(focus: true))
    #expect(!hides(keep: true))
}

/// Pages are whole systems. A single page overlaps the next by one system; pages side by side
/// do not overlap (the right page moves to the left instead).
@Test func standPagesAreWholeSystemsWithOneOverlapping() {
    // ten systems 100 pt tall with 20 pt between them, bar i on system i
    let systems = (0..<10).map { i in
        ScoreRenderer.System(frame: CGRect(x: 0, y: CGFloat(i) * 120, width: 390, height: 100), measureIDs: ["m\(i)"])
    }
    let bars = Dictionary(uniqueKeysWithValues: (0..<10).map { ("m\($0)", $0) })
    let single = MusicStand.paginate(systems, height: 400, overlap: true, bars: bars)
    #expect(single.map(\.systems) == [0...2, 2...4, 4...6, 6...8, 8...9])
    #expect(single[1].bars == 2...4)
    let spread = MusicStand.paginate(systems, height: 400, overlap: false, bars: bars)
    #expect(spread.map(\.systems) == [0...2, 3...5, 6...8, 9...9])
    // a system taller than the screen still gets a page of its own, and paging moves on
    #expect(MusicStand.paginate(systems, height: 50, overlap: true, bars: bars).count == 10)
    #expect(MusicStand.paginate([], height: 400, overlap: true, bars: [:]).isEmpty)
}

@Test(.enabled(if: fixtureDir() != nil)) @MainActor func standOpensOnYourPartAndHidesOnlyMyPartWithoutOne() throws {
    let dir = try #require(fixtureDir())
    let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
    let r = TranscriptionResult(jobID: "fixture", composition: nil, musicXML: xml, available: [.musicXML])
    let p = try Piece.create(title: "Stand", profile: .brassBand, result: r, original: nil, video: nil, fixtureDirectory: dir)
    defer { p.delete() }
    let m = try PracticeModel(piece: p)
    m.enterStand(from: .toolbar)
    let stand = try #require(m.stand)
    #expect(stand.onlyMine)
    #expect(m.layoutPart == m.myPart)
    #expect(m.shownPart == nil, "the stand has its own part choice")
    #expect(stand.partLine(m).contains("Solo Cornet"))
    #expect(!m.playAlong, "opening the stand does not mute your part")
    m.setOnlyMine(false)
    #expect(m.layoutPart == nil)
    #expect(stand.partLine(m) == String(localized: "All parts"))
    m.leaveStand()
    #expect(m.stand == nil)
    // no part to call yours (a conductor): the parts shown, and Only my part is off (and hidden)
    m.myPart = nil
    m.enterStand(from: .toolbar)
    #expect(m.stand?.onlyMine == false)
    #expect(m.layoutPart == nil)
}

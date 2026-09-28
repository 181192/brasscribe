import Testing
import Foundation
import ScoreKit
import TranscriptionKit
@testable import BrasscribePlay

@MainActor private func fixturePiece(_ title: String) throws -> Piece {
    let dir = try #require(fixtureDir())
    let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
    let comp = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    let r = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: [.musicXML])
    return try Piece.create(title: title, profile: .orchestraWithSoloist, result: r, original: nil, video: nil, fixtureDirectory: nil)
}

/// Opening a score builds everything off the main actor and hands over a started model: the same
/// score and a playing engine as the synchronous path.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func openBuildsTheModelOffTheMainActor() async throws {
    let piece = try fixturePiece("Open")
    defer { piece.delete() }
    let m = try await PracticeModel.open(piece)
    defer { m.stopAll() }
    #expect(m.score == (try piece.loadScore()))
    #expect(m.composition != nil)
    try #require(m.engine != nil, "no audio engine here: \(m.loadError ?? "")")
    m.togglePlay()
    #expect(m.isPlaying)
}

/// "Listen to this bar" is a toggle: the same button stops it, and it puts back the user's repeat.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func listenToggleStopsAndRestores() throws {
    let piece = try fixturePiece("Listen")
    defer { piece.delete() }
    let m = try PracticeModel(piece: piece)
    m.start()
    defer { m.stopAll() }
    try #require(m.engine != nil, "no audio engine here")
    m.loopFrom = 5; m.loopTo = 6
    m.setLoop(true)

    m.toggleListen(bars: 2...2, original: true)
    #expect(m.listening == 2...2)
    #expect(m.isPlaying)
    #expect(!m.looping, "listening plays the bar once, it doesn't repeat it")
    #expect(!m.hearOriginal, "no recording in this piece: the band plays")
    #expect(m.currentBar == 2)

    // another note's bar takes over; the first one isn't left playing
    m.toggleListen(bars: 3...4, original: true)
    #expect(m.listening == 3...4)
    #expect(m.currentBar == 3)

    // Stop
    m.toggleListen(bars: 3...4, original: true)
    #expect(m.listening == nil)
    #expect(!m.isPlaying)
    #expect(m.currentBar == 3, "back at the start of the bar")
    #expect(m.looping && m.loopFrom == 5 && m.loopTo == 6, "the user's repeat comes back")

    // pausing some other way (Space in the player) also ends listening
    m.listen(toBar: 1, original: false)
    m.togglePlay()
    RunLoop.main.run(until: Date().addingTimeInterval(0.2))
    #expect(m.listening == nil)
}

/// When the bar has played, the button is "Listen to this bar" again.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func listenEndsWithTheBar() async throws {
    let piece = try fixturePiece("ListenEnd")
    defer { piece.delete() }
    let m = try PracticeModel(piece: piece)
    m.start()
    defer { m.stopAll() }
    try #require(m.engine != nil, "no audio engine here")
    m.speedPercent = 150
    m.listen(toBar: 1, original: false)
    #expect(m.listening == 1...1)
    let deadline = Date().addingTimeInterval(10)
    while m.listening != nil, Date() < deadline { try await Task.sleep(for: .milliseconds(100)) }
    #expect(m.listening == nil)
    #expect(!m.isPlaying)
    #expect(m.currentBar == 1)
}

/// Screenshots hold the Stop state without sound, and choosing another note can't clear it.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func heldListeningForScreenshots() throws {
    let piece = try fixturePiece("Held")
    defer { piece.delete() }
    let m = try PracticeModel(piece: piece)
    m.start()
    defer { m.stopAll() }
    m.holdListening(bars: 4...4)
    RunLoop.main.run(until: Date().addingTimeInterval(0.2))
    #expect(m.listening == 4...4)
    m.stopListening(announce: false)
    #expect(m.listening == 4...4)
}

@Test func connectionWordsInBothLanguagesComeFromTheComputerName() {
    #expect(ConnectionCopy.name("Brasscribe on Studio Mac").hasSuffix("Studio Mac"))
    #expect(!ConnectionCopy.name("Brasscribe on Studio Mac").contains(" on Brasscribe"))
    #expect(ConnectionCopy.status(.connected(serverName: "Brasscribe on Studio Mac")).contains("Studio Mac"))
    #expect(ConnectionCopy.status(.reconnecting(serverName: "Brasscribe on Studio Mac")).hasSuffix("…"))
    // the state is always in words and has an icon, never colour alone
    for s in [ConnectionState.connected(serverName: "x"), .reconnecting(serverName: "x"), .offline, .needsPairing(serverName: "x")] {
        #expect(!ConnectionCopy.status(s).isEmpty)
        #expect(!ConnectionCopy.systemImage(s).isEmpty)
    }
}

/// Tests and screenshots never read or write the real Keychain.
@Test @MainActor func testsUseAnInMemoryCredentialStore() {
    #expect(AppModel.makeCredentialStore() is InMemoryCredentialStore)
}

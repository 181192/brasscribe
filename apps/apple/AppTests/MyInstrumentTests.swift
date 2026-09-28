import Testing
import Foundation
import ScoreKit
import TranscriptionKit
@testable import BrasscribePlay

/// "What do you play?": seats and names from the core, your part per score, where parts come from.

@Test func partNamesComeFromTheCore() {
    #expect(PartNames.display("1st Cornet", language: .norwegian) == "1. kornett")
    #expect(PartNames.display("Tenor Horn", language: .norwegian) == "Althorn")
    #expect(PartNames.display("Solo Horn", language: .norwegian) == "Solo althorn")
    #expect(PartNames.display("Solo Horn", language: .english) == "Solo Horn")
    // every seat's name is the core's table
    for s in Seats.all { #expect(PartNames.display(s.name, language: .norwegian) == s.nbName) }
}

@Test func thePickerOffersEveryInstrumentOnce() {
    let tiles = Seats.instruments
    #expect(tiles.count == 11)
    #expect(Set(tiles.flatMap(\.seats).map(\.id)) == Set(Seats.all.map(\.id)))
    #expect(tiles.first?.seats.map(\.id) == ["solo-cornet", "repiano-cornet", "2nd-cornet", "3rd-cornet"])
    #expect(tiles.first { $0.id == "eb-bass" }?.accessibilityName.contains("♭") == false)
}

/// Three spot checks of the core's seat → part table, through the FFI.
@Test func seatPartSpotChecks() throws {
    let a = try #require(Seats.part("1st-baritone", in: .minimalBand))
    #expect(a.part == "Euphonium" && !a.exact && a.sameKey)
    let b = try #require(Seats.part("eb-bass", in: .quartet))
    #expect(b.part == "Euphonium" && !b.exact && !b.sameKey)
    #expect(Seats.part("percussion", in: .quartet)?.part == nil)
}

@Test func theAnswerIsSavedAndReadBack() throws {
    let d = try #require(UserDefaults(suiteName: "my-instrument-tests"))
    defer { d.removePersistentDomain(forName: "my-instrument-tests") }
    for choice in [SeatChoice.seat("euphonium", reads: "bass"), .seat("2nd-cornet", reads: nil), .conductor, .notSet] {
        choice.save(to: d)
        #expect(SeatChoice.decode(d.string(forKey: SeatChoice.seatKey), reads: d.string(forKey: SeatChoice.readsKey)) == choice)
    }
    #expect(SeatChoice.parse("1st-baritone:bass") == .seat("1st-baritone", reads: "bass"))
    #expect(SeatChoice.parse("none") == .conductor)
    #expect(SeatChoice.parse("tuba") == .notSet)
}

@Test func settingsSaysWhatYouPlay() {
    #expect(SeatChoice.notSet.summary == "Not set")
    #expect(SeatChoice.seat("1st-baritone", reads: nil).summary == "1st Baritone · treble clef in B♭")
    #expect(SeatChoice.seat("euphonium", reads: "bass").summary == "Euphonium · bass clef, as it sounds")
    #expect(SeatChoice.seat("bass-trombone", reads: nil).summary == "Bass Trombone")
}

@Test func theMappingNoticeNamesTheLineup() throws {
    let seat = try #require(Seats.info("1st-baritone"))
    let sp = try #require(Seats.part("1st-baritone", in: .minimalBand))
    #expect(Seats.mappingNotice(seat: seat, lineup: .minimalBand, part: sp, reads: nil)
            == "This small band has no 1st Baritone. Your part here is Euphonium, the closest: the same key and clef.")
    let bass = try #require(Seats.info("eb-bass"))
    let q = try #require(Seats.part("eb-bass", in: .quartet))
    #expect(Seats.mappingNotice(seat: bass, lineup: .quartet, part: q, reads: nil)
            == "The quartet has no E♭ Bass. Your part here is Euphonium, written for B♭.")
    let exact = try #require(Seats.part("euphonium", in: .fullBand))
    #expect(Seats.mappingNotice(seat: try #require(Seats.info("euphonium")), lineup: .fullBand, part: exact, reads: nil) == nil)
}

// MARK: with the fixture score

@MainActor private func fixturePiece(output: OutputChoice? = nil, profile: SourceProfile = .brassBand) throws -> Piece {
    let dir = try #require(fixtureDir())
    let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
    let comp = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
    let r = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: [.musicXML])
    return try Piece.create(title: "My instrument", profile: profile, result: r, original: nil, video: nil, fixtureDirectory: nil, output: output)
}

@Test(.enabled(if: fixtureDir() != nil)) @MainActor func yourPartFollowsTheSeat() throws {
    let p = try fixturePiece(output: OutputChoice())
    defer { p.delete() }
    let score = try p.loadScore()
    func name(_ id: String?) -> String? { id.flatMap { score.part(id: $0)?.name } }
    // no seat: Solo Cornet, as before
    #expect(name(PracticeModel.resolveMyPart(piece: p, score: score, seat: .notSet).partID) == "Solo Cornet")
    // I conduct or listen: no part is yours
    #expect(PracticeModel.resolveMyPart(piece: p, score: score, seat: .conductor).partID == nil)
    let euph = PracticeModel.resolveMyPart(piece: p, score: score, seat: .seat("euphonium", reads: nil))
    #expect(name(euph.partID) == "Euphonium" && euph.notice == nil)
    #expect(name(PracticeModel.resolveMyPart(piece: p, score: score, seat: .seat("3rd-cornet", reads: nil)).partID) == "3rd Cornet")
}

@Test(.enabled(if: fixtureDir() != nil)) @MainActor func makeThisMyPartIsKeptWithTheScore() throws {
    let p = try fixturePiece(output: OutputChoice())
    defer { p.delete() }
    let m = PracticeModel(piece: p, score: try p.loadScore(), composition: p.loadComposition(), seat: .seat("euphonium", reads: nil))
    let second = try #require(m.score.parts.first { $0.name == "2nd Cornet" })
    m.makeMine(second.id)
    #expect(m.myPart == second.id)
    let reloaded = try #require(Piece.load(from: p.metaURL))
    #expect(reloaded.myPart == "2nd Cornet")
    // a changed seat in Settings doesn't move it
    let again = PracticeModel(piece: reloaded, score: try reloaded.loadScore(), composition: reloaded.loadComposition(), seat: .seat("1st-baritone", reads: nil))
    #expect(again.myPart == second.id)
}

/// The fixture is a soloist with band: the tune and the bass line were heard, the rest is arranged.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func partsSayWhereTheyComeFrom() throws {
    let p = try fixturePiece(output: OutputChoice())
    defer { p.delete() }
    let byName = PartSourceKind.sources(composition: p.loadComposition(), output: p.output)
    #expect(byName["Solo Cornet"] == .recording)
    #expect(byName["E♭ Bass"] == .recording)
    #expect(byName["Flugelhorn"] == .arranged)
    #expect(byName["1st Baritone"] == .arranged)
    #expect(byName.count == 18)
}

/// The small band has no 1st Baritone: your part is Euphonium, and the score says why.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func aSmallBandMapsTheSeat() throws {
    let app = AppModel()
    let p = try fixturePiece(output: OutputChoice())
    defer { p.delete() }
    let comp = try #require(p.loadComposition())
    let small = try app.rearrange(p, composition: comp, output: OutputChoice(lineup: .minimalBand), open: false)
    let m = PracticeModel(piece: small, score: try small.loadScore(), composition: small.loadComposition(), seat: .seat("1st-baritone", reads: nil))
    #expect(m.myPart.flatMap { m.score.part(id: $0)?.name } == "Euphonium")
    #expect(m.seatNotice?.hasPrefix("This small band has no 1st Baritone.") == true)
    #expect(m.mySource != nil)
}

/// A solo take with a seat is written for that instrument: one part, the seat's, from your recording.
@Test(.enabled(if: fixtureDir() != nil)) @MainActor func aSoloTakeIsWrittenForTheSeat() throws {
    let app = AppModel()
    let p = try fixturePiece(output: OutputChoice(), profile: .solo)
    defer { p.delete() }
    var comp = try #require(p.loadComposition())
    for i in comp.voices.indices where comp.voices[i].layer != "solo" { comp.voices[i].notes = [] }
    let choice = OutputChoice(lineup: .fullBand, seat: "1st-baritone", lead: "seat")
    let solo = try app.rearrange(p, composition: comp, output: choice, open: false)
    let score = try solo.loadScore()
    #expect(score.parts.map(\.name) == ["1st Baritone"])
    let m = PracticeModel(piece: solo, score: score, composition: comp, seat: .conductor)
    // the take's own seat is its part, whatever Settings says
    #expect(m.myPart == score.parts.first?.id)
    #expect(PartSourceKind.sources(composition: comp, output: choice)["1st Baritone"] == .yourRecording)
}

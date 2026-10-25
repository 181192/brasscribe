import Foundation
import Testing
import TabKit
import TranscriptionKit
@testable import Fretscribe

/// What Fretscribe sends to the computer and keeps of what comes back.
@MainActor
struct FretscribeModelTests {
    static func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../fixtures/\(name)").standardizedFileURL
    }

    /// A tab job carries the player's instrument, tuning and reading, and what "What is this?" was answered with; none of
    /// the band's options.
    @Test func aTabJobSaysTheInstrumentAndTheRecording() {
        let fields = FretscribeModel.fields(instrument: YourInstrument(.bass5, tuning: "drop-a", reads: .tabAndNotation), recording: .song)
        let sent = Dictionary(uniqueKeysWithValues: fields.map { ($0.name, $0.value) })
        #expect(sent == ["instrument": "bass-5", "tuning": "drop-a", "layout": "tab-and-notation", "recording": "song"])
        let request = TranscriptionRequest(audioURL: URL(fileURLWithPath: "/dev/null"), profile: FretscribeModel.profile, fields: fields)
        #expect(request.profile == "tab")
        #expect(request.field("lineup") == nil && request.field("seat") == nil)
    }

    /// A tab written from the fixture service is kept in Your songs with its tab data, and opens on Check the song.
    @Test(.timeLimit(.minutes(1))) func aFinishedTabIsKeptAndCheckedFirst() async throws {
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-model-\(UUID().uuidString)", directoryHint: .isDirectory)
        setenv("SCRIBE_SONGS", songs.path, 1)
        defer { try? FileManager.default.removeItem(at: songs) }
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-model-\(UUID().uuidString)")!)
        let svc = FixtureService(directory: Self.fixture("bass-line-marks"), stepDelay: 0, outputName: "tab")
        let src = PendingSource(audioURL: Self.fixture("bass-line/tab.json"), title: "Bass line")
        let job = TabJob(source: src, recording: .instrument, request: TranscriptionRequest(audioURL: src.audioURL, profile: "tab"), service: svc)
        var made: TranscriptionResult?
        job.start { made = $0 }
        let end = Date().addingTimeInterval(20)
        while made == nil, Date() < end { try await Task.sleep(for: .milliseconds(20)) }
        let result = try #require(made)
        let song = try TabSong.create(title: "Bass line", jobID: nil, musicXML: result.musicXML,
                                      tab: try await svc.artifact(.tab, jobID: result.jobID), recording: nil)
        model.refresh()
        #expect(model.songs.map(\.title) == ["Bass line"])
        #expect(song.preset == "bass-4-standard")
        #expect(song.toCheck == SongMarks.doubtfulCount(try #require(song.tab())))
        #expect(String(decoding: try song.musicXML(), as: UTF8.self).contains("<?fretted-note"))
        let facts = try #require(SongFacts.of(song))
        #expect(facts.tuningName == "Standard")
        #expect(facts.soundsLike?.tuning == "Drop D")
    }

    /// Sheet music opened from Home is refused with why: Fretscribe makes tabs from recordings.
    @Test func sheetMusicIsRefusedWithWhy() async {
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-model-\(UUID().uuidString)")!)
        await model.accept(url: Self.fixture("bass-line/tab.musicxml"))
        #expect(model.path.last == .problem(.sheetMusic))
    }

    /// The pairing link of the family, and the one a sibling hands over under this app's own scheme, pair this app.
    @Test func pairingLinksOfTheFamilyAndOfThisApp() throws {
        let family = try #require(URL(string: "scribe://pair?v=1&id=7f3a9c2e&name=Studio&h=192.168.1.20:8765&code=123456"))
        #expect(PairingLinks.link(in: family, ownScheme: "fretscribe") != nil)
        let handed = try #require(PairingLinks.handedOver(family, to: SiblingApp(name: "Fretscribe", scheme: "fretscribe")))
        #expect(handed.scheme == "fretscribe")
        #expect(PairingLinks.link(in: handed, ownScheme: "fretscribe") != nil)
        #expect(PairingLinks.link(in: handed, ownScheme: "brasscribe") == nil)
        #expect(PairingLinks.link(in: try #require(URL(string: "https://example.org/pair")), ownScheme: "fretscribe") == nil)
    }
}

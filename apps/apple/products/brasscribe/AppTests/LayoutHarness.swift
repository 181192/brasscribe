#if os(macOS)
import AppKit
import Foundation
import ScoreKit
import ScreenCatalogue
import SwiftUI
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// The window's layout, as `RootView` builds it on the Mac: the library in a sidebar (`LibrarySplit`,
/// with its window minimum and the sidebar rule) and the screen in the detail column's navigation stack.
struct HarnessShell<Content: View>: View {
    @State private var columns: NavigationSplitViewVisibility
    private let content: Content

    init(sidebar: Bool = true, @ViewBuilder content: () -> Content) {
        _columns = State(initialValue: sidebar ? .all : .detailOnly)
        self.content = content()
    }

    var body: some View {
        LibrarySplit(columns: $columns) { NavigationStack { content } }
            .tint(Color.Scribe.primary)
    }
}

/// The score screen's switch between the score and the music stand (`ScoreScreen`), for a model the
/// test holds.
struct ScoreOrStand: View {
    @Bindable var model: PracticeModel
    var body: some View {
        Group {
            if let stand = model.stand { MusicStandView(model: model, stand: stand) } else { PracticeView(model: model) }
        }
        .pageBackground()
    }
}

/// Fixture data for the layout tests: Old Hundredth, in a library of its own (unit tests keep
/// their scores out of the user's library).
@MainActor
enum LayoutFixtures {
    static func freshLibrary() {
        try? FileManager.default.removeItem(at: Piece.libraryURL)
        try? FileManager.default.createDirectory(at: Piece.libraryURL, withIntermediateDirectories: true)
    }

    static func app(connection: ConnectionState = .connected(serverName: "Brasscribe on Studio Mac")) -> AppModel {
        UserDefaults.standard.register(defaults: ["firstRunDone": true])
        // no engine answers here, so a Brasscribe running on this Mac never adds its scores to the library
        setenv("SCRIBE_COMPANION", "http://127.0.0.1:9", 1)
        let app = AppModel()
        app.pieces = []
        let record = connection == .offline ? nil
            : EngineRecord(serverID: "7f3a9c2e", serverName: "Brasscribe on Studio Mac", deviceID: "d-41b2", token: "staged",
                           lastAddress: "http://192.0.2.20:8765", lastOK: Date().addingTimeInterval(-12))
        app.connection.stage(connection, record: record)
        return app
    }

    static func piece(title: String = "Old Hundredth", lineup: Lineup? = nil) throws -> Piece {
        let dir = try #require(fixtureDir())
        let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
        let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
        let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
        return try Piece.create(title: title, profile: .brassBand, result: result, original: nil, video: nil, fixtureDirectory: dir,
                                output: lineup.map { OutputChoice(lineup: $0) })
    }

    /// The lived-in library of the `home-full` screenshot scene.
    static func library(_ app: AppModel) throws {
        let first = try piece()
        let day: TimeInterval = 86_400
        var all = [first]
        let rows: [(String, TimeInterval, Lineup, Int)] = [
            ("Deep Harmony", 1 * day, .fullBand, 0), ("Abide with Me", 2 * day, .minimalBand, 12), ("Crimond", 3 * day, .quartet, 0),
            ("20260815_155324", 5 * day, .fullBand, 0), ("Floral Dance", 12 * day, .fullBand, 4),
        ]
        for (title, ago, lineup, toCheck) in rows {
            var p = first
            p.id = UUID(); p.title = title; p.created = Date().addingTimeInterval(-ago); p.output = OutputChoice(lineup: lineup); p.toCheck = toCheck
            all.append(p)
        }
        app.pieces = all
    }

    static func model(_ piece: Piece) async throws -> PracticeModel { try await PracticeModel.open(piece) }

    /// The piece's first note to check as one Brasscribe is very unsure of (a boxed "?"), which the fixture has none
    /// of. Returns the composition as it was, to put back with `saveComposition`.
    static func makeFirstNoteVeryUnsure(_ piece: Piece) throws -> Composition {
        let was = try #require(piece.loadComposition())
        var comp = was
        let group = try #require(comp.review.first)
        comp.review[0].very = true
        for v in comp.voices.indices where comp.voices[v].id == group.voice {
            for n in comp.voices[v].notes.indices where comp.voices[v].notes[n].start >= group.start && comp.voices[v].notes[n].start < group.end {
                comp.voices[v].notes[n].confidence = 0.2
            }
        }
        try piece.saveComposition(comp)
        return was
    }
}

/// Where the thumbnails go: apps/apple/docs/responsive, only when SCRIBE_RESPONSIVE_SHOTS is set
/// (TEST_RUNNER_SCRIBE_RESPONSIVE_SHOTS=1 on the xcodebuild line).
enum Thumbnails {
    static var enabled: Bool { ProcessInfo.processInfo.environment["SCRIBE_RESPONSIVE_SHOTS"] != nil }

    static var directory: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appending(path: "docs/responsive")
    }

    /// A JPEG at most `width` px wide.
    static func save(_ rep: NSBitmapImageRep, name: String, width: CGFloat = 480) {
        guard enabled else { return }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let scale = min(1, width / CGFloat(rep.pixelsWide))
        let w = Int((CGFloat(rep.pixelsWide) * scale).rounded()), h = Int((CGFloat(rep.pixelsHigh) * scale).rounded())
        guard let small = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4,
                                           hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: small)
        NSGraphicsContext.current?.imageInterpolation = .high
        NSColor.white.setFill()
        CGRect(x: 0, y: 0, width: w, height: h).fill()
        rep.draw(in: CGRect(x: 0, y: 0, width: w, height: h), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
        NSGraphicsContext.restoreGraphicsState()
        if let data = small.representation(using: .jpeg, properties: [.compressionFactor: 0.72]) {
            try? data.write(to: directory.appending(path: "\(name).jpg"))
        }
    }

    /// The measurements, as JSON, next to the thumbnails.
    static func report(_ value: some Encodable, name: String) {
        guard enabled else { return }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try? enc.encode(value).write(to: directory.appending(path: "\(name).json"))
    }
}
#endif

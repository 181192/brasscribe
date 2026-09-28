#if os(macOS)
import AppKit
import Foundation
import ScoreKit
import SwiftUI
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// Every macOS screen rendered off screen at the window sizes people use, from the smallest the
/// window allows to a 27" display. See docs/research/14-macos-responsiveness.md.
@MainActor
@Suite(.serialized) struct ResponsiveLayoutTests {
    struct WindowSize: Codable {
        let label: String
        let width: CGFloat
        let height: CGFloat
    }

    static let windowSizes: [WindowSize] = [
        .init(label: "900x600", width: 900, height: 600),
        .init(label: "1024x700", width: 1024, height: 700),
        .init(label: "1280x800", width: 1280, height: 800),
        .init(label: "1512x900", width: 1512, height: 900),
        .init(label: "1920x1080", width: 1920, height: 1080),
        .init(label: "2560x1400", width: 2560, height: 1400),
    ]

    struct Render: Codable {
        var screen: String
        var size: String
        var window: CGSize
        var content: CGSize
        var file: String
    }

    struct ScreenReport: Codable {
        var screen: String
        var kind: String
        /// For a window screen, `min` is the window's content minimum SwiftUI reports.
        var sizes: Measure.Sizes
        var renders: [Render]
    }

    /// Renders a window screen at its minimum and every size in `windowSizes`.
    private func window(_ name: String, sizes: [WindowSize] = windowSizes, sidebar: Bool = true, app: AppModel,
                        wait: (() -> Bool)? = nil, @ViewBuilder _ content: () -> some View) async -> ScreenReport {
        let root = HarnessShell(sidebar: sidebar) { content() }.environment(app)
        var measured = Measure.sizes(root)
        measured.min = await OffscreenHost.windowMinimum(root)
        let minimum = WindowSize(label: "min", width: ceil(measured.min.width), height: ceil(measured.min.height) + OffscreenHost.toolbarHeight)
        let first = CGSize(width: 1280, height: 800 - OffscreenHost.toolbarHeight)
        let host = OffscreenHost(root, size: first)
        if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
        var renders: [Render] = []
        for s in [minimum] + sizes {
            // a window never goes below its content minimum: it grows to it, as the real window does
            let content = CGSize(width: max(s.width, measured.min.width),
                                 height: max(s.height - OffscreenHost.toolbarHeight, measured.min.height, 1))
            await host.resize(content)
            if let wait { await host.settle(0.4); await host.settle(until: wait, timeout: 8) } else { await host.settle(0.3) }
            let file = "\(name)-\(s.label)"
            Thumbnails.save(host.bitmap(), name: file, width: 640)
            renders.append(Render(screen: name, size: s.label, window: CGSize(width: s.width, height: s.height), content: content, file: file))
        }
        host.close()
        return ScreenReport(screen: name, kind: "window", sizes: measured, renders: renders)
    }

    /// A sheet opens at its ideal size, within its minimum and maximum.
    private func sheet(_ name: String, app: AppModel, wait: (() -> Bool)? = nil, @ViewBuilder _ content: () -> some View) async -> ScreenReport {
        let root = content().environment(app).tint(Color.Brasscribe.primary)
        let measured = Measure.sizes(root)
        let size = CGSize(width: min(max(measured.ideal.width, measured.min.width), measured.max.width),
                          height: min(max(measured.ideal.height, measured.min.height), measured.max.height))
        let host = OffscreenHost(root, size: size)
        if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
        let file = "sheet-\(name)"
        Thumbnails.save(host.bitmap(), name: file, width: 400)
        host.close()
        return ScreenReport(screen: name, kind: "sheet", sizes: measured,
                            renders: [Render(screen: name, size: "ideal", window: size, content: size, file: file)])
    }

    @Test(.enabled(if: fixtureDir() != nil)) func everyScreenAtEverySize() async throws {
        LayoutFixtures.freshLibrary()
        var reports: [ScreenReport] = []

        // Home
        let empty = LayoutFixtures.app()
        reports.append(await window("home-empty", app: empty) { HomeView() })
        let full = LayoutFixtures.app()
        try LayoutFixtures.library(full)
        reports.append(await window("home-scores", app: full) { HomeView() })
        for (label, state) in [("offline", ConnectionState.offline), ("needs-pairing", .needsPairing(serverName: "Brasscribe on Studio Mac"))] {
            let a = LayoutFixtures.app(connection: state)
            reports.append(await window("home-\(label)", sizes: [Self.windowSizes[2]], app: a) { HomeView() })
        }

        // What is this?
        let src = PendingSource(audioURL: ScreenshotScenes.sceneRecording, title: "Band practice", name: "Band practice.m4a")
        reports.append(await window("source", app: full) { SourceView(source: src) })

        // Transcribing
        let job = TranscriptionJob(source: src, profile: .brassBand, output: OutputChoice(), service: FrozenService())
        full.jobs[job.id] = job
        job.start { _ in }
        reports.append(await window("transcribing", app: full) { TranscribeView(jobID: job.id) })

        // Choose output
        let piece = try LayoutFixtures.piece()
        reports.append(await window("output", app: full) { OutputView(piece: piece) })

        // Score: all parts, one part
        let all = try await LayoutFixtures.model(piece)
        reports.append(await window("score-all", app: full, wait: { !all.pages.isEmpty && !all.engraving }) { PracticeView(model: all).pageBackground() })
        all.stopAll()
        let one = try await LayoutFixtures.model(piece)
        one.shownPart = one.myPart
        reports.append(await window("score-part", app: full, wait: { !one.pages.isEmpty && !one.engraving }) { PracticeView(model: one).pageBackground() })

        // The music stand: the whole window, the sidebar aside
        one.stopAll()
        let onStand = try await LayoutFixtures.model(piece)
        onStand.enterStand(from: .toolbar)
        let stand = try #require(onStand.stand)
        reports.append(await window("stand", sidebar: false, app: full, wait: { !onStand.pages.isEmpty && !onStand.engraving }) {
            MusicStandView(model: onStand, stand: stand).pageBackground()
        })
        onStand.leaveStand()
        onStand.stopAll()

        // Review
        reports.append(await window("review", app: full) { ReviewView(piece: piece) })

        // Problems
        reports.append(await window("problem-silence", app: full) { ProblemView(problem: .silence) })
        for (label, p) in [("copy-protected", Problem.copyProtected), ("cant-open", .cantOpenFile("AVFoundationErrorDomain -11828: cannot open"))] {
            reports.append(await window("problem-\(label)", sizes: [Self.windowSizes[2]], app: full) { ProblemView(problem: p) })
        }

        // Sheets
        reports.append(await sheet("settings", app: full) { SettingsView() })
        let pairing = LayoutFixtures.app(connection: .needsPairing(serverName: "Brasscribe on Studio Mac"))
        reports.append(await sheet("settings-pairing", app: pairing) { SettingsView() })
        let exportModel = try await LayoutFixtures.model(piece)
        reports.append(await sheet("export", app: full) { ExportView(model: exportModel) })
        reports.append(await sheet("talking-score", app: full) { TalkingScoreView(model: exportModel) })
        let items = ReviewList.items(score: exportModel.score, composition: exportModel.composition, uncertainty: exportModel.uncertainty)
        if let target = items.first {
            let xml = (try? String(contentsOf: piece.scoreURL, encoding: .utf8)) ?? ""
            reports.append(await sheet("change-note", app: full) { ChangeNoteSheet(piece: piece, target: target, xml: xml, evidence: nil) {} })
        }
        exportModel.stopAll()
        reports.append(await sheet("first-run", app: full) { FirstRunView() })
        reports.append(await sheet("record-mic", app: full) { MicRecordView() })
        reports.append(await sheet("record-capture", app: full) { CaptureView() })
        reports.append(await sheet("match-code", app: full) { MatchCodeView(code: "4821").padding(Space.s5) })

        Thumbnails.report(reports, name: "measurements")
        #expect(reports.count > 20)
    }
}
#endif

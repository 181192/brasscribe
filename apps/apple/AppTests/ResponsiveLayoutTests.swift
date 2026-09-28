#if os(macOS)
import AppKit
import Foundation
import ScoreKit
import SwiftUI
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// Every macOS screen rendered off screen at the window sizes people use, from the window's minimum
/// to a 27" display, with the layout rules of docs/research/14-macos-responsiveness.md checked on
/// each: one window minimum, actions that follow the content, capped reading columns, a sidebar that
/// steps aside, sheets that hug their content.
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
        /// The library sidebar is showing.
        var sidebar: Bool
        /// Landmarks (`layoutProbe`) in the content's coordinates.
        var probes: [String: CGRect]
    }

    struct ScreenReport: Codable {
        var screen: String
        var kind: String
        /// For a window screen, `min` is the window's content minimum SwiftUI reports.
        var sizes: Measure.Sizes
        var renders: [Render]

        func at(_ size: String) -> Render? { renders.first { $0.size == size } }
    }

    /// Renders a window screen at its minimum and every size in `windowSizes`.
    private func window(_ name: String, sizes: [WindowSize] = windowSizes, sidebar: Bool = true, app: AppModel,
                        opened: (() -> Void)? = nil, wait: (() -> Bool)? = nil, @ViewBuilder _ content: () -> some View) async -> ScreenReport {
        LayoutProbe.frames = [:]
        let root = HarnessShell(sidebar: sidebar) { content() }.environment(app)
        var measured = Measure.Sizes(min: .zero, ideal: .zero, max: .zero)
        let first = CGSize(width: 1280, height: 800 - OffscreenHost.toolbarHeight)
        let host = OffscreenHost(root, size: first)
        if let opened { await host.settle(0.8); opened() }
        if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
        measured.min = host.windowMinimum
        let minimum = WindowSize(label: "min", width: ceil(measured.min.width), height: ceil(measured.min.height) + OffscreenHost.toolbarHeight)
        var renders: [Render] = []
        for s in [minimum] + sizes {
            // a window never goes below its content minimum: it grows to it, as the real window does
            let content = CGSize(width: max(s.width, measured.min.width),
                                 height: max(s.height - OffscreenHost.toolbarHeight, measured.min.height, 1))
            await host.resize(content)
            if let wait { await host.settle(0.4); await host.settle(until: wait, timeout: 8) } else { await host.settle(0.3) }
            // The sidebar came or went. A window that is never shown gets no display pass, so the split
            // view lays the detail out again only at the next resize: nudge it, as a live resize would.
            if host.sidebarShown != renders.last?.sidebar {
                await host.settle(0.6)
                await host.resize(CGSize(width: content.width + 1, height: content.height))
                await host.resize(content)
                await host.settle(0.4)
            }
            let file = "\(name)-\(s.label)"
            Thumbnails.save(host.bitmap(), name: file, width: 640)
            renders.append(Render(screen: name, size: s.label, window: CGSize(width: s.width, height: s.height), content: content, file: file,
                                  sidebar: host.sidebarShown, probes: LayoutProbe.frames))
        }
        host.close()
        return ScreenReport(screen: name, kind: "window", sizes: measured, renders: renders)
    }

    /// A sheet opens at its ideal size, within its minimum and maximum.
    private func sheet(_ name: String, app: AppModel, wait: (() -> Bool)? = nil, @ViewBuilder _ content: () -> some View) async -> ScreenReport {
        LayoutProbe.frames = [:]
        let root = content().environment(app).tint(Color.Brasscribe.primary)
        let measured = Measure.sizes(root)
        let size = CGSize(width: min(max(measured.ideal.width, measured.min.width), measured.max.width),
                          height: min(max(measured.ideal.height, measured.min.height), measured.max.height))
        let host = OffscreenHost(root, size: size)
        if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
        let file = "sheet-\(name)"
        Thumbnails.save(host.bitmap(), name: file, width: 400)
        let probes = LayoutProbe.frames
        host.close()
        return ScreenReport(screen: name, kind: "sheet", sizes: measured,
                            renders: [Render(screen: name, size: "ideal", window: size, content: size, file: file, sidebar: false, probes: probes)])
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
        one.stopAll()

        // The music stand, opened from the score as the toolbar button does: the whole window, the sidebar aside
        let onStand = try await LayoutFixtures.model(piece)
        var spreads: [String: Int] = [:]
        var standPageCount = 0
        reports.append(await window("stand", app: full, opened: { onStand.enterStand(from: .toolbar) }, wait: {
            guard let stand = onStand.stand, !onStand.pages.isEmpty, !onStand.engraving else { return false }
            spreads[String(Int(stand.viewport.width))] = stand.shown(onStand).count
            standPageCount = stand.pages(onStand).count
            return true
        }) {
            ScoreOrStand(model: onStand)
        })
        // closing the test window leaves the stand, as closing the app's window does
        let standPages = standPageCount
        #expect(spreads.count >= Self.windowSizes.count, "the stand stayed open at every size: \(spreads)")
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
            reports.append(await sheet("change-note", app: full) { ChangeNoteSheet(piece: piece, target: target, xml: xml, evidence: nil) { _, _ in } })
        }
        exportModel.stopAll()
        reports.append(await sheet("first-run", app: full) { FirstRunView() })
        reports.append(await sheet("record-mic", app: full) { MicRecordView() })
        reports.append(await sheet("record-capture", app: full) { CaptureView() })
        reports.append(await sheet("match-code", app: full) { MatchCodeView(code: "4821").padding(Space.s5) })

        Thumbnails.report(reports, name: "measurements")
        check(reports, standPages: standPages, spreads: spreads)
    }

    // MARK: the rules

    private func check(_ reports: [ScreenReport], standPages: Int, spreads: [String: Int]) {
        let windows = reports.filter { $0.kind == "window" }
        let sheets = reports.filter { $0.kind == "sheet" }
        let minimum = WindowFit.minimumContent
        let flowPages = ["source", "transcribing", "output", "review", "problem-silence"]

        for r in windows {
            // F1–F3: one window minimum; no screen (the score with every part included) asks for more
            #expect(abs(r.sizes.min.width - minimum.width) <= 1 && abs(r.sizes.min.height - minimum.height) <= 1,
                    "\(r.screen) asks for a \(r.sizes.min) window; the minimum is \(minimum)")
            for x in r.renders {
                // every landmark lies inside the window across (nothing runs off the side)
                for (id, f) in x.probes where !f.isEmpty && !id.hasPrefix("standPage") {
                    #expect(f.minX >= -1 && f.maxX <= x.content.width + 1, "\(r.screen) at \(x.size): \(id) \(f) runs outside \(x.content.width)")
                }
                // F6: the sidebar steps aside below the collapse width, and is there above it
                if r.screen != "stand" {
                    #expect(x.sidebar == (x.content.width >= WindowFit.sidebarCollapseWidth),
                            "\(r.screen) at \(x.size): sidebar \(x.sidebar ? "shown" : "hidden")")
                } else {
                    #expect(!x.sidebar, "the music stand has the whole window")
                }
            }
        }

        // F4: a flow page's actions follow its content inside the column, never pinned to a tall window's bottom
        for name in flowPages {
            guard let r = windows.first(where: { $0.screen == name }) else { Issue.record("\(name) not rendered"); continue }
            for size in ["1920x1080", "2560x1400"] {
                guard let x = r.at(size), let actions = x.probes["pageActions"], let column = x.probes["pageColumn"] else {
                    Issue.record("\(name) at \(size): no actions or column"); continue
                }
                #expect(actions.maxY <= column.maxY + 1, "\(name) at \(size): the actions sit below the column")
                #expect(actions.maxX <= column.maxX + 1 && actions.minX >= column.minX - 1, "\(name) at \(size): the actions leave the column")
                #expect(x.content.height - actions.maxY > 200, "\(name) at \(size): the actions are at the window's bottom (\(actions.maxY) of \(x.content.height))")
            }
        }

        // readable widths at 2560: the reading column 720, Home 920, the output choices 880
        let caps: [String: CGFloat] = ["source": 720, "transcribing": 720, "review": 720, "problem-silence": 720,
                                       "home-empty": 920, "home-scores": 920, "output": 880]
        for (name, cap) in caps {
            guard let x = windows.first(where: { $0.screen == name })?.at("2560x1400"), let column = x.probes["pageColumn"] else {
                Issue.record("\(name): no column at 2560"); continue
            }
            #expect(column.width <= cap + 1, "\(name): the column is \(column.width) wide at 2560, more than \(cap)")
        }

        // Home: the two ways in fill the row in two equal columns (no empty third)
        for size in ["min", "1280x800", "2560x1400"] {
            guard let x = windows.first(where: { $0.screen == "home-scores" })?.at(size),
                  let a = x.probes["wayIn-record"], let b = x.probes["wayIn-capture"], let drop = x.probes["dropArea"] else {
                Issue.record("home at \(size): no ways in"); continue
            }
            #expect(abs(a.width - b.width) <= 1, "home at \(size): the ways in differ in width")
            #expect(abs(b.maxX - drop.maxX) <= 1, "home at \(size): the ways in leave the row's end empty")
        }

        // What is this?: the cards in a row are as tall as each other
        if let x = windows.first(where: { $0.screen == "source" })?.at("1280x800") {
            let rows = [("solo", "brass-band"), ("orchestra-with-soloist", "pop-rock")]
            for (l, r) in rows {
                if let a = x.probes["profile-\(l)"], let b = x.probes["profile-\(r)"] {
                    #expect(abs(a.height - b.height) <= 1, "What is this?: \(l) and \(r) differ in height")
                } else {
                    Issue.record("What is this?: no cards \(l), \(r)")
                }
            }
        }

        // the score: the parts column shows where it fits, and its toggles keep one line
        for name in ["score-all", "score-part"] {
            guard let r = windows.first(where: { $0.screen == name }) else { continue }
            for x in r.renders {
                if let parts = x.probes["partsColumn"] {
                    #expect(parts.maxX <= x.content.width + 1, "\(name) at \(x.size): the parts column runs off the window")
                    #expect(parts.height <= x.content.height + 1, "\(name) at \(x.size): the parts column is taller than the window")
                }
                let toggles = x.probes.filter { $0.key.hasPrefix("onlyThis-") }.values
                for t in toggles { #expect(t.height <= 36, "\(name) at \(x.size): Only this wraps (\(t.height) pt)") }
            }
            #expect(r.at("1280x800")?.probes["partsColumn"] != nil, "\(name): the parts column shows at 1280")
        }

        // the stand: a spread only with two pages; one page sits in the middle
        if standPages < 2 {
            #expect(spreads.values.allSatisfy { $0 == 1 }, "the stand shows a spread of one page: \(spreads)")
            if let x = windows.first(where: { $0.screen == "stand" })?.at("1920x1080"), let page = x.probes["standPage-0"] {
                #expect(abs(page.midX - x.content.width / 2) <= 2, "the stand's one page is off centre: \(page)")
                #expect(page.minX >= -1, "the stand's page is cut on the left: \(page)")
            }
        }

        // sheets: their content's size, within their limits and at most 90 % of the screen's height
        let maxHeight = SheetSize.maxHeight
        for s in sheets {
            #expect(s.sizes.ideal.height <= maxHeight + 1, "\(s.screen) opens \(s.sizes.ideal.height) tall, more than \(maxHeight)")
            #expect(s.sizes.min.height <= s.sizes.ideal.height + 1, "\(s.screen) is held taller (\(s.sizes.min.height)) than its content")
        }
        for name in ["export", "change-note", "first-run", "record-mic", "record-capture"] {
            guard let s = sheets.first(where: { $0.screen == name }) else { Issue.record("\(name) not rendered"); continue }
            #expect(s.sizes.min.height <= 1, "\(name) has a fixed minimum height (\(s.sizes.min.height))")
            #expect(s.sizes.max.height >= s.sizes.ideal.height, "\(name) has a fixed height")
        }
        if let s = sheets.first(where: { $0.screen == "settings" }) {
            #expect(s.sizes.ideal.width <= 680 && s.sizes.ideal.width >= 520, "Settings opens \(s.sizes.ideal.width) wide")
            #expect(s.renders.first?.probes["settingsDone"] != nil, "Settings on the Mac has a Done button")
        }
    }
}
#endif

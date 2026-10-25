#if os(macOS)
import AppKit
import Foundation
import Testing
import WebKit
import TabKit
@testable import Fretscribe

/// The page engraved off screen, in a window no one sees.
@MainActor
private func hosted(_ page: TabPage, width: CGFloat = 800) -> NSWindow {
    page.webView.frame = CGRect(x: 0, y: 0, width: width, height: 900)
    let window = NSWindow(contentRect: page.webView.frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = page.webView
    window.setFrameOrigin(NSPoint(x: -10_000, y: -10_000))
    window.orderBack(nil)
    return window
}

private func fixture(_ name: String) throws -> Data {
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appending(path: "../../../../fixtures/\(name)").standardizedFileURL
    return try Data(contentsOf: url)
}

/// With `TAB_SHOTS` set, the page with its marks' boxes drawn over it is written there, to look at.
@MainActor
private func save(_ page: TabPage, marks: [TabMarkBox], _ name: String) async throws {
    guard let dir = ProcessInfo.processInfo.environment["TAB_SHOTS"] else { return }
    let cfg = WKSnapshotConfiguration()
    cfg.afterScreenUpdates = true
    let image = try await page.webView.takeSnapshot(configuration: cfg)
    let marked = NSImage(size: image.size, flipped: true) { rect in
        image.draw(in: rect)
        NSColor.systemPink.setStroke()
        for m in marks {
            NSBezierPath(rect: CGRect(x: m.x - m.width / 2, y: m.top, width: m.width, height: m.bottom - m.top)).stroke()
            NSBezierPath(rect: MarkTarget.frame(m)).stroke()
        }
        return true
    }
    guard let tiff = marked.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return }
    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
    try png.write(to: URL(fileURLWithPath: dir).appending(path: name))
}

private let palette = TabPalette(ink: "#1a1a1a", string: "#8a8a8a", uncertain: "#c0392b", cursor: "#2f6fde", cursorTint: "#2f6fde33")

@MainActor
@Suite(.serialized) struct TabPageMarksTests {
    @Test(.timeLimit(.minutes(1))) func eachMarkStandsOverItsColumnAboveTheStaff() async throws {
        let json = try fixture("bass-line-marks/tab.json")
        let sheet = TabSheet(musicXML: String(decoding: try fixture("bass-line-marks/tab.musicxml"), as: UTF8.self),
                             data: try JSONDecoder().decode(TabData.self, from: json),
                             details: try JSONDecoder().decode(TabDetails.self, from: json))
        let page = TabPage()
        let window = hosted(page)
        defer { window.close() }
        let e = try await page.show(musicXML: Data(TabIndex.forRenderer(sheet.musicXML, header: sheet.index.header).utf8),
                                    palette: palette, scale: 1, marks: sheet.spots, markStaff: sheet.index.markStaff)
        #expect(e.bars.count == 16)
        #expect(e.marks.map(\.mark) == [0, 1, 2])
        #expect(!e.lines.isEmpty)
        #expect(e.lines.first?.first == 0 && e.lines.last?.last == 15)
        for box in e.marks {
            let column = sheet.marks.columns[box.mark]
            let bar = try #require(e.bars.first { $0.bar == column.bar })
            #expect(box.x >= bar.x && box.x <= bar.x + bar.w, "mark \(box) in bar \(bar)")
            #expect(box.bottom > box.top)
            // Above its column's numerals, below the line before it, and in the upper half of its own line.
            let line = try #require(e.lines.firstIndex { column.bar >= $0.first && column.bar <= $0.last })
            let above = line > 0 ? e.lines[line - 1].bottom : 0
            #expect(box.top >= above - 1 && box.bottom < box.columnBottom, "mark \(box) over its column in \(e.lines[line])")
            #expect(box.bottom < (e.lines[line].top + e.lines[line].bottom) / 2)
        }
        try await save(page, marks: e.marks, "tab-marks.png")
        // A narrower page is laid out again by itself, with more lines and its marks where its columns now are.
        page.webView.frame.size.width = 450
        var narrow = page.engraving
        for _ in 0..<40 where (narrow?.lines.count ?? 0) <= e.lines.count {
            try await Task.sleep(for: .milliseconds(50))
            narrow = page.engraving
        }
        #expect((narrow?.lines.count ?? 0) > e.lines.count)
        #expect(narrow?.marks.count == 3)
        page.webView.frame.size.width = 800
        // A larger page is engraved again, with the marks where its columns now are.
        let larger = try await page.show(musicXML: Data(TabIndex.forRenderer(sheet.musicXML, header: sheet.index.header).utf8),
                                         palette: palette, scale: 1.5, marks: sheet.spots, markStaff: sheet.index.markStaff)
        #expect(larger.height > e.height)
        #expect(larger.marks.count == 3)
    }
}
#endif

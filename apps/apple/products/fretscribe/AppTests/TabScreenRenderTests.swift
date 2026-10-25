#if os(macOS)
import AppKit
import Foundation
import ScreenCatalogue
import SwiftUI
import Testing
import TabKit
import WebKit
@testable import Fretscribe

/// The tab screen drawn off screen, in a window no one sees, with a song from the fixtures and no recording.
@MainActor
@Suite(.serialized) struct TabScreenRenderTests {
    private static func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../fixtures/\(name)").standardizedFileURL
    }

    /// The song "Bass line" in a folder of its own, with the recording `recording` when it is given.
    private static func song(in songs: URL, recording: URL? = nil) throws -> TabSong {
        setenv("SCRIBE_SONGS", songs.path, 1)
        let song = TabSong(id: UUID(), title: "Bass line", created: Date(), jobID: nil, preset: "bass-4-standard", toCheck: 2, recording: recording)
        try song.save()
        try FileManager.default.copyItem(at: fixture("bass-line-marks/tab.musicxml"), to: song.musicXMLURL)
        try FileManager.default.copyItem(at: fixture("bass-line-marks/tab.json"), to: song.tabURL)
        return song
    }

    /// Thirty seconds of silence, as a WAV file.
    private static func silence(_ url: URL) throws {
        let rate: UInt32 = 8000, bytes = rate * 2 * 30
        var d = Data("RIFF".utf8)
        func put<T: FixedWidthInteger>(_ v: T) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        put(UInt32(36 + bytes)); d.append(contentsOf: "WAVEfmt ".utf8)
        put(UInt32(16)); put(UInt16(1)); put(UInt16(1)); put(rate); put(rate * 2); put(UInt16(2)); put(UInt16(16))
        d.append(contentsOf: "data".utf8); put(bytes)
        d.append(Data(count: Int(bytes)))
        try d.write(to: url)
    }

    @MainActor private final class Window {
        let hosting: NSView
        let window: NSWindow
        init<V: View>(_ view: V) {
            hosting = NSHostingView(rootView: view)
            window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 900, height: 700), styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = hosting
            window.setFrameOrigin(NSPoint(x: -10_000, y: -10_000))
            window.orderBack(nil)
        }
        func close() { window.close() }
    }

    /// The tree once `ready` says it is there, for five seconds at most.
    private static func tree(_ view: NSView, until ready: ([AXNode]) -> Bool) async throws -> [AXNode] {
        var nodes: [AXNode] = []
        for _ in 0..<50 {
            try await Task.sleep(for: .milliseconds(100))
            nodes = AXTree.read(view)
            if ready(nodes) { break }
        }
        return nodes
    }

    /// The tempo and the speed are read in words longer than what they show ("100 beats a minute" for "♩ = 100", "Speed
    /// 100 %" for "100 %"): not text cut off.
    private static func findings(_ nodes: [AXNode], in view: NSView) -> [Finding] {
        Checks.run(nodes, bounds: view.bounds, text: TextFit()).filter { f in
            !(f.kind == .clippedText && (["beats a minute", "slag i minuttet", "“Speed ", "“Tempo "].contains { f.node.contains($0) }))
        }
    }

    @Test(.timeLimit(.minutes(1))) func thePlayerHasEveryControlNamedAndLargeEnough() async throws {
        AXTree.enableInProcess()
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-tab-screen-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? FileManager.default.removeItem(at: songs) }
        try FileManager.default.createDirectory(at: songs, withIntermediateDirectories: true)
        let recording = songs.appending(path: "take.wav")
        try Self.silence(recording)
        let song = try Self.song(in: songs, recording: recording)
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-tab-screen-\(UUID().uuidString)")!)
        let host = Window(NavigationStack { TabScreen(song: song) }.environment(model).playHost(model))
        defer { host.close() }
        let nodes = try await Self.tree(host.hosting) { $0.contains { $0.label == "Play" } && $0.contains { $0.label.hasPrefix("Bar 15,") } }
        for name in ["Play", "Back to the start", "Previous bar", "Next bar", "Slower", "Faster", "Repeat bars"] {
            #expect(nodes.contains { $0.label == name }, "\(name) in \(nodes.map(\.description).joined(separator: "\n"))")
        }
        #expect(nodes.contains { $0.words.hasPrefix("Speed 100") })
        for control in nodes where control.isActionable {
            #expect(control.frame.width >= 44 && control.frame.height >= 44, "\(control)")
        }
        let findings = Self.findings(nodes, in: host.hosting)
        #expect(findings.isEmpty, "\(findings.map(\.description).joined(separator: "\n"))")
        if let dir = ProcessInfo.processInfo.environment["TAB_SHOTS"] {
            try Pictures.write(Pictures.bitmap(of: host.hosting), tree: nodes, name: "tab-screen-player", to: URL(fileURLWithPath: dir))
        }
        model.practice.leave()
    }

    @Test(.timeLimit(.minutes(1))) func theTabIsOneElementWithItsMarksAndEveryControlIsNamedAndLargeEnough() async throws {
        AXTree.enableInProcess()
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-tab-screen-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? FileManager.default.removeItem(at: songs) }
        let song = try Self.song(in: songs)
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-tab-screen-\(UUID().uuidString)")!)
        let host = Window(NavigationStack { TabScreen(song: song) }.environment(model).playHost(model))
        defer { host.close() }
        let hosting = host.hosting

        let summary = "Bass line. Tab. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?. 1 note with no place."
        let nodes = try await Self.tree(hosting) { $0.contains { $0.label.hasPrefix("Bar 15, beat 1.") } }
        #expect(nodes.contains { $0.label == summary }, "\(nodes.map(\.description).joined(separator: "\n"))")
        let marks = nodes.filter { $0.role == "AXButton" && $0.label.hasPrefix("Bar ") }.map(\.label)
        #expect(marks == [
            "Bar 3, beat 2. 3rd string, fret 2, B. Fretscribe isn't sure about this one.",
            "Bar 7, beat 2. D1 is lower than your lowest string. Is the tuning right?",
            "Bar 15, beat 1. 4th string, open, E. Fretscribe isn't sure about this one.",
        ])
        #expect(nodes.contains { $0.role == "AXButton" && $0.label == "Tuning: Standard, no capo" })
        #expect(nodes.contains { $0.words.hasPrefix("The recording is not on this device.") })
        for mark in nodes where mark.role == "AXButton" && mark.label.hasPrefix("Bar ") {
            #expect(mark.frame.width >= 44 && mark.frame.height >= 44, "\(mark)")
        }
        let findings = Self.findings(nodes, in: hosting)
        // The tab is read first, then its marks in reading order.
        let tab = try #require(nodes.firstIndex { $0.label == summary })
        #expect(nodes.firstIndex { $0.label.hasPrefix("Bar 3,") }.map { $0 > tab } == true)
        #expect(findings.isEmpty, "\(findings.map(\.description).joined(separator: "\n"))")

        if let dir = ProcessInfo.processInfo.environment["TAB_SHOTS"] {
            try Pictures.write(Pictures.bitmap(of: hosting), tree: nodes, name: "tab-screen", to: URL(fileURLWithPath: dir))
        }
        // A click or the wheel over the tab goes to the screen, never to the web view under it.
        let over = try #require(hosting.superview).convert(NSPoint(x: 100, y: hosting.bounds.midY), from: hosting)
        var hit = hosting.superview?.hitTest(over)
        #expect(hit != nil)
        while let view = hit {
            #expect(!(view is WKWebView), "\(view)")
            hit = view.superview
        }
    }

    @Test(.timeLimit(.minutes(1)), arguments: [true, false])
    func inFullScreenTheControlsAreNamedAndLargeEnough(controls: Bool) async throws {
        AXTree.enableInProcess()
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-tab-screen-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? FileManager.default.removeItem(at: songs) }
        try FileManager.default.createDirectory(at: songs, withIntermediateDirectories: true)
        let recording = songs.appending(path: "take.wav")
        try Self.silence(recording)
        let song = try Self.song(in: songs, recording: recording)
        let model = FretscribeModel(defaults: UserDefaults(suiteName: "fs-tab-screen-\(UUID().uuidString)")!)
        let host = Window(NavigationStack { TabScreen(song: song, focus: TabFocus(on: true, controls: controls)) }.environment(model).playHost(model))
        defer { host.close() }
        let nodes = try await Self.tree(host.hosting) { $0.contains { $0.label == "Play" } && $0.contains { $0.label.hasPrefix("Bar 15,") } }
        let names = controls ? ["Leave full screen", "Zoom out", "Zoom in", "Play", "Previous bar", "Next bar", "Repeat bars"] : ["Play", "Leave full screen"]
        for name in names { #expect(nodes.contains { $0.label == name }, "\(name) in \(nodes.map(\.description).joined(separator: "\n"))") }
        if !controls {
            // Only the small buttons: no player, no header.
            #expect(!nodes.contains { $0.label == "Previous bar" })
            #expect(!nodes.contains { $0.label == "Tuning: Standard, no capo" })
        }
        for control in nodes where control.isActionable {
            #expect(control.frame.width >= 44 && control.frame.height >= 44, "\(control)")
        }
        let findings = Self.findings(nodes, in: host.hosting)
        #expect(findings.isEmpty, "\(findings.map(\.description).joined(separator: "\n"))")
        if let dir = ProcessInfo.processInfo.environment["TAB_SHOTS"] {
            try Pictures.write(Pictures.bitmap(of: host.hosting), tree: nodes, name: "tab-screen-full-\(controls ? "controls" : "minimal")",
                               to: URL(fileURLWithPath: dir))
        }
        model.practice.leave()
    }
}
#endif

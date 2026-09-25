import CoreGraphics
import Foundation
import Testing
import ScoreKit
import SVGRender
@testable import NotationKit

/// Resident footprint of this process (what jetsam counts on iOS).
func footprintMB() -> Double {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count) }
    }
    return kr == KERN_SUCCESS ? Double(info.phys_footprint) / 1_048_576 : 0
}

func mikkelXML() throws -> String {
    try String(contentsOf: try #require(goldenDir()).appending(path: "brass-band.musicxml"), encoding: .utf8)
}

@Suite(.serialized, .enabled(if: goldenDir() != nil)) struct NotationSpike {
    @Test func timemapMatchesScoreBeats() throws {
        let xml = try mikkelXML()
        let score = try MusicXMLParser.parse(Data(xml.utf8))
        let r = try #require(ScoreRenderer(musicXML: xml))
        #expect(r.apply(.init()))
        #expect(r.measureIDs.count == score.measures.count)
        // the solo cornet's first note at beat 3.5
        let s = r.sounding(atBeat: 3.5)
        #expect(!s.notes.isEmpty)
        #expect(s.measureIndex == 0)
        #expect(r.sounding(atBeat: 4.0).measureIndex == 1)
        #expect(r.sounding(atBeat: 40.1).measureIndex == 10)
    }

    @Test func showOnePartAndConcertPitch() throws {
        let xml = try mikkelXML()
        let score = try MusicXMLParser.parse(Data(xml.utf8))
        let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
        let r = try #require(ScoreRenderer(musicXML: xml))
        #expect(r.apply(.init(parts: [solo.id])))
        let written = try #require(r.page(1))
        #expect(written.svg.ids(ofClass: "staff").count == written.measureIDs.count) // one staff per measure
        #expect(written.measureIDs.count > 8)
        let keyWritten = written.svg.ids(ofClass: "keyAccid").count
        #expect(r.apply(.init(parts: [solo.id], pitch: .concert)))
        let concert = try #require(r.page(1))
        let keyConcert = concert.svg.ids(ofClass: "keyAccid").count
        // B-flat cornet reads D major (2 sharps) for concert C major (none)
        #expect(keyWritten > 0)
        #expect(keyConcert == 0)
        #expect(r.uncertainNoteIDs.count > 0)
    }

    /// The numbers behind docs/notation-spike.md.
    @Test func measureNativeRendering() throws {
        let xml = try mikkelXML()
        let m0 = footprintMB()
        let t0 = Date()
        let r = try #require(ScoreRenderer(musicXML: xml))
        #expect(r.apply(.init(width: 820)))
        let load = Date().timeIntervalSince(t0)
        let m1 = footprintMB()
        let t1 = Date()
        var svgBytes = 0, ops = 0
        var svgMS: [Double] = []
        var parseMS: [Double] = []
        let tk = try #require(VerovioToolkit())
        tk.setOptions(["pageWidth": 2050, "pageHeight": 60000, "adjustPageHeight": true, "scale": 40, "breaks": "auto",
                       "header": "none", "footer": "none"])
        _ = tk.loadData(xml)
        for p in 1...tk.pageCount {
            let a = Date()
            let s = tk.renderToSVG(page: p)
            svgMS.append(Date().timeIntervalSince(a) * 1000)
            svgBytes += s.utf8.count
            let b = Date()
            let d = try SVGDocument(svg: s)
            parseMS.append(Date().timeIntervalSince(b) * 1000)
            ops += d.ops.count
        }
        let pages = r.renderAllPages()
        let renderAll = Date().timeIntervalSince(t1)
        let m2 = footprintMB()
        // draw every page at 2x (retina) into a bitmap
        let t2 = Date()
        for p in pages {
            let s: CGFloat = 2
            let w = Int(p.svg.size.width * s), h = Int(p.svg.size.height * s)
            let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            ctx.translateBy(x: 0, y: CGFloat(h)); ctx.scaleBy(x: s, y: -s)
            p.svg.draw(in: ctx)
        }
        let draw = Date().timeIntervalSince(t2)
        let firstPage = (svgMS.first ?? 0) + (parseMS.first ?? 0)
        let report = """
        native: verovio load+layout \(Int(load * 1000)) ms; pages \(pages.count); svg total \(svgBytes / 1024) kB; \
        per page renderToSVG median \(Int(svgMS.sorted()[svgMS.count / 2])) ms, parse median \(Int(parseMS.sorted()[parseMS.count / 2])) ms; \
        first page ready \(Int(load * 1000 + firstPage)) ms; all pages svg+parse \(Int(renderAll * 1000)) ms; \
        draw all @2x \(Int(draw * 1000)) ms (\(ops) ops); footprint base \(Int(m0)) MB, +verovio \(Int(m1 - m0)) MB, +all pages \(Int(m2 - m1)) MB
        """
        print("SPIKE", report)
        if let out = ProcessInfo.processInfo.environment["SPIKE_OUT"] {
            try (report + "\n").write(toFile: out + ".native.txt", atomically: true, encoding: .utf8)
        }
        #expect(pages.count == r.pageCount)
    }

}


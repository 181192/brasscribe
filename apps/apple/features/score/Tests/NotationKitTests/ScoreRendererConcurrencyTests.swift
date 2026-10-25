import Foundation
import Testing
@testable import NotationKit

/// A small score whose timemap changes size with the layout: all four parts, or one.
private func quartet(bars: Int) -> String {
    let parts = (1...4).map { "<score-part id=\"P\($0)\"><part-name>Cornet \($0)</part-name></score-part>" }.joined()
    let steps = ["C", "D", "E", "F", "G", "A", "B"]
    let body = (1...4).map { p in
        let measures = (1...bars).map { m in
            let attrs = m > 1 ? "" : "<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>"
            // part p plays notes of 4 / p beats, so each part adds its own onsets to the timemap
            let dur = [1, 2, 4, 4][p - 1]
            let notes = (0..<(4 / dur)).map { i in
                "<note><pitch><step>\(steps[(m + i + p) % 7])</step><octave>4</octave></pitch><duration>\(dur)</duration></note>"
            }.joined()
            return "<measure number=\"\(m)\">\(attrs)\(notes)</measure>"
        }.joined()
        return "<part id=\"P\(p)\">\(measures)</part>"
    }.joined()
    return "<?xml version=\"1.0\"?><score-partwise version=\"4.0\"><part-list>\(parts)</part-list>\(body)</score-partwise>"
}

/// The cursor reads the engraving at 20 Hz on the main thread while `apply` re-engraves on a
/// background task (zoom, part or pitch change). Every read sees one whole engraving.
@Test func soundingIsSafeWhileApplyRuns() async throws {
    let bars = 24
    let r = try #require(ScoreRenderer(musicXML: quartet(bars: bars)))
    let all = ScoreRenderer.Layout(width: 800, zoom: 1)
    let one = ScoreRenderer.Layout(width: 800, zoom: 1, parts: ["P4"])
    #expect(r.apply(all))
    let full = r.timemap.count
    #expect(r.apply(one))
    let single = r.timemap.count
    #expect(full > single, "the layouts publish timemaps of different sizes")

    let stop = ManagedFlag()
    let writer = Task.detached {
        var n = 0
        while !stop.isSet {
            _ = r.apply(n % 2 == 0 ? all : one)
            _ = r.page(1)
            n += 1
        }
        return n
    }
    let readers = (0..<4).map { k in
        Task.detached {
            var reads = 0
            let deadline = Date().addingTimeInterval(2)
            while Date() < deadline {
                let beat = Double((reads * 7 + k) % (bars * 4))
                let s = r.sounding(atBeat: beat)
                let e = r.engraving
                // a snapshot is internally consistent: its timemap and bar list belong together
                precondition(e.timemap.count == full || e.timemap.count == single)
                precondition(e.measureIDs.count == bars && e.measureIndex.count == bars)
                precondition((0..<bars).contains(s.measureIndex))
                _ = r.uncertainNoteIDs
                reads += 1
            }
            return reads
        }
    }
    var reads = 0
    for t in readers { reads += await t.value }
    stop.set()
    let applies = await writer.value
    #expect(applies > 2 && reads > 100, "\(applies) engravings, \(reads) reads")
    // the cursor still lands on the right bar afterwards
    #expect(r.apply(all))
    #expect(r.sounding(atBeat: 4 * 5 + 0.5).measureIndex == 5)
}

private final class ManagedFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var isSet: Bool { lock.withLock { value } }
    func set() { lock.withLock { value = true } }
}

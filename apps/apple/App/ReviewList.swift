import Foundation
import ScoreKit

/// One uncertain note (or chord) to check: a part, a bar and an onset.
struct ReviewItem: Identifiable, Hashable {
    /// Stable across launches: part id and onset tick.
    let id: String
    let partID: String
    let partName: String
    let partIndex: Int
    /// 0-based bar index.
    let bar: Int
    let tick: Int
    /// Index into the part's notes of the first note at this onset.
    let noteIndex: Int
    let level: UncertaintyLevel
    /// A review group: the last tick of the group (exclusive) and how many marked notes it has.
    var endTick: Int? = nil
    var noteCount = 1
    /// 0-based last bar of the group (the same as `bar` for one note).
    var lastBar: Int? = nil
}

enum ReviewList {
    /// What to review: the engine's review groups when the Composition has them (one item
    /// per group and part it reaches), otherwise every uncertain onset.
    static func items(score: Score, composition: Composition?, uncertainty: UncertaintyIndex) -> [ReviewItem] {
        if let comp = composition, !comp.review.isEmpty { return groups(score: score, composition: comp, uncertainty: uncertainty) }
        return items(score: score, uncertainty: uncertainty)
    }

    /// One item per review group per arranged part that carries its notes: the part's notes
    /// starting inside the group that inherit its uncertainty. Keep keeps the whole group.
    static func groups(score: Score, composition comp: Composition, uncertainty: UncertaintyIndex) -> [ReviewItem] {
        let q = Double(Score.ticksPerQuarter) / Double(comp.ticksPerBeat)
        var out: [ReviewItem] = []
        let voices = Dictionary(comp.voices.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        // Only the parts the arranger marked play the reviewed voices; others that happen to share a pitch don't.
        let anyMarked = score.parts.contains(where: \.hasMarks)
        for (k, part) in score.parts.enumerated() where !part.isPercussion && (!anyMarked || part.hasMarks) {
            for g in comp.review {
                // the part carries the group when it plays the group's first note (onset and pitch class)
                guard let lead = voices[g.voice]?.notes.filter({ $0.start >= g.start && $0.start < g.end }).min(by: { $0.start < $1.start })
                else { continue }
                let lo = Int((Double(g.start) * q).rounded()), hi = Int((Double(g.end) * q).rounded())
                let leadTick = Int((Double(lead.start) * q).rounded())
                let pc = ((lead.pitch % 12) + 12) % 12
                guard let first = part.notes.enumerated().first(where: { _, n in
                    !n.isRest && !n.tieStop && n.startTick == leadTick && n.midiPitch.map { (($0 % 12) + 12) % 12 == pc } == true
                }) else { continue }
                let lastNote = part.notes.last { !$0.isRest && !$0.tieStop && $0.startTick >= lo && $0.startTick < hi } ?? first.element
                out.append(ReviewItem(id: "\(part.id)|g\(g.start)", partID: part.id, partName: part.displayName, partIndex: k,
                                      bar: first.element.measureIndex, tick: first.element.startTick, noteIndex: first.offset,
                                      level: g.very ? .veryUncertain : .uncertain, endTick: hi, noteCount: max(1, g.notes),
                                      lastBar: lastNote.measureIndex))
            }
        }
        return out
    }

    /// Every uncertain onset, sorted by part (score order), then bar.
    static func items(score: Score, uncertainty: UncertaintyIndex) -> [ReviewItem] {
        guard !uncertainty.isEmpty else { return [] }
        var out: [ReviewItem] = []
        for (k, part) in score.parts.enumerated() where !part.isPercussion {
            var byTick: [Int: (index: Int, level: UncertaintyLevel)] = [:]
            var order: [Int] = []
            for (i, n) in part.notes.enumerated() where !n.tieStop {
                guard let level = uncertainty.level(n) else { continue }
                if let have = byTick[n.startTick] {
                    if level == .veryUncertain, have.level != .veryUncertain { byTick[n.startTick] = (have.index, level) }
                } else {
                    byTick[n.startTick] = (i, level)
                    order.append(n.startTick)
                }
            }
            for t in order {
                guard let e = byTick[t] else { continue }
                out.append(ReviewItem(id: "\(part.id)|\(t)", partID: part.id, partName: part.displayName, partIndex: k,
                                      bar: part.notes[e.index].measureIndex, tick: t, noteIndex: e.index, level: e.level))
            }
        }
        return out
    }
}

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
}

enum ReviewList {
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

import Foundation
import TabKit

/// A "?" over a note Fretscribe is not sure of, or a boxed "!" over a note that has no place on the instrument.
enum MarkKind: Equatable, Sendable { case doubt, noPlace }

/// Why a note has no place on the instrument.
enum NoPlaceWhy: Equatable, Sendable { case tooLow, tooHigh, other }

/// One note under a mark.
struct MarkedNote: Equatable, Sendable {
    var kind: MarkKind
    /// Its place in the tab's notes; nil for a "!" read from the page alone, which says no more than a name.
    var note: Int?
    /// 1 is the top line.
    var string: Int?
    var fret: Int?
    /// The pitch as the page spells it; nil when the page does not spell it.
    var step: String?
    var alter: Int = 0
    /// The note as the boxed words name it ("D1"), for a note the tab staff leaves out.
    var name: String?
    var why: NoPlaceWhy = .other

    /// The pitch class it is spelled as (0 is C); nil without a spelling.
    var pitchClass: Int? {
        guard let step, let base = ["C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11][step] else { return nil }
        return ((base + alter) % 12 + 12) % 12
    }
}

/// A column of the tab with a mark over it: one beat of one staff, and the notes there the mark is for.
struct TabColumn: Equatable, Sendable {
    var staff: Int
    /// The measure, counted from 0 as written.
    var bar: Int
    var barNumber: String
    /// From the start of the measure, in `TabIndex.ticks`.
    var onset: Int
    /// 1 is the first beat of the bar.
    var beat: Int
    var notes: [MarkedNote]
    /// In the pickup: the notes before the first full bar.
    var pickup: Bool = false

    /// A column with a note that has no place shows the boxed "!"; its doubtful notes are still coloured and described.
    var kind: MarkKind { notes.contains { $0.kind == .noPlace } ? .noPlace : .doubt }

    var hasDoubt: Bool { notes.contains { $0.kind == .doubt } }

    /// What the page is told of the column: where it is, and its notes.
    var spot: TabMarkSpot {
        TabMarkSpot(staff: staff, bar: bar, tick: onset, notes: notes.map {
            TabMarkSpot.Note(string: $0.string, fret: $0.fret, pitchClass: $0.pitchClass, doubt: $0.kind == .doubt)
        })
    }
}

/// The marks of a tab, in reading order, with what the header counts: `doubtful` notes marked "?" and `noPlace`
/// notes under a "!", both as they are drawn. `unplaced` counts marked notes the page has no column for (a note the
/// writer folded into another, or a "!" the page and the data disagree about): they are not drawn, nor counted.
struct TabMarks: Equatable, Sendable {
    var columns: [TabColumn]
    var doubtful: Int
    var noPlace: Int
    var unplaced: Int

    /// A note below this confidence gets a "?".
    static let threshold = SongMarks.doubt

    /// The columns with a note in doubt, in reading order: where "Check them" and Next ? go.
    var doubts: [Int] { columns.indices.filter { columns[$0].hasDoubt } }

    /// The marks from the tab's data: a "?" for every note below `threshold`, a boxed "!" for every note without a
    /// place, each tied to its column by the page's note index. `details` says the instrument's range, for why a note
    /// has no place. Without `tab` the page itself is read: the confidence it carries on its doubtful notes, and its
    /// boxed words.
    static func of(_ index: TabIndex, tab: TabData?, details: TabDetails? = nil, threshold: Double = threshold) -> TabMarks {
        let staff = index.markStaff
        var order: [Key] = []
        var found: [Key: [MarkedNote]] = [:]
        var places: [Key: (String, Int, Bool)] = [:]
        var unplaced = 0

        func add(_ bar: Int, _ number: String, _ onset: Int, _ beat: Int, _ pickup: Bool, _ note: MarkedNote) {
            let at = Key(bar: bar, onset: onset)
            places[at] = (number, beat, pickup)
            if found[at] == nil { order.append(at) }
            found[at, default: []].append(note)
        }
        func doubt(_ p: TabPiece) {
            add(p.bar, p.barNumber, p.onset, p.beat, p.pickup,
                MarkedNote(kind: .doubt, note: p.note, string: p.string, fret: p.fret, step: p.step, alter: p.alter))
        }
        /// Where a note starts on the staff with the marks.
        func start(_ note: Int) -> TabPiece? {
            let all = index.of(note)
            return all.first { $0.staff == staff && $0.first } ?? all.first { $0.staff == staff }
        }

        let boxedWords = index.noPlace.filter { $0.staff == staff }
        if let tab {
            let strings = details?.instrument?.tuning?.strings ?? []
            let capo = details?.instrument?.capo ?? 0
            let lowest = strings.map { $0.openPitch + capo }.min()
            let highest = details?.instrument?.frets.flatMap { f in strings.map { $0.openPitch + f }.max() }
            // The boxed words of the page, one name each, in order: where the tab staff has no note to carry an index.
            var boxed = boxedWords.flatMap { b in (b.names.isEmpty ? [""] : b.names).map { (b, $0) } }
            for (i, note) in tab.notes.enumerated() {
                let outOfRange = details?.notes?[safe: i]?.outOfRange ?? false
                let placed = !outOfRange && note.string != nil && note.fret != nil
                if !placed {
                    let why: NoPlaceWhy = if let lowest, note.pitch < lowest { .tooLow }
                        else if let highest, note.pitch > highest { .tooHigh }
                        else { .other }
                    // On a notation staff the note is written, with its index; on a tab staff only the boxed words stand for it.
                    let written = index.of(i).first { $0.first } ?? index.of(i).first
                    let words = boxed.isEmpty ? nil : boxed.removeFirst()
                    let name = words.flatMap { $0.1.isEmpty ? nil : $0.1 }
                    if let w = written {
                        add(w.bar, w.barNumber, w.onset, w.beat, w.pickup,
                            MarkedNote(kind: .noPlace, note: i, step: w.step, alter: w.alter, name: name, why: why))
                    } else if let b = words?.0 {
                        add(b.bar, b.barNumber, b.onset, b.beat, b.pickup, MarkedNote(kind: .noPlace, note: i, name: name, why: why))
                    } else {
                        unplaced += 1
                    }
                } else if note.confidence < threshold {
                    if let p = start(i) { doubt(p) } else { unplaced += 1 }
                }
            }
            unplaced += boxed.count
        } else {
            // On a notation staff a note without a place is written, and may be in doubt as well: it is under the "!" its
            // boxed words give it, not also under a "?".
            func underABox(_ p: TabPiece) -> Bool {
                p.string == nil && boxedWords.contains { b in b.bar == p.bar && b.onset == p.onset && b.names.contains { $0.hasPrefix(p.step) } }
            }
            for p in index.pieces where p.staff == staff && (p.confidence ?? .greatestFiniteMagnitude) < threshold && !underABox(p) { doubt(p) }
            for b in boxedWords {
                for name in b.names.isEmpty ? [""] : b.names {
                    add(b.bar, b.barNumber, b.onset, b.beat, b.pickup, MarkedNote(kind: .noPlace, note: nil, name: name.isEmpty ? nil : name))
                }
            }
        }
        let columns = order.map { at in
            let (number, beat, pickup) = places[at]!
            return TabColumn(staff: staff, bar: at.bar, barNumber: number, onset: at.onset, beat: beat, notes: found[at]!, pickup: pickup)
        }.sorted { ($0.bar, $0.onset) < ($1.bar, $1.onset) }
        // The header counts what is drawn: a note under a "!" is not also a "?", and a note the page folded into another is neither.
        return TabMarks(columns: columns,
                        doubtful: columns.reduce(0) { $0 + $1.notes.count { $0.kind == .doubt } },
                        noPlace: columns.reduce(0) { $0 + $1.notes.count { $0.kind == .noPlace } },
                        unplaced: unplaced)
    }

    private struct Key: Hashable { var bar: Int; var onset: Int }
}

extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

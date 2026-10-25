import Foundation

/// The tab as text, bar by bar: what VoiceOver reads in the place of the page, which it cannot reach. Each bar says
/// its number and, beat by beat, the notes that start there, with their string and fret (or their pitch, on a staff of
/// notation alone). A note tied over from before is not said again.
public struct TabBarReading: Identifiable, Equatable, Sendable {
    /// A beat with notes that start on it.
    public struct Beat: Equatable, Sendable {
        /// 1 the first of its bar; in a pickup, the beat of the full bar it leads into.
        public var beat: Int
        /// Lowest string first.
        public var notes: [TabPiece]
    }

    /// Counted from 0, as written.
    public var bar: Int
    /// The printed number: 0 for a pickup.
    public var number: String
    public var pickup: Bool
    public var beats: [Beat]
    public var id: Int { bar }

    /// Every bar of [index], on the staff its marks stand on; a bar without notes is there with no beats (a rest).
    public static func bars(_ index: TabIndex) -> [TabBarReading] {
        let staff = index.markStaff
        var byBar: [Int: [TabPiece]] = [:]
        for p in index.pieces where p.staff == staff && p.first { byBar[p.bar, default: []].append(p) }
        return (0..<index.bars).map { bar in
            let measure = bar < index.measures.count ? index.measures[bar] : nil
            let pieces = (byBar[bar] ?? []).sorted { ($0.onset, -($0.string ?? 0), $0.pitch) < ($1.onset, -($1.string ?? 0), $1.pitch) }
            var beats: [Beat] = []
            for (onset, notes) in Dictionary(grouping: pieces, by: \.onset).sorted(by: { $0.key < $1.key }) {
                _ = onset
                beats.append(Beat(beat: notes[0].beat, notes: notes))
            }
            return TabBarReading(bar: bar, number: measure?.number ?? String(bar + 1), pickup: measure?.pickup ?? false, beats: beats)
        }
    }

    /// The bar in words, with the product's [words].
    public func text(_ words: Words = .english) -> String {
        let head = pickup ? words.pickup : words.bar(number)
        guard !beats.isEmpty else { return "\(head). \(words.rest)." }
        let said = beats.map { b in "\(words.beat(b.beat)): " + b.notes.map(words.note).joined(separator: ", ") }
        return "\(head). " + said.joined(separator: "; ") + "."
    }

    /// How a product says a bar: in its own words, in its own language.
    public struct Words: Sendable {
        public var bar: @Sendable (String) -> String
        public var pickup: String
        public var rest: String
        public var beat: @Sendable (Int) -> String
        public var note: @Sendable (TabPiece) -> String

        public init(bar: @escaping @Sendable (String) -> String, pickup: String, rest: String, beat: @escaping @Sendable (Int) -> String,
                    note: @escaping @Sendable (TabPiece) -> String) {
            self.bar = bar; self.pickup = pickup; self.rest = rest; self.beat = beat; self.note = note
        }

        /// "Bar 3. Beat 1: 4th string open; beat 2: 3rd string fret 2."
        public static let english = Words(
            bar: { "Bar \($0)" }, pickup: "Pickup bar", rest: "Rest", beat: { "beat \($0)" },
            note: { p in
                guard let s = p.string, let f = p.fret else { return p.step + (p.alter > 0 ? " sharp" : p.alter < 0 ? " flat" : "") }
                return f == 0 ? "\(ordinal(s)) string open" : "\(ordinal(s)) string fret \(f)"
            })

        static func ordinal(_ n: Int) -> String {
            switch n % 100 {
            case 11, 12, 13: "\(n)th"
            default: switch n % 10 { case 1: "\(n)st"; case 2: "\(n)nd"; case 3: "\(n)rd"; default: "\(n)th" }
            }
        }
    }
}

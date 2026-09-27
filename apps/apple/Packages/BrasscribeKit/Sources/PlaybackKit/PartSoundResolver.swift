import Foundation

/// Score part → band SoundFont preset, following `sounds/mapping.json` `resolve` exactly as the
/// reference `sounds/partsound.py` does (and as Android, Windows and Studio do):
///   1. exact: the normalized name equals a normalized key of `parts`
///   2. alias: the normalized name is a key of `aliases`
///   3. keyword: the first `keywords` entry that is a substring of the normalized name
///   4. instrument: the MusicXML `<instrument-sound>` (or instrument id) in `instruments`
///   5. program: the 0-based General MIDI program in `programs`
/// A brass part therefore never falls back to General MIDI; only a non-brass program stays
/// unresolved. `sounds/partsound-vectors.json` holds the shared test vectors.
public struct PartSoundResolver: Sendable {
    public struct Preset: Sendable, Equatable {
        /// The mapping.json part whose preset plays.
        public var part: String
        /// exact | alias | keyword | instrument | program
        public var step: String
        public var program: Int
        public var bank: Int
        public var channelGainDB: Double
        public var percussion: Bool
        /// The part's seat in seating.json.
        public var seat: String?
    }

    struct Entry: Sendable { var program: Int; var bank: Int; var gain: Double; var seat: String? }

    let parts: [String: Entry]
    let normalizedParts: [String: String]
    let aliases: [String: String]
    let keywords: [(String, String)]
    let instruments: [String: String]
    let programs: [Int: String]

    public init(mapping url: URL) throws {
        try self.init(data: Data(contentsOf: url))
    }

    public init(data: Data) throws {
        guard let m = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ps = m["parts"] as? [String: [String: Any]] else { throw CocoaError(.fileReadCorruptFile) }
        var parts: [String: Entry] = [:]
        for (name, p) in ps {
            guard let b = p["band_soundfont"] as? [String: Any], let prog = (b["program"] as? NSNumber)?.intValue,
                  let bank = (b["bank"] as? NSNumber)?.intValue else { continue }
            parts[name] = Entry(program: prog, bank: bank, gain: (b["channel_gain_db"] as? NSNumber)?.doubleValue ?? 0,
                                seat: p["seat"] as? String)
        }
        self.parts = parts
        var norm: [String: String] = [:]
        for k in parts.keys { norm[Self.normalize(k)] = k }
        normalizedParts = norm
        let r = m["resolve"] as? [String: Any] ?? [:]
        aliases = r["aliases"] as? [String: String] ?? [:]
        keywords = (r["keywords"] as? [[String]] ?? []).compactMap { $0.count == 2 ? ($0[0], $0[1]) : nil }
        instruments = r["instruments"] as? [String: String] ?? [:]
        var programs: [Int: String] = [:]
        for (k, v) in r["programs"] as? [String: String] ?? [:] { if let i = Int(k) { programs[i] = v } }
        self.programs = programs
    }

    /// lowercase; ♭ → b, ♯ → #; every run of whitespace (including U+00A0) → one space; trim.
    public static func normalize(_ name: String) -> String {
        let s = name.lowercased().replacingOccurrences(of: "♭", with: "b").replacingOccurrences(of: "♯", with: "#")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        return s.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    /// - Parameters:
    ///   - instrument: MusicXML `<instrument-sound>` id (e.g. `brass.alto-horn`) or instruments.py id.
    ///   - program: 0-based General MIDI program.
    public func resolve(name: String, instrument: String? = nil, program: Int? = nil) -> Preset? {
        let n = Self.normalize(name)
        var hit: String?, step = ""
        if let p = normalizedParts[n] {
            hit = p; step = "exact"
        } else if let p = aliases[n] {
            hit = p; step = "alias"
        } else if let (_, p) = keywords.first(where: { n.contains($0.0) }) {
            hit = p; step = "keyword"
        }
        if hit == nil, let instrument, !instrument.isEmpty, let p = instruments[instrument] { hit = p; step = "instrument" }
        if hit == nil, let program, let p = programs[program] { hit = p; step = "program" }
        guard let hit, let e = parts[hit] else { return nil }
        return Preset(part: hit, step: step, program: e.program, bank: e.bank, channelGainDB: e.gain,
                      percussion: e.bank == 128, seat: e.seat)
    }
}

import Foundation

/// The realistic tier from `sounds/`: one SF2 per brass-band instrument target
/// (`data/sounds/built/<target>/<target>.sf2`, program 0 = sustain), the part → target
/// mapping with mix gain (`sounds/mapping.json`) and contest seating (`sounds/seating.json`,
/// polar positions for the audience listener).
public struct PartSound: Sendable, Equatable {
    public var soundFont: URL
    public var target: String
    public var gainDB: Double
    public var azimuth: Double?
    public var distance: Double?
}

public enum BandSounds {
    /// Reads the mapping and seating and keeps parts whose SF2 exists. Parts are keyed by
    /// score part name, as in the MusicXML.
    public static func load(mapping: URL, seating: URL?, built: URL, listener: String = "audience") throws -> [String: PartSound] {
        guard let m = try JSONSerialization.jsonObject(with: Data(contentsOf: mapping)) as? [String: Any],
              let parts = m["parts"] as? [String: [String: Any]] else { return [:] }
        var seats: [String: [String: Any]] = [:]
        if let seating, let s = try? JSONSerialization.jsonObject(with: Data(contentsOf: seating)) as? [String: Any] {
            seats = s["seats"] as? [String: [String: Any]] ?? [:]
        }
        var out: [String: PartSound] = [:]
        for (name, p) in parts {
            guard let players = p["players"] as? [[String: Any]], let target = players.first?["target"] as? String else { continue }
            let sf2 = built.appending(path: "\(target)/\(target).sf2")
            guard FileManager.default.fileExists(atPath: sf2.path) else { continue }
            var az: Double?, dist: Double?
            if let seat = p["seat"] as? String, let polar = (seats[seat]?["polar"] as? [String: Any])?[listener] as? [String: Any] {
                az = (polar["azimuth_deg"] as? NSNumber)?.doubleValue
                dist = (polar["distance_m"] as? NSNumber)?.doubleValue
            }
            out[name] = PartSound(soundFont: sf2, target: target, gainDB: (p["gain_db"] as? NSNumber)?.doubleValue ?? 0,
                                  azimuth: az, distance: dist)
        }
        return out
    }

    /// `BRASSCRIBE_SOUNDS` = repository root (with `sounds/*.json` and `data/sounds/built`).
    public static func locate() -> [String: PartSound] {
        guard let root = ProcessInfo.processInfo.environment["BRASSCRIBE_SOUNDS"] else { return [:] }
        let r = URL(fileURLWithPath: root)
        return (try? load(mapping: r.appending(path: "sounds/mapping.json"), seating: r.appending(path: "sounds/seating.json"),
                          built: r.appending(path: "data/sounds/built"))) ?? [:]
    }
}

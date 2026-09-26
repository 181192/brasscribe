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
    /// Preset in the SoundFont: program 0 / melodic bank 0 for the per-instrument files;
    /// the band SoundFont's (bank, GM program) per part, drums on the percussion bank.
    public var program: Int = 0
    public var bankMSB: Int = 0x79
    public var bankLSB: Int = 0
}

public enum BandSounds {
    /// The band SoundFont (`data/sounds/band/brasscribe-band*.sf2`): every part has its own
    /// preset at (bank, program) with layered desks and a staccato bank; drums are bank 128.
    /// Gain is `band_soundfont.channel_gain_db`. Seats come from seating.json as above.
    public static func loadBand(mapping: URL, seating: URL?, soundFont: URL, listener: String = "audience") throws -> [String: PartSound] {
        guard FileManager.default.fileExists(atPath: soundFont.path),
              let m = try JSONSerialization.jsonObject(with: Data(contentsOf: mapping)) as? [String: Any],
              let parts = m["parts"] as? [String: [String: Any]] else { return [:] }
        let seats = seatTable(seating)
        var out: [String: PartSound] = [:]
        for (name, p) in parts {
            guard let b = p["band_soundfont"] as? [String: Any], let prog = (b["program"] as? NSNumber)?.intValue,
                  let bank = (b["bank"] as? NSNumber)?.intValue else { continue }
            let (az, dist) = polar(p["seat"] as? String, seats, listener)
            let drums = bank == 128
            out[name] = PartSound(soundFont: soundFont, target: drums ? "band-kit" : "band-\(prog)-\(bank)",
                                  gainDB: (b["channel_gain_db"] as? NSNumber)?.doubleValue ?? 0, azimuth: az, distance: dist,
                                  program: prog, bankMSB: drums ? 0x78 : 0x79, bankLSB: drums ? 0 : bank)
        }
        return out
    }

    static func seatTable(_ seating: URL?) -> [String: [String: Any]] {
        guard let seating, let s = try? JSONSerialization.jsonObject(with: Data(contentsOf: seating)) as? [String: Any] else { return [:] }
        return s["seats"] as? [String: [String: Any]] ?? [:]
    }

    static func polar(_ seat: String?, _ seats: [String: [String: Any]], _ listener: String) -> (Double?, Double?) {
        guard let seat, let p = (seats[seat]?["polar"] as? [String: Any])?[listener] as? [String: Any] else { return (nil, nil) }
        return ((p["azimuth_deg"] as? NSNumber)?.doubleValue, (p["distance_m"] as? NSNumber)?.doubleValue)
    }

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
        // Prefer the band SoundFont (16-bit build: 148 MB); fall back to per-instrument files.
        for name in ["brasscribe-band-16bit.sf2", "brasscribe-band.sf2"] {
            let sf = r.appending(path: "data/sounds/band/\(name)")
            if let parts = try? loadBand(mapping: r.appending(path: "sounds/mapping.json"), seating: r.appending(path: "sounds/seating.json"),
                                         soundFont: sf), !parts.isEmpty { return parts }
        }
        return (try? load(mapping: r.appending(path: "sounds/mapping.json"), seating: r.appending(path: "sounds/seating.json"),
                          built: r.appending(path: "data/sounds/built"))) ?? [:]
    }
}

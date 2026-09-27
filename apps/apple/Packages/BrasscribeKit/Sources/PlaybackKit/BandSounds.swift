import Foundation
import os

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

/// The band SoundFont with its mapping (resolver) and seating: what every score part plays.
public struct BandSoundFont: Sendable {
    public var soundFont: URL
    public var mapping: URL
    public var resolver: PartSoundResolver
    var seats: [String: [String: Double]]  // seat -> azimuth_deg / distance_m for the listener

    public init(soundFont: URL, mapping: URL, seating: URL?, listener: String = "audience") throws {
        self.soundFont = soundFont
        self.mapping = mapping
        resolver = try PartSoundResolver(mapping: mapping)
        var seats: [String: [String: Double]] = [:]
        let table = BandSounds.seatTable(seating)
        for name in table.keys {
            let (az, d) = BandSounds.polar(name, table, listener)
            if let az, let d { seats[name] = ["azimuth": az, "distance": d] }
        }
        self.seats = seats
    }

    /// The preset for a score part, or nil for a non-brass part (then the general bank plays it).
    public func sound(for name: String, instrumentSound: String?, midiProgram: Int?) -> PartSound? {
        guard let p = resolver.resolve(name: name, instrument: instrumentSound, program: midiProgram.map { $0 - 1 }) else { return nil }
        let seat = p.seat.flatMap { seats[$0] }
        return PartSound(soundFont: soundFont, target: p.percussion ? "band-kit" : "band-\(p.program)-\(p.bank)",
                         gainDB: p.channelGainDB, azimuth: seat?["azimuth"], distance: seat?["distance"],
                         program: p.program, bankMSB: p.percussion ? 0x78 : 0x79, bankLSB: p.percussion ? 0 : p.bank)
    }
}

/// Whether the band sounds were found. When they are missing the app plays the basic tier and
/// shows one line saying so (its string catalog: "The band sounds are missing. …"), with
/// `details` (where it looked) for the band's tech person.
public enum BandSoundStatus: Sendable, Equatable {
    case ready(URL)
    case missing(searched: [URL])

    public var isMissing: Bool { if case .missing = self { return true } else { return false } }

    /// Where the app looked, for a details view.
    public var details: String {
        switch self {
        case .ready(let url): return url.path
        case .missing(let searched): return searched.map(\.path).joined(separator: "\n")
        }
    }
}

public enum BandSounds {
    static let log = Logger(subsystem: "no.brasscribe.play", category: "sound")
    static let bandFiles = ["brasscribe-band-16bit.sf2", "brasscribe-band.sf2"]

    /// The band SoundFont (`data/sounds/band/brasscribe-band*.sf2`): every part has its own
    /// preset at (bank, program) with layered desks and a staccato bank; drums are bank 128.
    /// Gain is `band_soundfont.channel_gain_db`. Seats come from seating.json as above.
    /// Keyed by the mapping's part names; use `BandSoundFont` to resolve any score part name.
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
        let seats = seatTable(seating)
        var out: [String: PartSound] = [:]
        for (name, p) in parts {
            guard let players = p["players"] as? [[String: Any]], let target = players.first?["target"] as? String else { continue }
            let sf2 = built.appending(path: "\(target)/\(target).sf2")
            guard FileManager.default.fileExists(atPath: sf2.path) else { continue }
            let (az, dist) = polar(p["seat"] as? String, seats, listener)
            // one target per part (no layered desk): the single-voice balance gain when the mapping has it
            let single = ((p["band_soundfont"] as? [String: Any])?["single_voice_gain_db"] as? NSNumber)?.doubleValue
            out[name] = PartSound(soundFont: sf2, target: target, gainDB: single ?? (p["gain_db"] as? NSNumber)?.doubleValue ?? 0,
                                  azimuth: az, distance: dist)
        }
        return out
    }

    /// A place that may hold the band SoundFont, with its mapping and seating.
    struct Candidate { var dir: URL; var mapping: URL; var seating: URL }

    /// Where the band sounds are looked for, in order:
    ///   1. `BRASSCRIBE_SOUNDS` = a repository root (development): data/sounds/band + sounds/*.json
    ///   2. the app bundle: `Sounds/` (copied in by `make bandsound`) with mapping.json and seating.json
    ///   3. ~/Library/Application Support/Brasscribe/SoundFonts (mapping from there, else from the bundle)
    ///   4. the repository this package is built from (tests and `swift run` in a checkout)
    static func candidates(bundle: Bundle) -> [Candidate] {
        var out: [Candidate] = []
        func repo(_ r: URL) -> Candidate {
            Candidate(dir: r.appending(path: "data/sounds/band"), mapping: r.appending(path: "sounds/mapping.json"),
                      seating: r.appending(path: "sounds/seating.json"))
        }
        if let root = ProcessInfo.processInfo.environment["BRASSCRIBE_SOUNDS"] { out.append(repo(URL(fileURLWithPath: root))) }
        var bundled: Candidate?
        if let res = bundle.resourceURL?.appending(path: "Sounds") {
            bundled = Candidate(dir: res, mapping: res.appending(path: "mapping.json"), seating: res.appending(path: "seating.json"))
            out.append(bundled!)
        }
        if let support = try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
            .appending(path: "Brasscribe/SoundFonts") {
            let own = support.appending(path: "mapping.json")
            let mapping = FileManager.default.fileExists(atPath: own.path) ? own : (bundled?.mapping ?? own)
            out.append(Candidate(dir: support, mapping: mapping, seating: bundled?.seating ?? support.appending(path: "seating.json")))
        }
        var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<8 {
            // sounds/band.py, not only mapping.json: on a case-insensitive volume apps/apple/Sounds/
            // (the staged bundle copy) would otherwise pass for the repository's sounds/ folder
            if FileManager.default.fileExists(atPath: dir.appending(path: "sounds/band.py").path) { out.append(repo(dir)); break }
            dir = dir.deletingLastPathComponent()
        }
        return out
    }

    /// The band SoundFont from the first place that has both the file and its mapping.
    public static func locateBand(bundle: Bundle = .main) -> (BandSoundFont?, BandSoundStatus) {
        var searched: [URL] = []
        for c in candidates(bundle: bundle) {
            for name in bandFiles {
                let sf = c.dir.appending(path: name)
                searched.append(sf)
                guard FileManager.default.fileExists(atPath: sf.path), FileManager.default.fileExists(atPath: c.mapping.path),
                      let band = try? BandSoundFont(soundFont: sf, mapping: c.mapping, seating: c.seating) else { continue }
                log.info("band sounds: \(sf.path, privacy: .public)")
                return (band, .ready(sf))
            }
        }
        log.error("band sounds missing; basic tier. Looked in: \(searched.map(\.path).joined(separator: ", "), privacy: .public)")
        return (nil, .missing(searched: searched))
    }

    /// Per-instrument files from `BRASSCRIBE_SOUNDS` = repository root (`data/sounds/built`),
    /// for comparing against the band SoundFont in development.
    public static func locate() -> [String: PartSound] {
        guard let root = ProcessInfo.processInfo.environment["BRASSCRIBE_BUILT_SOUNDS"] else { return [:] }
        let r = URL(fileURLWithPath: root)
        return (try? load(mapping: r.appending(path: "sounds/mapping.json"), seating: r.appending(path: "sounds/seating.json"),
                          built: r.appending(path: "data/sounds/built"))) ?? [:]
    }
}

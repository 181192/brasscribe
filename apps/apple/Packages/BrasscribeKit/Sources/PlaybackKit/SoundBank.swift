import AVFoundation
import AudioToolbox
import Foundation
import ScoreKit

/// Where instrument sounds come from.
///
/// Band tier (the default): the band SoundFont (`brasscribe-band*.sf2`, bundled into the app by
/// `make bandsound`), every score part resolved to its own real-sample preset with
/// `PartSoundResolver` (mapping.json `resolve`), at the part's `channel_gain_db`. A brass part never
/// plays General MIDI while the band SoundFont is there.
///
/// Basic tier: only when the band SoundFont is missing (`bandStatus` says so, with the places
/// looked in), or for a part that is not a brass-band instrument: one General MIDI SF2
/// (MuseScore_General.sf2, `apps/apple/scripts/fetch-soundfont.sh`), else the macOS system GS DLS,
/// else the sampler's built-in tone.
public struct SoundBank: Sendable {
    public var general: URL?
    public var perSection: [Section: URL]
    /// Explicit presets by exact score part name (tests, per-instrument development files).
    public var perPart: [String: PartSound]
    /// The band SoundFont every other part name is resolved against.
    public var band: BandSoundFont?
    public var bandStatus: BandSoundStatus

    public init(general: URL?, perSection: [Section: URL] = [:], perPart: [String: PartSound] = [:],
                band: BandSoundFont? = nil, bandStatus: BandSoundStatus? = nil) {
        self.general = general; self.perSection = perSection; self.perPart = perPart; self.band = band
        self.bandStatus = bandStatus ?? (band.map { .ready($0.soundFont) } ?? .missing(searched: []))
    }

    public static let none = SoundBank(general: nil)

    public enum Tier: String, Sendable { case band, basic }

    /// `.band` when brass parts play real brass-band samples; `.basic` otherwise.
    public var tier: Tier { band != nil || !perPart.isEmpty ? .band : .basic }

    public var description: String {
        if let band { return "brass-band samples: \(band.soundFont.lastPathComponent)" }
        if !perPart.isEmpty { return "brass-band samples: \(Set(perPart.values.map(\.target)).count) instruments" }
        if !perSection.isEmpty { return "sections: \(perSection.count) SF2" }
        return "basic tier: " + (general?.lastPathComponent ?? "built-in tone")
    }

    /// The band SoundFont (see `BandSounds.locateBand`), plus the General MIDI bank for
    /// non-brass parts: `BRASSCRIBE_SOUNDFONT`, then Application Support/Brasscribe/SoundFonts,
    /// then the app bundle, then the macOS system DLS.
    public static func locate(bundle: Bundle = .main) -> SoundBank {
        var bank = locateGeneral(bundle: bundle)
        let (band, status) = BandSounds.locateBand(bundle: bundle)
        bank.band = band
        bank.bandStatus = status
        bank.perPart = BandSounds.locate()
        return bank
    }

    static func locateGeneral(bundle: Bundle) -> SoundBank {
        let fm = FileManager.default
        if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_SOUNDFONT"], fm.fileExists(atPath: env) {
            return SoundBank(general: URL(fileURLWithPath: env))
        }
        if let support = try? fm.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
            .appending(path: "Brasscribe/SoundFonts"),
           let files = try? fm.contentsOfDirectory(at: support, includingPropertiesForKeys: nil),
           let sf = files.first(where: { ["sf2", "dls"].contains($0.pathExtension.lowercased())
               && !$0.lastPathComponent.hasPrefix("brasscribe-band") }) {
            return SoundBank(general: sf)
        }
        if let b = bundle.url(forResource: "MuseScore_General", withExtension: "sf2") { return SoundBank(general: b) }
        #if os(macOS)
        let dls = URL(fileURLWithPath: "/System/Library/Components/CoreAudio.component/Contents/Resources/gs_instruments.dls")
        if fm.fileExists(atPath: dls.path) { return SoundBank(general: dls) }
        #endif
        return .none
    }

    /// The band preset a score part plays: an explicit `perPart` entry, else the band resolver.
    public func partSound(for part: Part) -> PartSound? {
        if let ps = perPart[part.name] { return ps }
        return band?.sound(for: part.name, instrumentSound: part.instrumentSound, midiProgram: part.midiProgram)
    }

    /// AUSampler streams SoundFont samples from disk by default, preloading only their start.
    /// When a read is late the voice plays silence: measured as 20–110 dB dropouts inside held
    /// notes on a cold file cache. Load every sample into memory instead.
    static func loadIntoMemory(_ sampler: AVAudioUnitSampler) {
        var off: UInt32 = 0
        AudioUnitSetProperty(sampler.audioUnit, kMusicDeviceProperty_StreamFromDisk, kAudioUnitScope_Global, 0,
                             &off, UInt32(MemoryLayout<UInt32>.size))
    }

    /// Load the instrument for `part` into its sampler. Returns false when the sampler keeps its
    /// default tone.
    @discardableResult
    func load(into sampler: AVAudioUnitSampler, part: Part) -> Bool {
        if let ps = partSound(for: part) {
            Self.loadIntoMemory(sampler)
            do {
                try sampler.loadSoundBankInstrument(at: ps.soundFont, program: UInt8(ps.program),
                                                    bankMSB: UInt8(ps.bankMSB), bankLSB: UInt8(ps.bankLSB))
                sampler.overallGain = Float(ps.gainDB)
                return true
            } catch {
                BandSounds.log.error("could not load the band preset for \(part.name, privacy: .public): \(error.localizedDescription, privacy: .public)")
            }
        } else if band != nil && !part.isPercussion {
            BandSounds.log.info("\(part.name, privacy: .public) is not a brass-band part; it plays the basic tier")
        }
        return load(into: sampler, section: part.section, program: part.midiProgram)
    }

    @discardableResult
    func load(into sampler: AVAudioUnitSampler, section: Section, program: Int?) -> Bool {
        do {
            if let url = perSection[section] {
                try sampler.loadSoundBankInstrument(at: url, program: 0, bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB), bankLSB: 0)
                return true
            }
            guard let url = general else { return false }
            if section == .percussion {
                try sampler.loadSoundBankInstrument(at: url, program: 0, bankMSB: UInt8(kAUSampler_DefaultPercussionBankMSB), bankLSB: 0)
            } else {
                try sampler.loadSoundBankInstrument(at: url, program: UInt8(max(0, min(127, (program ?? 1) - 1))),
                                                    bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB), bankLSB: 0)
            }
            return true
        } catch {
            return false
        }
    }
}

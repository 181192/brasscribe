import AVFoundation
import Foundation
import ScoreKit

/// Where instrument sounds come from.
///
/// Baseline: one General MIDI SF2 (MuseScore_General.sf2, MIT, downloaded by
/// `apps/apple/scripts/fetch-soundfont.sh`). Optionally one SF2 per section (the realistic
/// tier; program 0 sustain). Without any file, macOS falls back to the system GS DLS and
/// iOS to the sampler's built-in sine tone, so playback always works.
public struct SoundBank: Sendable, Equatable {
    public var general: URL?
    public var perSection: [Section: URL]

    public init(general: URL?, perSection: [Section: URL] = [:]) {
        self.general = general; self.perSection = perSection
    }

    public static let none = SoundBank(general: nil)

    public var description: String {
        if !perSection.isEmpty { return "sections: \(perSection.count) SF2" }
        return general?.lastPathComponent ?? "built-in tone"
    }

    /// Finds a sound font: `BRASSCRIBE_SOUNDFONT`, then Application Support/Brasscribe/SoundFonts,
    /// then the app bundle, then the macOS system DLS.
    public static func locate(bundle: Bundle = .main) -> SoundBank {
        let fm = FileManager.default
        if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_SOUNDFONT"], fm.fileExists(atPath: env) {
            return SoundBank(general: URL(fileURLWithPath: env))
        }
        if let support = try? fm.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
            .appending(path: "Brasscribe/SoundFonts"),
           let files = try? fm.contentsOfDirectory(at: support, includingPropertiesForKeys: nil),
           let sf = files.first(where: { ["sf2", "dls"].contains($0.pathExtension.lowercased()) }) {
            return SoundBank(general: sf)
        }
        if let b = bundle.url(forResource: "MuseScore_General", withExtension: "sf2") { return SoundBank(general: b) }
        #if os(macOS)
        let dls = URL(fileURLWithPath: "/System/Library/Components/CoreAudio.component/Contents/Resources/gs_instruments.dls")
        if fm.fileExists(atPath: dls.path) { return SoundBank(general: dls) }
        #endif
        return .none
    }

    /// Load the instrument for `section` (GM `program`, 1-based) into a sampler.
    /// Returns false when the sampler keeps its default tone.
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

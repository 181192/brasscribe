import BrasscribeCore
import Foundation
import ScoreKit

/// Part names in the musician's language, from the core's one table (`part_name_nb`): «Solokornett»,
/// «Solo althorn», «2. kornett». The same names on every platform, in the score, the pickers, review
/// and files. The app keeps no table of its own.
enum PartNames {
    /// "Solo Horn" → «Solo althorn» in Norwegian; unchanged in English and for names the core doesn't know.
    static func display(_ name: String, language: ScoreLanguage = .current) -> String {
        language == .norwegian ? partNameNb(name: name) : name
    }

    /// The MusicXML with its part names in the musician's language, for engraving.
    static func localized(_ xml: String) -> String {
        guard ScoreLanguage.current == .norwegian else { return xml }
        var out = xml
        for tag in ["part-name", "part-abbreviation"] {
            let open = "<\(tag)>", close = "</\(tag)>"
            var names = Set<String>()
            var rest = out[...]
            while let a = rest.range(of: open), let b = rest.range(of: close, range: a.upperBound..<rest.endIndex) {
                names.insert(String(rest[a.upperBound..<b.lowerBound]))
                rest = rest[b.upperBound...]
            }
            for en in names {
                let nb = partNameNb(name: en)
                if nb != en { out = out.replacingOccurrences(of: open + en + close, with: open + nb + close) }
            }
        }
        return out
    }
}

extension Lineup {
    /// The lineup as the library and the score's options name it.
    var shortTitle: String {
        switch self {
        case .fullBand: return String(localized: "Full band")
        case .minimalBand: return String(localized: "Small band")
        case .quartet: return String(localized: "Quartet")
        }
    }
}

extension Part {
    /// The part's name as the musician says it.
    var displayName: String { PartNames.display(name) }
}

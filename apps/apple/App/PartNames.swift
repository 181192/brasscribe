import Foundation
import ScoreKit

/// Part names in the musician's language. Norwegian bands say "Solokornett", "Sopran",
/// "2. kornett"; one convention everywhere the part appears (score, pickers, review, files).
enum PartNames {
    static let norwegian: [String: String] = [
        "Soprano Cornet": "Sopran", "Solo Cornet": "Solokornett", "Repiano Cornet": "Repiano",
        "2nd Cornet": "2. kornett", "3rd Cornet": "3. kornett", "Flugelhorn": "Flygelhorn",
        "Solo Horn": "Solohorn", "1st Horn": "1. horn", "2nd Horn": "2. horn",
        "1st Baritone": "1. baryton", "2nd Baritone": "2. baryton",
        "1st Trombone": "1. trombone", "2nd Trombone": "2. trombone", "Bass Trombone": "Basstrombone",
        "Euphonium": "Eufonium", "E♭ Bass": "Ess-bass", "B♭ Bass": "B-bass", "Percussion": "Slagverk",
        "Solo": "Solo", "Piano": "Piano", "Drums": "Trommer", "Bass": "Bass", "Strings": "Strykere",
    ]

    static func display(_ name: String) -> String {
        guard ScoreLanguage.current == .norwegian else { return name }
        return norwegian[name] ?? name
    }

    /// The MusicXML with its part names in the musician's language, for engraving.
    static func localized(_ xml: String) -> String {
        guard ScoreLanguage.current == .norwegian else { return xml }
        var out = xml
        for (en, nb) in norwegian where en != nb {
            out = out.replacingOccurrences(of: "<part-name>\(en)</part-name>", with: "<part-name>\(nb)</part-name>")
            out = out.replacingOccurrences(of: "<part-abbreviation>\(en)</part-abbreviation>", with: "<part-abbreviation>\(nb)</part-abbreviation>")
        }
        return out
    }
}

extension Part {
    /// The part's name as the musician says it.
    var displayName: String { PartNames.display(name) }
}

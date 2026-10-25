import Foundation
import Testing

/// The screens every Play app shares (features/play) say their words through each product's catalog: every one has
/// Fretscribe's bokmål, and none of them, in Fretscribe's English or bokmål, names Brasscribe.
@Test func everySharedWordIsInFretscribesOwnWords() throws {
    let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let shared = here.appending(path: "../../../features/play").standardizedFileURL
    let catalog = here.appending(path: "../App/Localizable.xcstrings").standardizedFileURL
    let strings = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: catalog)) as? [String: Any])["strings"] as? [String: Any]
    let keys = try SharedWords.keys(in: shared)
    #expect(keys.count > 50, "found \(keys.count) words in \(shared.path)")
    for key in keys {
        let entry = (strings?[key] as? [String: Any])?["localizations"] as? [String: Any]
        let nb = ((entry?["nb"] as? [String: Any])?["stringUnit"] as? [String: Any])?["value"] as? String
        let en = ((entry?["en"] as? [String: Any])?["stringUnit"] as? [String: Any])?["value"] as? String ?? key
        #expect(nb != nil, "\(key)")
        #expect(!(nb ?? "").contains("Brasscribe") || (nb ?? "").contains("Brasscribe Bandroom"), "\(key): \(nb ?? "")")
        #expect(!en.contains("Brasscribe") || en.contains("Brasscribe Bandroom"), "\(key): \(en)")
    }
}

enum SharedWords {
    /// The literal words of the Swift files in [dir]: what `Text`, `Button`, `Label`, `String(localized:)` and the
    /// like are given. A word with an interpolation is left out (its type decides `%@` or `%lld` in the catalog).
    static func keys(in dir: URL) throws -> Set<String> {
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).filter { $0.pathExtension == "swift" }
        let call = try Regex(#"(?:Text|Button|Label|Toggle|Section|LabeledContent|TextField|SecureField|String\(localized:|LocalizedStringKey\(|navigationTitle\(Text)\(?\s*"((?:[^"\\\n]|\\.)*)""#)
        var out = Set<String>()
        for f in files {
            let source = try String(contentsOf: f, encoding: .utf8)
            for m in source.matches(of: call) {
                guard let raw = m.output[1].substring.map(String.init), !raw.isEmpty, raw.rangeOfCharacter(from: .letters) != nil else { continue }
                if raw.contains("\\(") { continue }
                out.insert(raw.replacingOccurrences(of: "\\\"", with: "\"").replacingOccurrences(of: "\\n", with: "\n"))
            }
        }
        return out
    }
}

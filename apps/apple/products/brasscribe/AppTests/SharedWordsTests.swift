import Foundation
import Testing

/// The screens every Play app shares (features/play) say their words through each product's catalog: their keys name
/// no product, and every one has this product's Norwegian. A key the catalog does not have would show in English.
@Test func everySharedWordIsInThisProductsCatalog() throws {
    let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let shared = here.appending(path: "../../../features/play").standardizedFileURL
    let catalog = here.appending(path: "../App/Localizable.xcstrings").standardizedFileURL
    let strings = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: catalog)) as? [String: Any])["strings"] as? [String: Any]
    let keys = try SharedWords.keys(in: shared)
    #expect(keys.count > 50, "found \(keys.count) words in \(shared.path)")
    for key in keys {
        let entry = (strings?[key] as? [String: Any])?["localizations"] as? [String: Any]
        #expect(entry?["nb"] != nil, "\(key)")
        #expect(!key.contains("Brasscribe") && !key.contains("Fretscribe"), "a shared word names a product: \(key)")
    }
}

enum SharedWords {
    /// The literal words of the Swift files in [dir]: what `Text`, `Button`, `Label`, `String(localized:)` and the
    /// like are given, with each `\(…)` as the catalog writes it.
    static func keys(in dir: URL) throws -> Set<String> {
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).filter { $0.pathExtension == "swift" }
        let call = try Regex(#"(?:Text|Button|Label|Toggle|Section|LabeledContent|TextField|SecureField|String\(localized:|LocalizedStringKey\(|navigationTitle\(Text)\(?\s*"((?:[^"\\\n]|\\.)*)""#)
        var out = Set<String>()
        for f in files {
            let source = try String(contentsOf: f, encoding: .utf8)
            for m in source.matches(of: call) {
                guard let raw = m.output[1].substring.map(String.init), !raw.isEmpty, raw.rangeOfCharacter(from: .letters) != nil else { continue }
                // an interpolation is one argument in the catalog; its type decides %@ or %lld, so those are not checked
                if raw.contains("\\(") { continue }
                out.insert(raw.replacingOccurrences(of: "\\\"", with: "\"").replacingOccurrences(of: "\\n", with: "\n"))
            }
        }
        return out
    }
}

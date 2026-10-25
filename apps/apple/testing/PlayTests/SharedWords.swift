import Foundation

// Test code every Play app's tests share (compiled into each product's unit-test target).

/// The words of the screens every Play app shares (features/play), as each product's catalog must have them.
enum SharedWords {
    /// One word of the shared screens: its text, with each interpolation as `\u{1}`.
    struct Word: Hashable {
        let text: String
        var interpolated: Bool { text.contains("\u{1}") }

        /// The catalog's key for it: the same text, an interpolation written as `%@`, `%lld` and the like.
        func key(in catalog: [String: Any]) -> String? {
            guard interpolated else { return catalog[text] != nil ? text : nil }
            let parts = text.split(separator: "\u{1}", omittingEmptySubsequences: false).map { NSRegularExpression.escapedPattern(for: String($0)) }
            let pattern = "^" + parts.joined(separator: "%(?:\\d+\\$)?(?:@|lld|ld|d|lf|f|llu|lu|u)") + "$"
            guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
            return catalog.keys.first { re.firstMatch(in: $0, range: NSRange($0.startIndex..., in: $0)) != nil }
        }
    }

    /// The literal words of the Swift files in [dir]: what `Text`, `Button`, `Label`, `String(localized:)` and the
    /// like are given.
    static func words(in dir: URL) throws -> Set<Word> {
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).filter { $0.pathExtension == "swift" }
        let call = try NSRegularExpression(pattern: #"(?:Text|Button|Label|Toggle|Section|LabeledContent|TextField|SecureField|String\(localized:|LocalizedStringKey\(|navigationTitle\(Text)\(?\s*""#)
        var out = Set<Word>()
        for f in files {
            let source = try String(contentsOf: f, encoding: .utf8)
            let chars = Array(source.utf16)
            for m in call.matches(in: source, range: NSRange(source.startIndex..., in: source)) {
                // the literal up to its closing quote; a quote inside an interpolation (`\(a.joined(separator: " "))`) is not it
                var i = m.range.location + m.range.length, depth = 0, text: [UInt16] = []
                let quote = UInt16(UInt8(ascii: "\"")), slash = UInt16(UInt8(ascii: "\\")), open = UInt16(UInt8(ascii: "(")),
                    close = UInt16(UInt8(ascii: ")")), newline = UInt16(UInt8(ascii: "\n"))
                var ended = false
                while i < chars.count {
                    let c = chars[i]
                    if c == newline { break }
                    if depth == 0 && c == quote { ended = true; break }
                    if depth == 0 && c == slash && i + 1 < chars.count && chars[i + 1] != open {
                        text.append(c); text.append(chars[i + 1]); i += 2; continue
                    }
                    if c == open && depth > 0 || (c == open && i > 0 && chars[i - 1] == slash) { depth += 1 }
                    else if c == close && depth > 0 { depth -= 1 }
                    text.append(c); i += 1
                }
                let literal = String(decoding: text, as: UTF16.self)
                guard ended, !literal.isEmpty, literal.rangeOfCharacter(from: .letters) != nil else { continue }
                let raw = withoutInterpolations(literal)
                out.insert(Word(text: raw.replacingOccurrences(of: "\\\"", with: "\"").replacingOccurrences(of: "\\n", with: "\n")))
            }
        }
        return out
    }

    /// [text] with each `\(…)` as `\u{1}`, its parentheses balanced.
    static func withoutInterpolations(_ text: String) -> String {
        var out = "", chars = Array(text), i = 0
        while i < chars.count {
            if chars[i] == "\\", i + 1 < chars.count, chars[i + 1] == "(" {
                var depth = 0, j = i + 1
                while j < chars.count {
                    if chars[j] == "(" { depth += 1 } else if chars[j] == ")" { depth -= 1; if depth == 0 { break } }
                    j += 1
                }
                out.append("\u{1}")
                i = j + 1
            } else {
                out.append(chars[i]); i += 1
            }
        }
        return out
    }

    /// What is wrong with the shared words in the product's [catalog]: a word it has no entry or no bokmål for, a key
    /// that names a product, or an English or bokmål value that names one of [notOurs].
    static func problems(shared: URL, catalog: URL, notOurs: [String]) throws -> [String] {
        let json = try JSONSerialization.jsonObject(with: Data(contentsOf: catalog)) as? [String: Any]
        let strings = json?["strings"] as? [String: Any] ?? [:]
        var problems: [String] = []
        let words = try Self.words(in: shared)
        if words.count < 50 { problems.append("only \(words.count) words found in \(shared.path)") }
        if !words.contains(where: \.interpolated) { problems.append("no word with an interpolation found") }
        for w in words {
            for product in ["Brasscribe", "Fretscribe"] where w.text.contains(product) { problems.append("a shared key names \(product): \(w.text)") }
            guard let key = w.key(in: strings) else { problems.append("not in the catalog: \(w.text)"); continue }
            let loc = (strings[key] as? [String: Any])?["localizations"] as? [String: Any]
            func value(_ lang: String) -> String? { ((loc?[lang] as? [String: Any])?["stringUnit"] as? [String: Any])?["value"] as? String }
            guard let nb = value("nb") else { problems.append("no bokmål: \(key)"); continue }
            let en = value("en") ?? key
            for word in notOurs where en.contains(word) || nb.contains(word) { problems.append("names \(word): \(key) → \(en) / \(nb)") }
        }
        return problems
    }
}

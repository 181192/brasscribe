import Foundation

/// Text-level edits on MusicXML that keep the rest of the document byte-for-byte, so the
/// renderer sees exactly what the engine wrote. Works without XMLDocument (unavailable on iOS).
public enum MusicXMLFilter {
    /// Keep only the given parts (by `id`), removing their `<score-part>` and `<part>` blocks.
    public static func keepingParts(_ ids: Set<String>, in xml: String) -> String {
        var s = xml
        for (open, close) in [("<score-part ", "</score-part>"), ("<part ", "</part>")] {
            var out = ""
            out.reserveCapacity(s.utf8.count)
            var rest = s[...]
            while let r = rest.range(of: open) {
                out += rest[..<r.lowerBound]
                guard let end = rest.range(of: close, range: r.upperBound..<rest.endIndex) else {
                    out += rest[r.lowerBound...]; rest = rest[rest.endIndex...]; break
                }
                let block = rest[r.lowerBound..<end.upperBound]
                if let id = attribute("id", in: block), ids.contains(id) { out += block }
                rest = rest[end.upperBound...]
            }
            out += rest
            s = out
        }
        return s
    }

    static func attribute(_ name: String, in block: Substring) -> String? {
        guard let tagEnd = block.firstIndex(of: ">") else { return nil }
        let tag = block[..<tagEnd]
        for q in ["\"", "'"] {
            if let r = tag.range(of: " \(name)=\(q)"), let e = tag[r.upperBound...].firstIndex(of: Character(q)) {
                return String(tag[r.upperBound..<e])
            }
        }
        return nil
    }
}

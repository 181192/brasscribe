import Foundation

/// Small, targeted edits to a MusicXML string. Text-based, so it runs on iOS too
/// (Foundation's XMLDocument is macOS-only); everything outside the edit is kept byte for byte.
public enum MusicXMLNoteEditor {
    public enum EditError: Error {
        case partNotFound
        case noteNotFound
        case noteIsNotPitched
    }

    public static func replacingTitle(in xml: String, with title: String) throws -> String {
        let t = escaped(title)
        if let open = xml.range(of: "<work-title>"), let close = xml.range(of: "</work-title>", range: open.upperBound..<xml.endIndex) {
            return xml.replacingCharacters(in: open.upperBound..<close.lowerBound, with: t)
        }
        if let work = xml.range(of: "<work>") {
            return xml.replacingCharacters(in: work, with: "<work><work-title>\(t)</work-title>")
        }
        guard let root = xml.range(of: "<score-partwise"), let end = xml.range(of: ">", range: root.upperBound..<xml.endIndex) else {
            throw EditError.partNotFound
        }
        var out = xml
        out.insert(contentsOf: "<work><work-title>\(t)</work-title></work>", at: end.upperBound)
        return out
    }

    /// Replaces one parsed note's written pitch, using the parser's per-part note ordering
    /// (grace and cue notes are not counted).
    public static func replacingPitch(in xml: String, partID: String, noteIndex: Int, with pitch: SpelledPitch) throws -> String {
        guard let partStart = partRange(xml, id: partID) else { throw EditError.partNotFound }
        var cursor = partStart.lowerBound
        var current = 0
        while let open = nextNote(in: xml, from: cursor, before: partStart.upperBound) {
            guard let close = xml.range(of: "</note>", range: open.upperBound..<partStart.upperBound) else { break }
            let body = xml[open.lowerBound..<close.upperBound]
            cursor = close.upperBound
            if body.contains("<grace") || body.contains("<cue") { continue }
            guard current == noteIndex else { current += 1; continue }
            guard let p0 = xml.range(of: "<pitch>", range: open.lowerBound..<close.lowerBound),
                  let p1 = xml.range(of: "</pitch>", range: p0.upperBound..<close.lowerBound) else {
                throw EditError.noteIsNotPitched
            }
            var inner = "<step>\(pitch.step)</step>"
            if pitch.alter != 0 { inner += "<alter>\(pitch.alter)</alter>" }
            inner += "<octave>\(pitch.octave)</octave>"
            return xml.replacingCharacters(in: p0.upperBound..<p1.lowerBound, with: inner)
        }
        throw EditError.noteNotFound
    }

    private static func partRange(_ xml: String, id: String) -> Range<String.Index>? {
        var from = xml.startIndex
        while let r = xml.range(of: "<part ", range: from..<xml.endIndex) {
            guard let gt = xml.range(of: ">", range: r.upperBound..<xml.endIndex) else { return nil }
            let head = xml[r.upperBound..<gt.lowerBound]
            if head.contains("id=\"\(id)\"") || head.contains("id='\(id)'") {
                let end = xml.range(of: "</part>", range: gt.upperBound..<xml.endIndex)?.upperBound ?? xml.endIndex
                return gt.upperBound..<end
            }
            from = gt.upperBound
        }
        return nil
    }

    /// The next `<note>` or `<note …>` opening tag (not `<notehead>`, `<notations>`).
    private static func nextNote(in xml: String, from: String.Index, before end: String.Index) -> Range<String.Index>? {
        var i = from
        while let r = xml.range(of: "<note", range: i..<end) {
            let next = r.upperBound < end ? xml[r.upperBound] : " "
            if next == ">" || next == " " || next == "\n" || next == "\t" { return r }
            i = r.upperBound
        }
        return nil
    }

    private static func escaped(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
    }
}

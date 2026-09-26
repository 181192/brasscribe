import Foundation

public enum MusicXMLNoteEditor {
    public enum EditError: Error {
        case partNotFound
        case noteNotFound
        case noteIsNotPitched
    }

    public static func replacingTitle(in xml: String, with title: String) throws -> String {
        let document = try XMLDocument(xmlString: xml, options: [.nodePreserveAll])
        guard let root = document.rootElement() else { throw EditError.partNotFound }
        let work = root.elements(forName: "work").first ?? {
            let element = XMLElement(name: "work")
            root.insertChild(element, at: 0)
            return element
        }()
        let workTitle = work.elements(forName: "work-title").first ?? {
            let element = XMLElement(name: "work-title")
            work.addChild(element)
            return element
        }()
        workTitle.stringValue = title
        return document.xmlString(options: [])
    }

    /// Replaces one parsed note's written pitch, using the parser's per-part note ordering.
    public static func replacingPitch(in xml: String, partID: String, noteIndex: Int, with pitch: SpelledPitch) throws -> String {
        let document = try XMLDocument(xmlString: xml, options: [.nodePreserveAll])
        guard let root = document.rootElement() else { throw EditError.partNotFound }
        let parts = root.elements(forName: "part")
        guard let part = parts.first(where: { $0.attribute(forName: "id")?.stringValue == partID }) else {
            throw EditError.partNotFound
        }

        var current = 0
        for measure in part.elements(forName: "measure") {
            for note in measure.elements(forName: "note") {
                let children = note.children?.compactMap { $0 as? XMLElement } ?? []
                guard !children.contains(where: { ["grace", "cue"].contains($0.name ?? "") }) else { continue }
                guard current == noteIndex else { current += 1; continue }
                guard let pitchElement = children.first(where: { $0.name == "pitch" }) else {
                    throw EditError.noteIsNotPitched
                }
                pitchElement.children?.forEach { $0.detach() }
                pitchElement.addChild(XMLElement(name: "step", stringValue: pitch.step))
                if pitch.alter != 0 {
                    pitchElement.addChild(XMLElement(name: "alter", stringValue: String(pitch.alter)))
                }
                pitchElement.addChild(XMLElement(name: "octave", stringValue: String(pitch.octave)))
                return document.xmlString(options: [])
            }
        }
        throw EditError.noteNotFound
    }
}
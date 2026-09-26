import Foundation

public enum MusicXMLNoteEditor {
    public enum EditError: Error {
        case partNotFound
        case noteNotFound
        case noteIsNotPitched
        case malformed(String)
    }

    public static func replacingTitle(in xml: String, with title: String) throws -> String {
        let (root, bounds) = try parse(xml)
        let work = root.elements(named: "work").first ?? {
            let element = XMLNode(name: root.qualifiedName(for: "work"))
            root.children.insert(.element(element), at: 0)
            return element
        }()
        let workTitle = work.elements(named: "work-title").first ?? {
            let element = XMLNode(name: work.qualifiedName(for: "work-title"))
            work.children.insert(.element(element), at: 0)
            return element
        }()
        workTitle.children = [.text(title)]
        return replaceBody(in: xml, bounds: bounds, with: root.serialized)
    }

    /// Replaces one parsed note's written pitch, using the parser's per-part note ordering.
    public static func replacingPitch(in xml: String, partID: String, noteIndex: Int, with pitch: SpelledPitch) throws -> String {
        let (root, bounds) = try parse(xml)
        guard let part = root.elements(named: "part").first(where: { $0.attribute("id") == partID }) else {
            throw EditError.partNotFound
        }
        var current = 0
        for measure in part.elements(named: "measure") {
            for note in measure.elements(named: "note") {
                let children = note.elements
                guard !children.contains(where: { ["grace", "cue"].contains($0.localName) }) else { continue }
                guard current == noteIndex else { current += 1; continue }
                guard let pitchElement = children.first(where: { $0.localName == "pitch" }) else {
                    throw EditError.noteIsNotPitched
                }
                pitchElement.children = [.element(XMLNode(name: pitchElement.qualifiedName(for: "step"), text: pitch.step))]
                if pitch.alter != 0 {
                    pitchElement.children.append(.element(XMLNode(name: pitchElement.qualifiedName(for: "alter"), text: String(pitch.alter))))
                }
                pitchElement.children.append(.element(XMLNode(name: pitchElement.qualifiedName(for: "octave"), text: String(pitch.octave))))
                return replaceBody(in: xml, bounds: bounds, with: root.serialized)
            }
        }
        throw EditError.noteNotFound
    }

    private static func parse(_ xml: String) throws -> (XMLNode, Range<String.Index>) {
        let delegate = XMLTreeReader()
        let parser = XMLParser(data: Data(xml.utf8))
        parser.shouldResolveExternalEntities = false
        parser.delegate = delegate
        guard parser.parse(), let root = delegate.root else {
            throw EditError.malformed(delegate.error?.localizedDescription ?? parser.parserError?.localizedDescription ?? "parse failed")
        }
        let bounds = try rootBounds(in: xml, rootName: root.name)
        return (root, bounds)
    }

    private static func rootBounds(in xml: String, rootName: String) throws -> Range<String.Index> {
        let start = try rootStart(in: xml)
        guard let close = xml.range(of: "</\(rootName)", options: .backwards), close.lowerBound >= start,
              let closeEnd = xml[close.lowerBound...].firstIndex(of: ">") else {
            throw EditError.malformed("score root element was not closed")
        }
        return start..<xml.index(after: closeEnd)
    }

    private static func rootStart(in xml: String) throws -> String.Index {
        var cursor = xml.startIndex
        while let open = xml[cursor...].firstIndex(of: "<") {
            let tail = xml[open...]
            if tail.hasPrefix("<!--") {
                guard let end = xml.range(of: "-->", range: open..<xml.endIndex) else { break }
                cursor = end.upperBound
            } else if tail.hasPrefix("<?") {
                guard let end = xml.range(of: "?>", range: open..<xml.endIndex) else { break }
                cursor = end.upperBound
            } else if tail.hasPrefix("<!") {
                cursor = try declarationEnd(in: xml, startingAt: open)
            } else {
                return open
            }
        }
        throw EditError.malformed("score root element was not found")
    }

    private static func declarationEnd(in xml: String, startingAt start: String.Index) throws -> String.Index {
        var quote: Character?
        var subsetDepth = 0
        var index = xml.index(after: start)
        while index < xml.endIndex {
            let character = xml[index]
            if let activeQuote = quote {
                if character == activeQuote { quote = nil }
            } else if character == "\"" || character == "'" {
                quote = character
            } else if character == "[" {
                subsetDepth += 1
            } else if character == "]" {
                subsetDepth = max(0, subsetDepth - 1)
            } else if character == ">" && subsetDepth == 0 {
                return xml.index(after: index)
            }
            index = xml.index(after: index)
        }
        throw EditError.malformed("unterminated XML declaration")
    }

    private static func replaceBody(in xml: String, bounds: Range<String.Index>, with body: String) -> String {
        var result = xml
        result.replaceSubrange(bounds, with: body)
        return result
    }
}

private indirect enum XMLContent {
    case element(XMLNode)
    case text(String)
    case cdata(String)
    case comment(String)
    case instruction(String, String)

    var serialized: String {
        switch self {
        case .element(let node): node.serialized
        case .text(let value): XMLNode.escape(value)
        case .cdata(let value): "<![CDATA[\(value)]]>"
        case .comment(let value): "<!--\(value)-->"
        case .instruction(let target, let value): "<?\(target) \(value)?>"
        }
    }
}

private final class XMLNode {
    let name: String
    var attributes: [(String, String)]
    var children: [XMLContent]

    init(name: String, text: String? = nil, attributes: [(String, String)] = []) {
        self.name = name
        self.attributes = attributes
        children = text.map { [.text($0)] } ?? []
    }

    var localName: String { name.split(separator: ":").last.map(String.init) ?? name }
    var elements: [XMLNode] { children.compactMap { if case .element(let node) = $0 { node } else { nil } } }
    var serialized: String {
        let attrs = attributes.map { " \($0.0)=\"\(Self.escapeAttribute($0.1))\"" }.joined()
        guard !children.isEmpty else { return "<\(name)\(attrs)/>" }
        return "<\(name)\(attrs)>\(children.map(\.serialized).joined())</\(name)>"
    }

    func elements(named localName: String) -> [XMLNode] { elements.filter { $0.localName == localName } }
    func attribute(_ name: String) -> String? { attributes.first { $0.0 == name || $0.0.split(separator: ":").last.map(String.init) == name }?.1 }
    func qualifiedName(for localName: String) -> String {
        name.split(separator: ":").dropLast().first.map { "\($0):\(localName)" } ?? localName
    }

    static func escape(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
    }

    private static func escapeAttribute(_ text: String) -> String {
        escape(text).replacingOccurrences(of: "\"", with: "&quot;")
    }
}

private final class XMLTreeReader: NSObject, XMLParserDelegate {
    var root: XMLNode?
    var error: Error?
    private var stack: [XMLNode] = []

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        let node = XMLNode(name: qName ?? elementName, attributes: attributeDict.keys.sorted().map { ($0, attributeDict[$0] ?? "") })
        if let parent = stack.last { parent.children.append(.element(node)) } else { root = node }
        stack.append(node)
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        if !stack.isEmpty { stack.removeLast() }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        stack.last?.children.append(.text(string))
    }

    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) {
        stack.last?.children.append(.cdata(String(decoding: CDATABlock, as: UTF8.self)))
    }

    func parser(_ parser: XMLParser, foundComment comment: String) {
        stack.last?.children.append(.comment(comment))
    }

    func parser(_ parser: XMLParser, foundProcessingInstructionWithTarget target: String, data: String?) {
        if stack.isEmpty { return }
        stack.last?.children.append(.instruction(target, data ?? ""))
    }

    func parser(_ parser: XMLParser, parseErrorOccurred parseError: Error) { error = parseError }
}
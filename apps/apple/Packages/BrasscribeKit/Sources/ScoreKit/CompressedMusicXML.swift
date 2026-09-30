import Compression
import Foundation

/// Compressed MusicXML (`.mxl`): a ZIP archive whose `META-INF/container.xml` names the score file.
/// Only what MusicXML writers produce is read: stored or deflated entries, no encryption, no ZIP64.
/// Every size is checked against `maxBytes` before anything is inflated, so a small file that claims
/// or inflates to a huge score is refused.
public enum CompressedMusicXML {
    public static let defaultMaxBytes = 50 << 20

    /// True when the data starts like a ZIP archive.
    public static func isZip(_ data: Data) -> Bool { data.prefix(4) == Data([0x50, 0x4B, 0x03, 0x04]) }

    /// The score file's MusicXML.
    public static func musicXML(from data: Data, maxBytes: Int = defaultMaxBytes) throws -> Data {
        let entries = try centralDirectory(data)
        let root: Entry
        if let container = entries.first(where: { $0.name == "META-INF/container.xml" }),
           let path = rootfile(in: try read(container, from: data, maxBytes: maxBytes)),
           let e = entries.first(where: { $0.name == path }) {
            root = e
        } else if let e = entries.first(where: {
            !$0.name.hasPrefix("META-INF/") && ($0.name.lowercased().hasSuffix(".musicxml") || $0.name.lowercased().hasSuffix(".xml"))
        }) {
            root = e
        } else {
            throw MusicXMLError.malformed("no score in the .mxl archive")
        }
        return try read(root, from: data, maxBytes: maxBytes)
    }

    struct Entry {
        var name: String
        var method: UInt16
        var flags: UInt16
        var compressedSize: Int
        var size: Int
        var localHeader: Int
    }

    static func centralDirectory(_ d: Data) throws -> [Entry] {
        let b = [UInt8](d)
        func u16(_ i: Int) throws -> Int {
            guard i >= 0, i + 2 <= b.count else { throw MusicXMLError.malformed("truncated .mxl archive") }
            return Int(b[i]) | Int(b[i + 1]) << 8
        }
        func u32(_ i: Int) throws -> Int { try u16(i) | u16(i + 2) << 16 }
        // the end-of-central-directory record, within the last 64 KiB (its comment is at most 65535 bytes)
        guard b.count >= 22 else { throw MusicXMLError.malformed("not a .mxl archive") }
        var eocd = -1
        for i in stride(from: b.count - 22, through: max(0, b.count - 22 - 65_535), by: -1)
        where b[i] == 0x50 && b[i + 1] == 0x4B && b[i + 2] == 0x05 && b[i + 3] == 0x06 {
            eocd = i; break
        }
        guard eocd >= 0 else { throw MusicXMLError.malformed("not a .mxl archive") }
        let count = try u16(eocd + 10), start = try u32(eocd + 16)
        guard count <= 10_000 else { throw MusicXMLError.malformed("too many files in the .mxl archive") }
        var out: [Entry] = []
        var p = start
        for _ in 0..<count {
            guard try u32(p) == 0x0201_4B50 else { throw MusicXMLError.malformed("damaged .mxl archive") }
            let nameLen = try u16(p + 28), extraLen = try u16(p + 30), commentLen = try u16(p + 32)
            guard p + 46 + nameLen <= b.count else { throw MusicXMLError.malformed("truncated .mxl archive") }
            let name = String(decoding: b[(p + 46)..<(p + 46 + nameLen)], as: UTF8.self)
            out.append(Entry(name: name, method: UInt16(try u16(p + 10)), flags: UInt16(try u16(p + 8)),
                             compressedSize: try u32(p + 20), size: try u32(p + 24), localHeader: try u32(p + 42)))
            p += 46 + nameLen + extraLen + commentLen
        }
        return out
    }

    static func read(_ e: Entry, from d: Data, maxBytes: Int) throws -> Data {
        guard e.flags & 1 == 0 else { throw MusicXMLError.malformed("encrypted .mxl archive") }
        guard e.size <= maxBytes, e.compressedSize <= d.count else { throw MusicXMLError.malformed("the score in the .mxl archive is too large") }
        let b = [UInt8](d)
        let h = e.localHeader
        guard h >= 0, h + 30 <= b.count, b[h] == 0x50, b[h + 1] == 0x4B, b[h + 2] == 0x03, b[h + 3] == 0x04 else {
            throw MusicXMLError.malformed("damaged .mxl archive")
        }
        let nameLen = Int(b[h + 26]) | Int(b[h + 27]) << 8, extraLen = Int(b[h + 28]) | Int(b[h + 29]) << 8
        let start = h + 30 + nameLen + extraLen
        guard start + e.compressedSize <= b.count else { throw MusicXMLError.malformed("truncated .mxl archive") }
        let payload = Array(b[start..<(start + e.compressedSize)])
        switch e.method {
        case 0:
            guard payload.count == e.size else { throw MusicXMLError.malformed("damaged .mxl archive") }
            return Data(payload)
        case 8:
            if e.size == 0 { return Data() }
            // one byte more than declared: an entry that inflates past its declared size is refused
            var out = [UInt8](repeating: 0, count: e.size + 1)
            let n = payload.withUnsafeBufferPointer { src in
                out.withUnsafeMutableBufferPointer { dst in
                    compression_decode_buffer(dst.baseAddress!, dst.count, src.baseAddress!, src.count, nil, COMPRESSION_ZLIB)
                }
            }
            guard n == e.size else { throw MusicXMLError.malformed("damaged .mxl archive") }
            return Data(out.prefix(n))
        default:
            throw MusicXMLError.malformed("unsupported compression in the .mxl archive")
        }
    }

    /// `<rootfile full-path="…">` of META-INF/container.xml.
    static func rootfile(in xml: Data) -> String? {
        final class Finder: NSObject, XMLParserDelegate {
            var path: String?
            func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?, qualifiedName: String?,
                        attributes: [String: String] = [:]) {
                if name == "rootfile", path == nil { path = attributes["full-path"] }
            }
        }
        let f = Finder()
        let p = XMLParser(data: xml)
        p.shouldResolveExternalEntities = false
        p.delegate = f
        p.parse()
        return f.path
    }
}

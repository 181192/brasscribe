import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Pages of printed music the computer reads instead of a recording: pictures and PDFs, in order
/// (engine: pages.py, sheet.py). What a file is, is read from its first bytes, as the engine reads it.
public enum Pages {
    /// The most files one job takes, and the largest one may be (engine: pages.py).
    public static let maxPages = 40
    public static let maxPageBytes = 50 * 1024 * 1024
    /// The longest side of a picture this device makes (a photo, or one converted to JPEG). The engine takes up to
    /// 50 million pixels; a page's notes are read well below this.
    public static let maxSide = 3000

    /// The formats the engine reads as they are, by their first bytes.
    public enum Format: String, Sendable { case png, jpeg, webp, pdf }

    /// The format of a file that starts with `head`, or nil when the engine would not read it as it is.
    public static func format(of head: Data) -> Format? {
        let b = [UInt8](head.prefix(12))
        func starts(_ bytes: [UInt8], at i: Int = 0) -> Bool { b.count >= i + bytes.count && Array(b[i..<(i + bytes.count)]) == bytes }
        if starts([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) { return .png }
        if starts([0xFF, 0xD8, 0xFF]) { return .jpeg }
        if starts(Array("RIFF".utf8)) && starts(Array("WEBP".utf8), at: 8) { return .webp }
        if starts(Array("%PDF-".utf8)) { return .pdf }
        return nil
    }

    /// Why a file cannot be a page.
    public enum Refusal: Error, Equatable, Sendable {
        /// Not a picture or a PDF this device can read (a song, a document).
        case notAPage(String)
        /// Over `maxPageBytes`.
        case tooLarge(String)
    }

    /// A page as it is sent, in `folder`: a PNG, JPEG, WebP or PDF is copied as it is; any other picture the system
    /// can open (HEIC, AVIF, GIF, TIFF, BMP) is written as an upright JPEG, its longest side at most `maxSide`. A file
    /// over `maxPageBytes` is refused before it is copied.
    public static func prepare(_ url: URL, into folder: URL) throws -> URL {
        let name = url.lastPathComponent
        let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        guard size <= maxPageBytes else { throw Refusal.tooLarge(name) }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let reader = try FileHandle(forReadingFrom: url)
        let head = try reader.read(upToCount: 12) ?? Data()
        try reader.close()
        if let format = format(of: head) {
            let dst = folder.appending(path: "\(UUID().uuidString).\(format == .jpeg ? "jpg" : format.rawValue)")
            try FileManager.default.copyItem(at: url, to: dst)
            return dst
        }
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil), CGImageSourceGetCount(source) > 0 else {
            throw Refusal.notAPage(name)
        }
        let dst = folder.appending(path: "\(UUID().uuidString).jpg")
        try writeJPEG(from: source, to: dst, name: name)
        return dst
    }

    /// A picture taken on this device (the camera's), as an upright JPEG in `folder`.
    public static func photo(_ data: Data, into folder: URL) throws -> URL {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        guard let source = CGImageSourceCreateWithData(data as CFData, nil), CGImageSourceGetCount(source) > 0 else {
            throw Refusal.notAPage("photo")
        }
        let dst = folder.appending(path: "\(UUID().uuidString).jpg")
        try writeJPEG(from: source, to: dst, name: "photo")
        return dst
    }

    /// The first picture of `source`, turned the way it was taken and scaled to fit `maxSide`, as a JPEG.
    private static func writeJPEG(from source: CGImageSource, to dst: URL, name: String) throws {
        let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let w = props?[kCGImagePropertyPixelWidth] as? Int ?? 0, h = props?[kCGImagePropertyPixelHeight] as? Int ?? 0
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            // the orientation a camera writes beside the pixels is applied: the page is sent upright
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: min(maxSide, max(w, h, 1)),
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary),
              let out = CGImageDestinationCreateWithURL(dst as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw Refusal.notAPage(name)
        }
        CGImageDestinationAddImage(out, image, [kCGImageDestinationLossyCompressionQuality: 0.9] as CFDictionary)
        guard CGImageDestinationFinalize(out) else { throw Refusal.notAPage(name) }
    }

    /// Why the computer did not read the pages, by the fixed words a failed job's error ends with (engine: sheet.py).
    public enum Failure: String, CaseIterable, Sendable {
        case noMusic, onlyTab, tooManyPages, pageTooLarge, readerFilesMissing, diskFull, notRead

        /// The engine's words for it. `tooManyPages` names the limit.
        public var engineWords: String {
            switch self {
            case .noMusic: "no notes were found on the page"
            case .onlyTab: "no staff of notes was found on the page: a tab staff is not read"
            case .tooManyPages: "there are more than \(Pages.maxPages) pages"
            case .pageTooLarge: "a page is too large to read"
            case .readerFilesMissing: "the reader's files could not be fetched: check the network and try again"
            case .diskFull: "the computer's disk is full: free some space on it and try again"
            case .notRead: "the pages could not be read"
            }
        }

        /// The failure a job's error names, or nil for any other error. The words end the error, or its first line
        /// when a traceback follows.
        public static func of(_ error: String) -> Failure? {
            let whole = error.trimmingCharacters(in: .whitespacesAndNewlines)
            let first = whole.split(separator: "\n", maxSplits: 1).first.map { String($0).trimmingCharacters(in: .whitespaces) } ?? whole
            return allCases.first { f in [whole, first].contains { $0.hasSuffix(f.engineWords) } }
        }
    }

    /// The codes the computer refuses pages with before a job is made ({"code", "detail"}; engine: pages.py, sheet.py).
    public enum Refused: String, CaseIterable, Sendable {
        case notAPage = "not_a_page"
        case wrongInput = "wrong_input"
        case pageTooLarge = "page_too_large"
        case tooManyPages = "too_many_pages"
        case readerMissing = "reader_missing"
    }
}

extension TranscriptionError {
    /// The computer's named refusal of pages, when this is one.
    public var pagesRefused: Pages.Refused? {
        guard case .http(_, let body) = self else { return nil }
        if let obj = (try? JSONSerialization.jsonObject(with: Data(body.utf8))) as? [String: Any], let code = obj["code"] as? String {
            return Pages.Refused(rawValue: code)
        }
        // a body cut short still names its code
        return Pages.Refused.allCases.first { body.contains(#""code":"\#($0.rawValue)""#) || body.contains(#""code": "\#($0.rawValue)""#) }
    }

    /// The reason a job that read pages failed, when this is one.
    public var pagesFailure: Pages.Failure? {
        guard case .jobFailed(let said) = self else { return nil }
        return Pages.Failure.of(said)
    }
}

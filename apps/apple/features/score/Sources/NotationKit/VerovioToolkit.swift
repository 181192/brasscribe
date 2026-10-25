import Foundation
import Verovio

/// Thin Swift wrapper over Verovio's C interface (`tools/c_wrapper.h`). One instance holds
/// one loaded document. Verovio is not thread-safe: use an instance from one thread at a time.
public final class VerovioToolkit: @unchecked Sendable {
    private let handle: UnsafeMutableRawPointer

    /// Directory with the font data (`Leipzig/`, `Bravura/`, `text/`, `*.xml`): the app's
    /// `VerovioResources` folder, or `VEROVIO_RESOURCES`.
    public static func defaultResourcePath(bundle: Bundle = .main) -> String? {
        if let env = ProcessInfo.processInfo.environment["VEROVIO_RESOURCES"],
           FileManager.default.fileExists(atPath: env) { return env }
        if let u = bundle.url(forResource: "VerovioResources", withExtension: nil) { return u.path }
        var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<6 {
            let c = dir.appending(path: "Frameworks/VerovioResources")
            if FileManager.default.fileExists(atPath: c.path) { return c.path }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    public init?(resourcePath: String? = VerovioToolkit.defaultResourcePath()) {
        enableLog(false)
        guard let resourcePath, let h = vrvToolkit_constructorResourcePath(resourcePath) else { return nil }
        handle = h
    }

    deinit { vrvToolkit_destructor(handle) }

    public static var version: String {
        guard let t = VerovioToolkit(resourcePath: defaultResourcePath()) else { return "?" }
        // the string lives in the toolkit: keep it until it is copied
        return withExtendedLifetime(t) { String(cString: vrvToolkit_getVersion(t.handle)) }
    }

    @discardableResult
    public func setOptions(_ options: [String: Any]) -> Bool {
        guard let d = try? JSONSerialization.data(withJSONObject: options), let s = String(data: d, encoding: .utf8) else { return false }
        return vrvToolkit_setOptions(handle, s)
    }

    public func loadData(_ data: String) -> Bool { vrvToolkit_loadData(handle, data) }

    public var pageCount: Int { Int(vrvToolkit_getPageCount(handle)) }

    public func renderToSVG(page: Int, xmlDeclaration: Bool = false) -> String {
        String(cString: vrvToolkit_renderToSVG(handle, Int32(page), xmlDeclaration))
    }

    public func renderToMIDI() -> Data? {
        Data(base64Encoded: String(cString: vrvToolkit_renderToMIDI(handle)))
    }

    public func getMEI() -> String { String(cString: vrvToolkit_getMEI(handle, "{}")) }

    /// Restrict rendering to part of the loaded document, e.g. `{"measureRange": "14-15"}`; `{}` clears it.
    @discardableResult
    public func select(_ selection: [String: Any]) -> Bool {
        guard let d = try? JSONSerialization.data(withJSONObject: selection), let s = String(data: d, encoding: .utf8) else { return false }
        return vrvToolkit_select(handle, s)
    }

    public func redoLayout() { vrvToolkit_redoLayout(handle, "{}") }

    public func pageWithElement(_ id: String) -> Int { Int(vrvToolkit_getPageWithElement(handle, id)) }

    public func timemap() -> [TimemapEntry] {
        let s = String(cString: vrvToolkit_renderToTimemap(handle, #"{"includeMeasures": true, "includeRests": true}"#))
        return (try? JSONDecoder().decode([TimemapEntry].self, from: Data(s.utf8))) ?? []
    }

    public func log() -> String { String(cString: vrvToolkit_getLog(handle)) }
}

/// One entry of Verovio's timemap: at `qstamp` quarter notes (`tstamp` ms at the
/// encoded tempo) these element ids start or stop sounding.
public struct TimemapEntry: Decodable, Sendable, Equatable {
    public let tstamp: Double
    public let qstamp: Double
    public let on: [String]?
    public let off: [String]?
    public let measureOn: String?
    public let tempo: Double?
}

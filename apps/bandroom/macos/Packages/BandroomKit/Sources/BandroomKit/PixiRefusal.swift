import Foundation

/// pixi refused the engine workspace because it is older than `requires-pixi` in pixi.toml asks for: "this project
/// requires pixi '>=0.80', but you have pixi 0.79.0". Nothing Bandroom can retry fixes that; only an app that bundles a
/// newer pixi does.
public struct PixiRefusal: Equatable, Sendable {
    /// What the workspace asks for, as pixi wrote it (">=0.80").
    public var required: String
    /// The version of the pixi that refused ("0.79.0").
    public var found: String
    /// pixi's own line as it wrote it, for the tech person.
    public var message: String

    public init(required: String, found: String, message: String) {
        self.required = required; self.found = found; self.message = message
    }

    /// The first refusal in `text` (pixi's output). Matches the words only: the "Error: ×" before them differs by
    /// terminal and code page.
    public static func find(in text: String) -> PixiRefusal? {
        for line in text.split(whereSeparator: \.isNewline) {
            let s = String(line)
            guard let m = s.firstMatch(of: /requires pixi '([^']+)', but you have pixi ([0-9][0-9A-Za-z.+-]*)/) else { continue }
            let message = s.trimmingCharacters(in: .whitespaces)
            return PixiRefusal(required: String(m.output.1), found: String(m.output.2), message: message)
        }
        return nil
    }

    /// The refusal in what the latest run wrote to `log`, if it refused. Each run starts with a "--- <date> <command>"
    /// line (`PosixLauncher`); only what follows the last one counts, so an earlier session's refusal is never blamed.
    public static func inLatestRun(log: URL, maxBytes: Int = 64 << 10) -> PixiRefusal? {
        guard let h = try? FileHandle(forReadingFrom: log) else { return nil }
        defer { try? h.close() }
        let size = (try? h.seekToEnd()) ?? 0
        try? h.seek(toOffset: size > UInt64(maxBytes) ? size - UInt64(maxBytes) : 0)
        guard let data = try? h.readToEnd() else { return nil }
        let text = String(decoding: data, as: UTF8.self)
        let latest = text.range(of: "\n--- ", options: .backwards).map { String(text[$0.upperBound...]) }
            ?? (text.hasPrefix("--- ") ? text : "")
        return find(in: latest)
    }
}

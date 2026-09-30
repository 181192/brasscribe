import Foundation

/// Removes what Bandroom put on this Mac (design/server-app.md §3.10): the data folder (environments,
/// paired phones, the admin token) and the logs. The downloads (the models folder and the band writer in the
/// Hugging Face cache) can be kept for a later reinstall.
///
/// The standard folders (`~/Library/Application Support/Brasscribe`, `~/Library/Logs/Brasscribe`) go whole.
/// A folder moved elsewhere with BRASSCRIBE_DATA or BRASSCRIBE_LOGS may be one the user keeps other things in,
/// so there only what Bandroom and the engine make is deleted, and the folder itself only if that leaves it
/// empty. It never touches anything else, such as a source checkout's models.
public struct Uninstaller: Sendable {
    public enum Failure: Error, Equatable {
        /// The folder is the home folder, a parent of it, or outside it: never deleted.
        case unsafePath(String)
    }

    public let paths: BandroomPaths
    public let home: URL
    /// The Hugging Face hub cache the band writer was downloaded into; nil leaves the cache alone.
    public let hub: URL?

    /// What Bandroom and the engine keep in the data folder (BandroomPaths, and the engine's config.py).
    static let dataEntries = ["models", "companion", "envs", "cache", "runs", "uploads", "eval", "golden", "bench", "captures",
                              "admin-token", "engine.json"]
    /// The log files Bandroom writes, and their rotated copies.
    static let logFiles = ["bandroom.log", "engine.log", "setup.log"]

    public init(paths: BandroomPaths, home: URL = FileManager.default.homeDirectoryForCurrentUser, hub: URL? = nil) {
        self.paths = paths
        self.home = home
        self.hub = hub
    }

    /// The downloads: the models folder, and the band writer's folder in the hub cache when that is inside the home
    /// folder (a cache moved to another disk with HF_HUB_CACHE or HF_HOME is left alone).
    var downloads: [URL] {
        let writer = hub.map { ModelCatalog.hubRepoFolder(ModelCatalog.muscriptorRepo, hub: $0) }
        return [paths.models] + (writer.flatMap { (try? checkSafe($0)) != nil ? [$0] : nil } ?? [])
    }

    /// The size of the downloads in bytes, or nil when there are none.
    public func downloadsSize() -> Int64? {
        let sizes = downloads.compactMap(Self.size(of:))
        return sizes.isEmpty ? nil : sizes.reduce(0, +)
    }

    /// Deletes the data folder and the logs, and unless `keepDownloads`, the downloads. With `keepDownloads`, the
    /// data folder's `models` stays and everything else in it goes. Returns what was kept.
    @discardableResult
    public func remove(keepDownloads: Bool) throws -> [URL] {
        let fm = FileManager.default
        let hubFolder = keepDownloads ? nil : downloads.dropFirst().first
        for dir in [paths.data, paths.logs] + (hubFolder.map { [$0] } ?? []) { try checkSafe(dir) }
        var kept: [URL] = []
        let keepModels = keepDownloads && fm.fileExists(atPath: paths.models.path)
        if keepModels { kept.append(paths.models) }
        if isStandard(paths.data, "Library/Application Support/Brasscribe") {
            if keepModels {
                let children = (try? fm.contentsOfDirectory(at: paths.data, includingPropertiesForKeys: nil)) ?? []
                for child in children where child.lastPathComponent != paths.models.lastPathComponent {
                    try fm.removeItem(at: child)
                }
            } else if fm.fileExists(atPath: paths.data.path) {
                try fm.removeItem(at: paths.data)
            }
        } else {
            try removeOwn(in: paths.data, names: Self.dataEntries.filter { !(keepModels && $0 == paths.models.lastPathComponent) })
        }
        if isStandard(paths.logs, "Library/Logs/Brasscribe") {
            if fm.fileExists(atPath: paths.logs.path) { try fm.removeItem(at: paths.logs) }
        } else {
            try removeOwn(in: paths.logs, names: Self.logFiles.flatMap { [$0, $0 + ".1"] })
        }
        if let hubFolder, fm.fileExists(atPath: hubFolder.path) { try fm.removeItem(at: hubFolder) }
        return kept
    }

    /// Deletes `names` in `dir`, then `dir` itself if nothing else is in it.
    private func removeOwn(in dir: URL, names: [String]) throws {
        let fm = FileManager.default
        for name in names {
            let item = dir.appending(path: name)
            if fm.fileExists(atPath: item.path) { try fm.removeItem(at: item) }
        }
        let left = (try? fm.contentsOfDirectory(atPath: dir.path).filter { $0 != ".DS_Store" }) ?? []
        if left.isEmpty && fm.fileExists(atPath: dir.path) { try fm.removeItem(at: dir) }
    }

    /// `dir` is the default folder under the home folder, not one BRASSCRIBE_DATA or BRASSCRIBE_LOGS chose.
    private func isStandard(_ dir: URL, _ relative: String) -> Bool {
        Self.components(dir) == Self.components(home.appending(path: relative, directoryHint: .isDirectory))
    }

    /// A folder is safe to delete from when it lies strictly inside the home folder and isn't the home
    /// folder or a parent of it.
    func checkSafe(_ dir: URL) throws {
        let d = Self.components(dir)
        let h = Self.components(home)
        guard d.count > h.count && Array(d.prefix(h.count)) == h else { throw Failure.unsafePath(dir.path) }
    }

    /// Path components with symlinks resolved as far as the path exists, so a folder not made yet compares like
    /// one that is.
    private static func components(_ url: URL) -> [String] {
        var existing = url.standardizedFileURL
        var rest: [String] = []
        while !FileManager.default.fileExists(atPath: existing.path), existing.pathComponents.count > 1 {
            rest.insert(existing.lastPathComponent, at: 0)
            existing.deleteLastPathComponent()
        }
        return existing.resolvingSymlinksInPath().pathComponents + rest
    }

    static func size(of dir: URL) -> Int64? {
        let fm = FileManager.default
        var isDir: ObjCBool = false
        guard fm.fileExists(atPath: dir.path, isDirectory: &isDir), isDir.boolValue else { return nil }
        var total: Int64 = 0
        let keys: [URLResourceKey] = [.totalFileAllocatedSizeKey, .fileSizeKey, .isRegularFileKey]
        if let e = fm.enumerator(at: dir, includingPropertiesForKeys: keys) {
            for case let url as URL in e {
                guard let v = try? url.resourceValues(forKeys: Set(keys)), v.isRegularFile == true else { continue }
                total += Int64(v.totalFileAllocatedSize ?? v.fileSize ?? 0)
            }
        }
        return total
    }
}

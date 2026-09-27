import Foundation

/// Removes what Bandroom put on this Mac (design/server-app.md §3.10): the data folder (environments,
/// paired phones, the admin token) and the logs. The downloads can be kept for a later reinstall.
/// It never touches anything outside those two folders, such as a source checkout's models.
public struct Uninstaller: Sendable {
    public enum Failure: Error, Equatable {
        /// The folder is the home folder, a parent of it, or the root: never deleted.
        case unsafePath(String)
    }

    public let paths: BandroomPaths
    public let home: URL

    public init(paths: BandroomPaths, home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        self.paths = paths
        self.home = home
    }

    /// The size of the downloads folder in bytes, or nil when there is none.
    public func downloadsSize() -> Int64? {
        Self.size(of: paths.models)
    }

    /// Deletes the data folder and the logs. With `keepDownloads`, the data folder's `models`
    /// stays and everything else in it goes. Returns what was kept.
    @discardableResult
    public func remove(keepDownloads: Bool) throws -> [URL] {
        let fm = FileManager.default
        for dir in [paths.data, paths.logs] { try checkSafe(dir) }
        var kept: [URL] = []
        if keepDownloads, fm.fileExists(atPath: paths.models.path) {
            let children = (try? fm.contentsOfDirectory(at: paths.data, includingPropertiesForKeys: nil)) ?? []
            for child in children where child.standardizedFileURL.lastPathComponent != paths.models.lastPathComponent {
                try fm.removeItem(at: child)
            }
            kept.append(paths.models)
        } else if fm.fileExists(atPath: paths.data.path) {
            try fm.removeItem(at: paths.data)
        }
        if fm.fileExists(atPath: paths.logs.path) { try fm.removeItem(at: paths.logs) }
        return kept
    }

    /// A folder is safe to delete when it lies strictly inside the home folder and isn't the home
    /// folder or a parent of it.
    func checkSafe(_ dir: URL) throws {
        let d = dir.standardizedFileURL.resolvingSymlinksInPath().pathComponents
        let h = home.standardizedFileURL.resolvingSymlinksInPath().pathComponents
        let insideHome = d.count > h.count && Array(d.prefix(h.count)) == h
        if !insideHome && !Self.isTemporary(d) { throw Failure.unsafePath(dir.path) }
    }

    /// Tests and BRASSCRIBE_DATA overrides may point at a temporary folder.
    private static func isTemporary(_ components: [String]) -> Bool {
        let tmp = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath().pathComponents
        return components.count > tmp.count && Array(components.prefix(tmp.count)) == tmp
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

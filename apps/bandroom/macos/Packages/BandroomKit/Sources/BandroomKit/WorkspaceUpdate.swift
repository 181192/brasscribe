import CryptoKit
import Foundation

/// Which build a workspace is: `.brasscribe-workspace.json`, written into the app's workspace when the app is built
/// (scripts/stage-workspace.sh) and copied along with it into the data folder.
public struct WorkspaceStamp: Codable, Equatable, Sendable {
    /// A hash of every file's path and content.
    public var stamp: String
    /// SHA-256 of pixi.lock: only a new lockfile needs `pixi install` again.
    public var lock: String?
    public var commit: String?
    public var version: String?
    public var build: String?

    public static let fileName = ".brasscribe-workspace.json"

    public init(stamp: String, lock: String? = nil, commit: String? = nil, version: String? = nil, build: String? = nil) {
        self.stamp = stamp; self.lock = lock; self.commit = commit; self.version = version; self.build = build
    }

    /// The stamp file in `workspace`, if it has one.
    public static func read(in workspace: URL) -> WorkspaceStamp? {
        (try? Data(contentsOf: workspace.appending(path: fileName))).flatMap { try? JSONDecoder().decode(WorkspaceStamp.self, from: $0) }
    }

    /// The app's own workspace: its stamp file, else a stamp computed from its files (a build without one).
    public static func of(bundle: URL) -> WorkspaceStamp? {
        read(in: bundle) ?? (try? compute(bundle))
    }

    /// Paths and contents of every file but the stamp itself, in byte order of the path. Never dates. The same value
    /// stage-workspace.sh writes.
    public static func compute(_ dir: URL) throws -> WorkspaceStamp {
        let fm = FileManager.default
        let base = dir.standardizedFileURL.path
        var files: [String] = []
        if let walker = fm.enumerator(at: dir, includingPropertiesForKeys: [.isRegularFileKey]) {
            for case let url as URL in walker where (try? url.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true {
                let rel = String(url.standardizedFileURL.path.dropFirst(base.count + 1))
                if rel != fileName && url.lastPathComponent != ".DS_Store" { files.append(rel) }
            }
        }
        var all = SHA256()
        for rel in files.sorted(by: { $0.utf8.lexicographicallyPrecedes($1.utf8) }) {
            let hash = try fileHash(dir.appending(path: rel))
            all.update(data: Data("\(hash)  ./\(rel)\n".utf8))  // as `shasum` prints it in stage-workspace.sh
        }
        let lock = try? fileHash(dir.appending(path: "pixi.lock"))
        return WorkspaceStamp(stamp: hex(all.finalize()), lock: lock)
    }

    static func fileHash(_ url: URL) throws -> String {
        hex(SHA256.hash(data: try Data(contentsOf: url, options: .mappedIfSafe)))
    }

    private static func hex<D: Sequence>(_ digest: D) -> String where D.Element == UInt8 {
        digest.map { String(format: "%02x", $0) }.joined()
    }

    /// "0cf2582 · 5faffacca071": the commit and the start of the stamp, for the tech-person details.
    public var short: String {
        [commit, String(stamp.prefix(12))].compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: " · ")
    }
}

/// What a launch has to do with the copy of the workspace in the data folder.
public enum WorkspaceCheck: Equatable, Sendable {
    case upToDate
    /// No copy yet: the first run's setup makes it.
    case notInstalled
    /// The copy is from another build (or from before stamps): replace it, and `pixi install` again when the
    /// lockfile changed.
    case update(lockChanged: Bool)

    public static func compare(bundled: URL, installed: URL) -> WorkspaceCheck {
        let fm = FileManager.default
        guard fm.fileExists(atPath: installed.appending(path: "pixi.toml").path) else { return .notInstalled }
        guard let want = WorkspaceStamp.of(bundle: bundled) else { return .upToDate }
        let have = WorkspaceStamp.read(in: installed)
        if have?.stamp == want.stamp { return .upToDate }
        return .update(lockChanged: lockChanged(bundled: bundled, want: want, installed: installed))
    }

    /// At launch: first undo an update cut short (its stamp may already be in place while `pixi install` never
    /// finished), then compare.
    public static func atLaunch(bundled: URL, installed: URL) -> WorkspaceCheck {
        try? WorkspaceSwap.recover(installed)
        return compare(bundled: bundled, installed: installed)
    }

    static func lockChanged(bundled: URL, want: WorkspaceStamp, installed: URL) -> Bool {
        let wantLock = want.lock ?? (try? WorkspaceStamp.fileHash(bundled.appending(path: "pixi.lock")))
        let haveLock = try? WorkspaceStamp.fileHash(installed.appending(path: "pixi.lock"))
        return wantLock == nil || wantLock != haveLock
    }
}

/// Replaces the code in the data folder's workspace with the app's, all or nothing (design/server-app.md §3.8).
///
/// Only the app workspace's own top-level entries are replaced (engine, music, eval, ml, pixi.toml, pixi.lock and the
/// stamp). The pixi environments (`.pixi`) and anything else in the folder stay; runs, models, paired devices and
/// the rest of the data folder are outside it. The new copy is staged next to the old one (same volume, so moves are
/// renames), the old entries are moved aside, the new ones moved in, stamp last. Until `commit()` the old entries are
/// kept, so a failed `pixi install` can still `rollback()`. A journal records the replaced entries, so an update cut
/// short by a crash or power cut is undone at the next launch by `recover(_:)`.
public struct WorkspaceSwap: Sendable {
    public let workspace: URL
    let entries: [Entry]

    struct Entry: Codable, Equatable, Sendable {
        var name: String
        var hadOld: Bool
    }

    static let workDir = ".bandroom-update"
    static let journalName = "journal.json"

    var work: URL { workspace.appending(path: Self.workDir, directoryHint: .isDirectory) }
    var staging: URL { work.appending(path: "new", directoryHint: .isDirectory) }
    var backup: URL { work.appending(path: "old", directoryHint: .isDirectory) }

    /// Stages the app's workspace and moves it into place. On any error the old copy is back as it was.
    /// `beforeMove` runs before each entry moves in (tests use it to fail part-way).
    public static func install(from bundled: URL, into workspace: URL,
                               beforeMove: (String) throws -> Void = { _ in }) throws -> WorkspaceSwap {
        let fm = FileManager.default
        try recover(workspace)
        try fm.createDirectory(at: workspace, withIntermediateDirectories: true)
        var names = try fm.contentsOfDirectory(atPath: bundled.path).filter { $0 != ".DS_Store" && $0 != workDir }
        // The stamp goes in last: until it's there, the copy still reads as the old build.
        names.sort()
        if let i = names.firstIndex(of: WorkspaceStamp.fileName) { names.append(names.remove(at: i)) }
        // A build without a stamp file gets one computed, so the copy still knows which build it is.
        let computed = names.last == WorkspaceStamp.fileName ? nil : try WorkspaceStamp.compute(bundled)
        if computed != nil { names.append(WorkspaceStamp.fileName) }
        let entries = names.map { Entry(name: $0, hadOld: fm.fileExists(atPath: workspace.appending(path: $0).path)) }
        let swap = WorkspaceSwap(workspace: workspace, entries: entries)
        do {
            try fm.createDirectory(at: swap.staging, withIntermediateDirectories: true)
            try fm.createDirectory(at: swap.backup, withIntermediateDirectories: true)
            for e in entries {
                let target = swap.staging.appending(path: e.name)
                if let computed, e.name == WorkspaceStamp.fileName {
                    try JSONEncoder().encode(computed).write(to: target)
                } else {
                    try fm.copyItem(at: bundled.appending(path: e.name), to: target)
                }
            }
            let journal = JSONEncoder()
            try journal.encode(entries).write(to: swap.work.appending(path: journalName), options: .atomic)
            for e in entries {
                if e.hadOld { try fm.moveItem(at: workspace.appending(path: e.name), to: swap.backup.appending(path: e.name)) }
                try beforeMove(e.name)
                try fm.moveItem(at: swap.staging.appending(path: e.name), to: workspace.appending(path: e.name))
            }
        } catch {
            try? recover(workspace)
            throw error
        }
        return swap
    }

    /// Drops the old copy: the update is done.
    public func commit() {
        try? FileManager.default.removeItem(at: work)
    }

    /// Puts the old copy back.
    public func rollback() throws {
        try Self.recover(workspace)
    }

    /// Undoes an update that didn't commit: every replaced entry gets its old self back, new-only entries go.
    /// Without a journal there is nothing to undo; leftover staging is removed either way.
    public static func recover(_ workspace: URL) throws {
        let fm = FileManager.default
        let work = workspace.appending(path: workDir, directoryHint: .isDirectory)
        guard fm.fileExists(atPath: work.path) else { return }
        let journal = work.appending(path: journalName)
        if let data = try? Data(contentsOf: journal), let entries = try? JSONDecoder().decode([Entry].self, from: data) {
            let backup = work.appending(path: "old", directoryHint: .isDirectory)
            for e in entries.reversed() {
                let live = workspace.appending(path: e.name), old = backup.appending(path: e.name)
                if e.hadOld {
                    // Not moved aside yet: the original is still in place.
                    guard fm.fileExists(atPath: old.path) else { continue }
                    if fm.fileExists(atPath: live.path) { try fm.removeItem(at: live) }
                    try fm.moveItem(at: old, to: live)
                } else if fm.fileExists(atPath: live.path) {
                    try fm.removeItem(at: live)
                }
            }
        }
        try fm.removeItem(at: work)
    }
}

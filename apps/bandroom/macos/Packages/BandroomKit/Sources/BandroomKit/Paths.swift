import Foundation
import SystemConfiguration

/// Where Bandroom keeps things on this Mac (design/server-app.md §5.2).
public struct BandroomPaths: Sendable, Equatable {
    /// `~/Library/Application Support/Brasscribe`: downloads, environments, paired devices. BRASSCRIBE_DATA overrides it.
    public var data: URL
    /// `~/Library/Logs/Brasscribe`. BRASSCRIBE_LOGS overrides it.
    public var logs: URL

    public init(data: URL, logs: URL) {
        self.data = data
        self.logs = logs
    }

    public static func standard(environment: [String: String] = ProcessInfo.processInfo.environment) -> BandroomPaths {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser
        let data = environment["BRASSCRIBE_DATA"].map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? home.appending(path: "Library/Application Support/Brasscribe", directoryHint: .isDirectory)
        let logs = environment["BRASSCRIBE_LOGS"].map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? home.appending(path: "Library/Logs/Brasscribe", directoryHint: .isDirectory)
        return BandroomPaths(data: data, logs: logs)
    }

    public var models: URL { data.appending(path: "models", directoryHint: .isDirectory) }
    /// The engine's companion state (server id, paired devices): the engine's own default under the data folder.
    public var state: URL { data.appending(path: "companion", directoryHint: .isDirectory) }
    public var workspace: URL { data.appending(path: "envs", directoryHint: .isDirectory) }
    public var pixiCache: URL { data.appending(path: "cache/pixi", directoryHint: .isDirectory) }
    public var adminToken: URL { data.appending(path: "admin-token") }
    /// Port, pid and server id for Play on the same computer (§3.5).
    public var engineStatus: URL { data.appending(path: "engine.json") }
    public var engineLog: URL { logs.appending(path: "engine.log") }
    public var bandroomLog: URL { logs.appending(path: "bandroom.log") }

    public func ensure() throws {
        for dir in [data, logs] {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
    }
}

/// The name people know this Mac by (System Settings › General › About), e.g. "Kalli's MacBook".
public enum ComputerName {
    public static func current() -> String {
        if let name = SCDynamicStoreCopyComputerName(nil, nil) as String?, !name.isEmpty { return name }
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
    }

    /// "Brasscribe on Kalli's MacBook" → "Kalli's MacBook". Norwegian puts the name in its own sentence.
    public static func host(fromServerName name: String) -> String {
        let prefix = "Brasscribe on "
        return name.hasPrefix(prefix) ? String(name.dropFirst(prefix.count)) : name
    }
}

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

    /// A name nobody chose: a serial-like hostname ("DDPW3GWFDK") or Windows' default ("DESKTOP-4F2K9QZ").
    /// Capital letters and digits (and hyphens), at least 8 characters, no spaces, with at least one digit.
    public static func looksMachineGenerated(_ name: String) -> Bool {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard n.count >= 8 else { return false }
        let allowed = n.unicodeScalars.allSatisfy { ("A"..."Z").contains($0) || ("0"..."9").contains($0) || $0 == "-" }
        return allowed && n.unicodeScalars.contains { ("0"..."9").contains($0) }
    }

    /// The name phones see: the one set in Settings › Name shown to phones, else the computer's own.
    public static func shown(system: String, custom: String?) -> String {
        let c = custom?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return c.isEmpty ? system : c
    }

    /// Settings offers its own field only when the computer's name looks machine-made, or one is already set.
    public static func offersCustomName(system: String, custom: String?) -> Bool {
        looksMachineGenerated(system) || !(custom?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
    }

    /// UserDefaults key for the name shown to phones (BRASSCRIBE_COMPUTER_NAME).
    public static let customNameKey = "computerNameShown"

    /// "Brasscribe on Kalli's MacBook" → "Kalli's MacBook". Norwegian puts the name in its own sentence.
    public static func host(fromServerName name: String) -> String {
        let prefix = "Brasscribe on "
        return name.hasPrefix(prefix) ? String(name.dropFirst(prefix.count)) : name
    }
}

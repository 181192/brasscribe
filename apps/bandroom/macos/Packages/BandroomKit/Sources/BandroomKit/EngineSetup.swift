import Darwin
import Foundation

/// Where the engine comes from.
public enum EngineSource: Equatable, Sendable {
    /// A developer checkout of the repository: `pixi run` in it, its models and adapters.
    case checkout(URL)
    /// The workspace Bandroom copies into `<data>/envs` on first run (§5.1 option A).
    case installed(workspace: URL, adapters: URL?)

    public var workspace: URL {
        switch self {
        case .checkout(let url): url
        case .installed(let ws, _): ws
        }
    }

    public var manifest: URL { workspace.appending(path: "pixi.toml") }

    /// Whether `pixi install` has already made the engine environment.
    public var isEnvironmentReady: Bool {
        FileManager.default.fileExists(atPath: workspace.appending(path: ".pixi/envs/default/bin/brasscribe").path)
    }
}

public struct EngineConfiguration: Equatable, Sendable {
    public var source: EngineSource
    public var pixi: URL?
    public var paths: BandroomPaths
    public var computerName: String
    public var adminToken: String
    public var environmentName = "default"
    /// The band sounds the app bundles (`Contents/Resources/band`), passed to the engine for Studio; nil when missing.
    public var bandSounds: URL?

    public init(source: EngineSource, pixi: URL?, paths: BandroomPaths, computerName: String, adminToken: String,
                bandSounds: URL? = nil) {
        self.source = source; self.pixi = pixi; self.paths = paths
        self.computerName = computerName; self.adminToken = adminToken; self.bandSounds = bandSounds
    }

    /// `band/` in the app's resources when it holds the band SoundFont and its part map.
    public static func findBandSounds(resources: URL?) -> URL? {
        guard let dir = resources?.appending(path: "band") else { return nil }
        let fm = FileManager.default
        return ["brasscribe-band.sf2", "mapping.json"].allSatisfy { fm.fileExists(atPath: dir.appending(path: $0).path) } ? dir : nil
    }

    /// Checkout from BRASSCRIBE_CHECKOUT or the "engineCheckout" setting; otherwise the installed workspace.
    public static func resolveSource(environment: [String: String], defaults: UserDefaults, paths: BandroomPaths, bundle: Bundle) -> EngineSource {
        let fromEnv = environment["BRASSCRIBE_CHECKOUT"].flatMap { $0.isEmpty ? nil : $0 }
        let fromSetting = defaults.string(forKey: "engineCheckout").flatMap { $0.isEmpty ? nil : $0 }
        if let path = fromEnv ?? fromSetting {
            return .checkout(URL(fileURLWithPath: (path as NSString).expandingTildeInPath, isDirectory: true))
        }
        let adapters = bundle.resourceURL?.appending(path: "workspace/ml/adapters")
        return .installed(workspace: paths.workspace,
                          adapters: adapters.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil })
    }

    /// The pixi binary: bundled with the app, then the usual install places. A login-item launch gets a bare
    /// PATH, so never rely on PATH lookup.
    public static func findPixi(bundle: Bundle, environment: [String: String]) -> URL? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var candidates: [String] = []
        if let explicit = environment["BRASSCRIBE_PIXI"] { candidates.append(explicit) }
        if let bundled = bundle.url(forAuxiliaryExecutable: "pixi") ?? bundle.resourceURL?.appending(path: "bin/pixi") {
            candidates.append(bundled.path)
        }
        candidates += ["\(home)/.pixi/bin/pixi", "/opt/homebrew/bin/pixi", "/usr/local/bin/pixi"]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }.map { URL(fileURLWithPath: $0) }
    }

    /// Environment for the engine (§5.2). Keeps the variables a GUI app starts with, with a usable PATH.
    public func environment(base: [String: String]) -> [String: String] {
        var env = base.filter { key, _ in
            ["HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "SHELL", "__CF_USER_TEXT_ENCODING", "HF_HOME", "HF_HUB_CACHE", "HF_TOKEN"].contains(key)
        }
        let pixiDir = pixi?.deletingLastPathComponent().path
        env["PATH"] = ([pixiDir].compactMap { $0 } + ["/usr/bin", "/bin", "/usr/sbin", "/sbin", "/opt/homebrew/bin"]).joined(separator: ":")
        env["BRASSCRIBE_DATA"] = paths.data.path
        env["BRASSCRIBE_COMPUTER_NAME"] = computerName
        env["BRASSCRIBE_ADMIN_TOKEN"] = adminToken
        env["PYTHONUNBUFFERED"] = "1"
        env.removeValue(forKey: "BRASSCRIBE_TOKEN")
        if let bandSounds { env["BRASSCRIBE_BAND_SOUNDS_DIR"] = bandSounds.path }
        switch source {
        case .checkout:
            // A checkout brings its own models/ and ml/adapters; the engine finds them from its repo root.
            break
        case .installed(_, let adapters):
            env["BRASSCRIBE_MODELS"] = paths.models.path
            if let adapters { env["BRASSCRIBE_ADAPTERS"] = adapters.path }
            env["PIXI_CACHE_DIR"] = paths.pixiCache.path
        }
        return env
    }

    public func launchPlan(port: Int, base: [String: String]) throws -> LaunchPlan {
        guard let pixi else { throw LaunchFailure.notInstalled("pixi not found") }
        guard FileManager.default.fileExists(atPath: source.manifest.path) else {
            throw LaunchFailure.notInstalled("no workspace at \(source.workspace.path)")
        }
        return LaunchPlan(executable: pixi,
                          arguments: ["run", "--manifest-path", source.manifest.path, "--frozen", "-e", environmentName,
                                      "brasscribe", "serve", "--lan", "--port", String(port)],
                          environment: environment(base: base), workingDirectory: source.workspace,
                          log: paths.engineLog, port: port)
    }

    /// `pixi install` for the engine environment (first run, and after an update).
    public func installPlan(base: [String: String]) throws -> LaunchPlan {
        guard let pixi else { throw LaunchFailure.notInstalled("pixi not found") }
        return LaunchPlan(executable: pixi,
                          arguments: ["install", "--manifest-path", source.manifest.path, "--frozen", "-e", environmentName],
                          environment: environment(base: base), workingDirectory: source.workspace,
                          log: paths.logs.appending(path: "setup.log"), port: 0)
    }
}

public enum PortPicker {
    public static let range = 8765...8775

    /// The first port in 8765–8775 nobody listens on (§5.2). A busy port is skipped silently.
    public static func firstFree(in range: ClosedRange<Int> = range, isFree: (Int) -> Bool = PortPicker.isFree) -> Int? {
        range.first(where: isFree)
    }

    /// Free when the engine's own bind would work and nothing answers on 127.0.0.1, where Bandroom, Studio and
    /// Play on this Mac reach the engine. The bind alone isn't enough: with SO_REUSEADDR a wildcard bind succeeds
    /// on macOS while another program listens on 127.0.0.1 at the same port, which would then get that traffic.
    public static func isFree(_ port: Int) -> Bool {
        canBind(port) && !answersOnLoopback(port)
    }

    /// As the engine's own listener binds, so a port in TIME_WAIT after a restart counts as free.
    static func canBind(_ port: Int) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var one: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, socklen_t(MemoryLayout<Int32>.size))
        var addr = socketAddress(port, INADDR_ANY)
        let rc = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        return rc == 0
    }

    /// Something accepts connections on 127.0.0.1:`port` (waits at most `timeout` for an answer).
    static func answersOnLoopback(_ port: Int, timeout: Int32 = 200) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)
        var addr = socketAddress(port, UInt32(0x7f00_0001).bigEndian)
        let rc = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        if rc == 0 { return true }
        guard errno == EINPROGRESS else { return false }
        var p = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
        guard poll(&p, 1, timeout) == 1 else { return false }
        var err: Int32 = 0
        var len = socklen_t(MemoryLayout<Int32>.size)
        getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len)
        return err == 0
    }

    private static func socketAddress(_ port: Int, _ address: in_addr_t) -> sockaddr_in {
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(UInt16(port).bigEndian)
        addr.sin_addr = in_addr(s_addr: address)
        return addr
    }
}

/// engine.json in the data folder: how Play on the same Mac finds the engine (§3.5).
public struct EngineStatusFile: Codable, Equatable, Sendable {
    public var port: Int
    public var pid: Int32
    public var serverId: String?
    public var version: String?

    enum CodingKeys: String, CodingKey {
        case port, pid, version
        case serverId = "server_id"
    }

    public init(port: Int, pid: Int32, serverId: String?, version: String? = nil) {
        self.port = port; self.pid = pid; self.serverId = serverId; self.version = version
    }

    public static func read(_ url: URL) -> EngineStatusFile? {
        (try? Data(contentsOf: url)).flatMap { try? JSONDecoder().decode(EngineStatusFile.self, from: $0) }
    }

    public func write(_ url: URL) throws {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try enc.encode(self).write(to: url, options: .atomic)
    }

    /// The server id the engine at `state` will answer with, if it has started there before.
    public static func serverId(stateDir: URL) -> String? {
        struct Server: Decodable { var server_id: String }
        return (try? Data(contentsOf: stateDir.appending(path: "server.json")))
            .flatMap { try? JSONDecoder().decode(Server.self, from: $0) }?.server_id
    }
}

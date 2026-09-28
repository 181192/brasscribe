import Foundation

// Wire types of the engine API (engine/openapi.json, docs/plan/pairing-and-remote-access.md §4.8).

public struct Health: Codable, Sendable, Equatable {
    public var status: String
    public var version: String
    public var device: String
    public var authRequired: Bool
    public var serverId: String
    public var serverName: String
    /// Which build is running: the commit and workspace stamp of an installed engine; nil from older engines.
    public var build: String?

    enum CodingKeys: String, CodingKey {
        case status, version, device, build
        case authRequired = "auth_required"
        case serverId = "server_id"
        case serverName = "server_name"
    }

    public init(status: String = "ok", version: String, device: String, authRequired: Bool = false, serverId: String, serverName: String,
                build: String? = nil) {
        self.status = status; self.version = version; self.device = device
        self.authRequired = authRequired; self.serverId = serverId; self.serverName = serverName; self.build = build
    }
}

/// GET /v1/status: what the popover shows at a glance.
public struct EngineStatus: Codable, Sendable, Equatable {
    public var serverId: String
    public var serverName: String
    public var version: String
    public var onlineDevices: Int
    public var pairedDevices: Int
    public var pairingOpen: Bool
    public var jobsRunning: Int
    public var jobsQueued: Int

    enum CodingKeys: String, CodingKey {
        case serverId = "server_id"
        case serverName = "server_name"
        case version
        case onlineDevices = "online_devices"
        case pairedDevices = "paired_devices"
        case pairingOpen = "pairing_open"
        case jobsRunning = "jobs_running"
        case jobsQueued = "jobs_queued"
    }

    public init(serverId: String, serverName: String, version: String, onlineDevices: Int, pairedDevices: Int,
                pairingOpen: Bool, jobsRunning: Int, jobsQueued: Int) {
        self.serverId = serverId; self.serverName = serverName; self.version = version
        self.onlineDevices = onlineDevices; self.pairedDevices = pairedDevices; self.pairingOpen = pairingOpen
        self.jobsRunning = jobsRunning; self.jobsQueued = jobsQueued
    }
}

public struct DeviceInfo: Codable, Sendable, Equatable, Identifiable {
    public var deviceId: String
    public var name: String
    public var platform: String
    public var pairedAt: String
    public var lastSeen: String
    public var rotatedAt: String?
    /// Seen in the last 60 s. Absent on engines that predate presence; then `isOnline(now:)` estimates it.
    public var online: Bool?

    public var id: String { deviceId }

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case name, platform, online
        case pairedAt = "paired_at"
        case lastSeen = "last_seen"
        case rotatedAt = "rotated_at"
    }

    public init(deviceId: String, name: String, platform: String, pairedAt: String, lastSeen: String,
                rotatedAt: String? = nil, online: Bool? = nil) {
        self.deviceId = deviceId; self.name = name; self.platform = platform; self.pairedAt = pairedAt
        self.lastSeen = lastSeen; self.rotatedAt = rotatedAt; self.online = online
    }

    public var lastSeenDate: Date? { ISODate.parse(lastSeen) }
    public var pairedDate: Date? { ISODate.parse(pairedAt) }

    public func isOnline(now: Date = Date()) -> Bool {
        if let online { return online }
        guard let seen = lastSeenDate else { return false }
        return now.timeIntervalSince(seen) <= 60
    }

    public var isTablet: Bool { platform.lowercased().contains("ipad") || name.lowercased().contains("ipad") || name.lowercased().contains("tab") }
}

/// Body of POST /v1/pairing. `ttlSeconds == nil` means "no expiry" and must be sent as an explicit JSON null:
/// a missing key falls back to the engine's 10-minute default.
public struct PairingOpen: Encodable, Sendable, Equatable {
    public var ttlSeconds: Double?
    public var singleUse: Bool
    public var extend: Bool

    public init(ttlSeconds: Double?, singleUse: Bool = true, extend: Bool = false) {
        self.ttlSeconds = ttlSeconds; self.singleUse = singleUse; self.extend = extend
    }

    enum CodingKeys: String, CodingKey {
        case ttlSeconds = "ttl_s"
        case singleUse = "single_use"
        case extend
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        if let ttlSeconds { try c.encode(ttlSeconds, forKey: .ttlSeconds) } else { try c.encodeNil(forKey: .ttlSeconds) }
        try c.encode(singleUse, forKey: .singleUse)
        try c.encode(extend, forKey: .extend)
    }
}

public struct PairingState: Codable, Sendable, Equatable {
    public var open: Bool
    public var code: String?
    public var expiresAt: String?
    public var singleUse: Bool
    public var serverId: String
    public var serverName: String
    public var hosts: [String]
    public var fingerprint: String?
    public var uri: String
    /// Set by engines that report the wrong-code lockout; ISO 8601.
    public var lockedUntil: String?

    enum CodingKeys: String, CodingKey {
        case open, code, hosts, fingerprint, uri
        case expiresAt = "expires_at"
        case singleUse = "single_use"
        case serverId = "server_id"
        case serverName = "server_name"
        case lockedUntil = "locked_until"
    }

    public init(open: Bool, code: String?, expiresAt: String? = nil, singleUse: Bool = true, serverId: String,
                serverName: String, hosts: [String] = [], fingerprint: String? = nil, uri: String, lockedUntil: String? = nil) {
        self.open = open; self.code = code; self.expiresAt = expiresAt; self.singleUse = singleUse
        self.serverId = serverId; self.serverName = serverName; self.hosts = hosts
        self.fingerprint = fingerprint; self.uri = uri; self.lockedUntil = lockedUntil
    }

    /// "482 913": the code as people read it.
    public var displayCode: String? {
        guard let code, code.count == 6 else { return code }
        return "\(code.prefix(3)) \(code.suffix(3))"
    }
}

public struct PairRequestInfo: Codable, Sendable, Equatable, Identifiable {
    public var requestId: String
    public var name: String
    public var platform: String
    public var matchCode: String
    public var createdAt: String
    public var status: String

    public var id: String { requestId }

    enum CodingKeys: String, CodingKey {
        case name, platform, status
        case requestId = "request_id"
        case matchCode = "match_code"
        case createdAt = "created_at"
    }

    public init(requestId: String, name: String, platform: String, matchCode: String, createdAt: String, status: String = "pending") {
        self.requestId = requestId; self.name = name; self.platform = platform
        self.matchCode = matchCode; self.createdAt = createdAt; self.status = status
    }
}

public struct StageState: Codable, Sendable, Equatable {
    public var name: String
    public var kind: String?
    public var status: String
    public var seconds: Double?

    public init(name: String, kind: String?, status: String, seconds: Double? = nil) {
        self.name = name; self.kind = kind; self.status = status; self.seconds = seconds
    }
}

public struct Job: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var profile: String
    public var title: String?
    public var status: String
    public var created: Double
    public var started: Double?
    public var finished: Double?
    public var progress: Double
    public var stages: [StageState]
    /// The phone or tablet that sent the recording, on engines that report it.
    public var deviceName: String?

    enum CodingKeys: String, CodingKey {
        case id, profile, title, status, created, started, finished, progress, stages
        case deviceName = "device_name"
    }

    public init(id: String, profile: String, title: String?, status: String, created: Double, started: Double? = nil,
                finished: Double? = nil, progress: Double, stages: [StageState], deviceName: String? = nil) {
        self.id = id; self.profile = profile; self.title = title; self.status = status; self.created = created
        self.started = started; self.finished = finished; self.progress = progress; self.stages = stages
        self.deviceName = deviceName
    }
}

enum ISODate {
    static func parse(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: s) { return d }
        // Python's isoformat() without a zone: treat as UTC.
        let g = DateFormatter()
        g.locale = Locale(identifier: "en_US_POSIX")
        g.timeZone = TimeZone(identifier: "UTC")
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            g.dateFormat = format
            if let d = g.date(from: s) { return d }
        }
        return nil
    }
}

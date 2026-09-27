import Foundation
import Security

/// The pairing link a computer shows as a QR code:
/// `brasscribe://pair?v=1&id=<server_id>&name=<name>&h=<ip:port>[,<ip:port>]&code=<digits>[&fp=<spki sha256>]`.
public struct PairingLink: Equatable, Sendable {
    public var version: Int
    public var serverID: String
    public var serverName: String
    /// `ip:port` (IPv6 as `[addr]:port`), in the engine's order of preference.
    public var hosts: [String]
    public var code: String?
    public var fingerprint: String?

    public static let supportedVersion = 1

    public init(version: Int = 1, serverID: String, serverName: String, hosts: [String], code: String?, fingerprint: String? = nil) {
        self.version = version; self.serverID = serverID; self.serverName = serverName
        self.hosts = hosts; self.code = code; self.fingerprint = fingerprint
    }

    /// Parses the link from a QR code, a pasted string or an opened URL. Surrounding whitespace is ignored.
    /// Returns nil for anything that is not a version-1 pairing link with a server id and an address.
    public init?(string: String) {
        let text = string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let c = URLComponents(string: text), c.scheme?.lowercased() == "brasscribe",
              (c.host?.lowercased() ?? c.path.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "/"))) == "pair"
        else { return nil }
        var q: [String: String] = [:]
        for item in c.queryItems ?? [] where q[item.name] == nil { q[item.name] = item.value ?? "" }
        guard let v = Int(q["v"] ?? ""), v == Self.supportedVersion,
              let id = q["id"], !id.isEmpty else { return nil }
        let hosts = (q["h"] ?? "").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        guard !hosts.isEmpty else { return nil }
        let code = q["code"].map { $0.filter(\.isNumber) }.flatMap { $0.isEmpty ? nil : $0 }
        self.init(version: v, serverID: id, serverName: q["name"] ?? "", hosts: hosts, code: code,
                  fingerprint: q["fp"].flatMap { $0.isEmpty ? nil : $0 })
    }

    public init?(url: URL) { self.init(string: url.absoluteString) }

    /// Base URLs to try, in order. Plain HTTP until the engine serves TLS.
    public var baseURLs: [URL] { hosts.compactMap { URL(string: "http://\($0)") } }
}

/// What this device remembers about one engine it paired with (docs/plan/pairing-and-remote-access.md §4.5).
/// Only `token` is secret, but the whole record lives in the Keychain.
public struct EngineRecord: Codable, Equatable, Sendable {
    /// The engine's stable id. Empty for a credential moved from the old plain storage, until the
    /// first successful connection tells us which engine it belongs to.
    public var serverID: String
    public var serverName: String
    public var deviceID: String?
    public var token: String?
    public var fingerprint: String?
    public var lastAddress: String
    public var lastOK: Date?
    public var rotateAfter: Date?

    public init(serverID: String, serverName: String, deviceID: String? = nil, token: String?, fingerprint: String? = nil,
                lastAddress: String, lastOK: Date? = nil, rotateAfter: Date? = nil) {
        self.serverID = serverID; self.serverName = serverName; self.deviceID = deviceID; self.token = token
        self.fingerprint = fingerprint; self.lastAddress = lastAddress; self.lastOK = lastOK; self.rotateAfter = rotateAfter
    }

    enum CodingKeys: String, CodingKey {
        case serverID = "server_id", serverName = "server_name", deviceID = "device_id", token, fingerprint
        case lastAddress = "last_address", lastOK = "last_ok", rotateAfter = "rotate_after"
    }

    public var isProvisional: Bool { serverID.isEmpty }
    public var baseURL: URL? { URL(string: lastAddress) }

    /// The computer's own name: "Studio Mac" from "Brasscribe on Studio Mac".
    public var computerName: String { Self.computerName(fromServerName: serverName) }

    /// Also drops the " (2)" an mDNS instance name gains after a name clash.
    public static func computerName(fromServerName name: String) -> String {
        let prefix = "Brasscribe on "
        var n = name.hasPrefix(prefix) ? String(name.dropFirst(prefix.count)) : name
        if let r = n.range(of: #" \(\d+\)$"#, options: .regularExpression) { n.removeSubrange(r) }
        return n
    }

    public func rotationDue(now: Date) -> Bool { rotateAfter.map { now >= $0 } ?? false }
}

// MARK: - storage

/// Where engine credentials are kept: one record per `server_id`.
public protocol CredentialStore: AnyObject, Sendable {
    func all() throws -> [EngineRecord]
    func record(serverID: String) throws -> EngineRecord?
    func save(_ record: EngineRecord) throws
    func delete(serverID: String) throws
}

public enum CredentialStoreError: Error, Equatable, Sendable {
    case keychain(OSStatus)
}

/// Keeps records in memory: tests, screenshots and runs started with `-reset`.
public final class InMemoryCredentialStore: CredentialStore, @unchecked Sendable {
    private var records: [String: EngineRecord] = [:]
    private let lock = NSLock()

    public init(_ initial: [EngineRecord] = []) { for r in initial { records[r.serverID] = r } }

    public func all() throws -> [EngineRecord] { lock.withLock { Array(records.values) } }
    public func record(serverID: String) throws -> EngineRecord? { lock.withLock { records[serverID] } }
    public func save(_ record: EngineRecord) throws { lock.withLock { records[record.serverID] = record } }
    public func delete(serverID: String) throws { lock.withLock { _ = records.removeValue(forKey: serverID) } }
}

/// Generic-password items: service `no.brasscribe.engine`, account = `server_id`, readable after first
/// unlock and never synced or restored to another device.
public final class KeychainCredentialStore: CredentialStore, @unchecked Sendable {
    public static let defaultService = "no.brasscribe.engine"
    /// Account used for a credential moved from the old storage before its engine is known.
    static let provisionalAccount = "unknown"
    public let service: String

    public init(service: String = KeychainCredentialStore.defaultService) { self.service = service }

    private func account(_ serverID: String) -> String { serverID.isEmpty ? Self.provisionalAccount : serverID }

    private func base(_ account: String? = nil) -> [String: Any] {
        var q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service]
        if let account { q[kSecAttrAccount as String] = account }
        return q
    }

    public func all() throws -> [EngineRecord] {
        var q = base()
        q[kSecMatchLimit as String] = kSecMatchLimitAll
        q[kSecReturnAttributes as String] = true
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        if status == errSecItemNotFound { return [] }
        guard status == errSecSuccess else { throw CredentialStoreError.keychain(status) }
        let accounts = (out as? [[String: Any]] ?? []).compactMap { $0[kSecAttrAccount as String] as? String }
        // the legacy macOS keychain can't return data for several items at once, so read them one by one
        return try accounts.compactMap { try read(account: $0) }
    }

    public func record(serverID: String) throws -> EngineRecord? { try read(account: account(serverID)) }

    private func read(account: String) throws -> EngineRecord? {
        var q = base(account)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw CredentialStoreError.keychain(status) }
        return (out as? Data).flatMap { try? JSONDecoder.engine.decode(EngineRecord.self, from: $0) }
    }

    public func save(_ record: EngineRecord) throws {
        let data = try JSONEncoder.engine.encode(record)
        let q = base(account(record.serverID))
        let update: [String: Any] = [kSecValueData as String: data,
                                     kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var status = SecItemUpdate(q as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var add = q
            add.merge(update) { $1 }
            add[kSecAttrLabel as String] = record.serverName.isEmpty ? "Brasscribe" : record.serverName
            status = SecItemAdd(add as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw CredentialStoreError.keychain(status) }
    }

    public func delete(serverID: String) throws {
        let status = SecItemDelete(base(account(serverID)) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw CredentialStoreError.keychain(status) }
    }
}

extension JSONEncoder {
    static var engine: JSONEncoder { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; return e }
}

extension JSONDecoder {
    static var engine: JSONDecoder { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }
}

/// Moves the token older versions kept in UserDefaults (`companionToken`, next to `companionURL`) into
/// the credential store once, then deletes the plain copy. The record stays provisional (no server id)
/// until the first successful connection names its engine.
public enum CredentialMigration {
    public static let tokenKey = "companionToken"
    public static let addressKey = "companionURL"

    /// Returns the migrated record, or nil when there was nothing to move.
    @discardableResult
    public static func run(defaults: UserDefaults, store: CredentialStore, defaultAddress: String = "http://localhost:8765") throws -> EngineRecord? {
        guard let token = defaults.string(forKey: tokenKey) else { return nil }
        guard !token.isEmpty else { defaults.removeObject(forKey: tokenKey); return nil }
        let address = defaults.string(forKey: addressKey) ?? defaultAddress
        // Already moved (a second launch that crashed before the delete): keep what is stored.
        if let existing = try store.all().first(where: { $0.token == token }) {
            defaults.removeObject(forKey: tokenKey)
            return existing
        }
        let record = EngineRecord(serverID: "", serverName: "", token: token, lastAddress: address)
        try store.save(record)
        // only delete the plain copy once the secure one is written
        defaults.removeObject(forKey: tokenKey)
        return record
    }
}

// MARK: - dates from the engine

enum EngineDate {
    /// The engine writes `2026-09-27T12:00:00+00:00`; accept `Z` and fractional seconds too.
    static func parse(_ s: String?) -> Date? {
        guard let s, !s.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s)
    }
}

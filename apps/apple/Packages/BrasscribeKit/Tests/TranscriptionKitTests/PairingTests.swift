import Foundation
import Security
import Testing
@testable import TranscriptionKit

// MARK: pairing link

@Test func pairingLinkFromTheEnginesPayload() throws {
    // as engine/src/brasscribe_engine/companion.py pairing_uri writes it
    let link = try #require(PairingLink(string: "brasscribe://pair?v=1&id=srv-7f3a&name=Brasscribe%20on%20Kari%E2%80%99s%20Mac&h=192.168.0.20:8765,100.64.0.2:8765&code=482913"))
    #expect(link.version == 1)
    #expect(link.serverID == "srv-7f3a")
    #expect(link.serverName == "Brasscribe on Kari’s Mac")
    #expect(link.hosts == ["192.168.0.20:8765", "100.64.0.2:8765"])
    #expect(link.code == "482913")
    #expect(link.fingerprint == nil)
    #expect(link.baseURLs.map(\.absoluteString) == ["http://192.168.0.20:8765", "http://100.64.0.2:8765"])
}

@Test func pairingLinkOptionalPartsAndPastedText() throws {
    let link = try #require(PairingLink(string: "  brasscribe://pair?v=1&id=abc&name=X&h=[fe80::1]:8765&fp=q83vEjRWeJA\n"))
    #expect(link.code == nil)
    #expect(link.fingerprint == "q83vEjRWeJA")
    #expect(link.baseURLs.first?.host() == "fe80::1")
    // a code shown as "482 913" still works
    #expect(PairingLink(string: "brasscribe://pair?v=1&id=a&name=n&h=10.0.0.2:8765&code=482%20913")?.code == "482913")
    #expect(PairingLink(url: URL(string: "brasscribe://pair?v=1&id=a&name=n&h=10.0.0.2:8765")!)?.serverID == "a")
}

@Test func pairingLinkRejectsWhatItCannotUse() {
    #expect(PairingLink(string: "https://pair?v=1&id=a&h=10.0.0.2:8765") == nil)          // other scheme
    #expect(PairingLink(string: "brasscribe://open?v=1&id=a&h=10.0.0.2:8765") == nil)      // other action
    #expect(PairingLink(string: "brasscribe://pair?v=2&id=a&h=10.0.0.2:8765") == nil)      // newer version
    #expect(PairingLink(string: "brasscribe://pair?id=a&h=10.0.0.2:8765") == nil)          // no version
    #expect(PairingLink(string: "brasscribe://pair?v=1&h=10.0.0.2:8765") == nil)           // no server id
    #expect(PairingLink(string: "brasscribe://pair?v=1&id=a&name=n") == nil)               // no address
    #expect(PairingLink(string: "482913") == nil)
    #expect(PairingLink(string: "brasscribe://pair?v=1&id=a&h=203.0.113.9:8765") == nil)    // not on the local network
    #expect(PairingLink(string: "brasscribe://pair?v=1&id=a&h=example.com:8765") == nil)
    #expect(PairingLink(string: "") == nil)
}

// MARK: record and storage

@Test func recordNamesAndRotation() {
    let now = Date()
    var r = EngineRecord(serverID: "s", serverName: "Brasscribe on Studio Mac", token: "t", lastAddress: "http://10.0.0.2:8765")
    #expect(r.computerName == "Studio Mac")
    #expect(EngineRecord.computerName(fromServerName: "Band laptop") == "Band laptop")
    #expect(EngineRecord.computerName(fromServerName: "Brasscribe on Kari's MacBook (2)") == "Kari's MacBook")
    #expect(EngineBrowser.Engine(name: "Brasscribe on Studio (2)").computerName == "Studio")
    #expect(EngineBrowser.Engine(name: "Brasscribe on Studio (2)", host: "Studio Mac").computerName == "Studio Mac")
    #expect(!r.rotationDue(now: now))
    r.rotateAfter = now.addingTimeInterval(-1)
    #expect(r.rotationDue(now: now))
    #expect(!r.isProvisional)
    #expect(EngineRecord(serverID: "", serverName: "", token: "t", lastAddress: "x").isProvisional)
}

@Test func recordRoundTripsAsJSON() throws {
    let r = EngineRecord(serverID: "s", serverName: "Brasscribe on X", deviceID: "d", token: "t", fingerprint: nil,
                         lastAddress: "http://10.0.0.2:8765", lastOK: Date(timeIntervalSince1970: 1_790_000_000),
                         rotateAfter: Date(timeIntervalSince1970: 1_792_000_000))
    let data = try JSONEncoder.engine.encode(r)
    #expect(String(decoding: data, as: UTF8.self).contains(#""server_id":"s""#))
    #expect(try JSONDecoder.engine.decode(EngineRecord.self, from: data) == r)
}

@Test func engineDatesInEveryFormTheEngineWrites() {
    let expected = Date(timeIntervalSince1970: 1_790_000_000)
    #expect(EngineDate.parse("2026-09-21T14:13:20+00:00") == expected)
    #expect(EngineDate.parse("2026-09-21T14:13:20Z") == expected)
    #expect(EngineDate.parse("2026-09-21T14:13:20.000Z") == expected)
    #expect(EngineDate.parse("") == nil)
    #expect(EngineDate.parse(nil) == nil)
}

private func freshDefaults() -> UserDefaults {
    let name = "brasscribe-tests-\(UUID().uuidString)"
    let d = UserDefaults(suiteName: name)!
    d.removePersistentDomain(forName: name)
    return d
}

@Test func migrationMovesThePlainTokenOnceAndDeletesIt() throws {
    let defaults = freshDefaults()
    defaults.set("old-token", forKey: "companionToken")
    defaults.set("http://192.168.0.20:8765", forKey: "companionURL")
    let store = InMemoryCredentialStore()

    let moved = try #require(try CredentialMigration.run(defaults: defaults, store: store))
    #expect(moved.token == "old-token")
    #expect(moved.lastAddress == "http://192.168.0.20:8765")
    #expect(moved.isProvisional)
    #expect(defaults.string(forKey: "companionToken") == nil)
    #expect(try store.all() == [moved])

    // second launch: nothing left to move, the stored record stays
    #expect(try CredentialMigration.run(defaults: defaults, store: store) == nil)
    #expect(try store.all().count == 1)
}

@Test func migrationDoesNotDuplicateAndKeepsThePlainCopyWhenStorageFails() throws {
    let defaults = freshDefaults()
    defaults.set("tok", forKey: "companionToken")
    let known = EngineRecord(serverID: "srv", serverName: "Brasscribe on X", token: "tok", lastAddress: "http://10.0.0.2:8765")
    let store = InMemoryCredentialStore([known])
    #expect(try CredentialMigration.run(defaults: defaults, store: store) == known)
    #expect(try store.all() == [known])
    #expect(defaults.string(forKey: "companionToken") == nil)

    final class Failing: CredentialStore, @unchecked Sendable {
        func all() throws -> [EngineRecord] { [] }
        func record(serverID: String) throws -> EngineRecord? { nil }
        func save(_ record: EngineRecord) throws { throw CredentialStoreError.keychain(errSecNotAvailable) }
        func delete(serverID: String) throws {}
    }
    defaults.set("tok", forKey: "companionToken")
    #expect(throws: CredentialStoreError.self) { try CredentialMigration.run(defaults: defaults, store: Failing()) }
    #expect(defaults.string(forKey: "companionToken") == "tok")

    // no token, or an empty one: nothing to do, and the empty key is cleaned up
    defaults.set("", forKey: "companionToken")
    #expect(try CredentialMigration.run(defaults: defaults, store: store) == nil)
    #expect(defaults.object(forKey: "companionToken") == nil)
}

/// A real Keychain round trip, in a test-only service. Skipped where the test process has no keychain
/// (missing entitlement, or a locked keychain on a build machine).
@Test func keychainStoreRoundTrip() throws {
    let store = KeychainCredentialStore(service: "no.brasscribe.engine.tests.\(UUID().uuidString)")
    let r = EngineRecord(serverID: "srv-kc", serverName: "Brasscribe on Test", deviceID: "d", token: "secret", lastAddress: "http://10.0.0.2:8765")
    do { try store.save(r) } catch CredentialStoreError.keychain(let status) {
        withKnownIssue("keychain unavailable here (\(status))") { throw CredentialStoreError.keychain(status) }
        return
    }
    defer { try? store.delete(serverID: "srv-kc"); try? store.delete(serverID: "") }
    #expect(try store.record(serverID: "srv-kc") == r)
    var updated = r
    updated.token = "rotated"
    try store.save(updated)
    #expect(try store.record(serverID: "srv-kc")?.token == "rotated")
    let provisional = EngineRecord(serverID: "", serverName: "", token: "legacy", lastAddress: "http://localhost:8765")
    try store.save(provisional)
    #expect(Set(try store.all().map(\.token)) == ["rotated", "legacy"])
    try store.delete(serverID: "srv-kc")
    #expect(try store.record(serverID: "srv-kc") == nil)
    #expect(try store.record(serverID: "")?.token == "legacy")
}

// MARK: connection state machine

@Test func connectionHeartbeatsEveryTwentySecondsWhileConnected() {
    var m = ConnectionMachine()
    let t0 = Date()
    #expect(m.state == .offline)
    #expect(m.handle(.start(serverName: "Brasscribe on X"), at: t0) == 0)
    #expect(m.state == .reconnecting(serverName: "Brasscribe on X"))
    #expect(m.handle(.heartbeatOK(serverName: "Brasscribe on X"), at: t0) == 20)
    #expect(m.state == .connected(serverName: "Brasscribe on X"))
    #expect(m.handle(.heartbeatOK(serverName: "Brasscribe on X"), at: t0 + 20) == 20)
    // back in the foreground: still "Connected" while the first check runs
    m.handle(.suspended, at: t0 + 30)
    #expect(m.handle(.start(serverName: "Brasscribe on X"), at: t0 + 300) == 0)
    #expect(m.state == .connected(serverName: "Brasscribe on X"))
}

@Test func connectionBacksOffThenGivesUpAfterTwoMinutes() {
    var m = ConnectionMachine()
    let t0 = Date()
    m.handle(.start(serverName: "B"), at: t0)
    m.handle(.heartbeatOK(serverName: "B"), at: t0)
    var t = t0 + 20
    var delays: [TimeInterval] = []
    var states: [ConnectionState] = []
    while let d = m.handle(.heartbeatFailed, at: t) {
        states.append(m.state)
        delays.append(d)
        t += d
    }
    // one missed heartbeat keeps "Connected"; the second in a row shows "Looking for …"
    #expect(states.first == .connected(serverName: "B"))
    #expect(states.dropFirst().allSatisfy { $0 == .reconnecting(serverName: "B") })
    #expect(Array(delays.prefix(6)) == [2, 4, 8, 16, 30, 30])
    #expect(t.timeIntervalSince(t0 + 20) >= 120)
    #expect(t.timeIntervalSince(t0 + 20) < 125)
    #expect(m.state == .offline)
    // offline stays offline until Connect
    #expect(m.handle(.heartbeatFailed, at: t + 60) == nil)
    #expect(m.handle(.connectRequested(serverName: "B"), at: t + 60) == 0)
    #expect(m.state == .reconnecting(serverName: "B"))
    #expect(m.handle(.heartbeatOK(serverName: "B"), at: t + 61) == 20)
    #expect(m.failingSince == nil && m.attempt == 0)
}

@Test func connectionAsksToPairAgainOnlyOn401() {
    var m = ConnectionMachine()
    let t0 = Date()
    m.handle(.start(serverName: "B"), at: t0)
    m.handle(.heartbeatFailed, at: t0 + 1)
    #expect(m.state == .reconnecting(serverName: "B"))      // unreachable is never "pair again"
    #expect(m.handle(.unauthorized, at: t0 + 2) == nil)
    #expect(m.state == .needsPairing(serverName: "B"))
    // coming back to the foreground doesn't hide it, and failures don't turn it into offline
    #expect(m.handle(.start(serverName: "B"), at: t0 + 3) == nil)
    #expect(m.handle(.heartbeatFailed, at: t0 + 4) == nil)
    #expect(m.state == .needsPairing(serverName: "B"))
    // paired again
    m.handle(.heartbeatOK(serverName: "B"), at: t0 + 5)
    #expect(m.state == .connected(serverName: "B"))
    m.handle(.forgotten, at: t0 + 6)
    #expect(m.state == .offline)
}

@Test func connectionBackoffSequence() {
    #expect((1...7).map(ConnectionMachine.backoff(attempt:)) == [2, 4, 8, 16, 30, 30, 30])
}

@Test(arguments: ["10.0.0.2", "172.16.0.1", "172.31.255.255", "192.168.0.20", "169.254.3.4", "127.0.0.1", "100.64.0.2",
                  "::1", "fe80::1", "fe80::1%en0", "fd7a:115c:a1e0::1", "::ffff:192.168.0.1", "studio.local", "Studio.local.", "localhost"])
func localNetworkHostsAreAccepted(host: String) {
    #expect(PairingLink.isLocalNetwork(host))
}

@Test(arguments: ["8.8.8.8", "172.32.0.1", "192.169.0.1", "100.128.0.1", "203.0.113.9", "2001:db8::1", "::ffff:8.8.8.8",
                  "example.com", "local", ".local", "evil.local.example.com", "134744072", "0x08080808", ""])
func otherHostsAreRefused(host: String) {
    #expect(!PairingLink.isLocalNetwork(host))
}

@Test func onlyTheLocalAddressesOfALinkAreKept() throws {
    let link = try #require(PairingLink(string: "brasscribe://pair?v=1&id=a&name=n&h=203.0.113.9:8765,192.168.0.20:8765,[fe80::1]:8765&code=1"))
    #expect(link.hosts == ["192.168.0.20:8765", "[fe80::1]:8765"])
    #expect(link.displayHost == "192.168.0.20")
}

@Test func anAddressIsCheckedAsItIsConnectedTo() {
    #expect(PairingLink.host(of: "[fe80::1]:8765") == "fe80::1")
    #expect(PairingLink.host(of: "studio.local:8765") == "studio.local")
    // what a URL would connect to is example.com, whatever the text around it says
    #expect(PairingLink.host(of: "example.com#.local:8765") == nil)
    #expect(PairingLink.host(of: "192.168.0.2@example.com:8765") == nil)
    #expect(PairingLink(string: "brasscribe://pair?v=1&id=a&h=example.com%23.local:8765") == nil)
}

import Foundation
import Testing
@testable import BandroomKit

/// Answers requests from a routing table and records them.
final class StubProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var routes: [String: (Int, String)] = [:]
    nonisolated(unsafe) static var seen: [URLRequest] = []
    static let lock = NSLock()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        var req = request
        if req.httpBody == nil, let stream = req.httpBodyStream {
            stream.open()
            var data = Data()
            var buf = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let n = stream.read(&buf, maxLength: buf.count)
                if n <= 0 { break }
                data.append(buf, count: n)
            }
            stream.close()
            req.httpBody = data
        }
        let key = "\(req.httpMethod ?? "GET") \(req.url!.path)"
        let (code, body) = Self.lock.withLock {
            Self.seen.append(req)
            return Self.routes[key] ?? (404, #"{"detail":"Not Found"}"#)
        }
        let resp = HTTPURLResponse(url: req.url!, statusCode: code, httpVersion: "HTTP/1.1",
                                   headerFields: code == 429 ? ["Retry-After": "30"] : [:])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

let pairingJSON = """
{"open":true,"code":"482913","expires_at":null,"single_use":true,"server_id":"3f9c2a7e","server_name":"Brasscribe on Kalli's MacBook","hosts":["192.168.1.20:8765"],"fingerprint":null,"uri":"brasscribe://pair?v=1&id=3f9c2a7e&code=482913"}
"""

@Suite(.serialized) struct EngineClientTests {
    func client(_ routes: [String: (Int, String)]) -> EngineClient {
        StubProtocol.lock.withLock {
            StubProtocol.routes = routes
            StubProtocol.seen = []
        }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        return EngineClient(port: 8765, token: "admin-secret", session: URLSession(configuration: config),
                            now: { Date(timeIntervalSince1970: 1_790_000_000) })
    }

    @Test func decodesTheContractStatus() async throws {
        let c = client(["GET /v1/status": (200, """
        {"server_id":"3f9c2a7e","server_name":"Brasscribe on Kalli's MacBook","version":"0.9.4","online_devices":2,"paired_devices":3,"pairing_open":false,"jobs_running":1,"jobs_queued":1}
        """)])
        let s = try await c.status()
        #expect(s == EngineStatus(serverId: "3f9c2a7e", serverName: "Brasscribe on Kalli's MacBook", version: "0.9.4",
                                  onlineDevices: 2, pairedDevices: 3, pairingOpen: false, jobsRunning: 1, jobsQueued: 1))
    }

    @Test func composesStatusWhenTheEngineHasNoStatusEndpoint() async throws {
        // 2026-09-27T…: one device seen 10 s before "now", one a day ago; online field absent (older engine).
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        let f = ISO8601DateFormatter()
        let recent = f.string(from: now.addingTimeInterval(-10)), old = f.string(from: now.addingTimeInterval(-86400))
        let c = client([
            "GET /v1/health": (200, #"{"status":"ok","version":"0.9.4","device":"mps","auth_required":false,"server_id":"3f9c","server_name":"Brasscribe on Kalli's MacBook"}"#),
            "GET /v1/devices": (200, """
            [{"device_id":"a","name":"Kari's iPhone","platform":"ios","paired_at":"\(old)","last_seen":"\(recent)","rotated_at":null},
             {"device_id":"b","name":"Pixel 9","platform":"android","paired_at":"\(old)","last_seen":"\(old)","rotated_at":null}]
            """),
            "GET /v1/pairing": (200, pairingJSON),
            "GET /v1/jobs": (200, #"[{"id":"j1","profile":"solo","title":"Old Hundredth","status":"running","created":1,"progress":0.5,"stages":[]}]"#),
        ])
        let s = try await c.status()
        #expect(s.onlineDevices == 1)
        #expect(s.pairedDevices == 2)
        #expect(s.pairingOpen)
        #expect(s.jobsRunning == 1)
        #expect(s.serverName == "Brasscribe on Kalli's MacBook")
    }

    @Test func sendsTheAdminBearerOnEveryOwnerEndpoint() async throws {
        let c = client([
            "GET /v1/status": (200, #"{"server_id":"x","server_name":"Brasscribe on M","version":"1","online_devices":0,"paired_devices":0,"pairing_open":false,"jobs_running":0,"jobs_queued":0}"#),
            "GET /v1/devices": (200, "[]"),
            "DELETE /v1/devices/d1": (204, ""),
            "GET /v1/pairing": (200, pairingJSON),
            "POST /v1/pairing": (200, pairingJSON),
            "DELETE /v1/pairing": (200, pairingJSON),
            "GET /v1/pairing/requests": (200, "[]"),
            "POST /v1/pairing/requests/r1/approve": (200, #"{"request_id":"r1","name":"Kari's iPhone","platform":"ios","match_code":"4719","created_at":"","status":"approved"}"#),
            "POST /v1/pairing/requests/r2/deny": (200, #"{"request_id":"r2","name":"x","platform":"ios","match_code":"1111","created_at":"","status":"denied"}"#),
        ])
        _ = try await c.status()
        _ = try await c.devices()
        try await c.removeDevice(id: "d1")
        _ = try await c.pairing()
        _ = try await c.openPairing(PairingOpen(ttlSeconds: nil))
        _ = try await c.closePairing()
        _ = try await c.pairingRequests()
        _ = try await c.decide(requestId: "r1", approve: true)
        _ = try await c.decide(requestId: "r2", approve: false)
        let seen = StubProtocol.lock.withLock { StubProtocol.seen }
        #expect(seen.count == 9)
        for r in seen {
            #expect(r.value(forHTTPHeaderField: "Authorization") == "Bearer admin-secret", "\(r.url!.path)")
            #expect(r.url?.host == "127.0.0.1")
        }
    }

    @Test func forbiddenIsAnHTTPErrorNotAFallback() async {
        let c = client(["GET /v1/status": (403, #"{"detail":"only on the computer running the engine"}"#)])
        await #expect(throws: EngineError.http(status: 403, retryAfter: nil)) { try await c.status() }
    }

    @Test func unreachableEngine() async {
        let c = EngineClient(port: 1, token: nil)
        await #expect(throws: EngineError.unreachable) { try await c.health() }
    }

    @Test func noExpiryIsSentAsExplicitNull() async throws {
        let c = client(["POST /v1/pairing": (200, pairingJSON)])
        _ = try await c.openPairing(PairingOpen(ttlSeconds: nil, singleUse: true))
        let body = try #require(StubProtocol.lock.withLock { StubProtocol.seen.first?.httpBody })
        let obj = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(obj.keys.contains("ttl_s"))
        #expect(obj["ttl_s"] is NSNull)
        #expect(obj["single_use"] as? Bool == true)
        #expect(obj["extend"] as? Bool == false)
    }

    @Test func extendSendsTheLifetime() throws {
        let data = try JSONEncoder().encode(PairingOpen(ttlSeconds: 600, extend: true))
        let obj = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(obj["ttl_s"] as? Double == 600)
        #expect(obj["extend"] as? Bool == true)
    }

    @Test func decodesDevicesWithAndWithoutOnline() throws {
        let json = """
        [{"device_id":"a","name":"Kari's iPhone","platform":"ios","paired_at":"2026-09-20T10:00:00+00:00","last_seen":"2026-09-27T10:00:00+00:00","rotated_at":null,"online":true},
         {"device_id":"b","name":"Pixel","platform":"android","paired_at":"2026-09-20T10:00:00+00:00","last_seen":"2026-09-20T10:00:00+00:00"}]
        """
        let d = try JSONDecoder().decode([DeviceInfo].self, from: Data(json.utf8))
        #expect(d[0].online == true)
        #expect(d[0].isOnline())
        #expect(d[1].online == nil)
        #expect(!d[1].isOnline())
        #expect(d[1].lastSeenDate != nil)
    }

    @Test func pairingCodeReadsInTwoGroups() throws {
        let s = try JSONDecoder().decode(PairingState.self, from: Data(pairingJSON.utf8))
        #expect(s.displayCode == "482 913")
        #expect(s.expiresAt == nil)
    }
}

@Suite struct AdminTokenTests {
    @Test func createsOwnerOnlyAndReuses() throws {
        let url = tempDir().appending(path: "admin-token")
        let a = try AdminToken.loadOrCreate(at: url)
        #expect(a.count == 64)
        let mode = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? Int
        #expect(mode == 0o600)
        #expect(try AdminToken.loadOrCreate(at: url) == a)
    }

    @Test(arguments: ["", "abc\n"])
    func aFileCutShortIsReplacedOnce(content: String) throws {
        let dir = tempDir()
        let url = dir.appending(path: "admin-token")
        FileManager.default.createFile(atPath: url.path, contents: Data(content.utf8), attributes: [.posixPermissions: 0o600])
        let a = try AdminToken.loadOrCreate(at: url)
        #expect(a.count == 64)
        #expect(try AdminToken.loadOrCreate(at: url) == a, "the new one was kept")
        let mode = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? Int
        #expect(mode == 0o600)
        #expect(try FileManager.default.contentsOfDirectory(atPath: dir.path) == ["admin-token"], "no temporary file left")
    }

    @Test func narrowsAWidenedFile() throws {
        let url = tempDir().appending(path: "admin-token")
        let a = try AdminToken.loadOrCreate(at: url)
        chmod(url.path, 0o644)
        #expect(try AdminToken.loadOrCreate(at: url) == a)
        let mode = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? Int
        #expect(mode == 0o600)
    }
}

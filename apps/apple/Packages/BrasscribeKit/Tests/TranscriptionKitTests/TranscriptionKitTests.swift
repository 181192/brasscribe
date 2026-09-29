import Foundation
import Testing
import ScoreKit
@testable import TranscriptionKit

func goldenDir() -> URL? {
    if let env = ProcessInfo.processInfo.environment["BRASSCRIBE_FIXTURES"] { return URL(fileURLWithPath: env) }
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let c = dir.appending(path: "data/golden/mikkel-arranged-band")
        if FileManager.default.fileExists(atPath: c.appending(path: "brass-band.musicxml").path) { return c }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

@Test func sseParserHandlesEngineStream() {
    var p = SSEParser()
    let lines = [
        ": keepalive",
        "id: 3", "event: stage", #"data: {"id":3,"run":"r","type":"stage","time":1.0,"status":"ran","stage":"beats","kind":"adapter","fraction":0.25,"device":"mps"}"#, "",
        "id: 4", "event: log", #"data: {"id":4,"run":"r","type":"log","time":1.1,"status":"running","message":"hi"}"#,
        // no blank line: AsyncBytes.lines drops them, so the next id closes the event
        "id: 5", "event: job", #"data: {"id":5,"run":"r","type":"job","time":2,"status":"succeeded"}"#, "",
    ]
    let evs = lines.flatMap { p.feed(line: $0) }
    #expect(evs.map(\.id) == [3, 4, 5])
    #expect(evs[0].fraction == 0.25 && evs[0].stage == "beats" && evs[0].device == "mps")
    #expect(evs[1].message == "hi")
    #expect(evs[2].type == "job" && evs[2].status == "succeeded")

    // progress must not wait for the next event
    var q = SSEParser()
    #expect(q.feed(line: "id: 7").isEmpty)
    #expect(q.feed(line: "event: stage").isEmpty)
    let now = q.feed(line: #"data: {"id":7,"type":"stage","status":"ran","stage":"arrange","fraction":0.9}"#)
    #expect(now.map(\.id) == [7])
    #expect(q.feed(line: ": keepalive").isEmpty)
}

@Test func stagesReadAsPlainSteps() {
    #expect(StageKind.classify(name: "separate-solo", kind: "adapter") == .separating)
    #expect(StageKind.classify(name: "beat-this", kind: nil) == .findingBeat)
    #expect(StageKind.classify(name: "muscriptor", kind: nil) == .transcribing)
    #expect(StageKind.classify(name: "arrange", kind: nil) == .arranging)
    #expect(StageKind.classify(name: "musicxml", kind: nil) == .engraving)
    #expect(StageKind.classify(name: "xyz", kind: nil) == .working)
}

@Test func etaNeedsEvidence() {
    let t0 = Date(timeIntervalSince1970: 0)
    var e = ETAEstimator(start: t0)
    #expect(e.update(fraction: 0.01, now: t0.addingTimeInterval(10)) == nil)
    #expect(e.update(fraction: 0.5, now: t0.addingTimeInterval(1)) == nil)
    let v = e.update(fraction: 0.5, now: t0.addingTimeInterval(20))
    #expect(v == 20)
}

@Test(.enabled(if: goldenDir() != nil)) func fixtureServiceDeliversTheGoldenScore() async throws {
    let svc = FixtureService(directory: goldenDir()!, stepDelay: 0)
    var fractions: [Double] = []
    var result: TranscriptionResult?
    for try await ev in svc.transcribe(.init(audioURL: URL(fileURLWithPath: "/dev/null"), profile: .orchestraWithSoloist)) {
        switch ev {
        case .progress(let p): fractions.append(p.fraction)
        case .finished(let r): result = r
        }
    }
    #expect(fractions == fractions.sorted())
    #expect(fractions.last == 1)
    let r = try #require(result)
    #expect(r.composition?.voices.count == 5)
    #expect(try MusicXMLParser.parse(r.musicXML).parts.count == 18)
    #expect(r.available.isSuperset(of: [.musicXML, .pdf, .composition, .audio]))
    for kind in ArtifactKind.allCases where !r.available.contains(kind) {
        await #expect(throws: TranscriptionError.artifactUnavailable(kind)) { try await svc.artifact(kind, jobID: r.jobID) }
    }
}

// MARK: companion against a stubbed engine

@Test func evidenceComparesModelsAtUncertainNotes() throws {
    let json = """
    {"title":"t","voices":[{"id":"melody","role":"melody","notes":[
      {"pitch":67,"start":24,"dur":24,"confidence":0.5,"onset_s":1.0},
      {"pitch":69,"start":48,"dur":24,"confidence":0.9,"onset_s":2.0}]}],
     "meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0,"mode":"major"}],"ticks_per_beat":24}
    """
    let e = NoteEvidence.build(composition: try Composition.decode(Data(json.utf8)), models: [
        .init(model: "swift-f0", name: "SwiftF0", notes: [.init(onset: 1.02, offset: 1.4, pitch: 67)]),
        .init(model: "basic-pitch", name: "Basic Pitch", notes: [.init(onset: 1.01, offset: 1.4, pitch: 48), .init(onset: 1.03, offset: 1.4, pitch: 69)]),
    ])
    let note = try #require(e.notes.first)
    #expect(e.notes.count == 1 && note.confidence == 0.5)
    #expect(note.models.map(\.pitch) == [67, 69] && note.models.map(\.agrees) == [true, false])
    #expect(note.alternativeShift == 2)
    #expect(e.note(atScoreTick: Score.ticksPerQuarter, concertPitch: 55, ticksPerBeat: 24) == note)
}

final class StubEngine: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var musicXML = Data("<score-partwise/>".utf8)
    /// The bodies of the job uploads, in order (the request's body stream can be read only once).
    nonisolated(unsafe) static var uploads: [String] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        if request.url?.host() == "down.local" {
            client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
            return
        }
        let path = request.url!.path
        let (code, body, type): (Int, Data, String) = {
            switch (request.httpMethod ?? "GET", path) {
            case ("GET", "/v1/health") where request.url?.host() == "loop.local":
                return (200, Data(#"{"status":"ok","version":"1","device":"mps","auth_required":false,"server_id":"srv-local","server_name":"Brasscribe on This Mac"}"#.utf8), "application/json")
            case ("GET", "/v1/health"):
                return (200, Data(#"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-1","server_name":"Brasscribe on Studio"}"#.utf8), "application/json")
            case ("POST", "/v1/pair"):
                return request.bodyStreamData.contains("123456") ? (200, Data(#"{"token":"tok","device_id":"d1","server_id":"srv-1","server_name":"Brasscribe on Studio"}"#.utf8), "application/json") : (403, Data(), "application/json")
            case ("GET", "/v1/devices/me"):
                switch request.value(forHTTPHeaderField: "Authorization") {
                case "Bearer tok", "Bearer tok2":
                    return (200, Data(#"{"device_id":"d1","name":"test","platform":"macos","paired_at":"2026-08-01T10:00:00+00:00","last_seen":"2026-09-27T10:00:00+00:00","server_id":"srv-1","rotate_after":"2026-08-31T10:00:00+00:00","expires_if_idle_after":"2027-01-01T00:00:00+00:00"}"#.utf8), "application/json")
                case nil: return (404, Data(#"{"detail":"this client is not a paired device (loopback or static token)"}"#.utf8), "application/json")
                default: return (401, Data(), "application/json")
                }
            case ("POST", "/v1/devices/me/rotate"):
                return (200, Data(#"{"token":"tok2","device_id":"d1"}"#.utf8), "application/json")
            case ("POST", "/v1/pair/requests"):
                return (202, Data(#"{"request_id":"r1","name":"test","platform":"ios","match_code":"4821","created_at":"2026-09-27T10:00:00+00:00","status":"pending"}"#.utf8), "application/json")
            case ("GET", "/v1/pair/requests/r1"):
                return (200, Data(#"{"status":"approved","token":"tok","device_id":"d1","server_id":"srv-1","server_name":"Brasscribe on Studio"}"#.utf8), "application/json")
            // An engine from before the trumpet seat refuses it (the seat enum), with no refusal code.
            case ("POST", "/v1/jobs/upload") where { Self.uploads.append(request.bodyStreamData); return Self.uploads.last!.contains("\r\n\r\ntrumpet\r\n") }():
                return (422, Data(#"{"detail":[{"loc":["body","seat"],"msg":"Input should be 'soprano-cornet', ..."}]}"#.utf8), "application/json")
            case ("POST", "/v1/jobs/upload"):
                return (200, Data(#"{"id":"j1","profile":"solo","status":"queued","progress":0,"stages":[],"outputs":[],"created":0}"#.utf8), "application/json")
            case ("GET", "/v1/jobs/j1/events"):
                let s = """
                id: 0\nevent: stage\ndata: {"id":0,"run":"j1","type":"stage","time":0,"status":"ran","stage":"separate","fraction":0.5}\n\n\
                : keepalive\n\n\
                id: 1\nevent: job\ndata: {"id":1,"run":"j1","type":"job","time":1,"status":"succeeded"}\n\n
                """
                return (200, Data(s.utf8), "text/event-stream")
            case ("GET", "/v1/jobs/j1"):
                return (200, Data(#"{"id":"j1","profile":"solo","status":"succeeded","progress":1,"stages":[],"outputs":["brass-band.musicxml","brass-band.pdf"],"created":0}"#.utf8), "application/json")
            case ("GET", "/v1/jobs/j1/musicxml"):
                return (200, Self.musicXML, "application/xml")
            case ("GET", "/v1/jobs/j1/braille"):
                return (200, Data("#A BRF".utf8), "text/plain")
            case ("GET", "/v1/jobs/j1/talking-score"):
                return request.url!.query?.contains("format=text") == true ? (200, Data("Bar 1".utf8), "text/plain") : (400, Data(), "text/plain")
            case ("GET", "/v1/jobs"):
                return (200, Data(#"[{"id":"j2","profile":"brass-band","title":"Take","audio_id":"a1","status":"succeeded","progress":1,"stages":[],"outputs":["brass-band.musicxml"],"created":20}]"#.utf8), "application/json")
            case ("GET", "/v1/jobs/j1/evidence"):
                return (200, Data(#"{"models":[{"model":"basic-pitch","name":"Basic Pitch"}],"notes":[{"voice":"melody","start":24,"pitch":67,"confidence":0.5,"onset_s":1.0,"models":[{"model":"basic-pitch","name":"Basic Pitch","pitch":69,"agrees":false}]}]}"#.utf8), "application/json")
            case ("PATCH", "/v1/runs/j1"):
                return request.bodyStreamData.contains("Renamed") ? (200, Data(#"{"id":"j1","profile":"solo","status":"succeeded","progress":1,"stages":[],"outputs":[],"created":0}"#.utf8), "application/json") : (422, Data(), "application/json")
            case ("DELETE", "/v1/runs/j1"):
                return (204, Data(), "application/json")
            default:
                return (404, Data(#"{"detail":"not found"}"#.utf8), "application/json")
            }
        }()
        let resp = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": type])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

extension URLRequest {
    var bodyStreamData: String {
        if let b = httpBody { return String(decoding: b, as: UTF8.self) }
        guard let s = httpBodyStream else { return "" }
        s.open(); defer { s.close() }
        var d = Data(); var buf = [UInt8](repeating: 0, count: 4096)
        while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; d.append(buf, count: n) }
        return String(decoding: d, as: UTF8.self)
    }
}

@Suite(.serialized) struct CompanionTests {
    func service() -> CompanionService {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        return CompanionService(baseURL: URL(string: "http://engine.local:8765")!, session: URLSession(configuration: cfg))
    }

    @Test func pairing() async throws {
        let svc = service()
        await #expect(throws: TranscriptionError.pairingRejected) { try await svc.pair(code: "000000", deviceName: "test", platform: "macos") }
        let t = try await svc.pair(code: "123456", deviceName: "test", platform: "macos").token
        #expect(t == "tok")
        #expect(svc.token == "tok")
    }

    @Test func pairResultCarriesTheEngineIdentity() async throws {
        StubEngine.requests = []
        let r = try await service().pair(code: "123456", deviceName: "Kari's iPhone", platform: "ios")
        #expect(r == .init(token: "tok", deviceID: "d1", serverID: "srv-1", serverName: "Brasscribe on Studio"))
        let body = try #require(StubEngine.requests.first { $0.url?.path == "/v1/pair" }).bodyStreamData
        #expect(body.contains(#""platform":"ios""#))
    }

    @Test func heartbeatRotationAndApproveOnComputer() async throws {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        let session = URLSession(configuration: cfg)
        let base = URL(string: "http://engine.local:8765")!
        let me = try await CompanionService(baseURL: base, token: "tok", session: session).thisDevice()
        #expect(me.serverID == "srv-1" && me.deviceID == "d1")
        #expect(me.rotateAfter == ISO8601DateFormatter().date(from: "2026-08-31T10:00:00Z"))
        await #expect(throws: TranscriptionError.notPaired) { try await CompanionService(baseURL: base, token: "stale", session: session).thisDevice() }
        await #expect(throws: TranscriptionError.http(404, #"{"detail":"this client is not a paired device (loopback or static token)"}"#)) {
            try await CompanionService(baseURL: base, session: session).thisDevice()
        }
        #expect(try await CompanionService(baseURL: base, token: "tok", session: session).rotate() == "tok2")

        let svc = CompanionService(baseURL: base, session: session)
        let req = try await svc.requestPairing(deviceName: "Kari's iPhone", platform: "ios")
        #expect(req.matchCode == "4821" && req.requestID == "r1")
        #expect(try await svc.pollPairing("r1") == .approved(.init(token: "tok", deviceID: "d1", serverID: "srv-1", serverName: "Brasscribe on Studio")))
        #expect(svc.token == "tok")
        #expect(try await svc.pollPairing("gone") == .expired)
    }

    @Test func fullJob() async throws {
        StubEngine.requests = []
        let svc = service()
        try await svc.pair(code: "123456", deviceName: "test", platform: "macos")
        let audio = FileManager.default.temporaryDirectory.appending(path: "a.wav")
        try Data(repeating: 1, count: 3000).write(to: audio)
        var stages: [StageKind] = []
        var done: TranscriptionResult?
        for try await ev in svc.transcribe(.init(audioURL: audio, profile: .solo, title: "t")) {
            switch ev {
            case .progress(let p): stages.append(p.stage)
            case .finished(let r): done = r
            }
        }
        #expect(stages == [.uploading, .separating])
        #expect(done?.jobID == "j1")
        #expect(done?.available == [.musicXML, .pdf])
        #expect(done?.composition == nil)
        let upload = try #require(StubEngine.requests.first { $0.url?.path == "/v1/jobs/upload" })
        #expect(upload.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(upload.value(forHTTPHeaderField: "Content-Type")?.hasPrefix("multipart/form-data; boundary=") == true)
        #expect(try await svc.artifact(.brailleBRF, jobID: "j1") == Data("#A BRF".utf8))
        #expect(try await svc.artifact(.talkingScore, jobID: "j1") == Data("Bar 1".utf8))
    }

    /// An older engine refuses the trumpet seat: the job goes once more as solo-cornet (the same notes).
    @Test func anOlderEngineGetsATrumpetJobAsSoloCornet() async throws {
        StubEngine.requests = []
        StubEngine.uploads = []
        let svc = service()
        try await svc.pair(code: "123456", deviceName: "test", platform: "macos")
        let audio = FileManager.default.temporaryDirectory.appending(path: "t.wav")
        try Data(repeating: 1, count: 3000).write(to: audio)
        var done: TranscriptionResult?
        for try await ev in svc.transcribe(.init(audioURL: audio, profile: .orchestraWithSoloist, title: "t",
                                                  output: OutputChoice(seat: "trumpet", lead: "seat"))) {
            if case .finished(let r) = ev { done = r }
        }
        #expect(done?.jobID == "j1")
        let uploads = StubEngine.uploads
        #expect(uploads.count == 2)
        #expect(uploads.first?.contains("\r\n\r\ntrumpet\r\n") == true)
        #expect(uploads.last?.contains("\r\n\r\nsolo-cornet\r\n") == true && uploads.last?.contains("name=\"lead\"") == false)
    }

    @Test func recentScoresEvidenceAndRunManagement() async throws {
        StubEngine.requests = []
        let svc = service()
        let jobs = try await svc.jobs()
        #expect(jobs.first?.title == "Take" && jobs.first?.audioID == "a1" && jobs.first?.created == 20)
        let e = try await svc.evidence(jobID: "j1")
        #expect(e.notes.first?.confidence == 0.5)
        #expect(e.notes.first?.models.first == .init(model: "basic-pitch", name: "Basic Pitch", pitch: 69, agrees: false))
        try await svc.rename(jobID: "j1", title: "Renamed")
        try await svc.deleteRun(jobID: "j1")
        #expect(StubEngine.requests.contains { $0.httpMethod == "PATCH" && $0.url?.path == "/v1/runs/j1" })
        #expect(StubEngine.requests.contains { $0.httpMethod == "DELETE" && $0.url?.path == "/v1/runs/j1" })
    }

    // MARK: connection monitor against the stub engine

    static let now = ISO8601DateFormatter().date(from: "2026-09-27T12:00:00Z")!

    @MainActor func monitor(_ records: [EngineRecord], found: URL? = nil) -> (ConnectionMonitor, InMemoryCredentialStore) {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        let store = InMemoryCredentialStore(records)
        let m = ConnectionMonitor(store: store, session: URLSession(configuration: cfg), find: { _ in found }, now: { Self.now })
        return (m, store)
    }

    @Test @MainActor func heartbeatConnectsAndRotatesAMonthOldToken() async throws {
        StubEngine.requests = []
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://engine.local:8765")
        let (m, store) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        // rotate_after (2026-08-31) has passed: the new token is stored
        #expect(StubEngine.requests.contains { $0.httpMethod == "POST" && $0.url?.path == "/v1/devices/me/rotate" })
        #expect(try store.record(serverID: "srv-1")?.token == "tok2")
        #expect(try store.record(serverID: "srv-1")?.lastOK == Self.now)
        #expect(m.record?.deviceID == "d1")
    }

    @Test @MainActor func heartbeatFindsTheEngineAtItsNewAddress() async throws {
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://down.local:8765",
                             rotateAfter: Self.now.addingTimeInterval(86_400))
        let (m, store) = monitor([r], found: URL(string: "http://engine.local:9000")!)
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "srv-1")?.lastAddress == "http://engine.local:9000")
        #expect(try store.all().count == 1)   // an address change keeps the same credential record
    }

    @Test @MainActor func heartbeatUnreachableIsReconnectingNotPairAgain() async throws {
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://down.local:8765")
        let (m, store) = monitor([r])
        m.resume(); m.suspend()   // start the machine without a running loop
        #expect(await m.heartbeat() == 2)
        #expect(m.state == .reconnecting(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "srv-1") == r)
    }

    @Test @MainActor func heartbeatAnotherEngineAtTheOldAddressKeepsTheRecord() async throws {
        let r = EngineRecord(serverID: "srv-old", serverName: "Brasscribe on Old", token: "tok", lastAddress: "http://engine.local:8765")
        let (m, store) = monitor([r])
        m.resume(); m.suspend()
        #expect(await m.heartbeat() == 2)
        #expect(m.state == .reconnecting(serverName: "Brasscribe on Old"))
        #expect(try store.record(serverID: "srv-old") == r)
    }

    @Test @MainActor func heartbeat401AsksToPairAgain() async throws {
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "revoked", lastAddress: "http://engine.local:8765")
        let (m, _) = monitor([r])
        m.resume(); m.suspend()
        #expect(await m.heartbeat() == nil)
        #expect(m.state == .needsPairing(serverName: "Brasscribe on Studio"))
    }

    @Test @MainActor func sameComputerConnectsWithoutPairingThroughHealth() async throws {
        StubEngine.requests = []
        let (m, store) = monitor([])
        m.localAddress = URL(string: "http://loop.local:8765")
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on This Mac"))
        #expect(!StubEngine.requests.contains { $0.url?.path == "/v1/devices/me" })
        #expect(try store.all().isEmpty)   // nothing secret to keep
        // an engine elsewhere that wants pairing is not "connected"
        let (m2, _) = monitor([])
        m2.localAddress = URL(string: "http://engine.local:8765")
        #expect(await m2.heartbeat() == nil)
        #expect(m2.state == .offline)
    }

    @Test @MainActor func connectOnThisMacProbesAgainInsteadOfPairing() async throws {
        let (m, _) = monitor([])
        m.localAddress = URL(string: "http://down.local:8765")   // Brasscribe not running yet
        #expect(m.canConnect)
        #expect(await m.heartbeat() == nil)
        #expect(m.state == .offline)
        m.localAddress = URL(string: "http://loop.local:8765")   // now it is
        m.connect(); m.suspend()
        #expect(m.state == .reconnecting(serverName: ""))
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on This Mac"))
        // with neither a paired engine nor one on this computer, Connect means pairing
        let (none, _) = monitor([])
        #expect(!none.canConnect)
    }

    @Test @MainActor func migratedTokenLearnsItsEngineOnFirstContact() async throws {
        let provisional = EngineRecord(serverID: "", serverName: "", token: "tok", lastAddress: "http://engine.local:8765",
                                       rotateAfter: nil)
        let (m, store) = monitor([provisional])
        #expect(m.record == provisional)
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "") == nil)
        #expect(try store.record(serverID: "srv-1")?.serverName == "Brasscribe on Studio")
    }

    @Test @MainActor func pairingFromALinkAndUnpairing() async throws {
        StubEngine.requests = []
        let (m, store) = monitor([])
        let link = try #require(PairingLink(string: "brasscribe://pair?v=1&id=srv-1&name=Brasscribe%20on%20Studio&h=down.local:8765,engine.local:8765&code=123456"))
        #expect(try await m.pair(link: link, deviceName: "Kari's iPhone", platform: "ios") == nil)
        #expect(try store.record(serverID: "srv-1")?.token == "tok")
        #expect(m.record?.lastAddress == "http://engine.local:8765")
        m.suspend()
        // a link without a code: the address to ask for approval at
        let noCode = try #require(PairingLink(string: "brasscribe://pair?v=1&id=srv-1&name=x&h=engine.local:8765"))
        #expect(try await m.pair(link: noCode, deviceName: "x", platform: "ios")?.absoluteString == "http://engine.local:8765")
        // a link for another engine is not paired with whatever answers at the address
        let other = try #require(PairingLink(string: "brasscribe://pair?v=1&id=srv-9&name=x&h=engine.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.self) { try await m.pair(link: other, deviceName: "x", platform: "ios") }

        await m.forget()
        #expect(StubEngine.requests.contains { $0.httpMethod == "DELETE" && $0.url?.path == "/v1/devices/me" })
        #expect(try store.all().isEmpty)
        #expect(m.record == nil && m.state == .offline)
    }
}

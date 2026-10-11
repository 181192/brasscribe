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

@Test func theAppSeesOnlyItsOwnTargetsProfiles() throws {
    let answer = #"""
    [{"name":"solo","target":"brass","pipeline":"layered-solo","description":"d","validated":true,"stages":[]},
     {"name":"tab","target":"fretted","pipeline":"tab","description":"d","validated":false,"stages":[]},
     {"name":"brass-band","target":"brass","pipeline":"A","description":"d","validated":false,"stages":[]}]
    """#
    let own = try CompanionService.ownProfiles(Data(answer.utf8))
    #expect(own.map(\.name) == ["solo", "brass-band"])
    #expect(own.allSatisfy { $0.target == SourceProfile.target })
    // An answer without a target is not this engine's: it is refused, not shown whole.
    #expect(throws: (any Error).self) { try CompanionService.ownProfiles(Data(#"[{"name":"solo","description":"d","validated":true}]"#.utf8)) }
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
    /// Requests that were answered after a delay (a cancelled request is not).
    nonisolated(unsafe) static var answered: [String] = []
    /// The interface version `newer.local` answers with; nil is one above the app's. `older.local` has none, as an
    /// engine from before the number.
    nonisolated(unsafe) static var newerInterface: Int?
    /// A host that does not answer for now, besides `down.local`, which never does.
    nonisolated(unsafe) static var alsoDown: String?
    /// When the engine says this device's token is due for rotation: by default a month before the tests' "now".
    nonisolated(unsafe) static var rotateAfter = "2026-08-31T10:00:00+00:00"
    /// What `odd.local` answers `GET /v1/health` and `GET /v1/devices/me` with.
    nonisolated(unsafe) static var oddAnswer = "{}"

    /// `"interface_version":N` as `host` says it; nothing for `older.local`.
    static func interface(_ host: String?) -> String {
        switch host {
        case "older.local": ""
        case "newer.local": #","interface_version":\#(newerInterface ?? Wire.interfaceVersion + 1)"#
        default: #","interface_version":\#(Wire.interfaceVersion)"#
        }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        let host = request.url?.host()
        if host == "down.local" || (host != nil && host == Self.alsoDown) {
            client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
            return
        }
        let path = request.url!.path
        if request.httpMethod == "POST", path == "/v1/jobs/upload" { Self.uploads.append(request.bodyStreamData) }
        if request.httpMethod == "DELETE", path == "/v1/jobs/j9" {
            // answered a moment later, like a real computer: a request cancelled on the way never gets an answer
            let url = request.url!
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) { [self] in
                guard !stopped else { return }
                Self.answered.append("DELETE \(path)")
                client?.urlProtocol(self, didReceive: HTTPURLResponse(url: url, statusCode: 204, httpVersion: "HTTP/1.1", headerFields: [:])!,
                                    cacheStoragePolicy: .notAllowed)
                client?.urlProtocolDidFinishLoading(self)
            }
            return
        }
        if path == "/v1/jobs/j9/events" {
            // a job that keeps running: the stream opens and nothing more comes
            let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
            return
        }
        let (code, body, type): (Int, Data, String) = {
            switch (request.httpMethod ?? "GET", path) {
            case ("GET", "/v1/health") where host == "odd.local", ("GET", "/v1/devices/me") where host == "odd.local":
                return (200, Data(Self.oddAnswer.utf8), "application/json")
            // refuses every credential, and answers health as `odd.local` does
            case ("GET", "/v1/health") where host == "refusing.local":
                return (200, Data(Self.oddAnswer.utf8), "application/json")
            case ("GET", "/v1/devices/me") where host == "refusing.local":
                return (401, Data(), "application/json")
            case ("GET", "/v1/health") where host == "loop.local":
                return (200, Data(#"{"status":"ok","version":"1","device":"mps","auth_required":false,"server_id":"srv-local","server_name":"Brasscribe on This Mac","interface_version":\#(Wire.interfaceVersion)}"#.utf8), "application/json")
            // another engine than the one the tests pair with: it knows none of their credentials
            case ("GET", "/v1/health") where host == "other.local":
                return (200, Data(#"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-9","server_name":"Brasscribe on Other","interface_version":\#(Wire.interfaceVersion + 1)}"#.utf8), "application/json")
            case ("GET", "/v1/devices/me") where host == "other.local":
                return (401, Data(), "application/json")
            case ("GET", "/v1/health"):
                return (200, Data(#"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-1","server_name":"Brasscribe on Studio"\#(Self.interface(host))}"#.utf8), "application/json")
            case ("POST", "/v1/pair"):
                return request.bodyStreamData.contains("123456") ? (200, Data(#"{"token":"tok","device_id":"d1","server_id":"srv-1","server_name":"Brasscribe on Studio"}"#.utf8), "application/json") : (403, Data(), "application/json")
            case ("GET", "/v1/devices/me"):
                switch request.value(forHTTPHeaderField: "Authorization") {
                case "Bearer tok", "Bearer tok2":
                    return (200, Data(#"{"device_id":"d1","name":"test","platform":"macos","paired_at":"2026-08-01T10:00:00+00:00","last_seen":"2026-09-27T10:00:00+00:00","server_id":"srv-1","rotate_after":"\#(Self.rotateAfter)","expires_if_idle_after":"2027-01-01T00:00:00+00:00"\#(Self.interface(host))}"#.utf8), "application/json")
                case nil: return (404, Data(#"{"detail":"this client is not a paired device (loopback or static token)"}"#.utf8), "application/json")
                default: return (401, Data(), "application/json")
                }
            case ("POST", "/v1/devices/me/rotate"):
                return (200, Data(#"{"token":"tok2","device_id":"d1"}"#.utf8), "application/json")
            case ("POST", "/v1/pair/requests"):
                return (202, Data(#"{"request_id":"r1","name":"test","platform":"ios","match_code":"4821","created_at":"2026-09-27T10:00:00+00:00","status":"pending"}"#.utf8), "application/json")
            case ("GET", "/v1/pair/requests/r1"):
                return (200, Data(#"{"status":"approved","token":"tok","device_id":"d1","server_id":"srv-1","server_name":"Brasscribe on Studio"}"#.utf8), "application/json")
            case ("POST", "/v1/jobs/upload") where Self.uploads.last?.contains("\r\n\r\nslow\r\n") == true:
                return (200, Data(#"{"id":"j9","profile":"solo","status":"running","progress":0,"stages":[],"outputs":[],"created":0}"#.utf8), "application/json")
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
                return (200, Data(#"[{"id":"j2","profile":"brass-band","target":"brass","title":"Take","audio_id":"a1","status":"succeeded","progress":1,"stages":[],"outputs":["brass-band.musicxml"],"created":20},{"id":"t1","profile":"tab","target":"fretted","status":"succeeded","progress":1,"stages":[],"outputs":["tab.musicxml"],"created":30},{"id":"x1","profile":"hymn","target":"choir","status":"succeeded","progress":1,"stages":[],"outputs":[],"created":31},{"id":"n1","profile":"gone","target":null,"status":"succeeded","progress":1,"stages":[],"outputs":[],"created":32}]"#.utf8), "application/json")
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

    nonisolated(unsafe) private var stopped = false
    override func stopLoading() { stopped = true }
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

    /// Stopping a transcription stops the job on the computer too.
    @Test func stoppingATranscriptionCancelsTheJobOnTheComputer() async throws {
        StubEngine.requests = []
        StubEngine.uploads = []
        StubEngine.answered = []
        let svc = service()
        try await svc.pair(code: "123456", deviceName: "test", platform: "macos")
        let audio = FileManager.default.temporaryDirectory.appending(path: "t.wav")
        try Data(repeating: 1, count: 3000).write(to: audio)
        let consumer = Task {
            for try await ev in svc.transcribe(.init(audioURL: audio, profile: .solo, title: "slow")) { _ = ev }
        }
        func seen(_ method: String, _ path: String) -> Bool {
            StubEngine.requests.contains { $0.httpMethod == method && $0.url?.path == path }
        }
        var waited = 0
        while !seen("GET", "/v1/jobs/j9/events"), waited < 500 { try await Task.sleep(for: .milliseconds(10)); waited += 1 }
        #expect(seen("GET", "/v1/jobs/j9/events"))
        consumer.cancel()
        waited = 0
        while !StubEngine.answered.contains("DELETE /v1/jobs/j9"), waited < 500 { try await Task.sleep(for: .milliseconds(10)); waited += 1 }
        #expect(StubEngine.answered.contains("DELETE /v1/jobs/j9"))
    }

    /// The player's seat goes to the engine as it was chosen, once.
    @Test func aTrumpetJobIsSentAsTheTrumpetSeat() async throws {
        StubEngine.requests = []
        StubEngine.uploads = []
        let svc = service()
        try await svc.pair(code: "123456", deviceName: "test", platform: "macos")
        let audio = FileManager.default.temporaryDirectory.appending(path: "t.wav")
        try Data(repeating: 1, count: 3000).write(to: audio)
        for try await _ in svc.transcribe(.init(audioURL: audio, profile: .orchestraWithSoloist, title: "t",
                                                output: OutputChoice(seat: "trumpet", lead: "seat"))) {}
        let uploads = StubEngine.uploads
        #expect(uploads.count == 1)
        #expect(uploads.first?.contains("\r\n\r\ntrumpet\r\n") == true && uploads.first?.contains("name=\"lead\"") == true)
    }

    @Test func recentScoresEvidenceAndRunManagement() async throws {
        StubEngine.requests = []
        let svc = service()
        let jobs = try await svc.jobs()
        // The computer lists a tab, a job of a target this app does not know and one without a target: none is this app's.
        #expect(jobs.map(\.id) == ["j2"])
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
        let link = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=Brasscribe%20on%20Studio&h=down.local:8765,engine.local:8765&code=123456"))
        #expect(try await m.pair(link: link, deviceName: "Kari's iPhone", platform: "ios") == nil)
        #expect(try store.record(serverID: "srv-1")?.token == "tok")
        #expect(m.record?.lastAddress == "http://engine.local:8765")
        m.suspend()
        // a link without a code: the address to ask for approval at
        let noCode = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=engine.local:8765"))
        #expect(try await m.pair(link: noCode, deviceName: "x", platform: "ios")?.absoluteString == "http://engine.local:8765")
        // a link for another engine is not paired with whatever answers at the address
        let other = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-9&name=x&h=engine.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.self) { try await m.pair(link: other, deviceName: "x", platform: "ios") }

        await m.forget()
        #expect(StubEngine.requests.contains { $0.httpMethod == "DELETE" && $0.url?.path == "/v1/devices/me" })
        #expect(try store.all().isEmpty)
        #expect(m.record == nil && m.state == .offline)
    }

    // MARK: an engine with another interface version

    /// What was sent to `host`, as "GET /v1/health".
    func sent(to host: String) -> [String] {
        StubEngine.requests.filter { $0.url?.host() == host }.map { "\($0.httpMethod ?? "GET") \($0.url?.path ?? "")" }
    }

    @Test @MainActor func heartbeatAgainstAnotherInterfaceVersionSaysWhichToUpdateAndAsksNothingElse() async throws {
        StubEngine.requests = []
        StubEngine.newerInterface = nil
        // rotate_after has passed, and still no rotation is asked of this engine
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://newer.local:8765",
                             rotateAfter: Self.now.addingTimeInterval(-86_400))
        let (m, store) = monitor([r], found: URL(string: "http://engine.local:9000")!)
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .mismatch(serverName: "Brasscribe on Studio", update: .app))
        #expect(sent(to: "newer.local") == ["GET /v1/devices/me"])
        // the engine itself answered: it is not looked for elsewhere, and the pairing is kept as it was
        #expect(sent(to: "engine.local").isEmpty)
        #expect(try store.record(serverID: "srv-1") == r)

        let old = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://older.local:8765")
        let (m2, store2) = monitor([old])
        #expect(await m2.heartbeat() == 20)
        #expect(m2.state == .mismatch(serverName: "Brasscribe on Studio", update: .computer))
        #expect(sent(to: "older.local") == ["GET /v1/devices/me"])
        #expect(try store2.record(serverID: "srv-1") == old)
    }

    @Test @MainActor func aComputerUpdatedDuringTheSessionIsFoundAtTheNextHeartbeatAndThePairingIsKept() async throws {
        StubEngine.requests = []
        StubEngine.newerInterface = Wire.interfaceVersion
        defer { StubEngine.newerInterface = nil }
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://newer.local:8765",
                             rotateAfter: Self.now.addingTimeInterval(86_400))
        let (m, store) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        // Bandroom is updated while the app is open
        StubEngine.newerInterface = Wire.interfaceVersion + 1
        StubEngine.requests = []
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .mismatch(serverName: "Brasscribe on Studio", update: .app))
        #expect(sent(to: "newer.local") == ["GET /v1/devices/me"])
        // both up to date again: connected with the same pairing, nothing paired again
        StubEngine.newerInterface = Wire.interfaceVersion
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        #expect(try store.all().map(\.deviceID) == ["d1"])
        #expect(!StubEngine.requests.contains { $0.url?.path == "/v1/pair" })
    }

    @Test @MainActor func pairingWithAnotherInterfaceVersionSendsNoPairRequest() async throws {
        StubEngine.requests = []
        StubEngine.newerInterface = nil
        let (m, store) = monitor([])
        // from a link or QR code, with the code
        let withCode = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=older.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.interfaceMismatch(.computer)) { try await m.pair(link: withCode, deviceName: "x", platform: "ios") }
        // from a link without a code: no address to ask the computer at either
        let noCode = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=newer.local:8765"))
        await #expect(throws: TranscriptionError.interfaceMismatch(.app)) { try await m.pair(link: noCode, deviceName: "x", platform: "ios") }
        // the six digits, and asking the computer to allow this device
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        let session = URLSession(configuration: cfg)
        for (host, update) in [("older.local", InterfaceMatch.Update.computer), ("newer.local", .app)] {
            let base = URL(string: "http://\(host):8765")!
            await #expect(throws: TranscriptionError.interfaceMismatch(update)) {
                try await CompanionService(baseURL: base, session: session).pair(code: "123456", deviceName: "x", platform: "ios")
            }
            await #expect(throws: TranscriptionError.interfaceMismatch(update)) {
                try await CompanionService(baseURL: base, session: session).requestPairing(deviceName: "x", platform: "ios")
            }
            #expect(Set(sent(to: host)) == ["GET /v1/health"])
        }
        #expect(!StubEngine.requests.contains { $0.httpMethod == "POST" })
        #expect(try store.all().isEmpty)
        #expect(m.record == nil && m.state == .offline)
    }

    @Test func noJobIsSentToAnotherInterfaceVersion() async throws {
        StubEngine.requests = []
        StubEngine.uploads = []
        StubEngine.newerInterface = nil
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        let session = URLSession(configuration: cfg)
        let audio = FileManager.default.temporaryDirectory.appending(path: "m.wav")
        try Data(repeating: 1, count: 3000).write(to: audio)
        for (host, update) in [("older.local", InterfaceMatch.Update.computer), ("newer.local", .app)] {
            let svc = CompanionService(baseURL: URL(string: "http://\(host):8765")!, token: "tok", session: session)
            await #expect(throws: TranscriptionError.interfaceMismatch(update)) {
                for try await _ in svc.transcribe(.init(audioURL: audio, profile: .solo, title: "t")) {}
            }
            // nor are its jobs listed or its scores fetched
            await #expect(throws: TranscriptionError.interfaceMismatch(update)) { _ = try await svc.jobs() }
            await #expect(throws: TranscriptionError.interfaceMismatch(update)) { _ = try await svc.artifact(.musicXML, jobID: "j1") }
            #expect(Set(sent(to: host)) == ["GET /v1/health"])
        }
        #expect(StubEngine.uploads.isEmpty)
    }

    /// Health is not asked: the device's own answer says all a heartbeat needs.
    @Test @MainActor func aPairedHeartbeatIsOneRequest() async throws {
        StubEngine.requests = []
        StubEngine.rotateAfter = "2026-12-31T10:00:00+00:00"
        defer { StubEngine.rotateAfter = "2026-08-31T10:00:00+00:00" }
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://engine.local:8765")
        let (m, _) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        #expect(sent(to: "engine.local") == ["GET /v1/devices/me"])
        #expect(await m.heartbeat() == 20)
        #expect(sent(to: "engine.local") == ["GET /v1/devices/me", "GET /v1/devices/me"])
    }

    /// A token due for rotation is rotated through the service the heartbeat used, which knows the engine's
    /// interface version already: health is not asked for it.
    @Test @MainActor func rotationFollowsTheHeartbeatWithoutAskingHealth() async throws {
        StubEngine.requests = []
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://engine.local:8765")
        let (m, store) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(sent(to: "engine.local") == ["GET /v1/devices/me", "POST /v1/devices/me/rotate"])
        #expect(try store.record(serverID: "srv-1")?.token == "tok2")
    }

    /// The computer got a new address and another version at once: the record follows it there, so what the app asks
    /// next gets "update", not "can't reach" from the old address. The credential is as it was.
    @Test @MainActor func aMismatchFoundAtANewAddressMovesTheRecordThere() async throws {
        StubEngine.requests = []
        StubEngine.newerInterface = nil
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://down.local:8765",
                             rotateAfter: Self.now.addingTimeInterval(-86_400))
        let (m, store) = monitor([r], found: URL(string: "http://newer.local:8765")!)
        #expect(m.lastSeen == nil)
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .mismatch(serverName: "Brasscribe on Studio", update: .app))
        var moved = r
        moved.lastAddress = "http://newer.local:8765"
        #expect(m.record == moved)
        #expect(try store.record(serverID: "srv-1") == moved)
        // the computer answered: that is when it was last heard from
        #expect(m.lastSeen == Self.now)
        #expect(sent(to: "newer.local") == ["GET /v1/devices/me"])
    }

    @Test @MainActor func forgettingAComputerWithAnotherInterfaceVersionSendsItNothing() async throws {
        StubEngine.newerInterface = nil
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://older.local:8765")
        let (m, store) = monitor([r])
        await m.heartbeat()
        #expect(m.state.kind == .mismatch)
        StubEngine.requests = []
        await m.forget()
        #expect(sent(to: "older.local").isEmpty)
        #expect(try store.all().isEmpty)
        #expect(m.record == nil && m.state == .offline && m.lastSeen == nil)
    }

    /// Another engine at the old address answers 401 to a credential it never gave: that is "not there", not "pair
    /// again" and not "update", whatever its interface version.
    @Test @MainActor func anotherEngineThatRefusesTheCredentialIsNotPairAgain() async throws {
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://other.local:8765")
        let (m, store) = monitor([r])
        m.resume(); m.suspend()
        #expect(await m.heartbeat() == 2)
        #expect(m.state == .reconnecting(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "srv-1") == r)
    }

    func session() -> URLSession {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        return URLSession(configuration: cfg)
    }

    /// The engine is swapped for another version between two requests: the request that does not get through
    /// forgets what the old one said, and the next asks health again before anything else.
    @Test func afterARequestThatDidNotGetThroughTheInterfaceIsAskedAgain() async throws {
        StubEngine.requests = []
        StubEngine.newerInterface = Wire.interfaceVersion
        defer { StubEngine.newerInterface = nil; StubEngine.alsoDown = nil }
        let svc = CompanionService(baseURL: URL(string: "http://newer.local:8765")!, token: "tok", session: session())
        _ = try await svc.jobs()
        _ = try await svc.jobs()
        #expect(sent(to: "newer.local") == ["GET /v1/health", "GET /v1/jobs", "GET /v1/jobs"])

        StubEngine.alsoDown = "newer.local"
        await #expect(throws: TranscriptionError.self) { _ = try await svc.jobs() }
        StubEngine.alsoDown = nil
        StubEngine.newerInterface = Wire.interfaceVersion + 1
        StubEngine.requests = []
        await #expect(throws: TranscriptionError.interfaceMismatch(.app)) { _ = try await svc.jobs() }
        await #expect(throws: TranscriptionError.interfaceMismatch(.app)) { _ = try await svc.pollPairing("r1") }
        #expect(sent(to: "newer.local") == ["GET /v1/health"])
    }

    /// The same for a job's progress stream that breaks off.
    @Test func afterABrokenStreamTheInterfaceIsAskedAgain() async throws {
        StubEngine.newerInterface = Wire.interfaceVersion
        defer { StubEngine.newerInterface = nil; StubEngine.alsoDown = nil }
        let svc = CompanionService(baseURL: URL(string: "http://newer.local:8765")!, token: "tok", session: session())
        _ = try await svc.job("j1")
        StubEngine.alsoDown = "newer.local"
        await #expect(throws: URLError.self) { for try await _ in svc.events(jobID: "j1", after: -1) {} }
        StubEngine.alsoDown = nil
        StubEngine.newerInterface = Wire.interfaceVersion + 1
        StubEngine.requests = []
        await #expect(throws: TranscriptionError.interfaceMismatch(.app)) { for try await _ in svc.events(jobID: "j1", after: -1) {} }
        #expect(sent(to: "newer.local") == ["GET /v1/health"])
    }

    static let healthBut = #"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-1","server_name":"Brasscribe on Studio""#
    static let deviceBut = #"{"device_id":"d1","name":"test","server_id":"srv-1","rotate_after":"2026-08-31T10:00:00+00:00""#

    /// An interface version that is not a whole number, or one in an answer with other fields missing, is "update",
    /// never "can't reach": the number is read before the rest.
    @Test(arguments: [
        (#","interface_version":1.5}"#, InterfaceMatch.Update.computer), (#","interface_version":true}"#, .computer),
        (#","interface_version":"\#(Wire.interfaceVersion)"}"#, .computer), (#","interface_version":null}"#, .computer),
        (#","interface_version":99999999999999999999}"#, .computer), (#","interface_version":-1}"#, .computer), ("}", .computer),
    ])
    @MainActor func anInterfaceVersionThatIsNotAWholeNumberMeansUpdateTheComputer(tail: String, update: InterfaceMatch.Update) async throws {
        defer { StubEngine.oddAnswer = "{}" }
        // without a credential: health
        StubEngine.oddAnswer = Self.healthBut + tail
        let svc = CompanionService(baseURL: URL(string: "http://odd.local:8765")!, session: session())
        #expect(try await svc.health().interfaceVersion.map { $0 < Wire.interfaceVersion } ?? true)
        await #expect(throws: TranscriptionError.interfaceMismatch(update)) { _ = try await svc.jobs() }
        // paired: the device's own answer
        StubEngine.oddAnswer = Self.deviceBut + tail
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://odd.local:8765")
        let (m, _) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .mismatch(serverName: "Brasscribe on Studio", update: update))
    }

    /// The engine says who it is, and the rest of its answer can't be read: its interface version (or that it has none)
    /// still says which of the two to update.
    @Test(arguments: [(#"{"server_id":"srv-1","interface_version":\#(Wire.interfaceVersion + 1)}"#, InterfaceMatch.Update.app),
                      (#"{"server_id":"srv-1","interface_version":\#(Wire.interfaceVersion + 1),"status":7}"#, .app),
                      (#"{"server_id":"srv-1","interface_version":\#(Wire.interfaceVersion - 1)}"#, .computer),
                      (#"{"server_id":"srv-1"}"#, .computer), (#"{"server_id":"srv-1","status":"ok"}"#, .computer)])
    @MainActor func anAnswerWithFieldsMissingStillSaysWhichToUpdate(body: String, update: InterfaceMatch.Update) async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = body
        StubEngine.requests = []
        let base = URL(string: "http://odd.local:8765")!
        await #expect(throws: TranscriptionError.interfaceMismatch(update)) { _ = try await CompanionService(baseURL: base, session: session()).health() }
        await #expect(throws: TranscriptionError.interfaceMismatch(update)) {
            try await CompanionService(baseURL: base, session: session()).pair(code: "123456", deviceName: "x", platform: "ios")
        }
        #expect(!StubEngine.requests.contains { $0.httpMethod == "POST" })
        // the heartbeat, paired and on the same computer, and pairing from a link
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://odd.local:8765")
        let (m, _) = monitor([r])
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .mismatch(serverName: "Brasscribe on Studio", update: update))
        let (local, _) = monitor([])
        local.localAddress = base
        #expect(await local.heartbeat() == 20)
        #expect(local.state == .mismatch(serverName: "", update: update))
        let link = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=odd.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.interfaceMismatch(update)) { try await m.pair(link: link, deviceName: "x", platform: "ios") }
    }

    /// A 200 that is not an engine's (a network's sign-in page, another program on the port) is nothing reached: never
    /// "update the computer". The network is still searched for the paired engine, and a link's next address is tried.
    @Test(arguments: ["<html><body>Sign in to this network</body></html>", "{}", #"{"status":"ok"}"#, "[]",
                      #"{"interface_version":\#(Wire.interfaceVersion - 1)}"#, #"{"server_id":7,"interface_version":\#(Wire.interfaceVersion + 1)}"#])
    @MainActor func anAnswerThatIsNotAnEnginesIsNothingReached(body: String) async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = body
        StubEngine.requests = []
        let base = URL(string: "http://odd.local:8765")!
        let svc = CompanionService(baseURL: base, session: session())
        await #expect(throws: DecodingError.self) { _ = try await svc.health() }
        // and the next request asks again: "update" is not remembered for it
        await #expect(throws: DecodingError.self) { _ = try await svc.jobs() }
        await #expect(throws: DecodingError.self) {
            try await CompanionService(baseURL: base, session: session()).pair(code: "123456", deviceName: "x", platform: "ios")
        }
        #expect(Set(sent(to: "odd.local")) == ["GET /v1/health"])
        // paired: the engine is looked for by its id, and found at its new address
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://odd.local:8765",
                             rotateAfter: Self.now.addingTimeInterval(86_400))
        let (m, store) = monitor([r], found: URL(string: "http://engine.local:8765")!)
        #expect(await m.heartbeat() == 20)
        #expect(m.state == .connected(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "srv-1")?.lastAddress == "http://engine.local:8765")
        // not found either: looked for again, with the pairing as it was
        let (lost, _) = monitor([r])
        lost.resume(); lost.suspend()
        #expect(await lost.heartbeat() == 2)
        #expect(lost.state == .reconnecting(serverName: "Brasscribe on Studio"))
        // on the same computer: no Brasscribe there
        let (local, _) = monitor([])
        local.localAddress = base
        await local.heartbeat()
        #expect(local.state == .offline)
        // a link: its next address, and with none that is the engine's, "can't reach"
        let (fresh, _) = monitor([])
        let twoAddresses = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=odd.local:8765,engine.local:8765&code=123456"))
        #expect(try await fresh.pair(link: twoAddresses, deviceName: "x", platform: "ios") == nil)
        #expect(fresh.record?.lastAddress == "http://engine.local:8765")
        let (none, _) = monitor([])
        let oneAddress = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=odd.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.unreachable("")) { try await none.pair(link: oneAddress, deviceName: "x", platform: "ios") }
        #expect(!sent(to: "odd.local").contains { $0.hasPrefix("POST") })
    }

    /// Another engine's answer that can't be read in full says nothing about the paired one, or the one a link is for:
    /// it is "not there", whatever its interface version. A typed address has no engine to compare with.
    @Test(arguments: [#"{"server_id":"srv-9"}"#, #"{"server_id":"srv-9","interface_version":\#(Wire.interfaceVersion + 1)}"#])
    @MainActor func anotherEnginesUnreadableAnswerIsNotUpdate(body: String) async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = body
        StubEngine.requests = []
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://odd.local:8765")
        let (m, store) = monitor([r])
        m.resume(); m.suspend()
        #expect(await m.heartbeat() == 2)
        #expect(m.state == .reconnecting(serverName: "Brasscribe on Studio"))
        #expect(try store.record(serverID: "srv-1") == r)
        let link = try #require(PairingLink(string: "scribe://pair?v=1&id=srv-1&name=x&h=odd.local:8765&code=123456"))
        await #expect(throws: TranscriptionError.unreachable("")) { try await m.pair(link: link, deviceName: "x", platform: "ios") }
        await #expect(throws: TranscriptionError.self) {
            try await CompanionService(baseURL: URL(string: "http://odd.local:8765")!, session: session()).pair(code: "123456", deviceName: "x", platform: "ios")
        }
        // (what was sent to this address: other tests post to theirs at the same time)
        #expect(!sent(to: "odd.local").contains { $0.hasPrefix("POST") })
    }

    /// 401 means "pair again" only when health says the engine that refuses the credential is the paired one. With
    /// health not read it is not there; another engine never had the credential; and with another interface version
    /// the update comes first.
    @Test(arguments: [
        ("<html>Sign in</html>", ConnectionState.reconnecting(serverName: "Brasscribe on Studio")),
        ("{}", .reconnecting(serverName: "Brasscribe on Studio")),
        (#"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-9","server_name":"Brasscribe on Other","interface_version":\#(Wire.interfaceVersion)}"#,
         .reconnecting(serverName: "Brasscribe on Studio")),
        (CompanionTests.healthBut + #","interface_version":\#(Wire.interfaceVersion)}"#, .needsPairing(serverName: "Brasscribe on Studio")),
        (CompanionTests.healthBut + "}", .mismatch(serverName: "Brasscribe on Studio", update: .computer)),
        (#"{"server_id":"srv-1","interface_version":\#(Wire.interfaceVersion + 1)}"#, .mismatch(serverName: "Brasscribe on Studio", update: .app)),
    ])
    @MainActor func aRefusedCredentialIsPairAgainOnlyFromThePairedEngine(health: String, state: ConnectionState) async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = health
        StubEngine.requests = []
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://refusing.local:8765")
        let (m, store) = monitor([r])
        m.resume(); m.suspend()
        await m.heartbeat()
        #expect(m.state == state)
        #expect(sent(to: "refusing.local") == ["GET /v1/devices/me", "GET /v1/health"])
        #expect(try store.record(serverID: "srv-1") == r)
    }

    /// The computer's devices were reset: it answers 401 under a new identity, which from here is another computer at
    /// the old address. The paired one is looked for and not found, and after two minutes the row says Not connected,
    /// where the ways to pair are offered again. Nothing is forgotten and nothing is sent to the engine that answers.
    @Test @MainActor func aComputerUnderANewIdentityIsLookedForAndThenNotConnected() async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = #"{"status":"ok","version":"1","device":"cpu","auth_required":true,"server_id":"srv-new","server_name":"Brasscribe on Studio","interface_version":\#(Wire.interfaceVersion)}"#
        StubEngine.requests = []
        let r = EngineRecord(serverID: "srv-1", serverName: "Brasscribe on Studio", token: "tok", lastAddress: "http://refusing.local:8765")
        var clock = Self.now
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubEngine.self]
        let store = InMemoryCredentialStore([r])
        let m = ConnectionMonitor(store: store, session: URLSession(configuration: cfg), find: { _ in nil }, now: { clock })
        m.resume(); m.suspend()
        await m.heartbeat()
        #expect(m.state == .reconnecting(serverName: "Brasscribe on Studio"))
        clock = Self.now.addingTimeInterval(ConnectionMachine.giveUpAfter + 1)
        await m.heartbeat()
        #expect(m.state == .offline)
        #expect(try store.record(serverID: "srv-1") == r)
        #expect(Set(sent(to: "refusing.local")) == ["GET /v1/devices/me", "GET /v1/health"])
    }

    /// An answer that can't be read but carries this app's interface version is a failure, not "update".
    @Test func anUnreadableAnswerWithThisAppsVersionIsNotAMismatch() async throws {
        defer { StubEngine.oddAnswer = "{}" }
        StubEngine.oddAnswer = #"{"server_id":"srv-1","interface_version":\#(Wire.interfaceVersion)}"#
        let svc = CompanionService(baseURL: URL(string: "http://odd.local:8765")!, session: session())
        await #expect(throws: DecodingError.self) { _ = try await svc.health() }
    }
}

let enginesWirePath = "engine/src/scribe_engine/wire.py"

/// The repository this package sits in, found from this file by the engine's `wire.py`; nil outside a checkout of the
/// whole repository.
func repository() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        if FileManager.default.fileExists(atPath: dir.appending(path: enginesWirePath).path) { return dir }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// The tests that read the engine's file are skipped outside a checkout of the whole repository, but never in CI: there
/// a file that has moved fails them.
let enginesWireIsRead = repository() != nil || ProcessInfo.processInfo.environment["CI"] != nil

/// `NAME = value` in the engine's `wire.py`, without the quotes.
func enginesWire(_ name: String) throws -> String {
    let root = try #require(repository(), "\(enginesWirePath) was not found above this file")
    let wire = try String(contentsOf: root.appending(path: enginesWirePath), encoding: .utf8)
    let found = wire.firstMatch(of: try Regex("(?m)^\(name)\\s*=\\s*\"?([^\"\\s#]+)\"?"))?.output[1].substring.map(String.init)
    return try #require(found, "\(name) is not in \(enginesWirePath)")
}

/// The app's wire constants are the engine's: a change to one without the other fails here.
@Test(.enabled(if: enginesWireIsRead)) func theWireConstantsAreTheEngines() throws {
    #expect(try enginesWire("INTERFACE_VERSION") == String(Wire.interfaceVersion))
    #expect(try enginesWire("PAIRING_SCHEME") == Wire.pairScheme)
    #expect(try enginesWire("SERVICE_TYPE") == Wire.serviceType)
}

/// The system reads the link's scheme and the network service from the apps' Info.plist files, not from `Wire`: those,
/// and the project file they are made from, carry the engine's names too.
@Test(.enabled(if: enginesWireIsRead)) func theAppsInfoCarriesTheEnginesNames() throws {
    let scheme = try enginesWire("PAIRING_SCHEME"), service = try enginesWire("SERVICE_TYPE")
    let app = try #require(repository()).appending(path: "apps/apple")
    for name in ["Info-iOS.plist", "Info-macOS.plist"] {
        let data = try Data(contentsOf: app.appending(path: "App/\(name)"))
        let info = try #require(try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any], "\(name)")
        let schemes = (info["CFBundleURLTypes"] as? [[String: Any]] ?? []).flatMap { $0["CFBundleURLSchemes"] as? [String] ?? [] }
        #expect(schemes == [scheme], "\(name)")
        #expect(info["NSBonjourServices"] as? [String] == [service], "\(name)")
    }
    let project = try String(contentsOf: app.appending(path: "project.yml"), encoding: .utf8)
    func lists(_ key: String) throws -> [String] {
        project.matches(of: try Regex("(?m)^\\s*\(key):\\s*\\[([^\\]]*)\\]")).compactMap { $0.output[1].substring }
            .map { $0.trimmingCharacters(in: .whitespaces) }
    }
    #expect(try lists("CFBundleURLSchemes") == [scheme])
    #expect(try lists("NSBonjourServices") == [service])
}

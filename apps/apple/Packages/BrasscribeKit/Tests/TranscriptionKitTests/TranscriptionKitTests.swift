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
    await #expect(throws: TranscriptionError.artifactUnavailable(.brailleBRF)) {
        try await svc.artifact(.brailleBRF, jobID: r.jobID)
    }
}

// MARK: companion against a stubbed engine

final class StubEngine: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var musicXML = Data("<score-partwise/>".utf8)

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        let path = request.url!.path
        let (code, body, type): (Int, Data, String) = {
            switch (request.httpMethod ?? "GET", path) {
            case ("POST", "/v1/pair"):
                return request.bodyStreamData.contains("123456") ? (200, Data(#"{"token":"tok"}"#.utf8), "application/json") : (403, Data(), "application/json")
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
        await #expect(throws: TranscriptionError.pairingRejected) { try await svc.pair(code: "000000", deviceName: "test") }
        let t = try await svc.pair(code: "123456", deviceName: "test")
        #expect(t == "tok")
        #expect(svc.token == "tok")
    }

    @Test func fullJob() async throws {
        StubEngine.requests = []
        let svc = service()
        try await svc.pair(code: "123456", deviceName: "test")
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
}

import Foundation
import ScoreKit

/// Talks to the brasscribe engine running on the musician's own computer
/// (`brasscribe serve --host 0.0.0.0`, default port 8765), per `engine/openapi.json`.
///
/// Pairing: the engine prints a 6-digit code; `pair(code:)` exchanges it for a bearer
/// token. Loopback clients need no token.
public final class CompanionService: TranscriptionService, @unchecked Sendable {
    public let baseURL: URL
    public private(set) var token: String?
    let session: URLSession

    public var displayName: String { baseURL.host() ?? baseURL.absoluteString }

    public init(baseURL: URL, token: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL; self.token = token; self.session = session
    }

    public struct Health: Decodable, Sendable {
        public let status: String
        public let version: String
        public let device: String
        public let authRequired: Bool
        enum CodingKeys: String, CodingKey { case status, version, device; case authRequired = "auth_required" }
    }

    public struct Job: Decodable, Sendable {
        public struct Stage: Decodable, Sendable { public let name: String; public let kind: String?; public let status: String; public let seconds: Double?; public let device: String? }
        public let id: String
        public let status: String
        public let progress: Double
        public let stages: [Stage]
        public let outputs: [String]
        public let error: String?
    }

    public struct ProfileInfo: Decodable, Sendable {
        public let name: String
        public let description: String
        public let validated: Bool
    }

    /// One Server-Sent Event from `/v1/jobs/{id}/events`.
    public struct Event: Decodable, Sendable, Equatable {
        public let id: Int
        public let type: String
        public let status: String
        public let stage: String?
        public let kind: String?
        public let fraction: Double?
        public let device: String?
        public let message: String?
        public let error: String?
    }

    func request(_ path: String, method: String = "GET") -> URLRequest {
        var r = URLRequest(url: baseURL.appending(path: path))
        r.httpMethod = method
        if let token { r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        return r
    }

    func send(_ r: URLRequest) async throws -> Data {
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.data(for: r) } catch { throw TranscriptionError.unreachable(error.localizedDescription) }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw TranscriptionError.notPaired }
        guard (200..<300).contains(code) else { throw TranscriptionError.http(code, String(decoding: data.prefix(300), as: UTF8.self)) }
        return data
    }

    public func health() async throws -> Health {
        try JSONDecoder().decode(Health.self, from: try await send(request("v1/health")))
    }

    public func profiles() async throws -> [ProfileInfo] {
        try JSONDecoder().decode([ProfileInfo].self, from: try await send(request("v1/profiles")))
    }

    /// Exchange the code shown by the engine for a token. Stores and returns it.
    @discardableResult
    public func pair(code: String, deviceName: String) async throws -> String {
        var r = request("v1/pair", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["code": code, "device_name": deviceName])
        do {
            let d = try await send(r)
            let t = try JSONDecoder().decode([String: String].self, from: d)["token"] ?? ""
            token = t
            return t
        } catch TranscriptionError.http(403, _) {
            throw TranscriptionError.pairingRejected
        }
    }

    public func job(_ id: String) async throws -> Job {
        try JSONDecoder().decode(Job.self, from: try await send(request("v1/jobs/\(id)")))
    }

    public func cancel(_ id: String) async {
        _ = try? await send(request("v1/jobs/\(id)", method: "DELETE"))
    }

    /// Multipart upload streamed from a temporary file, so long recordings never sit in memory.
    func upload(_ req: TranscriptionRequest) async throws -> Job {
        let boundary = "brasscribe-\(UUID().uuidString)"
        let tmp = FileManager.default.temporaryDirectory.appending(path: "upload-\(UUID().uuidString)")
        FileManager.default.createFile(atPath: tmp.path, contents: nil)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let h = try FileHandle(forWritingTo: tmp)
        func field(_ name: String, _ value: String) {
            h.write(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("profile", req.profile.rawValue)
        if let t = req.title { field("title", t) }
        field("render_audio", "true")
        // Difficulty is recorded by the engine. Lineup and key make today's engine fail the
        // job, so the app arranges the small band itself and does not send them.
        field("difficulty", req.output.difficulty.rawValue)
        let name = req.audioURL.lastPathComponent.replacingOccurrences(of: "\"", with: "")
        h.write(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(name)\"\r\nContent-Type: application/octet-stream\r\n\r\n".utf8))
        let src = try FileHandle(forReadingFrom: req.audioURL)
        while let chunk = try src.read(upToCount: 1 << 20), !chunk.isEmpty { h.write(chunk) }
        try src.close()
        h.write(Data("\r\n--\(boundary)--\r\n".utf8))
        try h.close()

        var r = request("v1/jobs/upload", method: "POST")
        r.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.upload(for: r, fromFile: tmp) } catch { throw TranscriptionError.unreachable(error.localizedDescription) }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw TranscriptionError.notPaired }
        guard (200..<300).contains(code) else { throw TranscriptionError.http(code, String(decoding: data.prefix(300), as: UTF8.self)) }
        return try JSONDecoder().decode(Job.self, from: data)
    }

    public func transcribe(_ req: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var jobID: String?
                do {
                    continuation.yield(.progress(.init(stage: .uploading, fraction: 0, etaSeconds: nil)))
                    let job = try await upload(req)
                    jobID = job.id
                    var eta = ETAEstimator()
                    var lastID = -1
                    var terminal: Event?
                    var attempts = 0
                    while terminal == nil {
                        do {
                            for try await ev in events(jobID: job.id, after: lastID) {
                                lastID = ev.id
                                if ev.type == "job", ["succeeded", "failed", "cancelled"].contains(ev.status) { terminal = ev; break }
                                if ev.type == "stage" {
                                    let f = ev.fraction ?? 0
                                    continuation.yield(.progress(.init(stage: .classify(name: ev.stage, kind: ev.kind), stageName: ev.stage,
                                                                       fraction: f, etaSeconds: eta.update(fraction: f), device: ev.device)))
                                }
                            }
                        } catch is CancellationError {
                            throw CancellationError()
                        } catch {
                            attempts += 1
                            if attempts > 3 { throw error }
                            try await Task.sleep(for: .seconds(1))
                        }
                        if terminal == nil {
                            // stream ended without a terminal event: ask for the job state
                            let j = try await self.job(job.id)
                            if ["succeeded", "failed", "cancelled"].contains(j.status) {
                                terminal = Event(id: lastID, type: "job", status: j.status, stage: nil, kind: nil, fraction: 1,
                                                 device: nil, message: nil, error: j.error)
                            }
                        }
                    }
                    switch terminal!.status {
                    case "succeeded": break
                    case "cancelled": throw TranscriptionError.cancelled
                    default: throw TranscriptionError.jobFailed(terminal?.error ?? "unknown error")
                    }
                    let final = try await self.job(job.id)
                    let names = Set(final.outputs)
                    let available = Set(ArtifactKind.allCases.filter { names.contains($0.engineName) })
                    let xml = try await artifact(.musicXML, jobID: job.id)
                    let comp = try? Composition.decode(try await artifact(.composition, jobID: job.id))
                    continuation.yield(.finished(.init(jobID: job.id, composition: comp, musicXML: xml, available: available)))
                    continuation.finish()
                } catch {
                    if let jobID, Task.isCancelled || error is CancellationError { await cancel(jobID) }
                    continuation.finish(throwing: Task.isCancelled ? TranscriptionError.cancelled : error)
                }
            }
            continuation.onTermination = { reason in
                if case .cancelled = reason { task.cancel() }
            }
        }
    }

    /// Parsed SSE stream for a job, resuming after event `after`.
    public func events(jobID: String, after: Int) -> AsyncThrowingStream<Event, Error> {
        var r = request("v1/jobs/\(jobID)/events")
        if after >= 0 { r.setValue(String(after), forHTTPHeaderField: "Last-Event-ID") }
        r.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        r.timeoutInterval = 60 // heartbeats arrive every 15 s
        let session = self.session
        let req = r
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let (bytes, resp) = try await session.bytes(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200..<300).contains(code) else { throw TranscriptionError.http(code, "events") }
                    var parser = SSEParser()
                    for try await line in bytes.lines {
                        for ev in parser.feed(line: line) { continuation.yield(ev) }
                    }
                    for ev in parser.feed(line: "") { continuation.yield(ev) }
                    continuation.finish()
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data {
        let typed: [ArtifactKind: String] = [.composition: "composition", .musicXML: "musicxml", .pdf: "pdf", .midi: "midi",
                                             .audio: "audio", .brailleBRF: "braille", .talkingScore: "talking-score"]
        let path = typed[kind].map { "v1/jobs/\(jobID)/\($0)" } ?? "v1/jobs/\(jobID)/artifacts/\(kind.engineName)"
        var r = request(path)
        if kind == .talkingScore, var c = URLComponents(url: r.url!, resolvingAgainstBaseURL: false) {
            c.queryItems = [.init(name: "format", value: "text"), .init(name: "lang", value: ScoreLanguage.current.rawValue)]
            r.url = c.url
        }
        do { return try await send(r) } catch TranscriptionError.http(404, _) {
            throw TranscriptionError.artifactUnavailable(kind)
        }
    }
}

/// Incremental Server-Sent Events parser (event/id/data fields, comment lines ignored).
public struct SSEParser: Sendable {
    var data: [String] = []
    var eventType: String?
    var eventID: Int?

    public init() {}

    /// Feed one line (without its newline). Returns events completed by a blank line.
    /// `URLSession.AsyncBytes.lines` drops empty lines, so an `id:` field also closes
    /// the previous event.
    public mutating func feed(line: String) -> [CompanionService.Event] {
        if line.isEmpty { return flush() }
        if line.hasPrefix(":") { return [] }
        let (field, value): (Substring, Substring)
        if let c = line.firstIndex(of: ":") {
            field = line[..<c]
            var v = line[line.index(after: c)...]
            if v.first == " " { v = v.dropFirst() }
            value = v
        } else { field = line[...]; value = "" }
        var out: [CompanionService.Event] = []
        switch field {
        case "id":
            if !data.isEmpty { out = flush() }
            eventID = Int(value)
        case "event":
            if !data.isEmpty { out = flush() }
            eventType = String(value)
        case "data":
            data.append(String(value))
            // The engine sends one JSON object per data line. Emit it now, because
            // AsyncBytes.lines drops the blank line that would otherwise end the event.
            if value.first == "{", value.last == "}",
               (try? JSONSerialization.jsonObject(with: Data(data.joined(separator: "\n").utf8))) != nil {
                out += flush()
            }
        default: break
        }
        return out
    }

    mutating func flush() -> [CompanionService.Event] {
        defer { data = []; eventType = nil; eventID = nil }
        guard !data.isEmpty, let obj = try? JSONSerialization.jsonObject(with: Data(data.joined(separator: "\n").utf8)) as? [String: Any]
        else { return [] }
        let ev = CompanionService.Event(
            id: obj["id"] as? Int ?? eventID ?? -1,
            type: obj["type"] as? String ?? eventType ?? "message",
            status: obj["status"] as? String ?? "",
            stage: obj["stage"] as? String, kind: obj["kind"] as? String,
            fraction: (obj["fraction"] as? NSNumber)?.doubleValue,
            device: obj["device"] as? String, message: obj["message"] as? String, error: obj["error"] as? String)
        return [ev]
    }
}

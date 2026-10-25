import Foundation
import ScoreKit

/// Talks to the scribe engine running on the musician's own computer
/// (`scribe serve --lan`, default port 8765), per `engine/openapi.json`.
///
/// Pairing: the engine prints a 6-digit code; `pair(code:)` exchanges it for a bearer
/// token. Loopback clients need no token.
public final class CompanionService: TranscriptionService, @unchecked Sendable {
    public let baseURL: URL
    public private(set) var token: String?
    let session: URLSession
    private let lock = NSLock()
    private var lastInterface: InterfaceMatch?
    /// What this engine last said about its interface version (`GET /v1/health`, or a paired device's
    /// `GET /v1/devices/me`). Nil until it has answered, and again after a request, stream or upload did not get
    /// through: another engine may answer at this address by then, so the next request asks first.
    private var interface: InterfaceMatch? {
        get { lock.withLock { lastInterface } }
        set { lock.withLock { lastInterface = newValue } }
    }

    public var displayName: String { baseURL.host() ?? baseURL.absoluteString }

    public init(baseURL: URL, token: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL; self.token = token; self.session = session
    }

    /// `interface_version` as an answer carries it. Anything but a whole number reads as none, so the rest of the
    /// answer still decodes and the engine counts as the one to update.
    public struct InterfaceNumber: Decodable, Sendable, Equatable {
        public let value: Int?
        public init(from decoder: Decoder) throws { value = try? decoder.singleValueContainer().decode(Int.self) }
    }

    public struct Health: Decodable, Sendable {
        public let status: String
        public let version: String
        public let device: String
        public let authRequired: Bool
        public let serverID: String
        public let serverName: String
        let interface: InterfaceNumber?
        /// The engine's interface version; nil when it gives none, or one that is not a whole number.
        public var interfaceVersion: Int? { interface?.value }
        enum CodingKeys: String, CodingKey {
            case status, version, device
            case authRequired = "auth_required", serverID = "server_id", serverName = "server_name"
            case interface = "interface_version"
        }
    }

    /// `POST /v1/pair` and an approved `GET /v1/pair/requests/{id}`.
    public struct PairResult: Decodable, Sendable, Equatable {
        public let token: String
        public let deviceID: String
        public let serverID: String
        public let serverName: String
        enum CodingKeys: String, CodingKey {
            case token, deviceID = "device_id", serverID = "server_id", serverName = "server_name"
        }
        public init(token: String, deviceID: String, serverID: String, serverName: String) {
            self.token = token; self.deviceID = deviceID; self.serverID = serverID; self.serverName = serverName
        }
    }

    /// `GET /v1/devices/me`: a paired device's heartbeat. One request says which engine answers, that the stored
    /// credential still works, and the engine's interface version.
    public struct DeviceSelf: Decodable, Sendable, Equatable {
        public let deviceID: String
        public let name: String
        public let serverID: String
        public let rotateAfterText: String?
        public var rotateAfter: Date? { EngineDate.parse(rotateAfterText) }
        let interface: InterfaceNumber?
        /// As `Health.interfaceVersion`.
        public var interfaceVersion: Int? { interface?.value }
        enum CodingKeys: String, CodingKey {
            case deviceID = "device_id", name, serverID = "server_id", rotateAfterText = "rotate_after"
            case interface = "interface_version"
        }
    }

    /// `POST /v1/pair/requests`: ask the computer to allow this device, with a match code on both screens.
    public struct PairingRequest: Decodable, Sendable, Equatable {
        public let requestID: String
        public let matchCode: String
        public let status: String
        enum CodingKeys: String, CodingKey { case requestID = "request_id", matchCode = "match_code", status }
    }

    /// One poll of a pairing request.
    public enum PairingDecision: Equatable, Sendable {
        case pending
        case approved(PairResult)
        case denied
        /// Unknown or older than two minutes.
        case expired
    }

    public struct Job: Decodable, Sendable {
        public struct Stage: Decodable, Sendable { public let name: String; public let kind: String?; public let status: String; public let seconds: Double?; public let device: String? }
        public let id: String
        public let status: String
        public let progress: Double
        public let stages: [Stage]
        public let outputs: [String]
        public let error: String?
        public let profile: String?
        /// The target the job belongs to ("brass", "fretted"); nil when the engine cannot say.
        public let target: String?
        public let title: String?
        public let created: Double?
        public let audioID: String?
        enum CodingKeys: String, CodingKey {
            case id, status, progress, stages, outputs, error, profile, target, title, created
            case audioID = "audio_id"
        }

        /// The job belongs to an app that makes [target]'s output. A job without a target, or of another target,
        /// does not.
        public func belongs(to target: String) -> Bool { self.target == target }
    }

    /// What each transcriber heard at the notes the engine is unsure about.
    public struct Evidence: Codable, Sendable, Equatable {
        public struct Model: Codable, Sendable, Equatable { public let model: String; public let name: String }
        public struct Heard: Codable, Sendable, Equatable {
            public let model: String
            public let name: String
            public let pitch: Int?
            public let agrees: Bool
            public init(model: String, name: String, pitch: Int?, agrees: Bool) {
                self.model = model; self.name = name; self.pitch = pitch; self.agrees = agrees
            }
        }
        public struct Note: Codable, Sendable, Equatable {
            public let voice: String
            public let start: Int
            public let pitch: Int
            public let confidence: Double
            public let onsetS: Double?
            public let models: [Heard]
            enum CodingKeys: String, CodingKey { case voice, start, pitch, confidence, models; case onsetS = "onset_s" }
            public init(voice: String, start: Int, pitch: Int, confidence: Double, onsetS: Double?, models: [Heard]) {
                self.voice = voice; self.start = start; self.pitch = pitch; self.confidence = confidence
                self.onsetS = onsetS; self.models = models
            }
        }
        public let models: [Model]
        public let notes: [Note]
        public init(models: [Model], notes: [Note]) { self.models = models; self.notes = notes }
    }

    public struct ProfileInfo: Decodable, Sendable {
        public let name: String
        /// The target the profile belongs to: what it makes ("brass", "fretted").
        public let target: String
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

    func request(_ path: String, method: String = "GET", timeout: TimeInterval? = nil) -> URLRequest {
        var r = URLRequest(url: baseURL.appending(path: path))
        r.httpMethod = method
        if let timeout { r.timeoutInterval = timeout }
        if let token { r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        return r
    }

    /// Everything but the two requests that say the interface version (`health`, and `thisDevice` for a paired
    /// device) goes through here first: an engine with another interface version than this app's is sent nothing
    /// else. While the engine's version is not known, health is asked first.
    func requireMatch() async throws {
        // decided from the answer just read: a request that fails meanwhile may have cleared the stored one
        let match: InterfaceMatch
        if let known = interface { match = known } else { match = InterfaceMatch.of(engine: try await health(timeout: 5).interfaceVersion) }
        if case .mismatch(let update) = match { throw TranscriptionError.interfaceMismatch(update) }
    }

    func send(_ r: URLRequest) async throws -> Data {
        try await requireMatch()
        return try await sendUnchecked(r)
    }

    private func sendUnchecked(_ r: URLRequest) async throws -> Data {
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.data(for: r) } catch {
            interface = nil
            throw TranscriptionError.unreachable(error.localizedDescription)
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw TranscriptionError.notPaired }
        guard (200..<300).contains(code) else { throw TranscriptionError.http(code, String(decoding: data.prefix(300), as: UTF8.self)) }
        return data
    }

    public func health() async throws -> Health { try await health(timeout: nil) }

    /// The engine's profiles of [target]: the ones an app that makes that target's output can use.
    public func profiles(of target: String) async throws -> [ProfileInfo] {
        try Self.profiles(of: target, in: try await send(request("v1/profiles")))
    }

    /// The profiles of [target] in the engine's answer to `/v1/profiles`. The engine serves every app and lists
    /// the others' profiles too.
    static func profiles(of target: String, in data: Data) throws -> [ProfileInfo] {
        try JSONDecoder().decode([ProfileInfo].self, from: data).filter { $0.target == target }
    }

    /// Exchange the code shown by the engine for this device's own credential.
    @discardableResult
    public func pair(code: String, deviceName: String, platform: String) async throws -> PairResult {
        var r = request("v1/pair", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["code": code, "device_name": deviceName, "platform": platform])
        do {
            let result = try JSONDecoder().decode(PairResult.self, from: try await send(r))
            token = result.token
            return result
        } catch TranscriptionError.http(403, _) {
            throw TranscriptionError.pairingRejected
        } catch TranscriptionError.http(429, _) {
            throw TranscriptionError.pairingRejected
        }
    }

    /// Ask the computer to allow this device without a code. The computer shows the same match code.
    public func requestPairing(deviceName: String, platform: String) async throws -> PairingRequest {
        var r = request("v1/pair/requests", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["device_name": deviceName, "platform": platform])
        return try JSONDecoder().decode(PairingRequest.self, from: try await send(r))
    }

    /// Poll a pairing request. The token comes once, on the first poll after it is allowed.
    public func pollPairing(_ requestID: String) async throws -> PairingDecision {
        struct Poll: Decodable {
            let status: String
            let token: String?
            let device_id: String?
            let server_id: String?
            let server_name: String?
        }
        let p: Poll
        do { p = try JSONDecoder().decode(Poll.self, from: try await send(request("v1/pair/requests/\(requestID)"))) }
        catch TranscriptionError.http(404, _) { return .expired }
        switch p.status {
        case "approved":
            guard let t = p.token, let device = p.device_id, let server = p.server_id, let name = p.server_name else { return .expired }
            token = t
            return .approved(PairResult(token: t, deviceID: device, serverID: server, serverName: name))
        case "denied": return .denied
        default: return .pending
        }
    }

    /// A paired device's heartbeat, sent without asking health first: its answer carries the interface version, which
    /// is noted for `requireMatch`. Throws `.notPaired` on 401, `.http(404, …)` for a client the engine accepts but
    /// not as a paired device (loopback, a static token), and `.interfaceMismatch` as `health(timeout:from:)` does.
    public func thisDevice(timeout: TimeInterval = 5, from serverID: String? = nil) async throws -> DeviceSelf {
        try noteInterface(DeviceSelf.self, in: try await sendUnchecked(request("v1/devices/me", timeout: timeout)), from: serverID)
    }

    /// A new token for this device. Store it before using it: the old one keeps working until then.
    public func rotate() async throws -> String {
        struct Rotated: Decodable { let token: String }
        return try JSONDecoder().decode(Rotated.self, from: try await send(request("v1/devices/me/rotate", method: "POST"))).token
    }

    /// Forget this device on the computer.
    public func unpair() async throws {
        _ = try await send(request("v1/devices/me", method: "DELETE"))
    }

    /// Also notes whether the engine's interface version is this app's (`requireMatch`). `serverID` is the engine the
    /// caller expects at this address (the paired one, or a pairing link's), nil when any engine will do. Throws
    /// `.interfaceMismatch` when the answer can't be read in full, is that engine's and its interface version is not
    /// this app's. An answer that is not an engine's (a network's sign-in page, another program on the port), or is
    /// another engine's, throws as any answer that can't be read: nothing was reached.
    public func health(timeout: TimeInterval?, from serverID: String? = nil) async throws -> Health {
        try noteInterface(Health.self, in: try await sendUnchecked(request("v1/health", timeout: timeout)), from: serverID)
    }

    /// What says an answer is an engine's, and which: both answers that carry the interface version name the engine.
    private struct Identity: Decodable {
        let serverID: String
        let interface: InterfaceNumber?
        enum CodingKeys: String, CodingKey { case serverID = "server_id", interface = "interface_version" }
    }

    /// Reads who answers and `interface_version` on their own before the rest of an answer that carries them. A number
    /// that is not a whole number, or sits in an answer with other fields missing, still says which of the two to
    /// update, but only in an answer of the engine expected (any engine, when `expected` is nil).
    private func noteInterface<T: Decodable>(_ type: T.Type, in data: Data, from expected: String?) throws -> T {
        let engine = (try? JSONDecoder().decode(Identity.self, from: data)).flatMap { expected == nil || $0.serverID == expected ? $0 : nil }
        let match = engine.map { InterfaceMatch.of(engine: $0.interface?.value) }
        interface = match
        do { return try JSONDecoder().decode(T.self, from: data) } catch {
            if case .mismatch(let update) = match { throw TranscriptionError.interfaceMismatch(update) }
            throw error
        }
    }

    public func job(_ id: String) async throws -> Job {
        try JSONDecoder().decode(Job.self, from: try await send(request("v1/jobs/\(id)")))
    }

    public func cancel(_ id: String) async {
        _ = try? await send(request("v1/jobs/\(id)", method: "DELETE"))
    }

    /// The runs of [target] on the computer, newest first. The computer serves every app and lists the
    /// others' runs too.
    public func jobs(of target: String) async throws -> [Job] {
        try JSONDecoder().decode([Job].self, from: try await send(request("v1/jobs"))).filter { $0.belongs(to: target) }
    }

    /// The recording [jobID] was made from, as the computer keeps it, written to [file]: for an app that no
    /// longer has its own copy.
    public func jobInput(jobID: String, into file: URL) async throws {
        try await requireMatch()
        let (tmp, resp): (URL, URLResponse)
        do { (tmp, resp) = try await session.download(for: request("v1/jobs/\(jobID)/input")) } catch {
            interface = nil
            throw TranscriptionError.unreachable(error.localizedDescription)
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw TranscriptionError.notPaired }
        guard (200..<300).contains(code) else { throw TranscriptionError.http(code, "input") }
        try? FileManager.default.removeItem(at: file)
        try FileManager.default.moveItem(at: tmp, to: file)
    }

    public func evidence(jobID: String) async throws -> Evidence {
        try JSONDecoder().decode(Evidence.self, from: try await send(request("v1/jobs/\(jobID)/evidence")))
    }

    public func rename(jobID: String, title: String) async throws {
        var r = request("v1/runs/\(jobID)", method: "PATCH")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["title": title])
        _ = try await send(r)
    }

    public func deleteRun(jobID: String) async throws {
        _ = try await send(request("v1/runs/\(jobID)", method: "DELETE"))
    }

    /// Multipart upload streamed from a temporary file, so long recordings never sit in memory.
    func upload(_ req: TranscriptionRequest) async throws -> Job {
        try await requireMatch()
        let boundary = "scribe-\(UUID().uuidString)"
        let tmp = FileManager.default.temporaryDirectory.appending(path: "upload-\(UUID().uuidString)")
        FileManager.default.createFile(atPath: tmp.path, contents: nil)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let h = try FileHandle(forWritingTo: tmp)
        defer { try? h.close() }
        // the throwing write: the old write(_:) raises an Objective-C exception when the disk is full
        func field(_ name: String, _ value: String) throws {
            try h.write(contentsOf: Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        try field("profile", req.profile)
        if let t = req.title { try field("title", t) }
        // The app renders audio itself; skipping it on the engine avoids an extra MuseScore launch.
        try field("render_audio", "false")
        // The target's own options (engine/openapi.json), as the app chose them.
        for f in req.fields { try field(f.name, f.value) }
        let name = req.audioURL.lastPathComponent.replacingOccurrences(of: "\"", with: "")
        try h.write(contentsOf: Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(name)\"\r\nContent-Type: application/octet-stream\r\n\r\n".utf8))
        let src = try FileHandle(forReadingFrom: req.audioURL)
        defer { try? src.close() }
        while let chunk = try src.read(upToCount: 1 << 20), !chunk.isEmpty { try h.write(contentsOf: chunk) }
        try src.close()
        try h.write(contentsOf: Data("\r\n--\(boundary)--\r\n".utf8))
        try h.close()

        var r = request("v1/jobs/upload", method: "POST")
        r.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.upload(for: r, fromFile: tmp) } catch {
            interface = nil
            throw TranscriptionError.unreachable(error.localizedDescription)
        }
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
                        } catch TranscriptionError.interfaceMismatch(let update) {
                            // the engine was swapped for another version while the job ran: trying again can't help
                            throw TranscriptionError.interfaceMismatch(update)
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
                    let available = ArtifactKind.available(in: names)
                    let xml = try await artifact(.musicXML, jobID: job.id)
                    let comp = try? Composition.decode(try await artifact(.composition, jobID: job.id))
                    let evidence = try? await self.evidence(jobID: job.id)
                    continuation.yield(.finished(.init(jobID: job.id, composition: comp, musicXML: xml, available: available, evidence: evidence)))
                    continuation.finish()
                } catch {
                    if let jobID, Task.isCancelled || error is CancellationError {
                        // from a task of its own: this one is cancelled, and URLSession would not send the request
                        await Task { await self.cancel(jobID) }.value
                    }
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
                    try await self.requireMatch()
                    let (bytes, resp) = try await session.bytes(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200..<300).contains(code) else { throw TranscriptionError.http(code, "events") }
                    var parser = SSEParser()
                    for try await line in bytes.lines {
                        for ev in parser.feed(line: line) { continuation.yield(ev) }
                    }
                    for ev in parser.feed(line: "") { continuation.yield(ev) }
                    continuation.finish()
                } catch {
                    // a stream that did not open or broke off, not one the engine refused or the app stopped
                    if error is URLError, !Task.isCancelled { self.interface = nil }
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data {
        var r = request("v1/jobs/\(jobID)/\(kind.endpoint)")
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

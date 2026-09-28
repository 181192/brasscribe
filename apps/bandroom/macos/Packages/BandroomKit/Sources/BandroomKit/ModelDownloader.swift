import CryptoKit
import Foundation
import Observation

/// Why the model download stopped, each with its own words and fix in the setup window.
public enum DownloadError: Error, Equatable, Sendable {
    /// The band writer needs the user's own Hugging Face key, and there is none.
    case keyMissing
    /// Hugging Face answered 401: the key was deleted, expired or mistyped.
    case keyRefused
    /// Hugging Face answered 403: signed in, but the licence isn't accepted on the model page yet.
    case licenceNotAccepted
    case notEnoughSpace(neededBytes: Int64, freeBytes: Int64)
    /// The finished file isn't what upstream published; it was deleted, so trying again starts it afresh.
    case checksumMismatch(file: String)
    case http(status: Int, file: String)
    case network(String)
    case disk(String)
}

/// Fetches the missing components (ModelCatalog) from their original release URLs into the models folder and
/// the Hugging Face hub cache. Resumable: a stopped or paused file stays as `<name>.part` and continues with an
/// HTTP Range request. Checks the free space first and each file's size and SHA-256 when it's complete.
@MainActor
@Observable
public final class ModelDownloader {
    public enum Phase: Equatable, Sendable {
        case idle
        /// The key and the free space, before any large file.
        case checking
        case downloading
        case paused
        case done
        case failed(DownloadError)
    }

    public private(set) var phase: Phase = .idle
    /// What this run fetches, in catalogue order.
    public private(set) var components: [ModelComponent] = []
    public private(set) var current: ModelComponent?
    public private(set) var finished: Set<ModelComponent> = []
    public private(set) var bytesDone: Int64 = 0
    public private(set) var bytesTotal: Int64 = 0
    /// Smoothed, for "about 12 min left".
    public private(set) var bytesPerSecond: Double = 0
    /// While a finished file's checksum is computed (off the main actor): how far, 0...1. Nil otherwise.
    public private(set) var verifying: Double?

    public var fraction: Double { bytesTotal > 0 ? min(1, Double(bytesDone) / Double(bytesTotal)) : (phase == .done ? 1 : 0) }
    public var minutesLeft: Int? {
        guard phase == .downloading, bytesPerSecond > 0 else { return nil }
        return max(1, Int((Double(bytesTotal - bytesDone) / bytesPerSecond / 60).rounded(.up)))
    }

    /// Called once when a run completes.
    @ObservationIgnored public var onFinished: (() -> Void)?
    @ObservationIgnored public var log: ((String) -> Void)?

    @ObservationIgnored public let models: URL
    @ObservationIgnored public let hub: URL
    @ObservationIgnored private let configuration: URLSessionConfiguration
    @ObservationIgnored private let token: @Sendable () -> String?
    @ObservationIgnored private let freeSpace: @Sendable (URL) -> Int64
    @ObservationIgnored private let catalog: @Sendable (ModelComponent) -> [ModelFile]
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var fetch: FileFetch?
    @ObservationIgnored private var lastSample: (at: Date, bytes: Int64)?
    /// Counts fetches, so progress that arrives late from an earlier file is ignored.
    @ObservationIgnored private var fetchNumber = 0

    /// Head room left on the disk after the downloads: results need space too.
    public static let spareBytes: Int64 = 1_000_000_000

    public init(models: URL, hub: URL, configuration: URLSessionConfiguration = .default,
                token: @escaping @Sendable () -> String?,
                freeSpace: @escaping @Sendable (URL) -> Int64 = { HostSampler.diskFree($0) },
                catalog: @escaping @Sendable (ModelComponent) -> [ModelFile] = { ModelCatalog.files(for: $0) }) {
        self.models = models; self.hub = hub; self.configuration = configuration
        self.token = token; self.freeSpace = freeSpace; self.catalog = catalog
    }

    public var isActive: Bool { phase == .checking || phase == .downloading }

    /// Starts (or continues) fetching `components`; ones already complete are skipped file by file.
    public func start(_ components: [ModelComponent]) {
        guard !isActive else { return }
        self.components = components.sorted()
        finished = []
        bytesTotal = self.components.reduce(0) { total, c in total + catalog(c).reduce(0) { $0 + $1.size } }
        bytesDone = 0
        bytesPerSecond = 0
        verifying = nil
        lastSample = nil
        guard !self.components.isEmpty else { phase = .done; onFinished?(); return }
        phase = .checking
        task = Task { [weak self] in await self?.run() }
    }

    /// Stops the current file where it is; `resume()` continues it.
    public func pause() {
        guard isActive else { return }
        phase = .paused
        verifying = nil
        task?.cancel()
        fetch?.cancel()
    }

    public func resume() {
        guard phase == .paused || { if case .failed = phase { true } else { false } }() else { return }
        phase = .idle
        start(components)
    }

    // MARK: the run

    private func run() async {
        do {
            // A key or licence problem holds back only the band writer: the separators still come.
            var held: DownloadError?
            do {
                try await preflightKey()
            } catch let e as DownloadError {
                held = e
            }
            let fetching = held == nil ? components : components.filter { !$0.needsHuggingFaceKey }
            try checkSpace(fetching)
            phase = .downloading
            for c in fetching {
                current = c
                try await fetchComponent(c)
                finished.insert(c)
            }
            current = nil
            if let held {
                log?("models: band writer held back: \(held)")
                phase = .failed(held)
                return
            }
            bytesDone = bytesTotal
            phase = .done
            log?("models: \(components.map(\.rawValue).joined(separator: ", ")) downloaded")
            onFinished?()
        } catch is CancellationError {
            // Paused: the .part files stay.
        } catch let e as DownloadError {
            guard phase != .paused else { return }
            log?("models: download stopped: \(e)")
            phase = .failed(e)
        } catch {
            guard phase != .paused else { return }
            phase = .failed(.network(error.localizedDescription))
        }
    }

    /// The key and the licence, before any large file, so a refused key or licence shows at once.
    private func preflightKey() async throws {
        if components.contains(where: \.needsHuggingFaceKey) {
            guard let key = token()?.trimmingCharacters(in: .whitespacesAndNewlines), !key.isEmpty else { throw DownloadError.keyMissing }
            var whoami = URLRequest(url: URL(string: "https://\(ModelCatalog.huggingFaceHost)/api/whoami-v2")!)
            whoami.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
            if let status = try await Self.status(of: whoami, configuration: configuration), status == 401 {
                throw DownloadError.keyRefused
            }
            if let file = catalog(.bandWriter).first, !isComplete(file, of: .bandWriter) {
                var head = URLRequest(url: file.url)
                head.httpMethod = "HEAD"
                head.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
                switch try await Self.status(of: head, configuration: configuration) {
                case 401: throw DownloadError.keyRefused
                case 403: throw DownloadError.licenceNotAccepted
                default: break
                }
            }
        }
    }

    /// Needed bytes per volume (the hub cache is usually on the home volume, the models on the data volume).
    func checkSpace(_ components: [ModelComponent]) throws {
        var needed: [String: (root: URL, bytes: Int64)] = [:]
        for c in components {
            let root = rootFolder(c)
            let volume = Self.volumeKey(root)
            for f in catalog(c) where !isComplete(f, of: c) {
                let part = Self.size(of: partURL(f, of: c)) ?? 0
                needed[volume, default: (root, 0)].bytes += max(0, f.size - part)
            }
        }
        for (_, n) in needed where n.bytes > 0 {
            let free = freeSpace(n.root)
            if free < n.bytes + Self.spareBytes { throw DownloadError.notEnoughSpace(neededBytes: n.bytes + Self.spareBytes, freeBytes: free) }
        }
    }

    private func fetchComponent(_ c: ModelComponent) async throws {
        for f in catalog(c) {
            try Task.checkCancellation()
            let before = bytesDone
            if !isComplete(f, of: c) { try await fetchFile(f, of: c) }
            bytesDone = before + f.size
        }
        if case .hub(let repo, let rev) = c.home { try linkSnapshot(c, repo: repo, revision: rev) }
    }

    private func fetchFile(_ f: ModelFile, of c: ModelComponent) async throws {
        let dest = destination(f, of: c), part = partURL(f, of: c)
        let fm = FileManager.default
        do {
            try fm.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
        } catch { throw DownloadError.disk(error.localizedDescription) }
        let already = bytesDone
        fetchNumber += 1
        let number = fetchNumber
        var request = URLRequest(url: f.url)
        if f.url.host == ModelCatalog.huggingFaceHost, let key = token(), !key.isEmpty {
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        }
        // At most four main-actor hops a second, however small the network's chunks.
        let gate = Throttle<Int64>(interval: Self.progressInterval) { [weak self] written in
            Task { @MainActor in self?.progress(already + written, fetch: number) }
        }
        let fetch = FileFetch(request: request, part: part, configuration: configuration) { gate.offer($0) }
        self.fetch = fetch
        defer { self.fetch = nil }
        log?("models: fetching \(f.url.absoluteString)")
        try await withTaskCancellationHandler {
            try await fetch.run()
        } onCancel: { fetch.cancel() }
        try Task.checkCancellation()
        verifying = 0
        defer { verifying = nil }
        try await Self.verify(part, as: f, interval: Self.progressInterval) { [weak self] fraction in
            Task { @MainActor in self?.verified(fraction, fetch: number) }
        }
        do {
            try? fm.removeItem(at: dest)
            try fm.moveItem(at: part, to: dest)
        } catch { throw DownloadError.disk(error.localizedDescription) }
    }

    private func verified(_ fraction: Double, fetch number: Int) {
        guard phase == .downloading, number == fetchNumber, let v = verifying else { return }
        verifying = max(v, fraction)
    }

    private func progress(_ done: Int64, fetch number: Int) {
        guard phase == .downloading, number == fetchNumber, self.fetch != nil else { return }
        bytesDone = min(done, bytesTotal)
        let now = Date()
        if let last = lastSample {
            let dt = now.timeIntervalSince(last.at)
            guard dt >= 0.5 else { return }
            let rate = Double(done - last.bytes) / dt
            if rate >= 0 { bytesPerSecond = bytesPerSecond == 0 ? rate : bytesPerSecond * 0.8 + rate * 0.2 }
        }
        lastSample = (now, done)
    }

    // MARK: files

    private func rootFolder(_ c: ModelComponent) -> URL {
        switch c.home {
        case .models(let folder): models.appending(path: folder, directoryHint: .isDirectory)
        case .hub(let repo, _): ModelCatalog.hubRepoFolder(repo, hub: hub)
        }
    }

    /// Where a finished file lives: `<models>/<folder>/<name>`, or the hub cache's `blobs/<blob>`.
    func destination(_ f: ModelFile, of c: ModelComponent) -> URL {
        switch c.home {
        case .models: rootFolder(c).appending(path: f.name)
        case .hub: rootFolder(c).appending(path: "blobs/\(f.blobName ?? f.name)")
        }
    }

    func partURL(_ f: ModelFile, of c: ModelComponent) -> URL {
        let d = destination(f, of: c)
        return d.deletingLastPathComponent().appending(path: d.lastPathComponent + ".part")
    }

    func isComplete(_ f: ModelFile, of c: ModelComponent) -> Bool {
        ModelCheck.fileMatches(destination(f, of: c), size: f.size)
    }

    /// Size, then SHA-256 or git blob id where upstream publishes them, read on a background thread with
    /// `progress` (0...1) at most once per `interval`. A bad file is deleted; a cancelled check leaves it as it
    /// was, so resuming checks it again.
    nonisolated static func verify(_ part: URL, as f: ModelFile, chunk: Int = 4 << 20, interval: Duration = progressInterval,
                                   progress: @escaping @Sendable (Double) -> Void = { _ in }) async throws {
        let size = Self.size(of: part) ?? -1
        var ok = f.size <= 0 || size == f.size
        if ok, f.sha256 != nil || f.gitBlob != nil {
            let kind: Digest = f.sha256 != nil ? .sha256 : .gitBlob
            let digest: String?
            do {
                digest = try await Self.digest(of: part, kind, chunk: chunk, interval: interval, progress: progress)
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                digest = nil
            }
            ok = digest == (f.sha256 ?? f.gitBlob)
        }
        if !ok {
            try? FileManager.default.removeItem(at: part)
            throw DownloadError.checksumMismatch(file: f.name)
        }
    }

    /// `snapshots/<rev>/<name>` → `../../blobs/<blob>` and `refs/main`, as huggingface_hub writes them.
    private func linkSnapshot(_ c: ModelComponent, repo: String, revision: String) throws {
        let fm = FileManager.default
        let folder = ModelCatalog.hubRepoFolder(repo, hub: hub)
        let snapshot = folder.appending(path: "snapshots/\(revision)", directoryHint: .isDirectory)
        do {
            try fm.createDirectory(at: snapshot, withIntermediateDirectories: true)
            for f in catalog(c) {
                let link = snapshot.appending(path: f.name)
                let target = "../../blobs/\(f.blobName ?? f.name)"
                if (try? fm.destinationOfSymbolicLink(atPath: link.path)) == target { continue }
                try? fm.removeItem(at: link)
                try fm.createSymbolicLink(atPath: link.path, withDestinationPath: target)
            }
            try fm.createDirectory(at: folder.appending(path: "refs"), withIntermediateDirectories: true)
            try Data(revision.utf8).write(to: folder.appending(path: "refs/main"), options: .atomic)
        } catch { throw DownloadError.disk(error.localizedDescription) }
    }

    // MARK: helpers

    nonisolated static func size(of url: URL) -> Int64? {
        (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value
    }

    nonisolated static func volumeKey(_ url: URL) -> String {
        var probe = url
        while !FileManager.default.fileExists(atPath: probe.path), probe.path != "/" { probe.deleteLastPathComponent() }
        if let id = try? probe.resourceValues(forKeys: [.volumeIdentifierKey]).volumeIdentifier { return String(describing: id) }
        return probe.path
    }

    /// How often progress reaches the main actor: four times a second.
    nonisolated static let progressInterval: Duration = .milliseconds(250)

    enum Digest: Sendable {
        case sha256
        /// `git hash-object`: SHA-1 of "blob <size>\0" and the bytes.
        case gitBlob
    }

    /// The file's digest as lowercase hex, computed in a detached task (never on the caller's actor) in
    /// `chunk`-sized reads. Cancelling the caller cancels the read between chunks with CancellationError.
    nonisolated static func digest(of url: URL, _ kind: Digest, chunk: Int = 4 << 20, interval: Duration = progressInterval,
                                   progress: @escaping @Sendable (Double) -> Void = { _ in }) async throws -> String {
        let work = Task.detached(priority: .utility) {
            try hash(url, kind, chunk: chunk, interval: interval, progress: progress)
        }
        return try await withTaskCancellationHandler { try await work.value } onCancel: { work.cancel() }
    }

    /// Synchronous: call it from a background task. Checks for cancellation between chunks.
    nonisolated private static func hash(_ url: URL, _ kind: Digest, chunk: Int = 4 << 20, interval: Duration = .zero,
                                         progress: (Double) -> Void = { _ in }) throws -> String {
        let total = Double(max(1, size(of: url) ?? 0))
        var sha256 = SHA256(), sha1 = Insecure.SHA1()
        if kind == .gitBlob { sha1.update(data: Data("blob \(size(of: url) ?? 0)\u{0}".utf8)) }
        let h = try FileHandle(forReadingFrom: url)
        defer { try? h.close() }
        let clock = ContinuousClock()
        var last: ContinuousClock.Instant?
        var read: Int64 = 0
        while true {
            if Task.isCancelled { throw CancellationError() }
            let more: Bool = try autoreleasepool {
                guard let data = try h.read(upToCount: chunk), !data.isEmpty else { return false }
                switch kind {
                case .sha256: sha256.update(data: data)
                case .gitBlob: sha1.update(data: data)
                }
                read += Int64(data.count)
                return true
            }
            guard more else { break }
            let now = clock.now
            if last.map({ now - $0 >= interval }) ?? true {
                last = now
                progress(min(1, Double(read) / total))
            }
        }
        progress(1)
        let bytes: [UInt8] = kind == .sha256 ? Array(sha256.finalize()) : Array(sha1.finalize())
        return bytes.map { String(format: "%02x", $0) }.joined()
    }

    /// The HTTP status of a request, or nil when the network didn't answer (the download then says so itself).
    nonisolated static func status(of request: URLRequest, configuration: URLSessionConfiguration) async throws -> Int? {
        let session = URLSession(configuration: configuration, delegate: AuthStripping(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        do {
            let (_, response) = try await session.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode
        } catch let e as URLError where e.code == .cancelled {
            throw CancellationError()
        } catch {
            return nil
        }
    }
}

/// Passes on at most one value per `interval`; a value held back goes out when the interval ends, so the
/// last one is never lost (a stalled download still shows where it stopped).
final class Throttle<Value: Sendable>: @unchecked Sendable {
    private let interval: Duration
    private let sink: @Sendable (Value) -> Void
    private let lock = NSLock()
    private let clock = ContinuousClock()
    private var last: ContinuousClock.Instant?
    private var latest: Value?
    private var pending = false

    init(interval: Duration, sink: @escaping @Sendable (Value) -> Void) {
        self.interval = interval; self.sink = sink
    }

    func offer(_ value: Value) {
        lock.lock()
        let now = clock.now
        guard let last, now - last < interval else {
            self.last = now
            latest = nil
            lock.unlock()
            sink(value)
            return
        }
        latest = value
        guard !pending else { lock.unlock(); return }
        pending = true
        let wait = interval - (now - last)
        lock.unlock()
        let (seconds, atto) = wait.components
        let nanos = Int(seconds * 1_000_000_000 + atto / 1_000_000_000)
        DispatchQueue.global().asyncAfter(deadline: .now() + .nanoseconds(nanos)) { [self] in
            lock.lock()
            let value = latest
            latest = nil
            pending = false
            self.last = clock.now
            lock.unlock()
            if let value { sink(value) }
        }
    }
}

/// Drops the Hugging Face key when a redirect leaves the host it was meant for (the files come from a CDN).
class AuthStripping: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? {
        Self.redirected(from: task.originalRequest, to: request)
    }

    static func redirected(from original: URLRequest?, to new: URLRequest) -> URLRequest {
        var next = new
        if next.url?.host != original?.url?.host { next.setValue(nil, forHTTPHeaderField: "Authorization") }
        return next
    }
}

/// One file into `<part>`: appends after what is there with `Range`, or starts over when the server sends the
/// whole file. Writes as the bytes arrive, so a multi-GB file never sits in memory.
final class FileFetch: AuthStripping, URLSessionDataDelegate, @unchecked Sendable {
    private let request: URLRequest
    private let part: URL
    private let configuration: URLSessionConfiguration
    private let onProgress: @Sendable (Int64) -> Void
    private let lock = NSLock()
    private var session: URLSession?
    private var handle: FileHandle?
    private var written: Int64 = 0
    private var failure: DownloadError?
    private var continuation: CheckedContinuation<Void, Error>?
    private var cancelled = false

    init(request: URLRequest, part: URL, configuration: URLSessionConfiguration, onProgress: @escaping @Sendable (Int64) -> Void) {
        self.request = request; self.part = part; self.configuration = configuration; self.onProgress = onProgress
    }

    func run() async throws {
        let offset = ModelDownloader.size(of: part) ?? 0
        var req = request
        if offset > 0 { req.setValue("bytes=\(offset)-", forHTTPHeaderField: "Range") }
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            lock.lock()
            if cancelled { lock.unlock(); cont.resume(throwing: CancellationError()); return }
            continuation = cont
            let s = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
            session = s
            lock.unlock()
            s.dataTask(with: req).resume()
        }
    }

    func cancel() {
        lock.lock()
        cancelled = true
        let s = session
        lock.unlock()
        s?.invalidateAndCancel()
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse) async
        -> URLSession.ResponseDisposition {
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let name = request.url?.lastPathComponent ?? ""
        do {
            let fm = FileManager.default
            switch status {
            case 206:
                if !fm.fileExists(atPath: part.path) { fm.createFile(atPath: part.path, contents: nil) }
                let h = try FileHandle(forWritingTo: part)
                written = Int64(try h.seekToEnd())
                handle = h
            case 200:
                // The server ignored Range (or there was nothing yet): start the file over.
                fm.createFile(atPath: part.path, contents: nil)
                handle = try FileHandle(forWritingTo: part)
                written = 0
            case 416:
                // Nothing left to send: the part is already whole. The checksum decides.
                written = ModelDownloader.size(of: part) ?? 0
                return .cancel
            case 401: failure = .keyRefused; return .cancel
            case 403 where request.url?.host == ModelCatalog.huggingFaceHost: failure = .licenceNotAccepted; return .cancel
            default: failure = .http(status: status, file: name); return .cancel
            }
        } catch {
            failure = .disk(error.localizedDescription)
            return .cancel
        }
        onProgress(written)
        return .allow
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        do {
            try handle?.write(contentsOf: data)
            written += Int64(data.count)
            onProgress(written)
        } catch {
            failure = .disk(error.localizedDescription)
            dataTask.cancel()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        try? handle?.synchronize()
        try? handle?.close()
        handle = nil
        session.finishTasksAndInvalidate()
        lock.lock()
        let cont = continuation
        continuation = nil
        let wasCancelled = cancelled
        lock.unlock()
        if wasCancelled { cont?.resume(throwing: CancellationError()); return }
        if let failure { cont?.resume(throwing: failure); return }
        if let e = error as? URLError, e.code != .cancelled {
            cont?.resume(throwing: DownloadError.network(e.localizedDescription)); return
        }
        cont?.resume()
    }
}

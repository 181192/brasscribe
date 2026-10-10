import CryptoKit
import Foundation
import Testing
@testable import BandroomKit

/// A fake web for the downloader: files by URL, honouring Range; failures and hangs on demand.
final class StubWeb: URLProtocol, @unchecked Sendable {
    struct Route: Sendable {
        var status = 200
        var body = Data()
        /// Send only this many bytes, then drop the connection.
        var dropAfter: Int?
        /// Send this many bytes, then never finish (until cancelled).
        var hangAfter: Int?
        /// Answer with a 302 to this URL.
        var redirect: URL?
        /// Ignore Range and always send the whole file.
        var ignoresRange = false
    }

    nonisolated(unsafe) static var routes: [String: Route] = [:]
    nonisolated(unsafe) static var seen: [URLRequest] = []
    static let lock = NSLock()

    static func reset() { lock.withLock { routes = [:]; seen = [] } }
    static func set(_ url: String, _ route: Route) { lock.withLock { routes[url] = route } }
    static func update(_ url: String, _ change: (inout Route) -> Void) { lock.withLock { change(&routes[url]!) } }
    static func requests(to url: String) -> [URLRequest] { lock.withLock { seen.filter { $0.url?.absoluteString == url } } }

    static var configuration: URLSessionConfiguration {
        let c = URLSessionConfiguration.ephemeral
        c.protocolClasses = [StubWeb.self]
        return c
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let url = request.url!.absoluteString
        let route: Route? = Self.lock.withLock { Self.seen.append(request); return Self.routes[url] }
        guard let route else {
            respond(404, [:], Data(), finish: true)
            return
        }
        if let to = route.redirect {
            let r = HTTPURLResponse(url: request.url!, statusCode: 302, httpVersion: "HTTP/1.1", headerFields: ["Location": to.absoluteString])!
            var next = URLRequest(url: to)
            next.allHTTPHeaderFields = request.allHTTPHeaderFields
            client?.urlProtocol(self, wasRedirectedTo: next, redirectResponse: r)
            return
        }
        guard route.status == 200 else { respond(route.status, [:], Data(), finish: true); return }
        var body = route.body
        var status = 200
        var headers = ["Content-Length": String(body.count)]
        if !route.ignoresRange, let range = request.value(forHTTPHeaderField: "Range"),
           let from = Int(range.dropFirst("bytes=".count).dropLast()) {
            if from >= body.count { respond(416, [:], Data(), finish: true); return }
            body = body.subdata(in: from..<body.count)
            status = 206
            headers = ["Content-Length": String(body.count), "Content-Range": "bytes \(from)-\(route.body.count - 1)/\(route.body.count)"]
        }
        if request.httpMethod == "HEAD" { body = Data() }
        if let n = route.dropAfter, n < body.count {
            respond(status, headers, body.prefix(n), finish: false)
            // As on a real network, the bytes that arrived are handed over before the connection drops.
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) {
                self.client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
            }
            return
        }
        if let n = route.hangAfter, n < body.count {
            respond(status, headers, body.prefix(n), finish: false)
            return
        }
        respond(status, headers, body, finish: true)
    }

    private func respond(_ status: Int, _ headers: [String: String], _ body: Data, finish: Bool) {
        let r = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
        client?.urlProtocol(self, didReceive: r, cacheStoragePolicy: .notAllowed)
        if !body.isEmpty { client?.urlProtocol(self, didLoad: body) }
        if finish { client?.urlProtocolDidFinishLoading(self) }
    }

    override func stopLoading() {}
}

func sha256Hex(_ d: Data) -> String { SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }

@MainActor
@Suite(.serialized) struct ModelDownloadTests {
    let root: URL
    let models: URL
    let hub: URL
    let big = Data((0..<300_000).map { UInt8($0 % 251) })
    let small = Data("dim: 1024\n".utf8)

    init() {
        StubWeb.reset()
        root = FileManager.default.temporaryDirectory.appending(path: "bandroom-dl-\(UUID().uuidString)", directoryHint: .isDirectory)
        models = root.appending(path: "models", directoryHint: .isDirectory)
        hub = root.appending(path: "hub", directoryHint: .isDirectory)
    }

    nonisolated static let sepURL = "https://example.org/sep/BS-Roformer-SW.ckpt"
    nonisolated static let yamlURL = "https://example.org/sep/BS-Roformer-SW.yaml"
    nonisolated static let hfModel = "https://huggingface.co/MuScriptor/muscriptor-medium/resolve/r1/model.safetensors"
    nonisolated static let hfConfig = "https://huggingface.co/MuScriptor/muscriptor-medium/resolve/r1/config.json"
    nonisolated static let whoami = "https://huggingface.co/api/whoami-v2"

    func catalog(bigSha: String? = nil) -> @Sendable (ModelComponent) -> [ModelFile] {
        let big = big, small = small
        return { c in
            switch c {
            case .soloistSeparator:
                [ModelFile(name: "BS-Roformer-SW.ckpt", url: URL(string: Self.sepURL)!, size: Int64(big.count), sha256: bigSha ?? sha256Hex(big)),
                 ModelFile(name: "BS-Roformer-SW.yaml", url: URL(string: Self.yamlURL)!, size: 0)]
            case .instrumentSeparator: []
            case .bandWriter:
                [ModelFile(name: "model.safetensors", url: URL(string: Self.hfModel)!, size: Int64(big.count), sha256: sha256Hex(big)),
                 ModelFile(name: "config.json", url: URL(string: Self.hfConfig)!, size: Int64(small.count),
                           gitBlob: Insecure.SHA1.hash(data: Data("blob \(small.count)\u{0}".utf8) + small).map { String(format: "%02x", $0) }.joined())]
            }
        }
    }

    func downloader(token: String? = "hf_test", free: Int64 = 100_000_000_000, bigSha: String? = nil) -> ModelDownloader {
        ModelDownloader(models: models, hub: hub, configuration: StubWeb.configuration, token: { token },
                        freeSpace: { _ in free }, catalog: catalog(bigSha: bigSha))
    }

    func serveSeparator() {
        StubWeb.set(Self.sepURL, .init(body: big))
        StubWeb.set(Self.yamlURL, .init(body: small))
    }

    func serveBandWriter(model: StubWeb.Route? = nil) {
        StubWeb.set(Self.whoami, .init(body: Data("{}".utf8)))
        StubWeb.set(Self.hfModel, model ?? .init(body: big))
        StubWeb.set(Self.hfConfig, .init(body: small))
    }

    func wait(_ d: ModelDownloader, until: (ModelDownloader) -> Bool) async {
        for _ in 0..<500 where !until(d) { try? await Task.sleep(for: .milliseconds(10)) }
    }

    func settled(_ d: ModelDownloader) async {
        await wait(d) { $0.phase == .done || $0.phase == .paused || { if case .failed = $0.phase { true } else { false } }($0) }
    }

    @Test func downloadsIntoTheModelsFolderAndChecksTheSum() async throws {
        serveSeparator()
        let d = downloader()
        d.start([.soloistSeparator])
        await settled(d)
        #expect(d.phase == .done)
        #expect(try Data(contentsOf: models.appending(path: "separator/BS-Roformer-SW.ckpt")) == big)
        #expect(!FileManager.default.fileExists(atPath: models.appending(path: "separator/BS-Roformer-SW.ckpt.part").path))
        #expect(d.fraction == 1)
        let check = ModelCheck.check(models: models, environment: ["HF_HUB_CACHE": hub.path], catalog: catalog())
        #expect(check.missing == [.bandWriter])
    }

    @Test func aDroppedConnectionResumesWithRange() async throws {
        StubWeb.set(Self.sepURL, .init(body: big, dropAfter: 100_000))
        StubWeb.set(Self.yamlURL, .init(body: small))
        let d = downloader()
        d.start([.soloistSeparator])
        await settled(d)
        guard case .failed(.network) = d.phase else { Issue.record("expected a network failure, got \(d.phase)"); return }
        let part = models.appending(path: "separator/BS-Roformer-SW.ckpt.part")
        #expect(ModelDownloader.size(of: part) == 100_000, "part \(String(describing: ModelDownloader.size(of: part))) \(d.phase)")

        StubWeb.update(Self.sepURL) { $0.dropAfter = nil }
        d.resume()
        await settled(d)
        #expect(d.phase == .done)
        #expect(StubWeb.requests(to: Self.sepURL).last?.value(forHTTPHeaderField: "Range") == "bytes=100000-")
        #expect(try Data(contentsOf: models.appending(path: "separator/BS-Roformer-SW.ckpt")) == big)
    }

    @Test func aServerThatIgnoresRangeStartsTheFileOver() async throws {
        StubWeb.set(Self.sepURL, .init(body: big, dropAfter: 50_000))
        StubWeb.set(Self.yamlURL, .init(body: small))
        let d = downloader()
        d.start([.soloistSeparator])
        await settled(d)
        StubWeb.update(Self.sepURL) { $0.dropAfter = nil; $0.ignoresRange = true }
        d.resume()
        await settled(d)
        #expect(d.phase == .done)
        #expect(try Data(contentsOf: models.appending(path: "separator/BS-Roformer-SW.ckpt")) == big)
    }

    @Test func pauseKeepsThePartAndResumeFinishesIt() async throws {
        StubWeb.set(Self.sepURL, .init(body: big, hangAfter: 120_000))
        StubWeb.set(Self.yamlURL, .init(body: small))
        let d = downloader()
        d.start([.soloistSeparator])
        await wait(d) { $0.bytesDone >= 120_000 }
        #expect(d.phase == .downloading)
        d.pause()
        #expect(d.phase == .paused)
        try await Task.sleep(for: .milliseconds(100))
        #expect(d.phase == .paused)
        #expect(ModelDownloader.size(of: models.appending(path: "separator/BS-Roformer-SW.ckpt.part")) == 120_000)

        StubWeb.update(Self.sepURL) { $0.hangAfter = nil }
        d.resume()
        await settled(d)
        #expect(d.phase == .done)
        #expect(StubWeb.requests(to: Self.sepURL).last?.value(forHTTPHeaderField: "Range") == "bytes=120000-")
        #expect(try Data(contentsOf: models.appending(path: "separator/BS-Roformer-SW.ckpt")) == big)
    }

    @Test func aWrongChecksumDeletesTheFile() async throws {
        serveSeparator()
        let d = downloader(bigSha: String(repeating: "0", count: 64))
        d.start([.soloistSeparator])
        await settled(d)
        #expect(d.phase == .failed(.checksumMismatch(file: "BS-Roformer-SW.ckpt")))
        #expect(!FileManager.default.fileExists(atPath: models.appending(path: "separator/BS-Roformer-SW.ckpt").path))
        #expect(!FileManager.default.fileExists(atPath: models.appending(path: "separator/BS-Roformer-SW.ckpt.part").path))
    }

    /// download_checks.json: upstream edits it, so it has no size or checksum.
    func checksDownloader() -> ModelDownloader {
        ModelDownloader(models: models, hub: hub, configuration: StubWeb.configuration, token: { nil }, freeSpace: { _ in 100_000_000_000 },
                        catalog: { c in c == .soloistSeparator ? [ModelFile(name: "download_checks.json", url: URL(string: Self.checksURL)!, size: 0)] : [] })
    }

    nonisolated static let checksURL = "https://example.org/filelists/download_checks.json"

    @Test func aFileWithoutAPublishedSizeStartsAfreshAndMustParse() async throws {
        let json = Data(#"{"models": ["BS-Roformer-SW.ckpt"]}"#.utf8)
        StubWeb.set(Self.checksURL, .init(body: json))
        let folder = models.appending(path: "separator", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        // Left from an earlier version of the file.
        try Data("{\"old\": tr".utf8).write(to: folder.appending(path: "download_checks.json.part"))
        let d = checksDownloader()
        d.start([.soloistSeparator])
        await settled(d)
        #expect(d.phase == .done)
        #expect(StubWeb.requests(to: Self.checksURL).last?.value(forHTTPHeaderField: "Range") == nil)
        #expect(try Data(contentsOf: folder.appending(path: "download_checks.json")) == json)
    }

    @Test func aBrokenJSONFileIsNotKept() async throws {
        StubWeb.set(Self.checksURL, .init(body: Data("<html>rate limited</html>".utf8)))
        let d = checksDownloader()
        d.start([.soloistSeparator])
        await settled(d)
        #expect(d.phase == .failed(.checksumMismatch(file: "download_checks.json")))
        #expect(!FileManager.default.fileExists(atPath: models.appending(path: "separator/download_checks.json").path))
    }

    @Test func notEnoughSpaceStopsBeforeAnyDownload() async {
        serveSeparator()
        let d = downloader(free: 2_000_000)
        d.start([.soloistSeparator])
        await settled(d)
        guard case .failed(.notEnoughSpace(let needed, let free)) = d.phase else { Issue.record("got \(d.phase)"); return }
        #expect(needed == Int64(big.count) + ModelDownloader.spareBytes)
        #expect(free == 2_000_000)
        #expect(StubWeb.requests(to: Self.sepURL).isEmpty)
    }

    @Test func theBandWriterNeedsAKeyButTheSeparatorsStillCome() async {
        serveBandWriter()
        serveSeparator()
        let d = downloader(token: nil)
        d.start([.bandWriter, .soloistSeparator])
        await settled(d)
        #expect(d.phase == .failed(.keyMissing))
        #expect(StubWeb.requests(to: Self.hfModel).isEmpty)
        #expect(d.finished == [.soloistSeparator])
        #expect(FileManager.default.fileExists(atPath: models.appending(path: "separator/BS-Roformer-SW.ckpt").path))
    }

    @Test func aRefusedKeyIsSaidSo() async {
        serveBandWriter()
        StubWeb.set(Self.whoami, .init(status: 401))
        let d = downloader()
        d.start([.bandWriter])
        await settled(d)
        #expect(d.phase == .failed(.keyRefused))
    }

    @Test func aLicenceNotAcceptedIs403() async {
        serveBandWriter(model: .init(status: 403))
        let d = downloader()
        d.start([.bandWriter])
        await settled(d)
        #expect(d.phase == .failed(.licenceNotAccepted))
        #expect(StubWeb.requests(to: Self.hfModel).first?.httpMethod == "HEAD")
    }

    @Test func theBandWriterLandsInTheHubCacheAsHuggingFaceLaysItOut() async throws {
        let cdn = "https://cdn.example.org/xet/blob"
        serveBandWriter(model: .init(redirect: URL(string: cdn)!))
        StubWeb.set(cdn, .init(body: big))
        let d = downloader()
        d.start([.bandWriter])
        await settled(d)
        #expect(d.phase == .done)
        let repo = hub.appending(path: "models--MuScriptor--muscriptor-medium")
        #expect(try String(contentsOf: repo.appending(path: "refs/main"), encoding: .utf8) == ModelCatalog.muscriptorRevision)
        let snapshot = repo.appending(path: "snapshots/\(ModelCatalog.muscriptorRevision)")
        let link = try FileManager.default.destinationOfSymbolicLink(atPath: snapshot.appending(path: "model.safetensors").path)
        #expect(link == "../../blobs/\(sha256Hex(big))")
        #expect(try Data(contentsOf: snapshot.appending(path: "model.safetensors")) == big)
        #expect(try Data(contentsOf: snapshot.appending(path: "config.json")) == small)
        // The key went to Hugging Face, never to the CDN it redirects to.
        #expect(StubWeb.requests(to: Self.hfModel).allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer hf_test" })
        #expect(!StubWeb.requests(to: cdn).isEmpty)
        #expect(StubWeb.requests(to: cdn).allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == nil })
        let check = ModelCheck.check(models: models, environment: ["HF_HUB_CACHE": hub.path], catalog: catalog())
        #expect(check.missing == [.soloistSeparator])
    }

    @Test func onlyWhatIsMissingIsFetched() async throws {
        serveSeparator()
        let dir = models.appending(path: "separator")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try big.write(to: dir.appending(path: "BS-Roformer-SW.ckpt"))
        let d = downloader()
        d.start([.soloistSeparator])
        await settled(d)
        #expect(d.phase == .done)
        #expect(StubWeb.requests(to: Self.sepURL).isEmpty)
        #expect(StubWeb.requests(to: Self.yamlURL).count == 1)
    }
}

@Suite struct ModelCheckTests {
    /// A file of `size` bytes that takes no disk (sparse).
    func sparse(_ url: URL, size: Int64) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let h = try FileHandle(forWritingTo: url)
        try h.truncate(atOffset: UInt64(size))
        try h.close()
    }

    func fakeHome() -> (home: URL, models: URL) {
        let home = FileManager.default.temporaryDirectory.appending(path: "bandroom-check-\(UUID().uuidString)", directoryHint: .isDirectory)
        return (home, home.appending(path: "Library/Application Support/Brasscribe/models", directoryHint: .isDirectory))
    }

    func fill(_ c: ModelComponent, models: URL, hub: URL) throws {
        switch c.home {
        case .models(let folder):
            for f in c.files { try sparse(models.appending(path: "\(folder)/\(f.name)"), size: max(f.size, 1)) }
        case .hub(let repo, let rev):
            let folder = ModelCatalog.hubRepoFolder(repo, hub: hub)
            for f in c.files {
                try sparse(folder.appending(path: "blobs/\(f.blobName!)"), size: f.size)
                try FileManager.default.createDirectory(at: folder.appending(path: "snapshots/\(rev)"), withIntermediateDirectories: true)
                try FileManager.default.createSymbolicLink(atPath: folder.appending(path: "snapshots/\(rev)/\(f.name)").path,
                                                           withDestinationPath: "../../blobs/\(f.blobName!)")
            }
            try FileManager.default.createDirectory(at: folder.appending(path: "refs"), withIntermediateDirectories: true)
            try Data(rev.utf8).write(to: folder.appending(path: "refs/main"))
        }
    }

    @Test func nothingThereMissesAllThreeInOrder() {
        let (home, models) = fakeHome()
        #expect(ModelCheck.check(models: models, environment: [:], home: home).missing == [.soloistSeparator, .instrumentSeparator, .bandWriter])
    }

    @Test func allThereIsReady() throws {
        let (home, models) = fakeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let hub = home.appending(path: ".cache/huggingface/hub")
        for c in ModelComponent.allCases { try fill(c, models: models, hub: hub) }
        #expect(ModelCheck.check(models: models, environment: [:], home: home).isReady)
    }

    /// The owner's case: MuScriptor in the hub cache, the separators not in the models folder.
    @Test func theBandWriterInTheHubCacheCountsAndTheSeparatorsAreNamed() throws {
        let (home, models) = fakeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        try fill(.bandWriter, models: models, hub: home.appending(path: ".cache/huggingface/hub"))
        #expect(ModelCheck.check(models: models, environment: [:], home: home).missing == [.soloistSeparator, .instrumentSeparator])
    }

    @Test func aFolderAloneOrAWrongSizeIsNotEnough() throws {
        let (home, models) = fakeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        try FileManager.default.createDirectory(at: models.appending(path: "separator"), withIntermediateDirectories: true)
        try fill(.instrumentSeparator, models: models, hub: home)
        try sparse(models.appending(path: "mega53/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"), size: 1000)
        let missing = ModelCheck.check(models: models, environment: [:], home: home).missing
        #expect(missing.contains(.soloistSeparator))
        #expect(missing.contains(.instrumentSeparator))
    }

    @Test func hfHomeAndHubCacheAreHonoured() throws {
        let (home, models) = fakeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let custom = home.appending(path: "hf")
        try fill(.bandWriter, models: models, hub: custom.appending(path: "hub"))
        #expect(!ModelCheck.check(models: models, environment: ["HF_HOME": custom.path], home: home).missing.contains(.bandWriter))
        #expect(ModelCheck.check(models: models, environment: ["HF_HUB_CACHE": custom.path], home: home).missing.contains(.bandWriter))
        #expect(ModelCatalog.hubCache(environment: ["HF_HUB_CACHE": "/x", "HF_HOME": "/y"]).path == "/x")
    }

    @Test func redirectsDropTheKeyOnlyWhenLeavingTheHost() {
        var original = URLRequest(url: URL(string: "https://huggingface.co/a")!)
        original.setValue("Bearer k", forHTTPHeaderField: "Authorization")
        var sameHost = URLRequest(url: URL(string: "https://huggingface.co/b")!)
        sameHost.setValue("Bearer k", forHTTPHeaderField: "Authorization")
        var cdn = URLRequest(url: URL(string: "https://cdn.example.org/b")!)
        cdn.setValue("Bearer k", forHTTPHeaderField: "Authorization")
        #expect(AuthStripping.redirected(from: original, to: sameHost).value(forHTTPHeaderField: "Authorization") == "Bearer k")
        #expect(AuthStripping.redirected(from: original, to: cdn).value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test func theCatalogueMatchesTheAdapters() {
        #expect(ModelComponent.soloistSeparator.files.map(\.name).contains("BS-Roformer-SW.ckpt"))
        #expect(ModelComponent.instrumentSeparator.files.map(\.name) == ["mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
                                                                          "mvsep_mega_model_bs_roformer_53_stems.yaml"])
        for c in ModelComponent.allCases {
            for f in c.files where f.size > 1000 { #expect(f.sha256?.count == 64) }
        }
        #expect(ModelComponent.allCases.filter(\.needsHuggingFaceKey) == [.bandWriter])
    }
}

/// The checksum of a finished file: off the main thread, in chunks, with progress, and cancellable.
@Suite struct ChecksumTests {
    func file(_ bytes: Int) throws -> (URL, Data) {
        let data = Data((0..<bytes).map { UInt8(truncatingIfNeeded: $0 &* 31 &+ 7) })
        let url = FileManager.default.temporaryDirectory.appending(path: "bandroom-sum-\(UUID().uuidString)")
        try data.write(to: url)
        return (url, data)
    }

    final class Seen: @unchecked Sendable {
        let lock = NSLock()
        var fractions: [Double] = []
        var onMain = false
        func add(_ f: Double) { lock.withLock { fractions.append(f); if Thread.isMainThread { onMain = true } } }
        var snapshot: (fractions: [Double], onMain: Bool) { lock.withLock { (fractions, onMain) } }
    }

    static func file(named name: String, _ data: Data) -> ModelFile {
        ModelFile(name: name, url: URL(string: "https://example.org/\(name)")!, size: Int64(data.count), sha256: sha256Hex(data))
    }

    @Test func aMultiChunkFileHashesToItsSHA256WithRisingProgressOffTheMainThread() async throws {
        let (url, data) = try file(1_000_003)
        defer { try? FileManager.default.removeItem(at: url) }
        let seen = Seen()
        let hex = try await ModelDownloader.digest(of: url, .sha256, chunk: 64 << 10, interval: .zero) { seen.add($0) }
        #expect(hex == sha256Hex(data))
        let (fractions, onMain) = seen.snapshot
        #expect(fractions.count >= 16)
        #expect(fractions == fractions.sorted())
        #expect(fractions.last == 1)
        #expect(!onMain)
    }

    /// Called from the main actor, as the downloader does: the hashing still runs elsewhere.
    @MainActor @Test func fromTheMainActorTheHashingRunsElsewhere() async throws {
        let (url, data) = try file(300_000)
        defer { try? FileManager.default.removeItem(at: url) }
        let seen = Seen()
        try await ModelDownloader.verify(url, as: Self.file(named: "x.bin", data), interval: .zero) { seen.add($0) }
        #expect(!seen.snapshot.onMain)
        #expect(!seen.snapshot.fractions.isEmpty)
        #expect(FileManager.default.fileExists(atPath: url.path))
    }

    @Test func theGitBlobIDMatchesGit() async throws {
        let (url, data) = try file(200_000)
        defer { try? FileManager.default.removeItem(at: url) }
        let want = Insecure.SHA1.hash(data: Data("blob \(data.count)\u{0}".utf8) + data).map { String(format: "%02x", $0) }.joined()
        #expect(try await ModelDownloader.digest(of: url, .gitBlob, chunk: 16 << 10) == want)
    }

    @Test func progressIsThrottled() async throws {
        let (url, _) = try file(2_000_000)
        defer { try? FileManager.default.removeItem(at: url) }
        let seen = Seen()
        _ = try await ModelDownloader.digest(of: url, .sha256, chunk: 4 << 10, interval: .seconds(10)) { seen.add($0) }
        // The first chunk and the end, not one per chunk.
        #expect(seen.snapshot.fractions.count == 2)
    }

    @Test func cancellingStopsTheHashingAndKeepsTheFile() async throws {
        let (url, data) = try file(4_000_000)
        defer { try? FileManager.default.removeItem(at: url) }
        let seen = Seen()
        let started = AsyncStream<Void>.makeStream()
        let f = Self.file(named: "x.bin", data)
        let work = Task {
            try await ModelDownloader.verify(url, as: f, chunk: 64 << 10, interval: .zero) { fraction in
                seen.add(fraction)
                started.continuation.yield()
                // Slow enough that the cancel lands mid-file.
                Thread.sleep(forTimeInterval: 0.002)
            }
        }
        for await _ in started.stream { break }
        work.cancel()
        await #expect(throws: CancellationError.self) { try await work.value }
        let fractions = seen.snapshot.fractions
        #expect(fractions.last.map { $0 < 1 } == true, "stopped at \(String(describing: fractions.last))")
        // A cancelled check isn't a bad file: the part stays whole for the next try.
        #expect(try Data(contentsOf: url) == data)
    }
}

@Suite struct ThrottleTests {
    /// The time a throttle goes by, moved by the test: no real time passes, so a busy machine changes nothing.
    final class Time: @unchecked Sendable {
        private let lock = NSLock()
        private var instant = ContinuousClock.now
        private var waiting: [(due: ContinuousClock.Instant, work: @Sendable () -> Void)] = []

        var now: ContinuousClock.Instant { lock.withLock { instant } }
        /// How many pieces of work wait for their time.
        var held: Int { lock.withLock { waiting.count } }

        func later(_ delay: Duration, _ work: @escaping @Sendable () -> Void) {
            lock.withLock { waiting.append((instant + delay, work)) }
        }

        /// Moves the time on, and runs what has come due by then.
        func pass(_ duration: Duration) {
            let due = lock.withLock {
                instant += duration
                let due = waiting.filter { $0.due <= instant }
                waiting.removeAll { $0.due <= instant }
                return due
            }
            for d in due { d.work() }
        }
    }

    final class Box: @unchecked Sendable {
        private let lock = NSLock()
        private var seen: [Int] = []
        var values: [Int] { lock.withLock { seen } }
        func add(_ v: Int) { lock.withLock { seen.append(v) } }
    }

    private func throttle(_ time: Time, _ box: Box) -> Throttle<Int> {
        Throttle<Int>(interval: .milliseconds(100), now: { time.now }, later: { time.later($0, $1) }) { box.add($0) }
    }

    @Test func holdsBackBurstsButDeliversTheLastValue() {
        let time = Time(), box = Box()
        let t = throttle(time, box)
        for i in 1...1000 { t.offer(i) }
        // The first goes out at once; the rest wait as one, for the interval's end.
        #expect(box.values == [1])
        #expect(time.held == 1)
        time.pass(.milliseconds(99))
        #expect(box.values == [1])
        time.pass(.milliseconds(1))
        #expect(box.values == [1, 1000])
        #expect(time.held == 0)
    }

    @Test func aValueAfterAQuietIntervalGoesOutAtOnce() {
        let time = Time(), box = Box()
        let t = throttle(time, box)
        t.offer(1)
        time.pass(.milliseconds(100))
        t.offer(2)
        #expect(box.values == [1, 2])
        #expect(time.held == 0)
    }

    @Test func theIntervalStartsAgainWhenAHeldValueGoesOut() {
        let time = Time(), box = Box()
        let t = throttle(time, box)
        t.offer(1)
        time.pass(.milliseconds(40))
        t.offer(2)
        // Held for the 60 ms left of the first interval.
        time.pass(.milliseconds(60))
        #expect(box.values == [1, 2])
        // Within an interval of the 2: held back again, and out when that interval ends.
        time.pass(.milliseconds(50))
        t.offer(3)
        #expect(box.values == [1, 2])
        time.pass(.milliseconds(50))
        #expect(box.values == [1, 2, 3])
    }

    /// The time it goes by in the app: a held value does come out by the system's clock and queue. Waits for the value
    /// itself, however long the machine takes.
    @Test func withTheSystemsTimeAHeldValueComesOut() async {
        let (stream, continuation) = AsyncStream<Int>.makeStream()
        let t = Throttle<Int>(interval: .milliseconds(20)) { continuation.yield($0) }
        t.offer(1)
        t.offer(2)
        var seen: [Int] = []
        for await v in stream {
            seen.append(v)
            if seen.count == 2 { break }
        }
        #expect(seen == [1, 2])
    }
}

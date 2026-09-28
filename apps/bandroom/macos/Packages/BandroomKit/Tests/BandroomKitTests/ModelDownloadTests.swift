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

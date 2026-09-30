import Foundation
import Testing
@testable import BandroomKit

@Suite struct UninstallerTests {
    /// A fake home with Library/Application Support/Brasscribe and Library/Logs/Brasscribe filled in.
    private func makeHome() throws -> (home: URL, paths: BandroomPaths) {
        let fm = FileManager.default
        let home = fm.temporaryDirectory.appending(path: "bandroom-uninstall-\(UUID().uuidString)", directoryHint: .isDirectory)
        let paths = BandroomPaths(data: home.appending(path: "Library/Application Support/Brasscribe", directoryHint: .isDirectory),
                                  logs: home.appending(path: "Library/Logs/Brasscribe", directoryHint: .isDirectory))
        for dir in [paths.models, paths.state, paths.workspace, paths.logs] {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        try Data(repeating: 1, count: 4096).write(to: paths.models.appending(path: "weights.bin"))
        try Data("x".utf8).write(to: paths.adminToken)
        try Data("{}".utf8).write(to: paths.state.appending(path: "devices.json"))
        try Data("log".utf8).write(to: paths.engineLog)
        // Something else in the home folder that must survive.
        try Data("keep".utf8).write(to: home.appending(path: "Library/other.txt"))
        return (home, paths)
    }

    @Test func removesDataFolderAndLogs() throws {
        let (home, paths) = try makeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let kept = try Uninstaller(paths: paths, home: home).remove(keepDownloads: false)
        #expect(kept.isEmpty)
        #expect(!FileManager.default.fileExists(atPath: paths.data.path))
        #expect(!FileManager.default.fileExists(atPath: paths.logs.path))
        #expect(FileManager.default.fileExists(atPath: home.appending(path: "Library/other.txt").path))
    }

    @Test func keepingDownloadsLeavesOnlyTheModels() throws {
        let (home, paths) = try makeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let kept = try Uninstaller(paths: paths, home: home).remove(keepDownloads: true)
        #expect(kept == [paths.models])
        let left = try FileManager.default.contentsOfDirectory(atPath: paths.data.path)
        #expect(left == ["models"])
        #expect(FileManager.default.fileExists(atPath: paths.models.appending(path: "weights.bin").path))
        #expect(!FileManager.default.fileExists(atPath: paths.logs.path))
    }

    @Test func downloadsSizeCountsTheModels() throws {
        let (home, paths) = try makeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let size = try #require(Uninstaller(paths: paths, home: home).downloadsSize())
        #expect(size >= 4096)
        try FileManager.default.removeItem(at: paths.models)
        #expect(Uninstaller(paths: paths, home: home).downloadsSize() == nil)
    }

    @Test func refusesTheHomeFolderAndItsParents() throws {
        let home = URL(fileURLWithPath: "/Users/someone", isDirectory: true)
        for data in ["/Users/someone", "/Users", "/", "/Applications/Brasscribe"] {
            let paths = BandroomPaths(data: URL(fileURLWithPath: data, isDirectory: true),
                                      logs: URL(fileURLWithPath: "/Users/someone/Library/Logs/Brasscribe", isDirectory: true))
            #expect(throws: Uninstaller.Failure.self) { try Uninstaller(paths: paths, home: home).remove(keepDownloads: false) }
        }
    }

    @Test func theBandWriterInTheHuggingFaceCacheCountsAsADownload() throws {
        let (home, paths) = try makeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let fm = FileManager.default
        let hub = home.appending(path: ".cache/huggingface/hub", directoryHint: .isDirectory)
        let writer = ModelCatalog.hubRepoFolder(ModelCatalog.muscriptorRepo, hub: hub)
        let other = hub.appending(path: "models--someone--else", directoryHint: .isDirectory)
        for dir in [writer.appending(path: "blobs"), other] { try fm.createDirectory(at: dir, withIntermediateDirectories: true) }
        try Data(repeating: 2, count: 8192).write(to: writer.appending(path: "blobs/ac80"))
        let u = Uninstaller(paths: paths, home: home, hub: hub)
        let size = try #require(u.downloadsSize())
        #expect(size >= 4096 + 8192)
        try u.remove(keepDownloads: true)
        #expect(fm.fileExists(atPath: writer.path), "kept with the downloads")
        try u.remove(keepDownloads: false)
        #expect(!fm.fileExists(atPath: writer.path))
        #expect(fm.fileExists(atPath: other.path), "someone else's models stay")
    }

    @Test func aHuggingFaceCacheOnAnotherDiskIsLeftAlone() throws {
        let (home, paths) = try makeHome()
        defer { try? FileManager.default.removeItem(at: home) }
        let fm = FileManager.default
        let elsewhere = fm.temporaryDirectory.appending(path: "bandroom-external-\(UUID().uuidString)/hub", directoryHint: .isDirectory)
        defer { try? fm.removeItem(at: elsewhere.deletingLastPathComponent()) }
        let writer = ModelCatalog.hubRepoFolder(ModelCatalog.muscriptorRepo, hub: elsewhere)
        try fm.createDirectory(at: writer.appending(path: "blobs"), withIntermediateDirectories: true)
        try Data(repeating: 2, count: 8192).write(to: writer.appending(path: "blobs/ac80"))
        let u = Uninstaller(paths: paths, home: home, hub: elsewhere)
        #expect(u.downloadsSize() == Uninstaller(paths: paths, home: home).downloadsSize(), "not offered for deletion")
        try u.remove(keepDownloads: false)
        #expect(!fm.fileExists(atPath: paths.data.path))
        #expect(!fm.fileExists(atPath: paths.logs.path))
        #expect(fm.fileExists(atPath: writer.path))
    }

    @Test func aFolderChosenElsewhereLosesOnlyWhatBrasscribePutThere() throws {
        let fm = FileManager.default
        let home = fm.temporaryDirectory.appending(path: "bandroom-override-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? fm.removeItem(at: home) }
        // BRASSCRIBE_DATA and BRASSCRIBE_LOGS pointed at a folder the user keeps other things in.
        let documents = home.appending(path: "Documents", directoryHint: .isDirectory)
        let paths = BandroomPaths(data: documents, logs: documents)
        for dir in [paths.models, paths.state, paths.workspace.appending(path: ".pixi")] {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        for file in [paths.adminToken, paths.engineStatus, paths.engineLog, paths.bandroomLog, documents.appending(path: "thesis.txt")] {
            try Data("x".utf8).write(to: file)
        }
        try Uninstaller(paths: paths, home: home).remove(keepDownloads: false)
        #expect(try fm.contentsOfDirectory(atPath: documents.path) == ["thesis.txt"])

        // A folder of its own is gone once it's empty.
        let own = home.appending(path: "brasscribe-data", directoryHint: .isDirectory)
        let ownPaths = BandroomPaths(data: own, logs: home.appending(path: "brasscribe-logs"))
        try fm.createDirectory(at: ownPaths.state, withIntermediateDirectories: true)
        try Uninstaller(paths: ownPaths, home: home).remove(keepDownloads: false)
        #expect(!fm.fileExists(atPath: own.path))
    }

    @Test func missingFoldersAreFine() throws {
        let home = FileManager.default.temporaryDirectory.appending(path: "bandroom-empty-\(UUID().uuidString)", directoryHint: .isDirectory)
        let paths = BandroomPaths(data: home.appending(path: "data"), logs: home.appending(path: "logs"))
        #expect(try Uninstaller(paths: paths, home: home).remove(keepDownloads: true).isEmpty)
    }
}

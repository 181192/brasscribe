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

    @Test func missingFoldersAreFine() throws {
        let home = FileManager.default.temporaryDirectory.appending(path: "bandroom-empty-\(UUID().uuidString)", directoryHint: .isDirectory)
        let paths = BandroomPaths(data: home.appending(path: "data"), logs: home.appending(path: "logs"))
        #expect(try Uninstaller(paths: paths, home: home).remove(keepDownloads: true).isEmpty)
    }
}

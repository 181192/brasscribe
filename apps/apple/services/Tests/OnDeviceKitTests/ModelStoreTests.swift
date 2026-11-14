import CoreML
import Foundation
import Testing
@testable import OnDeviceKit

@Suite struct ModelStoreTests {
    /// Callers asking for the same model at once share one compile, and none of them loses the result.
    @Test(.enabled(if: modelsDir() != nil, "converted models not found")) func concurrentLoadsCompileOnce() async throws {
        let cache = FileManager.default.temporaryDirectory.appending(path: "models-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? FileManager.default.removeItem(at: cache) }
        let store = ModelStore(bundled: nil, cache: cache, localSource: modelsDir())
        let models = try await withThrowingTaskGroup(of: ObjectIdentifier.self) { group in
            for _ in 0..<4 { group.addTask { ObjectIdentifier(try await store.model(.basicPitch)) } }
            return try await group.reduce(into: []) { $0.append($1) }
        }
        #expect(models.count == 4)
        #expect(Set(models).count == 1)
        #expect(FileManager.default.fileExists(atPath: store.compiledURL(.basicPitch).path))
    }

    @Test func aMissingModelFailsAndIsTriedAgain() async throws {
        let cache = FileManager.default.temporaryDirectory.appending(path: "models-\(UUID().uuidString)", directoryHint: .isDirectory)
        let store = ModelStore(bundled: cache, cache: cache, localSource: cache)
        #expect(store.missing == OnDeviceModel.needed)
        await #expect(throws: OnDeviceError.modelMissing(OnDeviceModel.swiftF0.fileName)) { try await store.model(.swiftF0) }
        await #expect(throws: OnDeviceError.modelMissing(OnDeviceModel.swiftF0.fileName)) { try await store.model(.swiftF0) }
    }

    /// The models an app carries are loaded as they are: found by name in its Models folder, with
    /// nothing compiled or written on the device, and no other source asked.
    @Test(.enabled(if: modelsDir() != nil, "converted models not found")) func theAppsOwnModelsLoadWithNothingWritten() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appending(path: "models-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? fm.removeItem(at: root) }
        // what scripts/stage-models.sh puts in the app: each package compiled, under its own name
        let inApp = root.appending(path: "Models", directoryHint: .isDirectory)
        try fm.createDirectory(at: inApp, withIntermediateDirectories: true)
        for m in OnDeviceModel.needed {
            let compiled = try await MLModel.compileModel(at: try #require(modelsDir()).appending(path: "\(m.directory)/\(m.fileName)"))
            try fm.moveItem(at: compiled, to: inApp.appending(path: m.compiledName))
        }
        let cache = root.appending(path: "cache", directoryHint: .isDirectory)
        let store = ModelStore(bundled: inApp, cache: cache, localSource: root.appending(path: "nothing-here"))
        #expect(store.missing.isEmpty)
        for m in OnDeviceModel.needed {
            #expect(try await store.model(m).modelDescription.inputDescriptionsByName.isEmpty == false)
        }
        #expect(!fm.fileExists(atPath: cache.path))

        // an app built without one of them says so, and does not look anywhere else
        try fm.removeItem(at: inApp.appending(path: OnDeviceModel.basicPitch.compiledName))
        let partial = ModelStore(bundled: inApp, cache: cache, localSource: root.appending(path: "nothing-here"))
        #expect(partial.missing == [.basicPitch])
        await #expect(throws: OnDeviceError.modelMissing(OnDeviceModel.basicPitch.fileName)) { try await partial.model(.basicPitch) }
    }
}

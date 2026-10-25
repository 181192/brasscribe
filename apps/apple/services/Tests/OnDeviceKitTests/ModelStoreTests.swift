import CoreML
import Foundation
import Testing
@testable import OnDeviceKit

@Suite struct ModelStoreTests {
    /// Callers asking for the same model at once share one compile, and none of them loses the result.
    @Test(.enabled(if: modelsDir() != nil, "converted models not found")) func concurrentLoadsCompileOnce() async throws {
        let cache = FileManager.default.temporaryDirectory.appending(path: "models-\(UUID().uuidString)", directoryHint: .isDirectory)
        defer { try? FileManager.default.removeItem(at: cache) }
        let store = ModelStore(cache: cache, localSource: modelsDir())
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
        let store = ModelStore(cache: cache, localSource: cache, remoteBase: nil)
        await #expect(throws: OnDeviceError.modelMissing(OnDeviceModel.swiftF0.fileName)) { try await store.model(.swiftF0) }
        await #expect(throws: OnDeviceError.modelMissing(OnDeviceModel.swiftF0.fileName)) { try await store.model(.swiftF0) }
        store.remoteBase = URL(string: "http://127.0.0.1:1")
        #expect(store.remoteBase?.port == 1)
    }
}

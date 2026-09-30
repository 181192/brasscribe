import CoreML
import Foundation

/// The Core ML models the offline solo pipeline uses. They are downloaded on demand, not
/// bundled, so the app stays small. Only conversions whose parity gate passes are listed
/// (convert/README.md).
public enum OnDeviceModel: String, CaseIterable, Sendable {
    case swiftF0 = "swift-f0/swift-f0-window-fp32"
    case basicPitch = "basic-pitch/nmp-b1-fp32"
    case beatThisHalf = "beat-this/beat-this-small0-fp16"
    case beatThisFull = "beat-this/beat-this-small0-fp32"

    /// Beat This in fp16 (4.4 MB) on devices. The simulator's Core ML returns zeros for the
    /// fp16 program, so it gets the fp32 build (8.6 MB, same parity gate).
    public static var beatThis: OnDeviceModel {
        #if targetEnvironment(simulator)
        return .beatThisFull
        #else
        return .beatThisHalf
        #endif
    }

    /// The models this device needs.
    public static var needed: [OnDeviceModel] { [.swiftF0, .basicPitch, beatThis] }

    public var fileName: String { String(rawValue.split(separator: "/").last!) + ".mlpackage" }
    public var directory: String { String(rawValue.split(separator: "/").first!) }

    /// SwiftF0 and Basic Pitch lose accuracy in fp16 on the Neural Engine, so they run on
    /// CPU and GPU; Beat This passes everywhere.
    public var computeUnits: MLComputeUnits {
        switch self {
        case .swiftF0, .basicPitch: return .cpuAndGPU
        case .beatThisHalf, .beatThisFull: return .all
        }
    }

    /// Approximate download size in MB (for the UI).
    public var sizeMB: Double {
        switch self {
        case .swiftF0: return 1.2
        case .basicPitch: return 0.3
        case .beatThisHalf: return 4.4
        case .beatThisFull: return 8.6
        }
    }

    /// Files inside an .mlpackage.
    static let packageFiles = ["Manifest.json", "Data/com.apple.CoreML/model.mlmodel", "Data/com.apple.CoreML/weights/weight.bin"]
}

/// Finds, downloads and compiles the on-device models.
///
/// Sources, in order: the compiled cache in Application Support; a local folder laid out
/// like `models/converted/` (`BRASSCRIBE_MODELS`, for development and the simulator);
/// an HTTP base URL serving the same layout (for example the paired computer).
///
/// Thread-safe: the sources and the loaded models are behind one lock, and a model is fetched and
/// compiled once however many callers ask for it at the same time.
public final class ModelStore: @unchecked Sendable {
    public let cache: URL
    public var localSource: URL? {
        get { lock.withLock { _localSource } }
        set { lock.withLock { _localSource = newValue } }
    }
    public var remoteBase: URL? {
        get { lock.withLock { _remoteBase } }
        set { lock.withLock { _remoteBase = newValue } }
    }
    private var _localSource: URL?
    private var _remoteBase: URL?
    private var loaded: [OnDeviceModel: MLModel] = [:]
    /// The load in progress for each model, which later callers wait for.
    private var loading: [OnDeviceModel: Task<Shared, Error>] = [:]
    /// A loaded model handed between tasks: MLModel is safe to use from several threads but is not
    /// marked Sendable.
    private struct Shared: @unchecked Sendable { let model: MLModel }
    private let lock = NSLock()

    public static let shared = ModelStore()

    public init(cache: URL? = nil, localSource: URL? = nil, remoteBase: URL? = nil) {
        let support = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        self.cache = cache ?? support.appending(path: "Brasscribe/Models", directoryHint: .isDirectory)
        _localSource = localSource ?? ProcessInfo.processInfo.environment["BRASSCRIBE_MODELS"].map { URL(fileURLWithPath: $0) }
        _remoteBase = remoteBase
    }

    func compiledURL(_ m: OnDeviceModel) -> URL { cache.appending(path: m.rawValue.replacingOccurrences(of: "/", with: "--") + ".mlmodelc") }

    public func isAvailable(_ m: OnDeviceModel) -> Bool {
        FileManager.default.fileExists(atPath: compiledURL(m).path)
            || localSource.map { FileManager.default.fileExists(atPath: $0.appending(path: "\(m.directory)/\(m.fileName)").path) } ?? false
    }

    public var missing: [OnDeviceModel] { OnDeviceModel.needed.filter { !isAvailable($0) } }

    /// Download (if needed) and compile every model. `progress` gets 0...1.
    public func prepareAll(progress: (@Sendable (Double) -> Void)? = nil) async throws {
        for (i, m) in OnDeviceModel.needed.enumerated() {
            _ = try await model(m)
            progress?(Double(i + 1) / Double(OnDeviceModel.needed.count))
        }
    }

    public func model(_ m: OnDeviceModel) async throws -> MLModel {
        let task: Task<Shared, Error> = lock.withLock {
            if let x = loaded[m] { return Task { Shared(model: x) } }
            if let t = loading[m] { return t }
            let t = Task { Shared(model: try await self.load(m)) }
            loading[m] = t
            return t
        }
        do {
            let model = try await task.value.model
            lock.withLock { loaded[m] = model; loading[m] = nil }
            return model
        } catch {
            // a failed load is not remembered, so the next call tries again
            lock.withLock { loading[m] = nil }
            throw error
        }
    }

    /// Fetches and compiles the model when it is not in the cache yet, then loads it. Runs once per
    /// model at a time (`model(_:)`).
    private func load(_ m: OnDeviceModel) async throws -> MLModel {
        let fm = FileManager.default
        let compiled = compiledURL(m)
        if !fm.fileExists(atPath: compiled.path) {
            let (package, downloaded) = try await fetchPackage(m)
            // the downloaded package is only needed until it is compiled
            defer { if let downloaded { try? fm.removeItem(at: downloaded) } }
            let tmp = try await MLModel.compileModel(at: package)
            defer { try? fm.removeItem(at: tmp) }
            try fm.createDirectory(at: compiled.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? fm.removeItem(at: compiled)
            try fm.moveItem(at: tmp, to: compiled)
        }
        let cfg = MLModelConfiguration()
        cfg.computeUnits = m.computeUnits
        return try MLModel(contentsOf: compiled, configuration: cfg)
    }

    /// The .mlpackage, and the folder to delete afterwards when it was downloaded.
    private func fetchPackage(_ m: OnDeviceModel) async throws -> (package: URL, downloaded: URL?) {
        if let local = localSource?.appending(path: "\(m.directory)/\(m.fileName)"), FileManager.default.fileExists(atPath: local.path) {
            return (local, nil)
        }
        guard let base = remoteBase else { throw OnDeviceError.modelMissing(m.fileName) }
        let folder = FileManager.default.temporaryDirectory.appending(path: "download-\(UUID().uuidString)", directoryHint: .isDirectory)
        let dst = folder.appending(path: m.fileName)
        do {
            for f in OnDeviceModel.packageFiles {
                let url = base.appending(path: "\(m.directory)/\(m.fileName)/\(f)")
                let (tmp, resp) = try await URLSession.shared.download(from: url)
                guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                    try? FileManager.default.removeItem(at: tmp)
                    throw OnDeviceError.modelMissing("\(m.fileName) (\(url))")
                }
                let target = dst.appending(path: f)
                try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                try FileManager.default.moveItem(at: tmp, to: target)
            }
        } catch {
            try? FileManager.default.removeItem(at: folder)
            throw error
        }
        return (dst, folder)
    }

    /// Remove the compiled models (frees about 6 MB).
    public func removeAll() {
        try? FileManager.default.removeItem(at: cache)
        lock.withLock { loaded = [:]; loading = [:] }
    }
}

extension MLMultiArray {
    /// Contents as Float regardless of the storage type (fp16 or fp32).
    /// Row-major contents as Float, honouring the array's strides (Core ML outputs can be
    /// padded, for example 88 values in a row of 96) and storage type.
    func floats() -> [Float] {
        // Core ML's own conversion handles strides and fp16 on every platform (the
        // simulator's fp16 outputs are not readable through withUnsafeBytes).
        if dataType == .float16 || dataType == .double { return MLShapedArray<Float>(converting: self).scalars }
        let shape = self.shape.map(\.intValue), strides = self.strides.map(\.intValue)
        let n = count
        var out = [Float](repeating: 0, count: n)
        // storage offset of each logical element
        func offsets() -> [Int] {
            var idx = [Int](repeating: 0, count: shape.count)
            var res = [Int](repeating: 0, count: n)
            for k in 0..<n {
                var off = 0
                for d in 0..<shape.count { off += idx[d] * strides[d] }
                res[k] = off
                var d = shape.count - 1
                while d >= 0 { idx[d] += 1; if idx[d] < shape[d] { break }; idx[d] = 0; d -= 1 }
            }
            return res
        }
        let offs = offsets()
        withUnsafeBytes { raw in
            switch dataType {
            case .float32:
                let p = raw.bindMemory(to: Float.self); for k in 0..<n { out[k] = p[offs[k]] }
            case .float16:
                #if arch(arm64)
                let p = raw.bindMemory(to: Float16.self); for k in 0..<n { out[k] = Float(p[offs[k]]) }
                #endif
            case .double:
                let p = raw.bindMemory(to: Double.self); for k in 0..<n { out[k] = Float(p[offs[k]]) }
            default:
                break
            }
        }
        return out
    }

    static func float32(shape: [Int], values: UnsafeBufferPointer<Float>) throws -> MLMultiArray {
        let a = try MLMultiArray(shape: shape.map { NSNumber(value: $0) }, dataType: .float32)
        a.withUnsafeMutableBufferPointer(ofType: Float.self) { p, _ in
            _ = p.initialize(from: values)
        }
        return a
    }
}

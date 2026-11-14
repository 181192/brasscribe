import CoreML
import Foundation

/// The Core ML models the offline solo pipeline uses. They are in the app, compiled when it is built
/// (scripts/stage-models.sh). Only conversions whose parity gate passes are listed (convert/README.md).
public enum OnDeviceModel: String, CaseIterable, Sendable {
    case swiftF0 = "swift-f0/swift-f0-window-fp32"
    case basicPitch = "basic-pitch/nmp-b1-fp32"
    /// Beat This small0 in fp32. The fp16 conversion is half the size, but on a 30 s trumpet part it
    /// puts one more downbeat than the published model does, on every compute unit of a Mac, and the
    /// score then comes out with half as many bars; fp32 gives the published model's beats exactly.
    /// (The simulator's Core ML returns zeros for the fp16 program besides.)
    case beatThis = "beat-this/beat-this-small0-fp32"

    /// The models a device needs.
    public static var needed: [OnDeviceModel] { [.swiftF0, .basicPitch, .beatThis] }

    public var name: String { String(rawValue.split(separator: "/").last!) }
    /// The package a conversion writes, in `directory` under models/converted.
    public var fileName: String { name + ".mlpackage" }
    public var directory: String { String(rawValue.split(separator: "/").first!) }
    /// The compiled model as the app carries it.
    public var compiledName: String { name + ".mlmodelc" }

    /// CPU and GPU, in fp32, for all three: the Neural Engine computes in fp16, where SwiftF0 and
    /// Basic Pitch lose accuracy and Beat This moves a downbeat.
    public var computeUnits: MLComputeUnits { .cpuAndGPU }
}

/// Finds and loads the on-device models.
///
/// Sources, in order: the app's own `Models` folder, compiled when the app was built; a local folder
/// laid out like `models/converted/` (`SCRIBE_MODELS`, for development and the package tests), whose
/// packages are compiled once into the cache in Application Support. Nothing is downloaded.
///
/// Thread-safe: the sources and the loaded models are behind one lock, and a model is
/// compiled once however many callers ask for it at the same time.
public final class ModelStore: @unchecked Sendable {
    /// The folder of compiled models the app carries (nil outside an app that has one).
    public let bundled: URL?
    public let cache: URL
    public var localSource: URL? {
        get { lock.withLock { _localSource } }
        set { lock.withLock { _localSource = newValue } }
    }
    private var _localSource: URL?
    private var loaded: [OnDeviceModel: MLModel] = [:]
    /// The load in progress for each model, which later callers wait for.
    private var loading: [OnDeviceModel: Task<Shared, Error>] = [:]
    /// A loaded model handed between tasks: MLModel is safe to use from several threads but is not
    /// marked Sendable.
    private struct Shared: @unchecked Sendable { let model: MLModel }
    private let lock = NSLock()

    public static let shared = ModelStore()

    /// The `Models` folder among the main bundle's resources.
    public static var appModels: URL? { Bundle.main.resourceURL?.appending(path: "Models", directoryHint: .isDirectory) }

    public init(bundled: URL? = ModelStore.appModels, cache: URL? = nil, localSource: URL? = nil) {
        let support = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        self.bundled = bundled
        self.cache = cache ?? support.appending(path: "Scribe/Models", directoryHint: .isDirectory)
        _localSource = localSource ?? ProcessInfo.processInfo.environment["SCRIBE_MODELS"].map { URL(fileURLWithPath: $0) }
    }

    /// The compiled model in the app, when the app carries it.
    func bundledURL(_ m: OnDeviceModel) -> URL? {
        guard let url = bundled?.appending(path: m.compiledName, directoryHint: .isDirectory),
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }

    func compiledURL(_ m: OnDeviceModel) -> URL { cache.appending(path: m.rawValue.replacingOccurrences(of: "/", with: "--") + ".mlmodelc") }

    private func localPackage(_ m: OnDeviceModel) -> URL? {
        guard let url = localSource?.appending(path: "\(m.directory)/\(m.fileName)"),
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }

    public func isAvailable(_ m: OnDeviceModel) -> Bool {
        bundledURL(m) != nil || FileManager.default.fileExists(atPath: compiledURL(m).path) || localPackage(m) != nil
    }

    public var missing: [OnDeviceModel] { OnDeviceModel.needed.filter { !isAvailable($0) } }

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

    /// Loads the app's own compiled model, or compiles the local package when it is not in the cache
    /// yet and loads that. Runs once per model at a time (`model(_:)`).
    private func load(_ m: OnDeviceModel) async throws -> MLModel {
        let cfg = MLModelConfiguration()
        cfg.computeUnits = m.computeUnits
        if let inApp = bundledURL(m) { return try MLModel(contentsOf: inApp, configuration: cfg) }
        let fm = FileManager.default
        let compiled = compiledURL(m)
        if !fm.fileExists(atPath: compiled.path) {
            guard let package = localPackage(m) else { throw OnDeviceError.modelMissing(m.fileName) }
            let tmp = try await MLModel.compileModel(at: package)
            defer { try? fm.removeItem(at: tmp) }
            try fm.createDirectory(at: compiled.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? fm.removeItem(at: compiled)
            try fm.moveItem(at: tmp, to: compiled)
        }
        return try MLModel(contentsOf: compiled, configuration: cfg)
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

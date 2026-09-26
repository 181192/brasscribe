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

    /// Beat This in fp16 (39 MB) on devices. The simulator's Core ML returns zeros for the
    /// fp16 program, so it gets the fp32 build (78 MB, same parity gate).
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
        case .beatThisHalf: return 39
        case .beatThisFull: return 78
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
public final class ModelStore: @unchecked Sendable {
    public let cache: URL
    public var localSource: URL?
    public var remoteBase: URL?
    private var loaded: [OnDeviceModel: MLModel] = [:]
    private let lock = NSLock()

    public static let shared = ModelStore()

    public init(cache: URL? = nil, localSource: URL? = nil, remoteBase: URL? = nil) {
        let support = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        self.cache = cache ?? support.appending(path: "Brasscribe/Models", directoryHint: .isDirectory)
        self.localSource = localSource ?? ProcessInfo.processInfo.environment["BRASSCRIBE_MODELS"].map { URL(fileURLWithPath: $0) }
        self.remoteBase = remoteBase
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
        if let x = lock.withLock({ loaded[m] }) { return x }
        let fm = FileManager.default
        let compiled = compiledURL(m)
        if !fm.fileExists(atPath: compiled.path) {
            let package = try await fetchPackage(m)
            let tmp = try await MLModel.compileModel(at: package)
            try fm.createDirectory(at: compiled.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? fm.removeItem(at: compiled)
            try fm.moveItem(at: tmp, to: compiled)
        }
        let cfg = MLModelConfiguration()
        cfg.computeUnits = m.computeUnits
        let model = try MLModel(contentsOf: compiled, configuration: cfg)
        lock.withLock { loaded[m] = model }
        return model
    }

    private func fetchPackage(_ m: OnDeviceModel) async throws -> URL {
        if let local = localSource?.appending(path: "\(m.directory)/\(m.fileName)"), FileManager.default.fileExists(atPath: local.path) {
            return local
        }
        guard let base = remoteBase else { throw OnDeviceError.modelMissing(m.fileName) }
        let dst = FileManager.default.temporaryDirectory.appending(path: "download-\(UUID().uuidString)/\(m.fileName)")
        for f in OnDeviceModel.packageFiles {
            let url = base.appending(path: "\(m.directory)/\(m.fileName)/\(f)")
            let (tmp, resp) = try await URLSession.shared.download(from: url)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw OnDeviceError.modelMissing("\(m.fileName) (\(url))") }
            let target = dst.appending(path: f)
            try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
            try FileManager.default.moveItem(at: tmp, to: target)
        }
        return dst
    }

    /// Remove the compiled models (frees about 40 MB).
    public func removeAll() {
        try? FileManager.default.removeItem(at: cache)
        lock.withLock { loaded = [:] }
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

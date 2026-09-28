import Darwin
import Foundation

/// "This computer" in words (design/server-app.md §7.5). Numbers come from the host, not the engine.
public enum WorkLoad: Int, Equatable, Sendable, CaseIterable {
    case calm = 1, busy, veryBusy

    /// < 40 % calm, 40–85 % busy, > 85 % very busy.
    public static func from(percent: Double) -> WorkLoad {
        percent < 40 ? .calm : (percent <= 85 ? .busy : .veryBusy)
    }
}

public enum MemoryLevel: Int, Equatable, Sendable, CaseIterable {
    case plentyFree = 1, gettingFull, almostFull

    /// > 25 % free plenty, 10–25 % getting full, < 10 % almost full.
    public static func from(freePercent: Double) -> MemoryLevel {
        freePercent > 25 ? .plentyFree : (freePercent >= 10 ? .gettingFull : .almostFull)
    }
}

public struct HostSnapshot: Equatable, Sendable {
    public var cpuPercent: Double
    public var memoryFreePercent: Double
    public var diskFreeBytes: Int64
    public var physicalMemoryBytes: UInt64

    public init(cpuPercent: Double, memoryFreePercent: Double, diskFreeBytes: Int64, physicalMemoryBytes: UInt64 = 0) {
        self.cpuPercent = cpuPercent; self.memoryFreePercent = memoryFreePercent
        self.diskFreeBytes = diskFreeBytes; self.physicalMemoryBytes = physicalMemoryBytes
    }

    public var workLoad: WorkLoad { .from(percent: cpuPercent) }
    public var memory: MemoryLevel { .from(freePercent: memoryFreePercent) }
    /// Whole GB, as people see them on their phones.
    public var diskFreeGB: Int { Int(diskFreeBytes / 1_000_000_000) }

    /// Warn under 10 GB; the engine stops taking jobs under 3 GB (§6.2).
    public static let lowDiskWarning: Int64 = 10_000_000_000
    public var isDiskLow: Bool { diskFreeBytes < Self.lowDiskWarning }
}

/// Samples CPU, memory and disk. CPU is averaged over the last 30 s.
public final class HostSampler: @unchecked Sendable {
    private var lastTicks: (busy: UInt64, total: UInt64)?
    private var window: [(Date, Double)] = []
    private let lock = NSLock()
    public let volume: URL

    public init(volume: URL) { self.volume = volume }

    public func sample(now: Date = Date()) -> HostSnapshot {
        lock.lock()
        defer { lock.unlock() }
        if let ticks = Self.cpuTicks() {
            if let last = lastTicks, ticks.total > last.total {
                let pct = Double(ticks.busy - last.busy) / Double(ticks.total - last.total) * 100
                window.append((now, pct))
            }
            lastTicks = ticks
        }
        window.removeAll { now.timeIntervalSince($0.0) > 30 }
        let cpu = window.isEmpty ? 0 : window.map(\.1).reduce(0, +) / Double(window.count)
        return HostSnapshot(cpuPercent: cpu, memoryFreePercent: Self.memoryFreePercent(), diskFreeBytes: Self.diskFree(volume),
                            physicalMemoryBytes: ProcessInfo.processInfo.physicalMemory)
    }

    static func cpuTicks() -> (busy: UInt64, total: UInt64)? {
        var info = host_cpu_load_info()
        var count = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info>.size / MemoryLayout<integer_t>.size)
        let rc = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO, $0, &count)
            }
        }
        guard rc == KERN_SUCCESS else { return nil }
        let user = UInt64(info.cpu_ticks.0), system = UInt64(info.cpu_ticks.1)
        let idle = UInt64(info.cpu_ticks.2), nice = UInt64(info.cpu_ticks.3)
        return (user + system + nice, user + system + idle + nice)
    }

    static func memoryFreePercent() -> Double {
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let rc = withUnsafeMutablePointer(to: &stats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count)
            }
        }
        guard rc == KERN_SUCCESS else { return 100 }
        let page = UInt64(getpagesize())
        // What macOS can hand out without pressure: free, inactive, purgeable and speculative pages.
        let available = (UInt64(stats.free_count) + UInt64(stats.inactive_count) + UInt64(stats.purgeable_count)
                         + UInt64(stats.speculative_count)) * page
        let total = ProcessInfo.processInfo.physicalMemory
        return total == 0 ? 100 : min(100, Double(available) / Double(total) * 100)
    }

    public static func diskFree(_ url: URL) -> Int64 {
        var probe = url
        while !FileManager.default.fileExists(atPath: probe.path), probe.path != "/" { probe.deleteLastPathComponent() }
        let values = try? probe.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey, .volumeAvailableCapacityKey])
        if let important = values?.volumeAvailableCapacityForImportantUsage, important > 0 { return important }
        return Int64(values?.volumeAvailableCapacity ?? 0)
    }

    /// "Apple M3 Pro".
    public static func chipName() -> String {
        var size = 0
        sysctlbyname("machdep.cpu.brand_string", nil, &size, nil, 0)
        guard size > 0 else { return "Mac" }
        var buf = [CChar](repeating: 0, count: size)
        sysctlbyname("machdep.cpu.brand_string", &buf, &size, nil, 0)
        return String(cString: buf)
    }
}

/// Whether the downloads a full-band score needs are there (§7 "Ready to make scores"). Runs every few
/// seconds, so it looks at names and sizes only; checksums are checked once, when a download finishes.
public enum ModelCheck {
    public struct Result: Equatable, Sendable {
        /// What is missing, in catalogue order.
        public var missing: [ModelComponent]
        public var isReady: Bool { missing.isEmpty }
        public init(missing: [ModelComponent]) { self.missing = missing }
    }

    /// `models` is the folder the engine gets as BRASSCRIBE_MODELS; the band writer lives in the hub cache.
    public static func check(models: URL, environment: [String: String] = ProcessInfo.processInfo.environment,
                             home: URL = FileManager.default.homeDirectoryForCurrentUser,
                             catalog: (ModelComponent) -> [ModelFile] = { ModelCatalog.files(for: $0) }) -> Result {
        let hub = ModelCatalog.hubCache(environment: environment, home: home)
        return Result(missing: ModelComponent.allCases.filter { !isPresent($0, models: models, hub: hub, files: catalog($0)) })
    }

    public static func isPresent(_ c: ModelComponent, models: URL, hub: URL, files: [ModelFile]) -> Bool {
        switch c.home {
        case .models(let folder):
            let dir = models.appending(path: folder, directoryHint: .isDirectory)
            return files.allSatisfy { fileMatches(dir.appending(path: $0.name), size: $0.size) }
        case .hub(let repo, let pinned):
            // As hf_hub_download resolves "main": refs/main names the snapshot the adapter reads.
            let folder = ModelCatalog.hubRepoFolder(repo, hub: hub)
            guard let rev = try? String(contentsOf: folder.appending(path: "refs/main"), encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines), !rev.isEmpty else { return false }
            let snapshot = folder.appending(path: "snapshots/\(rev)", directoryHint: .isDirectory)
            // A newer upstream revision has other sizes; then the files being there is enough.
            return files.allSatisfy { fileMatches(snapshot.appending(path: $0.name), size: rev == pinned ? $0.size : 0) }
        }
    }

    /// Exists (through symlinks) and, when `size` > 0, has exactly that many bytes.
    static func fileMatches(_ url: URL, size: Int64) -> Bool {
        let path = url.resolvingSymlinksInPath().path
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: path),
              (attrs[.type] as? FileAttributeType) == .typeRegular else { return false }
        return size <= 0 || (attrs[.size] as? NSNumber)?.int64Value == size
    }
}

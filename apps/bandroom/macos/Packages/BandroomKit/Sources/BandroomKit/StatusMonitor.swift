import Foundation
import Observation

/// Play's plain step names (design/server-app.md §7.2), one per engine stage kind, as the phones say them.
public enum JobStep: String, Equatable, Sendable {
    case preparing, findingBeat, separatingInstruments, separatingSoloist, transcribing, arranging, engraving

    /// From the engine's stage kind (profiles.py: beats, stems, layers, transcribe, arrange, export).
    public static func from(kind: String?) -> JobStep {
        switch kind {
        case "beats": .findingBeat
        case "stems": .separatingInstruments
        case "layers": .separatingSoloist
        case "transcribe": .transcribing
        case "arrange": .arranging
        case "export", "engrave", "render": .engraving
        default: .preparing
        }
    }
}

/// The "Now" block: what is being made.
public struct JobSummary: Equatable, Sendable {
    public var jobId: String
    public var title: String?
    /// Who sent it: "Kari's iPhone".
    public var deviceName: String?
    public var step: JobStep
    /// 0…100
    public var percent: Int
    public var minutesLeft: Int?
    public var waiting: Int

    public init(jobId: String, title: String?, deviceName: String? = nil, step: JobStep, percent: Int, minutesLeft: Int?, waiting: Int) {
        self.jobId = jobId; self.title = title; self.deviceName = deviceName; self.step = step; self.percent = percent
        self.minutesLeft = minutesLeft; self.waiting = waiting
    }

    public static func current(from jobs: [Job], now: Date = Date()) -> JobSummary? {
        guard let job = jobs.filter({ $0.status == "running" }).min(by: { ($0.started ?? $0.created) < ($1.started ?? $1.created) }) else {
            return nil
        }
        let stage = job.stages.first { $0.status == "running" } ?? job.stages.first { $0.status == "pending" }
        let progress = max(0, min(1, job.progress))
        var minutes: Int?
        if let started = job.started, progress >= 0.05, progress < 1 {
            let elapsed = now.timeIntervalSince1970 - started
            let left = elapsed / progress * (1 - progress)
            minutes = max(1, Int((left / 60).rounded(.up)))
        }
        return JobSummary(jobId: job.id, title: job.title, deviceName: job.deviceName, step: .from(kind: stage?.kind), percent: Int((progress * 100).rounded()),
                          minutesLeft: minutes, waiting: jobs.filter { $0.status == "queued" }.count)
    }
}

/// Keeps the popover's picture of the engine fresh: every 5 s while the panel is open, every 30 s otherwise,
/// and pairing requests every 3 s (a person is standing there with a phone).
@MainActor
@Observable
public final class StatusMonitor {
    public private(set) var status: EngineStatus?
    public private(set) var health: Health?
    public private(set) var devices: [DeviceInfo] = []
    public private(set) var job: JobSummary?
    public private(set) var requests: [PairRequestInfo] = []
    public private(set) var lastUpdate: Date?
    public private(set) var reachable = false
    /// Status checks in a row the engine didn't answer; back to 0 on an answer or a new engine.
    public private(set) var failedRefreshes = 0

    /// This many unanswered checks in a row: the engine runs but is stuck (§6.2 Needs attention).
    public static let unresponsiveAfter = 3
    public var isUnresponsive: Bool { failedRefreshes >= Self.unresponsiveAfter }

    public var isPanelOpen = false {
        didSet { if isPanelOpen && !oldValue { refreshDue = true } }
    }

    /// Called for each pairing request seen for the first time.
    @ObservationIgnored public var onNewRequest: ((PairRequestInfo) -> Void)?
    /// Called when the number of running jobs changes (for the sleep assertion and "restart when done").
    @ObservationIgnored public var onJobsChanged: ((Int) -> Void)?

    @ObservationIgnored public var client: (any EngineAPI)? {
        didSet { if client == nil { clear() } else { refreshDue = true; requestsDue = true; healthDue = true } }
    }
    /// A new engine process (a restart, an update) may be another build: ask for its health again.
    @ObservationIgnored private var healthDue = false

    @ObservationIgnored private var refreshDue = true
    @ObservationIgnored private var requestsDue = true
    @ObservationIgnored private var lastRefresh: Date?
    @ObservationIgnored private var lastRequests: Date?
    @ObservationIgnored private var seenRequests: Set<String> = []
    @ObservationIgnored private let now: () -> Date
    @ObservationIgnored private let sleep: @Sendable (TimeInterval) async -> Void
    @ObservationIgnored private var loop: Task<Void, Never>?

    public static let openInterval: TimeInterval = 5
    public static let closedInterval: TimeInterval = 30
    public static let requestsInterval: TimeInterval = 3

    public init(now: @escaping () -> Date = Date.init,
                sleep: @escaping @Sendable (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) }) {
        self.now = now
        self.sleep = sleep
    }

    public var interval: TimeInterval { isPanelOpen ? Self.openInterval : Self.closedInterval }

    public func start() {
        loop?.cancel()
        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.tick()
                await self.sleep(1)
            }
        }
    }

    public func stop() {
        loop?.cancel()
        loop = nil
    }

    /// One pass of the loop: refreshes whatever is due.
    public func tick() async {
        let t = now()
        if refreshDue || lastRefresh.map({ t.timeIntervalSince($0) >= interval }) ?? true {
            refreshDue = false
            lastRefresh = t
            await refresh()
        }
        if requestsDue || lastRequests.map({ t.timeIntervalSince($0) >= Self.requestsInterval }) ?? true {
            requestsDue = false
            lastRequests = t
            await refreshRequests()
        }
    }

    /// Asks for a refresh on the next tick (after an action such as Remove).
    public func setNeedsRefresh() { refreshDue = true; requestsDue = true }

    public func refresh() async {
        guard let client else { return }
        do {
            let s = try await client.status()
            let previousRunning = status?.jobsRunning
            status = s
            reachable = true
            failedRefreshes = 0
            lastUpdate = now()
            if health == nil || health?.serverId != s.serverId || healthDue {
                if let h = try? await client.health() { health = h; healthDue = false }
            }
            devices = Self.ordered((try? await client.devices()) ?? devices, now: now())
            if s.jobsRunning > 0 || s.jobsQueued > 0 {
                job = JobSummary.current(from: (try? await client.jobs()) ?? [], now: now())
            } else {
                job = nil
            }
            if previousRunning != s.jobsRunning { onJobsChanged?(s.jobsRunning) }
        } catch {
            reachable = false
            failedRefreshes += 1
        }
    }

    public func refreshRequests() async {
        guard let client, let list = try? await client.pairingRequests() else { return }
        let pending = list.filter { $0.status == "pending" }
        requests = pending
        for r in pending where !seenRequests.contains(r.requestId) {
            seenRequests.insert(r.requestId)
            onNewRequest?(r)
        }
    }

    public func removeDevice(_ id: String) async throws {
        guard let client else { throw EngineError.unreachable }
        try await client.removeDevice(id: id)
        devices.removeAll { $0.deviceId == id }
        refreshDue = true
    }

    /// Allow or deny a phone. Returns false when the request had expired (404).
    public func decide(_ request: PairRequestInfo, approve: Bool) async throws -> Bool {
        guard let client else { throw EngineError.unreachable }
        defer { requests.removeAll { $0.requestId == request.requestId }; refreshDue = true }
        do {
            _ = try await client.decide(requestId: request.requestId, approve: approve)
            return true
        } catch let e as EngineError where e.isNotFound {
            return false
        }
    }

    /// Connected devices first, then by last use (§8).
    public static func ordered(_ devices: [DeviceInfo], now: Date) -> [DeviceInfo] {
        devices.sorted { a, b in
            let ao = a.isOnline(now: now), bo = b.isOnline(now: now)
            if ao != bo { return ao }
            return (a.lastSeenDate ?? .distantPast) > (b.lastSeenDate ?? .distantPast)
        }
    }

    /// No engine: nothing is being made and its numbers are gone, so nothing waits on a job that isn't there.
    private func clear() {
        reachable = false
        failedRefreshes = 0
        status = nil
        job = nil
        requests = []
    }
}

import Foundation
import Observation

/// Starts the engine as a child process, restarts it with back-off when it exits unexpectedly, and stops it
/// (design/server-app.md §3.3). Runs `SupervisorMachine`'s effects.
@MainActor
@Observable
public final class EngineSupervisor {
    public private(set) var machine = SupervisorMachine()
    public private(set) var pid: Int32?
    public private(set) var port: Int?
    public private(set) var serverId: String?
    public private(set) var lastExitStatus: Int32?
    public var configuration: EngineConfiguration

    public var phase: SupervisorPhase { machine.phase }

    /// Called once the engine answers, with a client for it.
    public var onHealthy: ((any EngineAPI) -> Void)?
    /// Called when the engine is given up on (Error).
    public var onFailure: ((LaunchFailure?) -> Void)?
    /// Called on every change of phase, with the new one: whatever held on to the running engine (a client, the
    /// sleep assertion while a score is made) lets go when it isn't `.running` any more.
    public var onPhaseChange: ((SupervisorPhase) -> Void)?
    public var log: (String) -> Void = { _ in }

    @ObservationIgnored private let launcher: ProcessLauncher
    @ObservationIgnored private let makeClient: (Int, String) -> any EngineAPI
    @ObservationIgnored private let sleep: @Sendable (TimeInterval) async -> Void
    @ObservationIgnored private let now: () -> Date
    @ObservationIgnored private let pickPort: () -> Int?
    /// What the engine starts with; a new Hugging Face key replaces it before the next start.
    @ObservationIgnored public var baseEnvironment: [String: String]
    @ObservationIgnored public var healthTimeout: TimeInterval
    @ObservationIgnored public var terminateGrace: TimeInterval = 8
    @ObservationIgnored private var healthTask: Task<Void, Never>?
    @ObservationIgnored private var retryTask: Task<Void, Never>?
    /// Bumped on every launch so a late exit from an old process can't move the new one's state.
    @ObservationIgnored private var generation = 0

    public init(configuration: EngineConfiguration,
                launcher: ProcessLauncher = PosixLauncher(),
                makeClient: @escaping (Int, String) -> any EngineAPI = { EngineClient(port: $0, token: $1) },
                sleep: @escaping @Sendable (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) },
                now: @escaping () -> Date = Date.init,
                pickPort: @escaping () -> Int? = { PortPicker.firstFree() },
                baseEnvironment: [String: String] = ProcessInfo.processInfo.environment,
                healthTimeout: TimeInterval = 180) {
        self.configuration = configuration
        self.launcher = launcher
        self.makeClient = makeClient
        self.sleep = sleep
        self.now = now
        self.pickPort = pickPort
        self.baseEnvironment = baseEnvironment
        self.healthTimeout = healthTimeout
    }

    public var client: (any EngineAPI)? {
        guard case .running = phase, let port else { return nil }
        return makeClient(port, configuration.adminToken)
    }

    // MARK: commands

    public func start() { send(.start) }
    public func stop() { send(.stop) }
    public func restart() { send(.restart) }

    /// Stops the engine and waits (up to the grace period) for it to be gone. For quitting Bandroom.
    public func shutdown() {
        guard let pid, machine.isProcessAlive else { return }
        send(.stop)
        let deadline = Date().addingTimeInterval(terminateGrace + 1)
        while kill(-pid, 0) == 0 && Date() < deadline { usleep(100_000) }
        if kill(-pid, 0) == 0 { kill(-pid, SIGKILL) }
        try? FileManager.default.removeItem(at: configuration.paths.engineStatus)
    }

    /// Stops an engine an earlier, crashed Bandroom left running, using engine.json.
    public func reapStrayEngine() {
        guard let old = EngineStatusFile.read(configuration.paths.engineStatus) else { return }
        log("stopping an engine left from an earlier session (pid \(old.pid))")
        PosixLauncher.killStrayGroup(pid: old.pid)
        try? FileManager.default.removeItem(at: configuration.paths.engineStatus)
    }

    // MARK: machine

    func send(_ event: SupervisorEvent) {
        let before = machine.phase
        let effects = machine.handle(event, now: now())
        if before != machine.phase { log("engine: \(before) → \(machine.phase) on \(event)") }
        if before != machine.phase { onPhaseChange?(machine.phase) }
        for effect in effects { run(effect) }
    }

    private func run(_ effect: SupervisorEffect) {
        switch effect {
        case .launch: launch()
        case .terminate:
            healthTask?.cancel()
            if let pid { launcher.terminate(pid: pid, grace: terminateGrace) }
        case .waitForHealth: waitForHealth()
        case .scheduleRetry(let delay):
            retryTask?.cancel()
            retryTask = Task { [weak self, sleep] in
                await sleep(delay)
                guard !Task.isCancelled else { return }
                self?.send(.retryDue)
            }
        case .cancelRetry:
            retryTask?.cancel()
            retryTask = nil
        case .announceFailure:
            if case .failed(let why) = machine.phase { onFailure?(why) }
        }
    }

    private func launch() {
        generation += 1
        let gen = generation
        guard let port = pickPort() else { return send(.launchFailed(.noFreePort)) }
        do {
            let plan = try configuration.launchPlan(port: port, base: baseEnvironment)
            let pid = try launcher.launch(plan) { [weak self] status in
                Task { @MainActor in self?.exited(status: status, generation: gen) }
            }
            self.pid = pid
            self.port = port
            log("engine: launched pid \(pid) on port \(port)")
        } catch let failure as LaunchFailure {
            send(.launchFailed(failure))
        } catch {
            send(.launchFailed(.spawn(String(describing: error))))
        }
    }

    private func exited(status: Int32, generation gen: Int) {
        guard gen == generation else { return }
        lastExitStatus = status
        log("engine: exited with status \(status)")
        healthTask?.cancel()
        pid = nil
        try? FileManager.default.removeItem(at: configuration.paths.engineStatus)
        send(.exited(status: status))
    }

    private func waitForHealth() {
        healthTask?.cancel()
        guard machine.phase == .starting, let port else { return }
        let client = makeClient(port, configuration.adminToken)
        let expected = EngineStatusFile.serverId(stateDir: configuration.paths.state)
        let deadline = now().addingTimeInterval(healthTimeout)
        let gen = generation
        healthTask = Task { [weak self, sleep] in
            while !Task.isCancelled {
                if let h = try? await client.health(), expected == nil || h.serverId == expected {
                    guard let self, gen == self.generation, self.machine.phase == .starting else { return }
                    self.serverId = h.serverId
                    if let pid = self.pid {
                        try? EngineStatusFile(port: port, pid: pid, serverId: h.serverId, version: h.version).write(self.configuration.paths.engineStatus)
                    }
                    self.send(.healthy)
                    self.onHealthy?(client)
                    return
                }
                guard let self, gen == self.generation else { return }
                if self.now() > deadline {
                    self.send(.healthTimedOut)
                    return
                }
                await sleep(0.5)
            }
        }
    }
}

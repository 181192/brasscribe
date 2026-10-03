import Foundation

/// Why the engine could not run at all (not a crash): shown as Needs attention or Error.
public enum LaunchFailure: Equatable, Sendable {
    /// Ports 8765–8775 are all taken.
    case noFreePort
    /// The engine environment isn't set up (first run unfinished, or pixi missing).
    case notInstalled(String)
    case spawn(String)
    /// The pixi Bandroom runs the engine with is older than the engine workspace asks for; starting again can't help.
    case pixiTooOld(PixiRefusal)
}

/// The engine's life as Bandroom sees it (design/server-app.md §3.3, §3.7).
public enum SupervisorPhase: Equatable, Sendable {
    /// Not started yet this session.
    case idle
    /// Launched, waiting for /v1/health to answer.
    case starting
    case running
    /// Asked to exit; `then` says what happens after it does.
    case stopping(then: AfterStop)
    /// Stopped on purpose.
    case stopped
    /// Exited unexpectedly; starts again after `delay`.
    case waitingToRetry(attempt: Int, delay: TimeInterval)
    /// Three unexpected exits in five minutes, or it can't be launched: "Stopped unexpectedly".
    case failed(LaunchFailure?)

    public enum AfterStop: Equatable, Sendable { case stop, restart, fail }

    /// Stopped on purpose: Start brings it back. Decided by the engine's phase, not by what the panel shows, so a
    /// Needs-attention note (low disk space) never hides the button.
    public var offersStart: Bool { self == .stopped }

    /// Running, or on its way there: Restart and Stop apply.
    public var offersStop: Bool {
        switch self {
        case .starting, .running, .waitingToRetry, .stopping(then: .restart): true
        default: false
        }
    }
}

public enum SupervisorEvent: Equatable, Sendable {
    case start
    case stop
    case restart
    case launchFailed(LaunchFailure)
    case healthy
    case healthTimedOut
    case exited(status: Int32)
    case retryDue
}

public enum SupervisorEffect: Equatable, Sendable {
    case launch
    case terminate
    case waitForHealth
    case scheduleRetry(after: TimeInterval)
    case cancelRetry
    case announceFailure
}

/// Pure state machine for engine supervision: no processes, no clocks. `EngineSupervisor` runs the effects.
public struct SupervisorMachine: Equatable, Sendable {
    public private(set) var phase: SupervisorPhase = .idle
    /// Times of unexpected exits, newest last.
    public private(set) var failures: [Date] = []

    public static let failureWindow: TimeInterval = 5 * 60
    public static let maxFailures = 3

    public init() {}

    /// 2, 4, 8 … 30 s.
    public static func backoff(attempt: Int) -> TimeInterval {
        min(30, 2 * pow(2, Double(max(0, attempt - 1))))
    }

    public var isProcessAlive: Bool {
        switch phase {
        case .starting, .running, .stopping: true
        default: false
        }
    }

    public mutating func handle(_ event: SupervisorEvent, now: Date) -> [SupervisorEffect] {
        switch (phase, event) {
        // Starting from rest. "Try again" after an error forgets the old failures.
        case (.idle, .start), (.stopped, .start):
            phase = .starting
            return [.launch, .waitForHealth]
        case (.failed, .start), (.failed, .restart):
            failures = []
            phase = .starting
            return [.launch, .waitForHealth]
        case (.waitingToRetry, .start), (.waitingToRetry, .restart), (.waitingToRetry, .retryDue):
            phase = .starting
            return [.cancelRetry, .launch, .waitForHealth]
        case (.idle, .restart), (.stopped, .restart):
            phase = .starting
            return [.launch, .waitForHealth]

        case (.starting, .healthy):
            phase = .running
            return []
        case (.starting, .healthTimedOut):
            phase = .stopping(then: .fail)
            return [.terminate]
        case (.starting, .launchFailed(let why)), (.waitingToRetry, .launchFailed(let why)):
            phase = .failed(why)
            return [.announceFailure]

        case (.starting, .stop), (.running, .stop):
            phase = .stopping(then: .stop)
            return [.terminate]
        case (.starting, .restart), (.running, .restart):
            phase = .stopping(then: .restart)
            return [.terminate]
        case (.stopping, .stop):
            phase = .stopping(then: .stop)
            return []
        case (.stopping, .restart):
            phase = .stopping(then: .restart)
            return []
        case (.waitingToRetry, .stop):
            phase = .stopped
            return [.cancelRetry]
        case (.failed, .stop), (.idle, .stop):
            phase = .stopped
            return []

        case (.stopping(let then), .exited):
            switch then {
            case .stop:
                phase = .stopped
                return []
            case .restart:
                phase = .starting
                return [.launch, .waitForHealth]
            case .fail:
                return crashed(now: now)
            }
        case (.starting, .exited), (.running, .exited):
            return crashed(now: now)

        default:
            return []
        }
    }

    private mutating func crashed(now: Date) -> [SupervisorEffect] {
        failures = failures.filter { now.timeIntervalSince($0) < Self.failureWindow } + [now]
        if failures.count >= Self.maxFailures {
            phase = .failed(nil)
            return [.announceFailure]
        }
        let delay = Self.backoff(attempt: failures.count)
        phase = .waitingToRetry(attempt: failures.count, delay: delay)
        return [.scheduleRetry(after: delay)]
    }
}

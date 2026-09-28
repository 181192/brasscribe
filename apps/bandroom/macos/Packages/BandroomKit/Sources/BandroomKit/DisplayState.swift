import Foundation

/// A Needs-attention problem with one fix (design/server-app.md §6.2).
public enum Problem: Equatable, Sendable {
    case lowDisk(freeGB: Int)
    /// What a full-band score still needs, in catalogue order; empty when Brasscribe's own tools (the engine
    /// environment) aren't installed yet.
    case missingDownload([ModelComponent])
    case noFreePort
    /// The app was updated but its engine couldn't be: the previous one still runs. The fix tries again.
    case updateFailed
}

/// What the menu-bar icon, the tooltip and the status line show (§6.1).
public enum DisplayState: Equatable, Sendable {
    case settingUp(percent: Int)
    case starting
    case running
    case busy(percent: Int)
    case attention(Problem)
    case stopped
    case updating
    case error

    /// Error › Needs attention › Updating › Busy › Starting › Running › Stopped. Setting up comes first while
    /// the first run isn't finished.
    public static func resolve(setupPercent: Int?, phase: SupervisorPhase, updating: Bool, problems: [Problem],
                               jobPercent: Int?) -> DisplayState {
        if let setupPercent { return .settingUp(percent: setupPercent) }
        switch phase {
        case .failed(.noFreePort): return .attention(.noFreePort)
        case .failed(.notInstalled): return .attention(.missingDownload([]))
        case .failed: return .error
        default: break
        }
        if let first = problems.first { return .attention(first) }
        if updating { return .updating }
        switch phase {
        case .running:
            if let jobPercent { return .busy(percent: jobPercent) }
            return .running
        case .starting, .waitingToRetry, .stopping(then: .restart), .stopping(then: .fail), .idle:
            return .starting
        case .stopping(then: .stop), .stopped:
            return .stopped
        case .failed:
            return .error
        }
    }

    /// The busy badge is a pie that changes in 8 steps, never animated (§9, 2.3.3).
    public static func pieStep(percent: Int) -> Int {
        max(0, min(8, Int((Double(percent) / 12.5).rounded(.down))))
    }
}

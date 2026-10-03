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
    /// As `updateFailed`, because pixi refused the new workspace (too old for it). The previous engine still runs, so
    /// Brasscribe can start; the fix is a newer Bandroom. With no engine running, a start refusal says `pixiTooOld`.
    case updateRefused(PixiRefusal)
    /// The engine runs but hasn't answered for several checks in a row (hung). The fix restarts it.
    case notResponding
    /// The pixi this app bundles is too old for its engine: first-run setup or a start was refused, so no engine
    /// runs. The fix is a newer Bandroom.
    case pixiTooOld(PixiRefusal)

    /// Shown even while setting up: setup can't get past it.
    public var outranksSetup: Bool {
        if case .pixiTooOld = self { true } else { false }
    }

    /// pixi's refusal behind this problem, for the tech person.
    public var pixiRefusal: PixiRefusal? {
        switch self {
        case .pixiTooOld(let r), .updateRefused(let r): r
        default: nil
        }
    }

    /// What a failed update shows while the previous engine stays: why it failed, when pixi said.
    public static func afterFailedUpdate(refusal: PixiRefusal?) -> Problem {
        refusal.map(Problem.updateRefused) ?? .updateFailed
    }
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
        if case .failed(.pixiTooOld(let refusal)) = phase { return .attention(.pixiTooOld(refusal)) }
        if let first = problems.first(where: \.outranksSetup) { return .attention(first) }
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

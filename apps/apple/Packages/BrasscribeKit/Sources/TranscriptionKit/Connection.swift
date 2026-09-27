import Foundation

/// How this device stands with its computer, the same four states on every Play app.
public enum ConnectionState: Equatable, Sendable {
    /// The last heartbeat was answered.
    case connected(serverName: String)
    /// Heartbeats fail; looking at the last address, then on the network by server id.
    case reconnecting(serverName: String)
    /// No computer paired, or it could not be found for two minutes.
    case offline
    /// The computer answered 401: this device's credential is no longer accepted.
    case needsPairing(serverName: String)

    /// The kind without the name, for deciding whether a change is worth announcing.
    public enum Kind: Sendable { case connected, reconnecting, offline, needsPairing }
    public var kind: Kind {
        switch self {
        case .connected: .connected
        case .reconnecting: .reconnecting
        case .offline: .offline
        case .needsPairing: .needsPairing
        }
    }
}

/// The connection state machine without any timers or networking: feed it events with the time they
/// happened, and it says how long to wait before the next heartbeat (nil: stop until something changes).
public struct ConnectionMachine: Equatable, Sendable {
    /// Heartbeat interval while connected.
    public static let heartbeatInterval: TimeInterval = 20
    /// Reconnecting gives up and reports offline after this long without an answer.
    public static let giveUpAfter: TimeInterval = 120
    /// Retry delays while reconnecting: 2, 4, 8, 16, then every 30 s.
    public static func backoff(attempt: Int) -> TimeInterval {
        min(30, pow(2, Double(max(1, attempt))))
    }

    public enum Event: Equatable, Sendable {
        /// A paired engine exists (launch, app back in the foreground, network change, pairing done).
        case start(serverName: String)
        /// The user pressed "Connect".
        case connectRequested(serverName: String)
        case heartbeatOK(serverName: String)
        case heartbeatFailed
        case unauthorized
        /// No engine paired any more (unpaired, or nothing stored).
        case forgotten
        /// App went to the background: stop heartbeats, keep the state as it was.
        case suspended
    }

    public private(set) var state: ConnectionState
    /// When the current run of failures began.
    public private(set) var failingSince: Date?
    public private(set) var attempt = 0
    private var serverName = ""

    public init(state: ConnectionState = .offline) { self.state = state }

    /// Applies an event and returns the delay before the next heartbeat, or nil to stop.
    @discardableResult
    public mutating func handle(_ event: Event, at now: Date) -> TimeInterval? {
        switch event {
        case .start(let name), .connectRequested(let name):
            serverName = name
            if case .needsPairing = state, event == .start(serverName: name) { return nil }
            if case .connected = state { return 0 }
            state = .reconnecting(serverName: name)
            failingSince = now
            attempt = 0
            return 0
        case .heartbeatOK(let name):
            serverName = name
            state = .connected(serverName: name)
            failingSince = nil
            attempt = 0
            return Self.heartbeatInterval
        case .heartbeatFailed:
            if case .needsPairing = state { return nil }
            if case .offline = state { return nil }
            let since = failingSince ?? now
            failingSince = since
            attempt += 1
            if now.timeIntervalSince(since) >= Self.giveUpAfter {
                state = .offline
                return nil
            }
            state = .reconnecting(serverName: serverName)
            return min(Self.backoff(attempt: attempt), max(0, Self.giveUpAfter - now.timeIntervalSince(since)))
        case .unauthorized:
            state = .needsPairing(serverName: serverName)
            failingSince = nil
            attempt = 0
            return nil
        case .forgotten:
            state = .offline
            failingSince = nil
            attempt = 0
            serverName = ""
            return nil
        case .suspended:
            return nil
        }
    }
}

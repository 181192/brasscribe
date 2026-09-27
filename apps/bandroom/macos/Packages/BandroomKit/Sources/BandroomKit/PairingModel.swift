import Foundation
import Observation

/// The Pair a phone window (design/server-app.md §3.4). The engine's pairing window is open, with no expiry,
/// exactly while this window is open; each code works once.
@MainActor
@Observable
public final class PairingModel {
    public enum Phase: Equatable, Sendable {
        case idle
        case opening
        case open
        /// The engine isn't running, or refused.
        case unavailable
    }

    public private(set) var phase: Phase = .idle
    public private(set) var state: PairingState?
    /// The phone that paired last while this window was open: "Kari's iPhone is paired."
    public private(set) var pairedDevice: String?
    /// "Too many wrong codes. Wait a moment, or allow the phone here."
    public private(set) var isLockedOut = false

    @ObservationIgnored public var client: (any EngineAPI)?
    @ObservationIgnored private var knownDevices: Set<String>?
    @ObservationIgnored private var loop: Task<Void, Never>?
    @ObservationIgnored private let now: () -> Date
    @ObservationIgnored private let sleep: @Sendable (TimeInterval) async -> Void

    /// Refresh cadence while the window is open.
    public static let pollInterval: TimeInterval = 2
    /// Extend a fixed-lifetime window when less than this is left (engines that ignore "no expiry").
    public static let extendMargin: TimeInterval = 120

    public init(client: (any EngineAPI)? = nil, now: @escaping () -> Date = Date.init,
                sleep: @escaping @Sendable (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) }) {
        self.client = client
        self.now = now
        self.sleep = sleep
    }

    public var code: String? { state?.open == true ? state?.code : nil }
    public var displayCode: String? { state?.open == true ? state?.displayCode : nil }
    public var uri: String? { state?.open == true ? state?.uri : nil }
    public var host: String? { state.map { ComputerName.host(fromServerName: $0.serverName) } }

    /// First LAN address and port, for "type this address" (tech help).
    public var address: (ip: String, port: String)? {
        guard let first = state?.hosts.first, let colon = first.lastIndex(of: ":") else { return nil }
        return (String(first[..<colon]), String(first[first.index(after: colon)...]))
    }

    /// Opens a pairing window with a fresh code and starts watching for a phone.
    public func open() async {
        guard let client else { phase = .unavailable; return }
        phase = .opening
        pairedDevice = nil
        isLockedOut = false
        do {
            knownDevices = Set(try await client.devices().map(\.deviceId))
            state = try await client.openPairing(PairingOpen(ttlSeconds: nil, singleUse: true))
            phase = .open
            startPolling()
        } catch {
            phase = .unavailable
        }
    }

    /// "Pair another phone": the next code.
    public func pairAnother() async {
        await open()
    }

    /// Closes the engine's pairing window; call when the window closes.
    public func close() async {
        loop?.cancel()
        loop = nil
        phase = .idle
        guard let client else { return }
        _ = try? await client.closePairing()
    }

    public func startPolling() {
        loop?.cancel()
        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.sleep(Self.pollInterval)
                if Task.isCancelled { return }
                await self.poll()
            }
        }
    }

    /// One refresh: notices a new paired phone, a lockout, and keeps a fixed-lifetime code alive.
    public func poll() async {
        guard let client, phase == .open else { return }
        if let devices = try? await client.devices() {
            let ids = Set(devices.map(\.deviceId))
            if let known = knownDevices, let new = devices.first(where: { !known.contains($0.deviceId) }) {
                pairedDevice = new.name
            }
            knownDevices = ids
        }
        guard var s = try? await client.pairing() else { return }
        if let locked = s.lockedUntil.flatMap(ISODate.parse) {
            isLockedOut = locked > now()
        } else {
            isLockedOut = false
        }
        if s.open, let expires = s.expiresAt.flatMap(ISODate.parse), expires.timeIntervalSince(now()) < Self.extendMargin,
           let extended = try? await client.openPairing(PairingOpen(ttlSeconds: 600, singleUse: true, extend: true)) {
            s = extended
        }
        state = s
    }
}

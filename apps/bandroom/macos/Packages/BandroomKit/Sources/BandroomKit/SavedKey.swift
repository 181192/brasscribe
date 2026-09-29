import Foundation
import Observation
import os

/// What one read of the saved Hugging Face key found.
public enum SecretRead: Equatable, Sendable {
    case found(String)
    case none
    /// A key is saved but couldn't be read: the Keychain prompt was denied or cancelled, or no prompt could be
    /// shown. `status` is the OSStatus, for the log.
    case unreadable(status: Int32)
}

/// Where the key is kept. Every call may block while macOS asks the user (a Keychain prompt waits for an
/// answer), so `SavedKey` never calls it on the main thread or on a Swift concurrency thread.
public protocol SecretStore: Sendable {
    func read() -> SecretRead
    /// Replaces the saved key; false when the store refused.
    func save(_ key: String) -> Bool
    func delete()
}

/// The saved Hugging Face key, read in the background so the app and the engine start without it. The engine
/// gets it when it arrives (`onChange`); when it can't be read, Bandroom runs without it and says so.
@MainActor
@Observable
public final class SavedKey {
    public enum State: Equatable, Sendable {
        /// Not read (HF_TOKEN is set, or nothing asked yet).
        case notRead
        case reading
        case found
        case none
        /// Saved, but the Keychain didn't hand it over.
        case unreadable
    }

    public private(set) var state: State = .notRead
    /// The OSStatus of the last read that failed.
    public private(set) var lastFailure: Int32?
    /// The read under way has waited `unansweredAfter` (a Keychain prompt nobody has answered, or one hidden
    /// behind other windows). Cleared when the read ends.
    public private(set) var unanswered = false
    /// On the main actor, whenever the key the engine should get changes.
    @ObservationIgnored public var onChange: ((String?) -> Void)?
    @ObservationIgnored private let store: any SecretStore
    @ObservationIgnored private let queue: DispatchQueue
    private let box = OSAllocatedUnfairLock<String?>(initialState: nil)
    @ObservationIgnored private var reading = false
    /// Bumped by a save or delete that went through, so a read that started before them can't undo them.
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var waiters: [UUID: CheckedContinuation<Void, Never>] = [:]
    @ObservationIgnored private let unansweredAfter: Duration
    /// Bumped by every read, so an old read's timer can't mark a newer read unanswered.
    @ObservationIgnored private var readNumber = 0

    public init(store: any SecretStore, queue: DispatchQueue = .global(qos: .userInitiated),
                unansweredAfter: Duration = .seconds(30)) {
        self.store = store
        self.queue = queue
        self.unansweredAfter = unansweredAfter
    }

    /// The key, from any thread (the downloader asks from its own tasks); nil until it has been read.
    public nonisolated var value: String? { box.withLock { $0 } }

    public var isReading: Bool { reading }

    /// Starts a read unless one is under way. Returns at once.
    public func read() {
        guard !reading else { return }
        reading = true
        state = .reading
        readNumber += 1
        let store = store, queue = queue, started = generation, number = readNumber, after = unansweredAfter
        Task { [weak self] in
            let result = await withCheckedContinuation { (c: CheckedContinuation<SecretRead, Never>) in
                queue.async { c.resume(returning: store.read()) }
            }
            self?.apply(result, started: started)
        }
        Task { [weak self] in
            try? await Task.sleep(for: after)
            guard let self, self.reading, self.state == .reading, self.readNumber == number else { return }
            self.unanswered = true
        }
    }

    /// Waits for the read under way, at most `limit`. The engine starts after that whether or not the key came.
    public func settled(within limit: Duration) async {
        guard reading else { return }
        let id = UUID()
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            waiters[id] = c
            Task { [weak self] in
                try? await Task.sleep(for: limit)
                self?.waiters.removeValue(forKey: id)?.resume()
            }
        }
    }

    /// Saves a key typed in setup, off the main thread. False when the Keychain refused; the state is unchanged then.
    public func save(_ key: String) async -> Bool {
        let key = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return false }
        let store = store, queue = queue
        let ok = await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in
            queue.async { c.resume(returning: store.save(key)) }
        }
        guard ok else { return false }
        generation += 1
        lastFailure = nil
        unanswered = false
        state = .found
        set(key)
        return true
    }

    /// Forgets the key (Remove from this Mac), off the main thread.
    public func delete() async {
        let store = store, queue = queue
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            queue.async { store.delete(); c.resume() }
        }
        generation += 1
        unanswered = false
        state = .none
        set(nil)
    }

    private func apply(_ result: SecretRead, started: Int) {
        reading = false
        unanswered = false
        defer {
            let done = waiters.values
            waiters.removeAll()
            done.forEach { $0.resume() }
        }
        guard started == generation else { return }
        switch result {
        case .found(let key):
            lastFailure = nil
            state = .found
            set(key)
        case .none:
            lastFailure = nil
            state = .none
            set(nil)
        case .unreadable(let status):
            lastFailure = status
            state = .unreadable
            set(nil)
        }
    }

    private func set(_ key: String?) {
        let old = box.withLock { old in
            defer { old = key }
            return old
        }
        if old != key { onChange?(key) }
    }
}

/// What a changed key means for a running engine, which reads HF_TOKEN only at launch.
public enum EngineKeyUpdate: Equatable, Sendable {
    /// Nothing is running, or the next launch picks it up anyway.
    case none
    case restartNow
    /// A score is being made: restart after it.
    case restartWhenDone

    public static func action(phase: SupervisorPhase, busy: Bool) -> EngineKeyUpdate {
        switch phase {
        case .running: busy ? .restartWhenDone : .restartNow
        // Launched without the key and not answering yet: nothing to lose.
        case .starting: .restartNow
        case .idle, .stopped, .failed, .waitingToRetry, .stopping: .none
        }
    }
}

extension EngineSupervisor {
    /// Gives the engine the saved key as HF_TOKEN (HF_TOKEN already in `environment` wins) from its next launch,
    /// and says what that means for the engine now.
    public func useHuggingFaceKey(_ key: String?, environment: [String: String], busy: Bool) -> EngineKeyUpdate {
        let env = Self.environment(environment, huggingFaceKey: key)
        guard env["HF_TOKEN"] != baseEnvironment["HF_TOKEN"] else { return .none }
        baseEnvironment = env
        return EngineKeyUpdate.action(phase: phase, busy: busy)
    }

    public nonisolated static func environment(_ environment: [String: String], huggingFaceKey key: String?) -> [String: String] {
        var env = environment
        if (env["HF_TOKEN"] ?? "").isEmpty {
            env["HF_TOKEN"] = key
        }
        return env
    }
}

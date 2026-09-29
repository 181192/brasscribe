import Foundation
import Testing
@testable import BandroomKit

/// A keychain in memory. `hold()` makes reads wait (a Keychain prompt nobody has answered) until `release()`.
final class FakeKeychain: SecretStore, @unchecked Sendable {
    private let lock = NSLock()
    private var _result: SecretRead
    private var _saveWorks = true
    private var _reads = 0
    private var gate: DispatchSemaphore?

    init(_ result: SecretRead) { _result = result }

    var result: SecretRead {
        get { lock.withLock { _result } }
        set { lock.withLock { _result = newValue } }
    }
    var saveWorks: Bool {
        get { lock.withLock { _saveWorks } }
        set { lock.withLock { _saveWorks = newValue } }
    }
    var reads: Int { lock.withLock { _reads } }

    func hold() { lock.withLock { gate = DispatchSemaphore(value: 0) } }
    /// Answers the waiting reads. Safe to call more than once (tests call it in `defer`).
    func release() {
        let g = lock.withLock { () -> DispatchSemaphore? in defer { gate = nil }; return gate }
        for _ in 0..<8 { g?.signal() }
    }

    func read() -> SecretRead {
        let g = lock.withLock { () -> DispatchSemaphore? in _reads += 1; return gate }
        g?.wait()
        return result
    }

    func save(_ key: String) -> Bool {
        lock.withLock {
            guard _saveWorks else { return false }
            _result = .found(key)
            return true
        }
    }

    func delete() { lock.withLock { _result = .none } }
}

@MainActor
func waitUntil(_ condition: () -> Bool, seconds: Double = 5) async {
    let end = Date().addingTimeInterval(seconds)
    while !condition() && Date() < end { try? await Task.sleep(for: .milliseconds(5)) }
}

@MainActor
@Suite struct SavedKeyTests {
    @Test func readsTheKeyInTheBackgroundAndHandsItOver() async {
        let keychain = FakeKeychain(.found("hf_saved"))
        let key = SavedKey(store: keychain)
        var changes: [String?] = []
        key.onChange = { changes.append($0) }
        key.read()
        #expect(key.state == .reading)
        await key.settled(within: .seconds(5))
        #expect(key.state == .found)
        #expect(key.value == "hf_saved")
        #expect(changes == ["hf_saved"])
    }

    @Test func noSavedKeyIsNotAProblem() async {
        let key = SavedKey(store: FakeKeychain(.none))
        key.read()
        await key.settled(within: .seconds(5))
        #expect(key.state == .none)
        #expect(key.value == nil)
        #expect(key.lastFailure == nil)
    }

    @Test func aDeniedReadRunsWithoutTheKeyAndSaysSo() async {
        // errSecUserCanceled: Deny in the Keychain prompt.
        let key = SavedKey(store: FakeKeychain(.unreadable(status: -128)))
        var changes: [String?] = []
        key.onChange = { changes.append($0) }
        key.read()
        await key.settled(within: .seconds(5))
        #expect(key.state == .unreadable)
        #expect(key.lastFailure == -128)
        #expect(key.value == nil)
        #expect(changes.isEmpty)
    }

    @Test func aReadThatWaitsForThePromptDoesNotHoldUpTheWait() async {
        let keychain = FakeKeychain(.found("hf_late"))
        keychain.hold()
        defer { keychain.release() }
        let key = SavedKey(store: keychain)
        key.read()
        let start = ContinuousClock.now
        await key.settled(within: .milliseconds(50))
        #expect(ContinuousClock.now - start < .seconds(2))
        #expect(key.state == .reading)
        #expect(key.value == nil)
        keychain.release()
        await waitUntil { key.state == .found }
        #expect(key.value == "hf_late")
    }

    @Test func tryAgainAfterADenialReadsAgain() async {
        let keychain = FakeKeychain(.unreadable(status: -25293))
        let key = SavedKey(store: keychain)
        key.read()
        await key.settled(within: .seconds(5))
        #expect(key.state == .unreadable)
        keychain.result = .found("hf_allowed")
        key.read()
        await key.settled(within: .seconds(5))
        #expect(keychain.reads == 2)
        #expect(key.state == .found)
        #expect(key.value == "hf_allowed")
    }

    @Test func enteringTheKeyAgainReplacesAnUnreadableOne() async {
        let key = SavedKey(store: FakeKeychain(.unreadable(status: -128)))
        var changes: [String?] = []
        key.onChange = { changes.append($0) }
        key.read()
        await key.settled(within: .seconds(5))
        #expect(await key.save("  hf_new \n"))
        #expect(key.state == .found)
        #expect(key.value == "hf_new")
        #expect(key.lastFailure == nil)
        #expect(changes == ["hf_new"])
    }

    @Test func aRefusedSaveSaysSoAndChangesNothing() async {
        let keychain = FakeKeychain(.unreadable(status: -128))
        keychain.saveWorks = false
        let key = SavedKey(store: keychain)
        key.read()
        await key.settled(within: .seconds(5))
        #expect(await key.save("hf_new") == false)
        #expect(key.state == .unreadable)
        #expect(key.value == nil)
    }

    @Test func aReadAnsweredAfterASaveDoesNotUndoIt() async {
        let keychain = FakeKeychain(.unreadable(status: -128))
        keychain.hold()
        defer { keychain.release() }
        let key = SavedKey(store: keychain)
        key.read()
        #expect(await key.save("hf_typed"))
        // The old prompt is answered with Deny only now.
        keychain.result = .unreadable(status: -128)
        keychain.release()
        await waitUntil { !key.isReading }
        #expect(key.state == .found)
        #expect(key.value == "hf_typed")
    }

    @Test func deleteForgetsTheKey() async {
        let key = SavedKey(store: FakeKeychain(.found("hf_saved")))
        key.read()
        await key.settled(within: .seconds(5))
        await key.delete()
        #expect(key.state == .none)
        #expect(key.value == nil)
    }

    @Test func aNewKeyRestartsTheEngineOnlyWhenThatLosesNothing() {
        #expect(EngineKeyUpdate.action(phase: .running, busy: false) == .restartNow)
        #expect(EngineKeyUpdate.action(phase: .running, busy: true) == .restartWhenDone)
        #expect(EngineKeyUpdate.action(phase: .starting, busy: false) == .restartNow)
        for phase: SupervisorPhase in [.idle, .stopped, .failed(nil), .waitingToRetry(attempt: 1, delay: 2), .stopping(then: .restart)] {
            #expect(EngineKeyUpdate.action(phase: phase, busy: false) == .none)
        }
    }

    @Test func hfTokenFromTheEnvironmentWins() {
        #expect(EngineSupervisor.environment(["HF_TOKEN": "hf_env"], huggingFaceKey: "hf_saved")["HF_TOKEN"] == "hf_env")
        #expect(EngineSupervisor.environment([:], huggingFaceKey: "hf_saved")["HF_TOKEN"] == "hf_saved")
        #expect(EngineSupervisor.environment([:], huggingFaceKey: nil)["HF_TOKEN"] == nil)
    }
}

/// Startup as Bandroom does it: read the key in the background, wait briefly, start the engine either way, and
/// hand the key over when it comes.
@MainActor
@Suite struct StartupWithoutTheKeyTests {
    func startup(_ keychain: FakeKeychain) async -> (SavedKey, EngineSupervisor, FakeLauncher) {
        let launcher = FakeLauncher()
        let (sup, _) = EngineSupervisorTests().make(launcher, FakeEngine())
        let key = SavedKey(store: keychain)
        let env = sup.baseEnvironment
        key.onChange = { [unowned sup] k in
            if sup.useHuggingFaceKey(k, environment: env, busy: false) == .restartNow { sup.restart() }
        }
        key.read()
        await key.settled(within: .milliseconds(50))
        sup.start()
        await settle()
        return (key, sup, launcher)
    }

    @Test func theEngineStartsWhileTheKeychainPromptIsUnanswered() async throws {
        let keychain = FakeKeychain(.found("hf_late"))
        keychain.hold()
        defer { keychain.release() }
        let (key, sup, launcher) = await startup(keychain)
        #expect(key.state == .reading)
        #expect(sup.phase == .running)
        #expect(launcher.launched.count == 1)
        #expect(try #require(launcher.launched.first).environment["HF_TOKEN"] == nil)

        // Allow: the engine restarts with the key.
        keychain.release()
        await waitUntil { launcher.launched.count == 2 }
        await settle()
        #expect(sup.phase == .running)
        #expect(launcher.launched.last?.environment["HF_TOKEN"] == "hf_late")
    }

    @Test func aDeniedPromptLeavesTheEngineRunningWithoutTheKey() async throws {
        let keychain = FakeKeychain(.unreadable(status: -128))
        keychain.hold()
        defer { keychain.release() }
        let (key, sup, launcher) = await startup(keychain)
        keychain.release()
        await waitUntil { key.state == .unreadable }
        await settle()
        #expect(sup.phase == .running)
        #expect(launcher.launched.count == 1)
        #expect(try #require(launcher.launched.first).environment["HF_TOKEN"] == nil)
        #expect(sup.baseEnvironment["HF_TOKEN"] == nil)
    }

    @Test func aKeyReadInTimeIsThereFromTheFirstLaunch() async throws {
        let (key, sup, launcher) = await startup(FakeKeychain(.found("hf_saved")))
        #expect(key.state == .found)
        #expect(sup.phase == .running)
        #expect(launcher.launched.count == 1)
        #expect(try #require(launcher.launched.first).environment["HF_TOKEN"] == "hf_saved")
    }
}

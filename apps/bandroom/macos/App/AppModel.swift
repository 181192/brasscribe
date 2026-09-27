import AppKit
import BandroomKit
import IOKit.pwr_mgt
import Observation
import ServiceManagement
import SwiftUI
import UserNotifications

/// Everything the menu-bar panel, the windows and the notifications share.
@MainActor
@Observable
final class AppModel {
    let paths: BandroomPaths
    let supervisor: EngineSupervisor
    let monitor = StatusMonitor()
    let pairing = PairingModel()
    let bootstrapper = Bootstrapper()
    private(set) var host: HostSnapshot?
    private(set) var models: ModelCheck.Result = .init(missing: [])
    var setupComplete: Bool {
        didSet { UserDefaults.standard.set(setupComplete, forKey: "setupComplete") }
    }
    /// "Restart when “Old Hundredth” is done".
    var restartWhenDone = false
    var isPairWindowOpen = false
    /// The name on a request that lapsed before it was answered.
    var expiredRequest: String?
    var loginItemEnabled = false
    /// Where the panel is: the main status or the phones list.
    var panelPage: PanelPage = .status

    enum PanelPage: Equatable { case status, phones }

    @ObservationIgnored var openWindow: ((String) -> Void)?
    @ObservationIgnored private let sampler: HostSampler
    @ObservationIgnored private var sampleTask: Task<Void, Never>?
    @ObservationIgnored private var sleepAssertion: IOPMAssertionID = 0
    @ObservationIgnored private var lastAnnounced: DisplayState?
    @ObservationIgnored private let logger: FileLogger
    @ObservationIgnored private let environment = ProcessInfo.processInfo.environment
    /// BANDROOM_DEMO=busy|idle (Debug builds): canned engine data for screenshots, no engine started.
    @ObservationIgnored let demo: Bool

    init() {
        let env = ProcessInfo.processInfo.environment
        let paths = BandroomPaths.standard(environment: env)
        try? paths.ensure()
        self.paths = paths
        self.logger = FileLogger(url: paths.bandroomLog)
        let token: String
        do {
            token = try AdminToken.loadOrCreate(at: paths.adminToken)
        } catch {
            token = AdminToken.generate()
        }
        let source = EngineConfiguration.resolveSource(environment: env, defaults: .standard, paths: paths, bundle: .main)
        let config = EngineConfiguration(source: source, pixi: EngineConfiguration.findPixi(bundle: .main, environment: env),
                                         paths: paths, computerName: ComputerName.current(), adminToken: token)
        supervisor = EngineSupervisor(configuration: config, baseEnvironment: AppModel.engineBaseEnvironment(env))
        sampler = HostSampler(volume: paths.data)
        #if DEBUG
        demo = env["BANDROOM_DEMO"] != nil
        #else
        demo = false
        #endif
        // A checkout that already has its environment needs no first-run setup.
        let checkoutReady: Bool = if case .checkout = source { source.isEnvironmentReady } else { false }
        setupComplete = UserDefaults.standard.bool(forKey: "setupComplete") || checkoutReady || demo
        loginItemEnabled = SMAppService.mainApp.status == .enabled

        let log = logger
        supervisor.log = { log.write($0) }
        supervisor.onHealthy = { [weak self] client in self?.engineAnswered(client) }
        supervisor.onFailure = { [weak self] _ in self?.notifyFailure() }
        monitor.onNewRequest = { [weak self] r in self?.pairRequestArrived(r) }
        monitor.onJobsChanged = { [weak self] n in self?.jobsChanged(n) }
        log.write("Bandroom \(Bundle.main.shortVersion) starting; data \(paths.data.path); source \(source)")
    }

    /// Adds the Hugging Face key from the Keychain for the model downloads.
    static func engineBaseEnvironment(_ env: [String: String]) -> [String: String] {
        var env = env
        if env["HF_TOKEN"] == nil, let key = HuggingFaceKey.read() { env["HF_TOKEN"] = key }
        return env
    }

    func log(_ line: String) { logger.write(line) }

    // MARK: lifecycle

    func launch() {
        monitor.start()
        startSampling()
        #if DEBUG
        if demo {
            let engine = DemoEngine(busy: environment["BANDROOM_DEMO"] == "busy")
            monitor.client = engine
            pairing.client = engine
            return
        }
        #endif
        supervisor.reapStrayEngine()
        if setupComplete {
            supervisor.start()
        } else {
            openWindow?("setup")
        }
    }

    func quit() {
        monitor.stop()
        supervisor.shutdown()
        releaseSleep()
    }

    private func engineAnswered(_ client: any EngineAPI) {
        monitor.client = client
        pairing.client = client
        // The engine opens a code at start that would stay valid until closed; codes should only work while
        // the Pair window is open (§3.4).
        if isPairWindowOpen {
            Task { await pairing.open() }
        } else {
            Task { _ = try? await client.closePairing() }
        }
    }

    private func startSampling() {
        sampleTask?.cancel()
        let sampler = sampler, paths = paths
        sampleTask = Task { [weak self] in
            while !Task.isCancelled {
                let snap = await Task.detached { sampler.sample() }.value
                let models = await Task.detached { ModelCheck.check(models: AppModel.modelsDir(paths)) }.value
                self?.host = snap
                self?.models = (self?.demo ?? false) ? .init(missing: []) : models
                self?.announceIfChanged()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    nonisolated static func modelsDir(_ paths: BandroomPaths) -> URL {
        let env = ProcessInfo.processInfo.environment
        if let checkout = env["BRASSCRIBE_CHECKOUT"] ?? UserDefaults.standard.string(forKey: "engineCheckout"), !checkout.isEmpty,
           !FileManager.default.fileExists(atPath: paths.models.path) {
            return URL(fileURLWithPath: (checkout as NSString).expandingTildeInPath).appending(path: "models")
        }
        return paths.models
    }

    // MARK: state

    var problems: [Problem] {
        var list: [Problem] = []
        if let host, host.isDiskLow { list.append(.lowDisk(freeGB: host.diskFreeGB)) }
        if case .running = phase, !models.isReady { list.append(.missingDownload) }
        return list
    }

    var setupPercent: Int? {
        setupComplete ? nil : bootstrapper.percent
    }

    var displayState: DisplayState {
        let jobPercent: Int? = (monitor.status?.jobsRunning ?? 0) > 0 ? (monitor.job?.percent ?? 0) : nil
        return DisplayState.resolve(setupPercent: setupPercent, phase: phase, updating: false,
                                    problems: problems, jobPercent: jobPercent)
    }

    var isRunning: Bool { phase == .running }

    /// The engine's phase; a screenshot demo pretends it runs.
    var phase: SupervisorPhase { demo ? .running : supervisor.phase }
    var isBusy: Bool { (monitor.status?.jobsRunning ?? 0) > 0 }
    var serverName: String { monitor.status?.serverName ?? "Brasscribe on \(supervisor.configuration.computerName)" }
    var hostName: String { ComputerName.host(fromServerName: serverName) }

    private func announceIfChanged() {
        let state = displayState
        let comparable: DisplayState = if case .busy = state { .busy(percent: 0) } else { state }
        guard comparable != lastAnnounced else { return }
        let first = lastAnnounced == nil
        lastAnnounced = comparable
        // Only while someone is looking at the panel; the Error notification covers the rest (6.3).
        guard !first, monitor.isPanelOpen else { return }
        AccessibilityNotification.Announcement(Strings.tooltip(state, connected: monitor.status?.onlineDevices ?? 0)).post()
    }

    // MARK: actions

    func start() { supervisor.start() }

    func stopNow() {
        restartWhenDone = false
        monitor.client = nil
        pairing.client = nil
        supervisor.stop()
    }

    func restartNow() {
        restartWhenDone = false
        monitor.client = nil
        pairing.client = nil
        supervisor.restart()
    }

    func tryAgain() {
        if case .failed(.notInstalled) = supervisor.phase {
            openWindow?("setup")
            return
        }
        supervisor.start()
    }

    func openStudio() {
        guard let port = supervisor.port, isRunning else { return }
        NSWorkspace.shared.open(URL(string: "http://127.0.0.1:\(port)/")!)
    }

    func showLogs() {
        let log = FileManager.default.fileExists(atPath: paths.engineLog.path) ? paths.engineLog : paths.logs
        NSWorkspace.shared.activateFileViewerSelecting([log])
    }

    func openPrivacySettings() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocalNetwork")!)
    }

    func openStorageSettings() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.settings.Storage")!)
    }

    func copyDiagnostics() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(diagnostics(), forType: .string)
    }

    func diagnostics() -> String {
        var lines = ["Brasscribe Bandroom \(Bundle.main.shortVersion)", "macOS \(ProcessInfo.processInfo.operatingSystemVersionString)",
                     "Chip: \(HostSampler.chipName())", "State: \(supervisor.phase)"]
        if let s = monitor.status {
            lines += ["Server: \(s.serverName) (\(s.serverId))", "Engine version: \(s.version)",
                      "Phones: \(s.onlineDevices) connected, \(s.pairedDevices) paired", "Jobs: \(s.jobsRunning) running, \(s.jobsQueued) waiting"]
        }
        if let port = supervisor.port { lines.append("Port: \(port)") }
        lines.append("Addresses: \(addresses.joined(separator: ", "))")
        if let h = monitor.health { lines.append("Runs on: \(h.device)") }
        if let last = supervisor.lastExitStatus { lines.append("Last exit status: \(last)") }
        lines.append("Data: \(paths.data.path)")
        lines.append("Logs: \(paths.logs.path)")
        if !models.missing.isEmpty { lines.append("Missing: \(models.missing.joined(separator: ", "))") }
        if let host { lines.append(String(format: "CPU %.0f%%, memory free %.0f%%, disk free %d GB", host.cpuPercent, host.memoryFreePercent, host.diskFreeGB)) }
        return lines.joined(separator: "\n")
    }

    /// LAN addresses the engine listens on, from the pairing payload.
    var addresses: [String] {
        let hosts = pairing.state?.hosts ?? []
        if !hosts.isEmpty { return hosts }
        return LANAddresses.current().map { "\($0):\(supervisor.port ?? 8765)" }
    }

    func setLoginItem(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            logger.write("login item: \(error)")
        }
        loginItemEnabled = SMAppService.mainApp.status == .enabled
    }

    // MARK: remove from this Mac (§3.10)

    /// The downloads folder in GB, when there is one to keep or delete.
    func downloadsGB() -> Double? {
        Uninstaller(paths: paths).downloadsSize().map { Double($0) / 1_000_000_000 }
    }

    /// Stops the engine, unregisters the login item, deletes the data folder (all of it, or all but
    /// the downloads) and the logs, forgets the access key and settings, moves the app to the Bin and
    /// quits. Scores on the phones are theirs and are not touched.
    func removeFromThisMac(deleteDownloads: Bool) {
        logger.write("removing Brasscribe from this Mac (delete downloads: \(deleteDownloads))")
        if demo { NSApp.terminate(nil); return }
        monitor.stop()
        supervisor.shutdown()
        releaseSleep()
        try? SMAppService.mainApp.unregister()
        do {
            try Uninstaller(paths: paths).remove(keepDownloads: !deleteDownloads)
        } catch {
            logger.write("remove: \(error)")
        }
        HuggingFaceKey.delete()
        if let id = Bundle.main.bundleIdentifier { UserDefaults.standard.removePersistentDomain(forName: id) }
        let app = Bundle.main.bundleURL
        NSWorkspace.shared.recycle([app]) { _, error in
            // Where the app can't be moved (a read-only disk image), show it so it can be dragged to the Bin.
            if error != nil { NSWorkspace.shared.activateFileViewerSelecting([app]) }
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
    }

    func finishSetup(startAtLogin: Bool) {
        setupComplete = true
        if startAtLogin && environment["BANDROOM_NO_LOGIN_ITEM"] == nil { setLoginItem(true) }
        supervisor.configuration.source = EngineConfiguration.resolveSource(environment: environment, defaults: .standard, paths: paths, bundle: .main)
        if !isRunning { supervisor.start() }
    }

    // MARK: pairing requests

    @discardableResult
    func decide(_ request: PairRequestInfo, approve: Bool) async -> Bool {
        let ok = (try? await monitor.decide(request, approve: approve)) ?? false
        if !ok && approve { expiredRequest = request.name }
        return ok
    }

    private func pairRequestArrived(_ r: PairRequestInfo) {
        guard !isPairWindowOpen else { return }
        Notifier.pairRequest(r)
    }

    private func notifyFailure() {
        Notifier.post(id: "engine-error", title: String(localized: "Brasscribe stopped unexpectedly"),
                      body: String(localized: "It tried to start three times. Recordings on your phones are safe."))
    }

    // MARK: jobs

    private func jobsChanged(_ running: Int) {
        if running > 0 { holdSleep() } else { releaseSleep() }
        if running == 0 && restartWhenDone {
            restartNow()
        }
    }

    /// Don't idle-sleep while a score is being made; never blocks lid-close or a sleep the user asks for.
    private func holdSleep() {
        guard sleepAssertion == 0 else { return }
        IOPMAssertionCreateWithName(kIOPMAssertPreventUserIdleSystemSleep as CFString, IOPMAssertionLevel(kIOPMAssertionLevelOn),
                                    "Brasscribe is making a score" as CFString, &sleepAssertion)
    }

    private func releaseSleep() {
        guard sleepAssertion != 0 else { return }
        IOPMAssertionRelease(sleepAssertion)
        sleepAssertion = 0
    }
}

extension Bundle {
    var shortVersion: String { infoDictionary?["CFBundleShortVersionString"] as? String ?? "?" }
}

/// Appends lines to ~/Library/Logs/Brasscribe/bandroom.log.
final class FileLogger: @unchecked Sendable {
    private let url: URL
    private let queue = DispatchQueue(label: "bandroom.log")

    init(url: URL) { self.url = url }

    func write(_ line: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let data = Data("\(stamp) \(line)\n".utf8)
        queue.async { [url] in
            if let h = try? FileHandle(forWritingTo: url) {
                h.seekToEndOfFile(); h.write(data); try? h.close()
            } else {
                try? data.write(to: url)
            }
        }
    }
}

enum LANAddresses {
    /// IPv4 addresses on active, non-loopback interfaces.
    static func current() -> [String] {
        var result: [String] = []
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return [] }
        defer { freeifaddrs(ifaddr) }
        for ptr in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let flags = Int32(ptr.pointee.ifa_flags)
            guard let addr = ptr.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET),
                  flags & IFF_UP != 0, flags & IFF_LOOPBACK == 0 else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            if getnameinfo(addr, socklen_t(addr.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST) == 0 {
                let s = String(decoding: host.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
                if !s.hasPrefix("169.254") { result.append(s) }
            }
        }
        return result
    }
}

/// The Hugging Face access key, kept in the Keychain, never in a file (§3.2 step 2).
enum HuggingFaceKey {
    static let service = "no.brasscribe.bandroom.huggingface"

    static func read() -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func delete() {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service] as CFDictionary)
    }

    @discardableResult
    static func save(_ key: String) -> Bool {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service]
        SecItemDelete(base as CFDictionary)
        var add = base
        add[kSecValueData as String] = Data(key.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }
}

/// Sparse notifications (§6.3): pair requests while the Pair window is closed, and Error.
enum Notifier {
    static let pairCategory = "pair-request"

    static func setUp(delegate: UNUserNotificationCenterDelegate) {
        let center = UNUserNotificationCenter.current()
        center.delegate = delegate
        let allow = UNNotificationAction(identifier: "allow", title: String(localized: "Allow"), options: [])
        let deny = UNNotificationAction(identifier: "deny", title: String(localized: "Don't allow"), options: [])
        center.setNotificationCategories([UNNotificationCategory(identifier: pairCategory, actions: [allow, deny], intentIdentifiers: [])])
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func pairRequest(_ r: PairRequestInfo) {
        let content = UNMutableNotificationContent()
        content.title = String(localized: "\(r.name) wants to use this computer.")
        content.body = String(localized: "The phone shows the number: \(r.matchCode)")
        content.categoryIdentifier = pairCategory
        content.userInfo = ["request_id": r.requestId, "name": r.name, "platform": r.platform, "match_code": r.matchCode]
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "pair-\(r.requestId)", content: content, trigger: nil))
    }

    static func post(id: String, title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: id, content: content, trigger: nil))
    }
}

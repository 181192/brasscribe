import Darwin
import Foundation

/// A command to run the engine: what, where, with which environment, and where its output goes.
public struct LaunchPlan: Equatable, Sendable {
    public var executable: URL
    public var arguments: [String]
    public var environment: [String: String]
    public var workingDirectory: URL
    public var log: URL
    public var port: Int

    public init(executable: URL, arguments: [String], environment: [String: String], workingDirectory: URL, log: URL, port: Int) {
        self.executable = executable; self.arguments = arguments; self.environment = environment
        self.workingDirectory = workingDirectory; self.log = log; self.port = port
    }
}

public protocol ProcessLauncher: Sendable {
    /// Starts the process in its own process group; `onExit` gets the wait status once it has exited. When it exits by
    /// itself (not through `terminate`), whatever is left in its group is killed first: an engine whose `pixi run`
    /// died must not keep the port or the graphics chip.
    func launch(_ plan: LaunchPlan, onExit: @escaping @Sendable (Int32) -> Void) throws -> Int32
    /// SIGTERM to the whole group, then SIGKILL after `grace` seconds if anything is left.
    func terminate(pid: Int32, grace: TimeInterval)
}

/// posix_spawn with a new process group, so `pixi run` and the Python engine under it stop together.
public final class PosixLauncher: ProcessLauncher, @unchecked Sendable {
    private let lock = NSLock()
    /// Groups asked to stop: `terminate` gives them their grace period.
    private var terminating: Set<Int32> = []

    public init() {}

    public func launch(_ plan: LaunchPlan, onExit: @escaping @Sendable (Int32) -> Void) throws -> Int32 {
        try FileManager.default.createDirectory(at: plan.log.deletingLastPathComponent(), withIntermediateDirectories: true)
        LogRotation.rotate(plan.log, maxBytes: 10 << 20)
        let logFD = open(plan.log.path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0o644)
        guard logFD >= 0 else { throw LaunchFailure.spawn("can't open \(plan.log.path)") }
        defer { close(logFD) }
        let stamp = "\n--- \(Date()) \(plan.executable.path) \(plan.arguments.joined(separator: " "))\n"
        _ = stamp.withCString { write(logFD, $0, strlen($0)) }

        var attr: posix_spawnattr_t?
        posix_spawnattr_init(&attr)
        defer { posix_spawnattr_destroy(&attr) }
        posix_spawnattr_setflags(&attr, Int16(POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK))
        posix_spawnattr_setpgroup(&attr, 0)
        var none = sigset_t(), all = sigset_t()
        sigemptyset(&none)
        sigfillset(&all)
        posix_spawnattr_setsigmask(&attr, &none)
        posix_spawnattr_setsigdefault(&attr, &all)

        var actions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_adddup2(&actions, logFD, 1)
        posix_spawn_file_actions_adddup2(&actions, logFD, 2)
        posix_spawn_file_actions_addchdir_np(&actions, plan.workingDirectory.path)

        let argv = [plan.executable.path] + plan.arguments
        let envp = plan.environment.map { "\($0.key)=\($0.value)" }
        var pid: pid_t = 0
        let rc = withCStrings(argv) { cargv in
            withCStrings(envp) { cenv in
                posix_spawn(&pid, plan.executable.path, &actions, &attr, cargv, cenv)
            }
        }
        guard rc == 0 else { throw LaunchFailure.spawn(String(cString: strerror(rc))) }

        let waited = pid
        let thread = Thread { [self] in
            var status: Int32 = 0
            while waitpid(waited, &status, 0) == -1 && errno == EINTR {}
            // Right away, while the group id can't have been handed to anyone else.
            let asked = lock.withLock { terminating.remove(waited) != nil }
            if !asked { kill(-waited, SIGKILL) }
            onExit(status)
        }
        thread.name = "engine-wait-\(pid)"
        thread.start()
        return pid
    }

    public func terminate(pid: Int32, grace: TimeInterval) {
        guard pid > 0 else { return }
        lock.withLock { _ = terminating.insert(pid) }
        kill(-pid, SIGTERM)
        kill(pid, SIGTERM)
        DispatchQueue.global().asyncAfter(deadline: .now() + grace) {
            // Only if the group still exists.
            if kill(-pid, 0) == 0 { kill(-pid, SIGKILL) }
        }
    }

    /// Stops an engine left behind by an earlier Bandroom that didn't get to stop it (engine.json).
    public static func killStrayGroup(pid: Int32) {
        guard pid > 0, kill(-pid, 0) == 0 else { return }
        var name = [CChar](repeating: 0, count: 256)
        proc_name(pid, &name, UInt32(name.count))
        let proc = String(cString: name).lowercased()
        guard proc.contains("pixi") || proc.contains("python") || proc.contains("brasscribe") else { return }
        kill(-pid, SIGTERM)
        for _ in 0..<50 where kill(-pid, 0) == 0 { usleep(100_000) }
        if kill(-pid, 0) == 0 { kill(-pid, SIGKILL) }
    }
}

extension LaunchFailure: Error {}

/// A wait status in words, for logs and the tech-person details: "exit code 1", "signal 9".
public enum ExitStatus {
    public static func describe(_ status: Int32) -> String {
        let signal = status & 0x7f
        return signal == 0 ? "exit code \((status >> 8) & 0xff)" : "signal \(signal)"
    }
}

enum LogRotation {
    static func rotate(_ url: URL, maxBytes: Int) {
        let fm = FileManager.default
        guard let size = (try? fm.attributesOfItem(atPath: url.path)[.size]) as? Int, size > maxBytes else { return }
        let old = url.appendingPathExtension("1")
        try? fm.removeItem(at: old)
        try? fm.moveItem(at: url, to: old)
    }
}

private func withCStrings<R>(_ strings: [String], _ body: (UnsafePointer<UnsafeMutablePointer<CChar>?>) -> R) -> R {
    var pointers: [UnsafeMutablePointer<CChar>?] = strings.map { strdup($0) } + [nil]
    defer { pointers.forEach { free($0) } }
    return pointers.withUnsafeMutableBufferPointer { body($0.baseAddress!) }
}

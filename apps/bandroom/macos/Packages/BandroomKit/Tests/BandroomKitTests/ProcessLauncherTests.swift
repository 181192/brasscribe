import Darwin
import Foundation
import Testing
@testable import BandroomKit

private final class ExitBox: @unchecked Sendable {
    private let lock = NSLock()
    private var status: Int32?
    var value: Int32? { lock.withLock { status } }
    func set(_ s: Int32) { lock.withLock { status = s } }
}

/// The real launcher, with processes the test starts itself.
@Suite struct ProcessLauncherTests {
    /// Waits up to `seconds` for `condition`.
    private func eventually(_ seconds: Double = 5, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if condition() { return true }
            usleep(20_000)
        }
        return condition()
    }

    @Test func whatALeaderThatDiesLeavesBehindIsStopped() throws {
        let dir = tempDir()
        defer { try? FileManager.default.removeItem(at: dir) }
        let pidFile = dir.appending(path: "child.pid")
        // The group leader starts a child in its group, notes its pid, and exits by itself.
        let plan = LaunchPlan(executable: URL(fileURLWithPath: "/bin/sh"),
                              arguments: ["-c", "sleep 30 & echo $! > '\(pidFile.path)'; exit 3"],
                              environment: ["PATH": "/usr/bin:/bin"], workingDirectory: dir,
                              log: dir.appending(path: "out.log"), port: 0)
        let status = ExitBox()
        _ = try PosixLauncher().launch(plan) { status.set($0) }
        #expect(eventually { status.value != nil })
        #expect(status.value.map(ExitStatus.describe) == "exit code 3")
        let child = try #require(Int32(String(decoding: try Data(contentsOf: pidFile), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)))
        #expect(eventually { kill(child, 0) != 0 }, "the child left in the group is gone")
    }

    @Test func aStrayEngineIsOnlyTheProcessThatWasRunningWhenEngineJSONWasWritten() {
        let me = getpid()
        #expect(PosixLauncher.isRecordedProcess(pid: me, recordedAt: Date()))
        // A file older than the process: the number was handed to this process later.
        #expect(!PosixLauncher.isRecordedProcess(pid: me, recordedAt: Date(timeIntervalSince1970: 0)))
        #expect(!PosixLauncher.isRecordedProcess(pid: 99_999_999, recordedAt: Date()), "no such process")
    }

    @Test func exitStatusInWords() {
        #expect(ExitStatus.describe(0) == "exit code 0")
        #expect(ExitStatus.describe(256) == "exit code 1")
        #expect(ExitStatus.describe(9) == "signal 9")
        #expect(ExitStatus.describe(15) == "signal 15")
    }
}

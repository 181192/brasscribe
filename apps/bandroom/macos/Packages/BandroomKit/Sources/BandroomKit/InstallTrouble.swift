import Foundation

/// What stopped an install that fetches packages (`pixi install` of an environment, the reader's install), when its
/// output says: no connection, or a full disk. Anything else is told by the log.
public enum InstallTrouble: Equatable, Sendable {
    case network
    case diskFull

    /// What an installer (pixi, uv) says when it cannot reach where the packages are: the words of the HTTP and
    /// socket layers under it, which stay the same from one version to the next where its own wording does not.
    static let noConnection = ["error sending request", "dns error", "failed to lookup address", "tcp connect error",
                               "connection refused", "network is unreachable", "no route to host", "operation timed out"]
    /// What it, or the system under it, says when the disk is full.
    static let noSpace = ["no space left on device", "os error 28"]

    /// The last line of `output` that names a full disk or no connection; `refusals` are whole lines a runner of our
    /// own ends on, with what each means. Nil when it says neither.
    static func find(in output: String, refusals: [String: InstallTrouble] = [:]) -> InstallTrouble? {
        var why: InstallTrouble?
        for line in output.split(whereSeparator: \.isNewline) {
            let said = line.trimmingCharacters(in: .whitespaces).lowercased()
            if let r = refusals[said] {
                why = r
            } else if noSpace.contains(where: said.contains) {
                why = .diskFull
            } else if noConnection.contains(where: said.contains) {
                why = .network
            }
        }
        return why
    }

    /// What the latest run wrote to `log` says (`LatestRun`).
    static func inLatestRun(log: URL) -> InstallTrouble? {
        find(in: LatestRun.text(log: log))
    }
}

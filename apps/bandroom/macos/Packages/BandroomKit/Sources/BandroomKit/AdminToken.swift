import Foundation
import Security

/// The local admin credential for the engine's owner endpoints (/v1/status, /v1/devices, /v1/pairing…).
/// Bandroom creates it once, owner-only (0600), passes it to the engine as BRASSCRIBE_ADMIN_TOKEN and
/// sends it as a bearer token.
public enum AdminToken {
    public enum Failure: Error, Equatable {
        case unreadable(String)
        case insecurePermissions(UInt16)
    }

    /// Reads the token at `url`, or creates it atomically with mode 0600 if it does not exist.
    public static func loadOrCreate(at url: URL) throws -> String {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let fd = open(url.path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
        if fd >= 0 {
            let token = generate()
            let bytes = Array((token + "\n").utf8)
            let written = bytes.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
            close(fd)
            if written != bytes.count {
                try? FileManager.default.removeItem(at: url)
                throw Failure.unreadable("could not write \(url.path)")
            }
            return token
        }
        guard errno == EEXIST else { throw Failure.unreadable(String(cString: strerror(errno))) }
        var info = stat()
        guard stat(url.path, &info) == 0 else { throw Failure.unreadable(String(cString: strerror(errno))) }
        let mode = UInt16(info.st_mode) & 0o777
        if mode & 0o077 != 0 {
            // Someone widened it: narrow it again rather than hand out a readable secret.
            guard chmod(url.path, 0o600) == 0 else { throw Failure.insecurePermissions(mode) }
        }
        let text = try String(contentsOf: url, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        // Empty or cut short (Bandroom stopped between creating the file and writing it): make a new one in its
        // place, so the next launch doesn't have to.
        guard text.count >= 32 else { return try replace(at: url) }
        return text
    }

    /// A new token written beside `url` and renamed over it, so the file is never seen half written.
    static func replace(at url: URL) throws -> String {
        let temp = url.deletingLastPathComponent().appending(path: ".\(url.lastPathComponent).\(UUID().uuidString)")
        let fd = open(temp.path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw Failure.unreadable(String(cString: strerror(errno))) }
        let token = generate()
        let bytes = Array((token + "\n").utf8)
        let written = bytes.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        let synced = fsync(fd) == 0
        close(fd)
        guard written == bytes.count, synced, rename(temp.path, url.path) == 0 else {
            try? FileManager.default.removeItem(at: temp)
            throw Failure.unreadable("could not replace \(url.path)")
        }
        return token
    }

    /// 32 random bytes, hex.
    public static func generate() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        precondition(status == errSecSuccess, "no system randomness")
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}

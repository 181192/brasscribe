import Foundation

/// Something went wrong. Every problem says what happened (title), why (one or two
/// reasons), and offers the way forward (actions, the most likely fix first). The
/// technical detail, if any, is kept for "Details for the band's tech person".
enum Problem: Hashable, Identifiable {
    case copyProtected
    case silence
    case cantOpenFile(String)
    case notAScore(String)
    case demoMissing
    case arrangeFailed(String)

    enum Action: Hashable { case importFile, recordMic, home }

    var id: String { "\(self)" }

    var title: String {
        switch self {
        case .copyProtected: return String(localized: "This recording is copy-protected")
        case .silence: return String(localized: "Nothing was heard")
        case .cantOpenFile: return String(localized: "This file can't be opened")
        case .notAScore: return String(localized: "This isn't a score Brasscribe can read")
        case .demoMissing: return String(localized: "The demo isn't on this device")
        case .arrangeFailed: return String(localized: "The score couldn't be arranged")
        }
    }

    var lead: String? {
        switch self {
        case .silence: return String(localized: "The recording is silent. This usually means one of these:")
        case .copyProtected: return String(localized: "Brasscribe can't use it, for one of these reasons:")
        default: return nil
        }
    }

    var reasons: [String] {
        switch self {
        case .copyProtected:
            return [String(localized: "Music and video from streaming apps and shops are usually copy-protected."),
                    String(localized: "The system doesn't let any app record or read protected music.")]
        case .silence:
            return [String(localized: "The music app blocks recording. Streaming apps usually do."),
                    String(localized: "Nothing was playing while you recorded.")]
        case .cantOpenFile:
            return [String(localized: "Try an MP3, WAV, M4A or MP4 file.")]
        case .notAScore:
            return [String(localized: "Brasscribe opens MusicXML scores and its own score files.")]
        case .demoMissing:
            return [String(localized: "The demo recording wasn't included with this copy of Brasscribe.")]
        case .arrangeFailed:
            return [String(localized: "Brasscribe couldn't make brass-band parts from this score.")]
        }
    }

    var hint: String? {
        switch self {
        case .copyProtected, .silence: return String(localized: "A file you own, or a recording with the microphone, always works.")
        default: return nil
        }
    }

    /// The error text from the system, shown only under the tech-person disclosure.
    var detail: String? {
        switch self {
        case .cantOpenFile(let d), .notAScore(let d), .arrangeFailed(let d): return d.isEmpty ? nil : d
        default: return nil
        }
    }

    var actions: [Action] {
        switch self {
        case .copyProtected, .silence: return [.importFile, .recordMic]
        case .cantOpenFile, .notAScore: return [.importFile, .recordMic]
        case .demoMissing, .arrangeFailed: return [.importFile, .home]
        }
    }
}

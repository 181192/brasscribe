import BandroomKit
import Foundation

/// Words for states and values (design/server-app.md §10). English keys; bokmål in Localizable.xcstrings.
enum Strings {
    static func tooltip(_ state: DisplayState, connected: Int) -> String {
        switch state {
        case .settingUp(let n): String(localized: "Brasscribe: setting up, \(n)%")
        case .starting: String(localized: "Brasscribe: starting")
        case .running:
            connected == 1 ? String(localized: "Brasscribe: running · 1 phone connected")
                : String(localized: "Brasscribe: running · \(connected) phones connected")
        case .busy(let n): String(localized: "Brasscribe: making a score, \(n)%")
        case .attention(let p): String(localized: "Brasscribe needs attention: \(problemInSentence(p))")
        case .stopped: String(localized: "Brasscribe: stopped")
        case .updating: String(localized: "Brasscribe: updating")
        case .error: String(localized: "Brasscribe stopped unexpectedly")
        }
    }

    /// The status line under the header.
    static func statusWord(_ state: DisplayState) -> String {
        switch state {
        case .settingUp: String(localized: "Setting up")
        case .starting: String(localized: "Starting…")
        case .running: String(localized: "Running")
        case .busy: String(localized: "Running · Making a score")
        case .attention: String(localized: "Needs attention")
        case .stopped: String(localized: "Stopped")
        case .updating: String(localized: "Updating")
        case .error: String(localized: "Stopped unexpectedly")
        }
    }

    /// Why the engine was given up on (Error, and the notification): three failed starts, or a start that
    /// couldn't happen at all.
    static func failureTitle(_ why: LaunchFailure?) -> String {
        switch why {
        case nil: String(localized: "Brasscribe stopped unexpectedly")
        case .spawn: problemTitle(.noFreePort)
        case .noFreePort: problemTitle(.noFreePort)
        case .notInstalled: problemTitle(.missingDownload([]))
        }
    }

    static func failureWhy(_ why: LaunchFailure?) -> String {
        switch why {
        case nil: String(localized: "It tried to start three times. Recordings on your phones are safe.")
        case .spawn: String(localized: "It couldn't be started. Recordings on your phones are safe.")
        case .noFreePort: problemWhy(.noFreePort)
        case .notInstalled: problemWhy(.missingDownload([]))
        }
    }

    static func problemTitle(_ p: Problem) -> String {
        switch p {
        case .lowDisk: String(localized: "Space is running low")
        case .missingDownload: String(localized: "Full-band scores need one more step")
        case .noFreePort: String(localized: "Brasscribe can't start")
        case .updateFailed: String(localized: "Brasscribe couldn't finish updating")
        case .notResponding: String(localized: "Brasscribe isn't answering")
        }
    }

    /// The problem inside "Brasscribe needs attention: …".
    static func problemInSentence(_ p: Problem) -> String {
        switch p {
        case .lowDisk: String(localized: "space is running low")
        case .missingDownload: String(localized: "full-band scores need one more step")
        case .noFreePort: String(localized: "Brasscribe can't start")
        case .updateFailed: String(localized: "Brasscribe couldn't finish updating")
        case .notResponding: String(localized: "Brasscribe isn't answering")
        }
    }

    static func problemWhy(_ p: Problem) -> String {
        switch p {
        case .lowDisk(let gb): String(localized: "\(gb) GB free. Brasscribe needs 3 GB to make a score.")
        case .missingDownload(let missing): notDownloaded(missing)
        case .noFreePort: String(localized: "Another program on this computer is in the way.")
        case .updateFailed: String(localized: "The previous version is still running, so phones can keep sending recordings.")
        case .notResponding: String(localized: "It is running but hasn't answered for a while. Restarting it usually helps.")
        }
    }

    static func problemFix(_ p: Problem) -> String {
        switch p {
        case .lowDisk: String(localized: "Free up space…")
        case .missingDownload: String(localized: "Finish setting up")
        case .noFreePort: String(localized: "Restart")
        case .updateFailed: String(localized: "Try again")
        case .notResponding: String(localized: "Restart")
        }
    }

    /// "the soloist separator": the component inside a sentence.
    static func componentName(_ c: ModelComponent) -> String {
        switch c {
        case .soloistSeparator: String(localized: "the soloist separator")
        case .instrumentSeparator: String(localized: "the instrument separator")
        case .bandWriter: String(localized: "the band writer")
        }
    }

    /// The setup window's list: "Band writer (MuScriptor)" is the one place the model is named (§3.2.1).
    static func componentItem(_ c: ModelComponent) -> String {
        switch c {
        case .soloistSeparator: String(localized: "Soloist separator")
        case .instrumentSeparator: String(localized: "Instrument separator")
        case .bandWriter: String(localized: "Band writer (MuScriptor)")
        }
    }

    /// "The band writer isn't downloaded yet." · "The soloist separator and the band writer aren't downloaded yet."
    static func notDownloaded(_ missing: [ModelComponent]) -> String {
        switch missing.count {
        case 0: return String(localized: "Brasscribe's own tools aren't installed yet.")
        case 1:
            switch missing[0] {
            case .soloistSeparator: return String(localized: "The soloist separator isn't downloaded yet.")
            case .instrumentSeparator: return String(localized: "The instrument separator isn't downloaded yet.")
            case .bandWriter: return String(localized: "The band writer isn't downloaded yet.")
            }
        default:
            // In the app's language ("og" in bokmål), not the region's.
            let f = ListFormatter()
            f.locale = Locale(identifier: Bundle.main.preferredLocalizations.first ?? "en")
            let list = f.string(from: missing.map(componentName)) ?? missing.map(componentName).joined(separator: ", ")
            return capitalizedFirst(String(localized: "\(list) aren't downloaded yet."))
        }
    }

    /// "Missing one download" · "Missing 2 downloads".
    static func missingDownloads(_ n: Int) -> String {
        n == 1 ? String(localized: "Missing one download") : String(localized: "Missing \(n) downloads")
    }

    static func capitalizedFirst(_ s: String) -> String { s.prefix(1).uppercased() + s.dropFirst() }

    /// "1.4 GB", "3.1 of 9.8 GB".
    static func gigabytes(_ bytes: Int64) -> String {
        let gb = Double(bytes) / 1_000_000_000
        return gb.formatted(.number.precision(.fractionLength(1)))
    }

    static func step(_ s: JobStep) -> String {
        switch s {
        case .preparing: String(localized: "Getting the recording ready")
        case .findingBeat: String(localized: "Finding the beat")
        case .separatingInstruments: String(localized: "Separating the instruments")
        case .separatingSoloist: String(localized: "Separating the soloist from the band")
        case .transcribing: String(localized: "Writing down the notes")
        case .arranging: String(localized: "Arranging for brass band")
        case .engraving: String(localized: "Laying out the pages")
        }
    }

    static func load(_ w: WorkLoad) -> String {
        switch w {
        case .calm: String(localized: "Calm")
        case .busy: String(localized: "Busy")
        case .veryBusy: String(localized: "Very busy")
        }
    }

    static func memory(_ m: MemoryLevel) -> String {
        switch m {
        case .plentyFree: String(localized: "Plenty free")
        case .gettingFull: String(localized: "Getting full")
        case .almostFull: String(localized: "Almost full")
        }
    }

    static func devicesSummary(connected: Int, paired: Int) -> String {
        connected == 0 ? String(localized: "None connected now · \(paired) paired")
            : String(localized: "\(connected) connected now · \(paired) paired")
    }

    /// "Connected now", "Last used 3 days ago", "Last used 26 September".
    static func lastUsed(_ d: DeviceInfo, now: Date = Date()) -> String {
        if d.isOnline(now: now) { return String(localized: "Connected now") }
        guard let seen = d.lastSeenDate else { return String(localized: "Paired") }
        let days = Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: seen),
                                                   to: Calendar.current.startOfDay(for: now)).day ?? 0
        let when: String
        if days < 7 {
            let f = RelativeDateTimeFormatter()
            f.unitsStyle = .full
            f.dateTimeStyle = .named
            when = f.localizedString(for: seen, relativeTo: now)
        } else {
            when = seen.formatted(.dateTime.day().month(.wide))
        }
        return String(localized: "Last used \(when)")
    }

    /// "4 8 2, 9 1 3": the code read digit by digit.
    static func codeForVoiceOver(_ code: String) -> String {
        let d = code.map(String.init)
        guard d.count == 6 else { return code.map(String.init).joined(separator: " ") }
        return String(localized: "Code: \(d[0]) \(d[1]) \(d[2]), \(d[3]) \(d[4]) \(d[5])")
    }

    /// "192 dot 0 dot 2 dot 20".
    static func addressForVoiceOver(_ ip: String) -> String {
        ip.split(separator: ".").joined(separator: String(localized: " dot "))
    }

    static func runsOn(_ device: String?) -> String {
        switch device?.lowercased() {
        case "mps": "MPS · \(HostSampler.chipName()) · \(ProcessInfo.processInfo.physicalMemory / 1_073_741_824) GB"
        case "cuda": "CUDA"
        case "cpu": "CPU"
        default: device ?? "–"
        }
    }
}

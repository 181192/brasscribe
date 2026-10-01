import Foundation
import TranscriptionKit

/// What went wrong, in the player's words: the engine's refusal codes, the connection, the core's
/// refusals. The engine's and the core's own text is English; it stays in the problem screen's
/// details, never in the reasons or a notice.
enum ErrorWords {
    /// The core's refusal of a drummer's solo take (instruments.rs PERCUSSION_SOLO).
    private static let corePercussionSolo = "percussion can't be written down from a solo take"

    /// The words for `error`, or nil when nothing more specific than "it failed" is known.
    static func specific(_ error: Error) -> String? {
        switch error {
        case TranscriptionError.needsWholeGroup: return String(localized: "Needs a recording of the whole group")
        case TranscriptionError.notPaired, TranscriptionError.pairingRejected:
            return String(localized: "Your computer no longer knows this device. Connect them again in Settings.")
        case TranscriptionError.unreachable: return unreachable
        case TranscriptionError.jobFailed: return String(localized: "Brasscribe on your computer couldn't finish the score. Try again.")
        case TranscriptionError.http(let status, let body): return http(status, code: engineCode(body))
        case is DraftTooLong: return draftTooLong(computerThere: false)
        case let e as URLError:
            return e.code == .timedOut ? String(localized: "Your computer took too long to answer. Try again.") : unreachable
        default:
            if "\(error)".contains(corePercussionSolo) || error.localizedDescription.contains(corePercussionSolo) {
                return Seats.percussionSoloRefused
            }
            return nil
        }
    }

    /// A recording too long for a draft on this device: the computer makes the score from it, when it is there.
    static func draftTooLong(computerThere: Bool) -> String {
        computerThere ? String(localized: "Your computer can make the score from this recording.")
            : String(localized: "Open Brasscribe on your computer to make the score from this recording, or choose a shorter one.")
    }

    /// A title more specific than "The score couldn't be made", when there is one.
    static func title(_ error: Error) -> String? {
        error is DraftTooLong ? String(localized: "Too long for a draft on this device") : nil
    }

    /// The words for `error`, a generic line when nothing more is known.
    static func plain(_ error: Error) -> String { specific(error) ?? String(localized: "Something went wrong. Try again.") }

    private static var unreachable: String {
        String(localized: "Can't reach Brasscribe on your computer. Check that it is running and on the same network.")
    }

    /// The `code` of an engine error body ({"code": ..., "detail": ...}); nil for anything else.
    static func engineCode(_ body: String) -> String? {
        if let obj = (try? JSONSerialization.jsonObject(with: Data(body.utf8))) as? [String: Any], let c = obj["code"] as? String { return c }
        // a body cut short still starts with its code
        guard let r = body.range(of: #""code"\s*:\s*"([a-z_]+)""#, options: .regularExpression) else { return nil }
        return body[r].split(separator: "\"").dropFirst(2).first.map(String.init)
    }

    static func http(_ status: Int, code: String?) -> String? {
        switch code {
        case "quartet_needs_group": return String(localized: "Needs a recording of the whole group")
        case "percussion_solo": return Seats.percussionSoloRefused
        case "seat_no_tune": return String(localized: "The tune can't go on your part in this band. Under Who plays the tune?, choose the band's usual part.")
        case "reads_not_offered": return String(localized: "Your instrument isn't written in that clef. Choose again under What you play.")
        case "invalid_options": return invalidOptions
        default:
            switch status {
            case 401, 403: return String(localized: "Your computer no longer knows this device. Connect them again in Settings.")
            case 408, 504: return String(localized: "Your computer took too long to answer. Try again.")
            case 422: return invalidOptions
            case 500...599: return String(localized: "Brasscribe on your computer couldn't finish the score. Try again.")
            default: return nil
            }
        }
    }

    private static var invalidOptions: String {
        String(localized: "Brasscribe on your computer didn't accept these choices. It may need an update.")
    }
}

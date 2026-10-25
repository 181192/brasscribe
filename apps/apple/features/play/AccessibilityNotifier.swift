import SwiftUI
#if os(macOS)
import AppKit
#endif

/// What VoiceOver is told, and whether it is running.
enum AccessibilityNotifier {
    /// VoiceOver is on (or a test says so with `-stand-assistive`).
    @MainActor static var screenReaderRunning: Bool {
        if ProcessInfo.processInfo.arguments.contains("-stand-assistive") { return true }
        #if os(iOS)
        return UIAccessibility.isVoiceOverRunning
        #else
        return NSWorkspace.shared.isVoiceOverEnabled
        #endif
    }

    /// `polite`: queued after what is being read, for background changes such as the connection.
    @MainActor static func announce(_ s: String, polite: Bool = false) {
        #if os(iOS)
        if polite {
            var text = AttributedString(s)
            text.accessibilitySpeechAnnouncementPriority = .low
            AccessibilityNotification.Announcement(text).post()
        } else {
            UIAccessibility.post(notification: .announcement, argument: s)
        }
        #else
        NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested,
                             userInfo: [.announcement: s,
                                        .priority: (polite ? NSAccessibilityPriorityLevel.medium : .high).rawValue])
        #endif
    }
}

import SwiftUI
import TranscriptionKit
#if os(iOS)
import UIKit
#endif

/// What the shared Play screens ask of the app they are in: the computer and the connection to it, and where a new
/// recording or a problem goes. Each product's app model is one; the screens find it in the environment
/// (`.playHost(model)`).
@MainActor
protocol PlayHost: AnyObject, Observable {
    /// The paired computer and the connection to it.
    var connection: ConnectionMonitor { get }
    /// The address typed under "Details for the tech person", used to pair by code.
    var companionURL: String { get set }
    /// A `scribe://pair` link opened from outside the app, waiting for Settings to ask before it pairs.
    var pendingLink: PairingLink? { get set }
    /// Settings is open (the connection row's "Connect" and "Pair again" open it).
    var showSettings: Bool { get set }
    /// The device was paired: what the app lists from the computer is fetched again.
    func pairedWithComputer() async
    /// The connection changed: what the app lists from the computer is fetched again, or goes.
    func connectionChanged() async
    /// A take was recorded: the app asks what it is.
    func recorded(_ url: URL, title: String)
    /// A take was silent: the app says so, and nothing is kept.
    func recordedSilence()
}

extension EnvironmentValues {
    /// The app the shared Play screens are in.
    @Entry var playHost: (any PlayHost)? = nil
}

extension View {
    /// Gives the shared Play screens their app.
    func playHost(_ host: any PlayHost) -> some View { environment(\.playHost, host) }
}

/// This device, as the computer lists it.
enum ThisDevice {
    static var name: String {
        #if os(iOS)
        UIDevice.current.name
        #else
        Host.current().localizedName ?? "Mac"
        #endif
    }

    static var platform: String {
        #if os(iOS)
        "ios"
        #else
        "macos"
        #endif
    }
}

/// Titles people can tell recordings apart by.
enum RecordingTitles {
    /// "Recording, 26 Sep 19:02"
    static func recording(at date: Date) -> String {
        String(localized: "Recording, \(date.formatted(.dateTime.day().month(.abbreviated))) \(date.formatted(.dateTime.hour().minute()))")
    }
}

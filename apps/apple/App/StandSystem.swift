import SwiftUI
#if os(iOS)
import UIKit
#else
import AppKit
#endif

/// What the music stand asks of the system: the screen stays awake, the rotation lock (iPhone
/// only), and whether a keyboard or switch needs the controls to stay.
@MainActor
enum StandSystem {
    #if os(macOS)
    private static var activity: NSObjectProtocol?
    #endif

    /// Keep the screen on while the stand is open.
    static func keepAwake(_ on: Bool) {
        #if os(iOS)
        UIApplication.shared.isIdleTimerDisabled = on
        #else
        if on, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(options: [.idleDisplaySleepDisabled, .userInitiated],
                                                             reason: "Reading from the music stand")
        } else if !on, let a = activity {
            ProcessInfo.processInfo.endActivity(a)
            activity = nil
        }
        #endif
    }

    /// The lock is offered on phones only: iPadOS and macOS ignore an app's orientation.
    static var canLockRotation: Bool {
        #if os(iOS)
        UIDevice.current.userInterfaceIdiom == .phone
        #else
        false
        #endif
    }

    /// Lock the way the phone is held now, or give rotation back to the system.
    static func lockRotation(_ on: Bool) {
        #if os(iOS)
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else { return }
        let now: UIInterfaceOrientation
        if #available(iOS 26, *) { now = scene.effectiveGeometry.interfaceOrientation } else { now = scene.interfaceOrientation }
        OrientationLock.mask = on ? mask(for: now) : .all
        scene.keyWindow?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
        if on { scene.requestGeometryUpdate(.iOS(interfaceOrientations: OrientationLock.mask)) }
        #endif
    }

    #if os(iOS)
    private static func mask(for o: UIInterfaceOrientation) -> UIInterfaceOrientationMask {
        switch o {
        case .landscapeLeft: .landscapeLeft
        case .landscapeRight: .landscapeRight
        case .portraitUpsideDown: .portraitUpsideDown
        default: .portrait
        }
    }
    #endif

    /// Full Keyboard Access on the Mac keeps the controls. iOS has no public check for it, and a
    /// hardware keyboard alone must not keep them: a Bluetooth page turner is a keyboard. There,
    /// focus in the layer (and Switch Control, which Full Keyboard Access users often have) keeps it.
    static var keyboardNeedsControls: Bool {
        if LaunchOptions.standIgnoreKeyboard { return false }
        #if os(iOS)
        return false
        #else
        return NSApp.isFullKeyboardAccessEnabled
        #endif
    }

    /// Switch Control on the Mac (SwiftUI's environment value covers iOS).
    static var switchControlRunning: Bool {
        #if os(macOS)
        NSWorkspace.shared.isSwitchControlEnabled
        #else
        UIAccessibility.isSwitchControlRunning
        #endif
    }
}

#if os(iOS)
/// The app delegate's only job: the orientations the stand's rotation lock allows.
final class OrientationLock: NSObject, UIApplicationDelegate {
    @MainActor static var mask: UIInterfaceOrientationMask = .all

    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        MainActor.assumeIsolated { Self.mask }
    }
}
#endif

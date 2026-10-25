import AVFoundation
import Foundation
import Testing
@testable import PlaybackKit

private final class TestBundleMarker: NSObject {}

/// The PlaybackEngineProbe executable, built next to the test bundle.
private func probeExecutable() -> URL? {
    let dir = Bundle(for: TestBundleMarker.self).bundleURL.deletingLastPathComponent()
    let exe = dir.appending(path: "PlaybackEngineProbe")
    return FileManager.default.isExecutableFile(atPath: exe.path) ? exe : nil
}

/// The Mac app runs in the App Sandbox. There, an in-process audio unit that is not marked
/// sandbox-safe fails to instantiate (error -3000), and AVAudioUnitEffect raises an Objective-C
/// exception that ends the app. This builds the engine the way opening a score does (a fresh
/// process, a background thread, nothing registered beforehand) inside a sandbox.
@Test func engineBuildsInASandboxedProcessOffTheMainThread() throws {
    let exe = try #require(probeExecutable(), "PlaybackEngineProbe is not built next to the test bundle")
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/sandbox-exec")
    p.arguments = ["-p", "(version 1)(allow default)", exe.path]
    let out = Pipe()
    p.standardOutput = out
    p.standardError = out
    try p.run()
    let log = String(decoding: out.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    p.waitUntilExit()
    #expect(p.terminationReason == .exit && p.terminationStatus == 0,
            "probe ended with \(p.terminationReason == .exit ? "exit" : "signal") \(p.terminationStatus):\n\(log)")
}

/// Both units are registered sandbox-safe, so the sandboxed app can instantiate them.
@Test func audioUnitsAreRegisteredSandboxSafe() throws {
    PlaybackEngine.prepare()
    for desc in [OutputStageAU.componentDescription, ConvolutionReverbAU.componentDescription] {
        var find = desc
        find.componentFlags = 0
        let comp = try #require(AudioComponentFindNext(nil, &find), "\(desc.componentSubType) is not registered")
        var registered = AudioComponentDescription()
        #expect(AudioComponentGetDescription(comp, &registered) == noErr)
        #expect(registered.componentFlags & AudioComponentFlags.sandboxSafe.rawValue != 0)
    }
}

/// An audio unit that cannot be made is a Swift error, not an exception that ends the app.
@Test func anEffectThatCannotBeMadeThrows() {
    let missing = AudioComponentDescription(componentType: kAudioUnitType_Effect, componentSubType: fourCC("none"),
                                            componentManufacturer: fourCC("Brsc"), componentFlags: 0, componentFlagsMask: 0)
    // AVFAudio raises for it; the error carries the exception's reason
    #expect(throws: PlaybackError.audioUnit("none: required condition is false: comp != nullptr")) {
        try PlaybackEngine.makeEffect(missing)
    }
}

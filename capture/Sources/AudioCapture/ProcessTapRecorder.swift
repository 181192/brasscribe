// Records system or per-app audio on macOS through a Core Audio process tap and a
// private aggregate device, writing 32-bit float PCM to a WAV/CAF file.
//
// The first use triggers the "audio recording" privacy prompt
// (NSAudioCaptureUsageDescription). When permission is denied, or the source is
// DRM-protected, the tap delivers silence; `Result.isSilent` reports that so callers
// can tell the user instead of handing silence to transcription.

import AVFoundation
import CoreAudio
import Foundation

public struct CaptureError: Error, CustomStringConvertible, Sendable {
    public let description: String
    init(_ what: String, _ status: OSStatus? = nil) {
        description = status.map { "\(what) failed (OSStatus \($0))" } ?? what
    }
}

/// An app that currently has an audio process object (it may or may not be playing).
public struct AudioApp: Hashable, Sendable, Identifiable {
    public let bundleID: String
    public let pid: pid_t
    public let isPlaying: Bool
    public var id: String { bundleID }
}

public enum CaptureSource: Sendable, Equatable {
    /// Everything playing on the Mac, mixed to stereo.
    case system
    /// One app's output, identified by bundle id (macOS 26 or later).
    case app(bundleID: String)
}

public final class ProcessTapRecorder: @unchecked Sendable {
    public struct Result: Sendable {
        public let url: URL
        public let seconds: Double
        public let peak: Float
        /// True when nothing but digital silence arrived: permission denied, nothing
        /// playing, or protected (DRM) playback that the system refuses to tap.
        public var isSilent: Bool { peak == 0 }
    }

    public let source: CaptureSource
    public let outputURL: URL
    public private(set) var sampleRate: Double = 0
    public private(set) var channelCount: Int = 0

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggID = AudioObjectID(kAudioObjectUnknown)
    private var procID: AudioDeviceIOProcID?
    private var file: AVAudioFile?
    private let queue = DispatchQueue(label: "brasscribe.capture")
    private var framesWritten: AVAudioFramePosition = 0
    private var peakValue: Float = 0
    private var writeError: Error?
    private var running = false
    private var outputDevice = AudioObjectID(kAudioObjectUnknown)
    private var aliveListener: AudioObjectPropertyListenerBlock?
    private var lost = false

    /// Latest peak level (0...1) since start; safe to poll from the UI for a meter.
    public var currentPeak: Float { queue.sync { peakValue } }
    /// The output device the recording is clocked by went away (unplugged, or turned off): nothing more
    /// arrives, so the caller should `stop()` and keep what was recorded.
    public var outputLost: Bool { queue.sync { lost } }
    public var elapsedSeconds: Double { queue.sync { sampleRate > 0 ? Double(framesWritten) / sampleRate : 0 } }

    public init(source: CaptureSource, outputURL: URL) {
        self.source = source
        self.outputURL = outputURL
    }

    deinit { if running { _ = try? stop() } else { destroyDevices() } }

    public func start() throws {
        guard !running else { return }
        let desc: CATapDescription
        switch source {
        case .system:
            desc = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        case .app(let bundleID):
            guard #available(macOS 26.0, *) else { throw CaptureError("recording a single app needs macOS 26") }
            desc = CATapDescription(stereoMixdownOfProcesses: [])
            desc.bundleIDs = [bundleID]
            desc.isProcessRestoreEnabled = true
        }
        desc.name = "brasscribe-tap"
        desc.isPrivate = true
        desc.muteBehavior = .unmuted

        try check(AudioHardwareCreateProcessTap(desc, &tapID), "AudioHardwareCreateProcessTap")
        let tapUID: String
        var asbd: AudioStreamBasicDescription
        let output: AudioDeviceID, outputUID: String
        do {
            tapUID = try getString(tapID, kAudioTapPropertyUID)
            asbd = try getProperty(tapID, kAudioTapPropertyFormat, AudioStreamBasicDescription())
            (output, outputUID) = try Self.defaultOutputDevice()
        } catch {
            destroyDevices()
            throw error
        }
        let aggDesc: [String: Any] = [
            kAudioAggregateDeviceNameKey: "brasscribe-aggregate",
            kAudioAggregateDeviceUIDKey: "brasscribe-aggregate-\(UUID().uuidString)",
            kAudioAggregateDeviceMainSubDeviceKey: outputUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
            kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                               kAudioSubTapUIDKey: tapUID]],
        ]
        do {
            try check(AudioHardwareCreateAggregateDevice(aggDesc as CFDictionary, &aggID), "AudioHardwareCreateAggregateDevice")
            guard let format = AVAudioFormat(streamDescription: &asbd) else { throw CaptureError("unsupported tap format") }
            sampleRate = format.sampleRate
            channelCount = Int(format.channelCount)
            let settings: [String: Any] = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: format.sampleRate,
                AVNumberOfChannelsKey: format.channelCount,
                AVLinearPCMBitDepthKey: 32,
                AVLinearPCMIsFloatKey: true,
                AVLinearPCMIsNonInterleaved: false,
            ]
            let file = try AVAudioFile(forWriting: outputURL, settings: settings,
                                       commonFormat: .pcmFormatFloat32, interleaved: format.isInterleaved)
            self.file = file
            framesWritten = 0
            peakValue = 0
            writeError = nil
            lost = false
            try check(AudioDeviceCreateIOProcIDWithBlock(&procID, aggID, queue) { [unowned self] _, inInputData, _, _, _ in
                guard self.writeError == nil,
                      let buf = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: inInputData, deallocator: nil) else { return }
                if let ch = buf.floatChannelData {
                    // interleaved: every sample is in the one buffer; otherwise one buffer per channel
                    let buffers = format.isInterleaved ? 1 : Int(format.channelCount)
                    let n = Int(buf.frameLength) * (format.isInterleaved ? Int(format.channelCount) : 1)
                    var p = self.peakValue
                    for c in 0..<buffers { for i in 0..<n { p = max(p, abs(ch[c][i])) } }
                    self.peakValue = p
                }
                do { try file.write(from: buf) } catch {
                    // the disk is full or the file went away: keep what is there and say so at stop()
                    self.writeError = error
                    return
                }
                self.framesWritten += AVAudioFramePosition(buf.frameLength)
            }, "AudioDeviceCreateIOProcIDWithBlock")
            try watchOutput(output)
            try check(AudioDeviceStart(aggID, procID), "AudioDeviceStart")
            running = true
        } catch {
            destroyDevices()
            throw error
        }
    }

    @discardableResult
    public func stop() throws -> Result {
        guard running else { throw CaptureError("not recording") }
        AudioDeviceStop(aggID, procID)
        queue.sync {}
        destroyDevices()
        file?.close()
        file = nil
        running = false
        let (frames, peak, failed) = queue.sync { (framesWritten, peakValue, writeError) }
        if let failed { throw CaptureError("writing the recording: \(failed.localizedDescription)") }
        return Result(url: outputURL, seconds: sampleRate > 0 ? Double(frames) / sampleRate : 0, peak: peak)
    }

    /// Notes when the output device the aggregate device runs on stops being alive.
    private func watchOutput(_ device: AudioDeviceID) throws {
        var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceIsAlive,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self else { return }
            let alive: UInt32 = (try? getProperty(device, kAudioDevicePropertyDeviceIsAlive, UInt32(1))) ?? 0
            if alive == 0 { self.lost = true }
        }
        try check(AudioObjectAddPropertyListenerBlock(device, &addr, queue, listener), "watch the output device")
        outputDevice = device
        aliveListener = listener
    }

    private func destroyDevices() {
        if let listener = aliveListener, outputDevice != kAudioObjectUnknown {
            var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceIsAlive,
                                                  mScope: kAudioObjectPropertyScopeGlobal,
                                                  mElement: kAudioObjectPropertyElementMain)
            AudioObjectRemovePropertyListenerBlock(outputDevice, &addr, queue, listener)
        }
        aliveListener = nil
        outputDevice = AudioObjectID(kAudioObjectUnknown)
        if let procID, aggID != kAudioObjectUnknown { AudioDeviceDestroyIOProcID(aggID, procID) }
        procID = nil
        if aggID != kAudioObjectUnknown { AudioHardwareDestroyAggregateDevice(aggID) }
        if tapID != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tapID) }
        aggID = AudioObjectID(kAudioObjectUnknown)
        tapID = AudioObjectID(kAudioObjectUnknown)
    }

    // MARK: device and process queries

    public static func defaultOutputDeviceUID() throws -> String { try defaultOutputDevice().uid }

    static func defaultOutputDevice() throws -> (id: AudioDeviceID, uid: String) {
        let dev: AudioDeviceID = try getProperty(AudioObjectID(kAudioObjectSystemObject),
                                                 kAudioHardwarePropertyDefaultSystemOutputDevice, AudioDeviceID(0))
        return (dev, try getString(dev, kAudioDevicePropertyDeviceUID))
    }

    /// Apps that have registered with the audio server, playing ones first.
    public static func audioApps() -> [AudioApp] {
        var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyProcessObjectList,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr else { return [] }
        var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids) == noErr else { return [] }
        var apps: [String: AudioApp] = [:]
        for id in ids {
            guard let bundle = try? getString(id, kAudioProcessPropertyBundleID), !bundle.isEmpty else { continue }
            let pid: pid_t = (try? getProperty(id, kAudioProcessPropertyPID, pid_t(0))) ?? 0
            let out: UInt32 = (try? getProperty(id, kAudioProcessPropertyIsRunningOutput, UInt32(0))) ?? 0
            let app = AudioApp(bundleID: bundle, pid: pid, isPlaying: out != 0)
            if let existing = apps[app.bundleID], existing.isPlaying { continue }
            apps[app.bundleID] = app
        }
        return apps.values.sorted { ($0.isPlaying ? 0 : 1, $0.bundleID) < ($1.isPlaying ? 0 : 1, $1.bundleID) }
    }
}

private func check(_ status: OSStatus, _ what: String) throws {
    if status != noErr { throw CaptureError(what, status) }
}

private func getProperty<T>(_ obj: AudioObjectID, _ selector: AudioObjectPropertySelector, _ initial: T) throws -> T {
    var addr = AudioObjectPropertyAddress(mSelector: selector,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    try check(AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, &value), "get property \(selector)")
    return value
}

/// A CFString property. Core Audio hands it over retained (+1), so it is taken, not borrowed.
private func getString(_ obj: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> String {
    var addr = AudioObjectPropertyAddress(mSelector: selector,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    try check(withUnsafeMutablePointer(to: &value) { AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, $0) },
              "get property \(selector)")
    guard let value else { throw CaptureError("get property \(selector): empty") }
    return value.takeRetainedValue() as String
}

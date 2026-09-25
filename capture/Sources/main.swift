// brasscribe-capture: record system or per-app audio via a Core Audio process tap.
//
// Usage: brasscribe-capture --out file.wav [--seconds N] [--bundle-id com.spotify.client]
// Without --bundle-id it records a global stereo mixdown of everything playing.
// Stops after N seconds, on SIGINT, or on SIGTERM.

import AVFoundation
import CoreAudio
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data("error: \(msg)\n".utf8))
    exit(1)
}

func check(_ status: OSStatus, _ what: String) {
    if status != noErr { fail("\(what) failed (OSStatus \(status))") }
}

func getProperty<T>(_ obj: AudioObjectID, _ selector: AudioObjectPropertySelector, _ initial: T) -> T {
    var addr = AudioObjectPropertyAddress(mSelector: selector,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    check(AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, &value), "get property \(selector)")
    return value
}

func defaultOutputDeviceUID() -> String {
    let dev: AudioDeviceID = getProperty(AudioObjectID(kAudioObjectSystemObject),
                                         kAudioHardwarePropertyDefaultSystemOutputDevice, AudioDeviceID(0))
    let uid: CFString = getProperty(dev, kAudioDevicePropertyDeviceUID, "" as CFString)
    return uid as String
}

// MARK: args

var outPath: String?
var seconds: Double = 0
var bundleID: String?
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--out": outPath = it.next()
    case "--seconds": seconds = Double(it.next() ?? "") ?? 0
    case "--bundle-id": bundleID = it.next()
    default: fail("unknown argument \(a)")
    }
}
guard let outPath else { fail("--out is required") }

// MARK: tap

let desc: CATapDescription
if let bundleID {
    guard #available(macOS 26.0, *) else { fail("--bundle-id needs macOS 26") }
    desc = CATapDescription(stereoMixdownOfProcesses: [])
    desc.bundleIDs = [bundleID]
    desc.isProcessRestoreEnabled = true
} else {
    desc = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
}
desc.name = "brasscribe-tap"
desc.isPrivate = true
desc.muteBehavior = .unmuted

var tapID = AudioObjectID(kAudioObjectUnknown)
check(AudioHardwareCreateProcessTap(desc, &tapID), "AudioHardwareCreateProcessTap")
let tapUID: CFString = getProperty(tapID, kAudioTapPropertyUID, "" as CFString)
var asbd: AudioStreamBasicDescription = getProperty(tapID, kAudioTapPropertyFormat, AudioStreamBasicDescription())

let outputUID = defaultOutputDeviceUID()
let aggDesc: [String: Any] = [
    kAudioAggregateDeviceNameKey: "brasscribe-aggregate",
    kAudioAggregateDeviceUIDKey: "brasscribe-aggregate-\(UUID().uuidString)",
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                       kAudioSubTapUIDKey: tapUID as String]],
]
var aggID = AudioObjectID(kAudioObjectUnknown)
check(AudioHardwareCreateAggregateDevice(aggDesc as CFDictionary, &aggID), "AudioHardwareCreateAggregateDevice")

func cleanup() {
    AudioHardwareDestroyAggregateDevice(aggID)
    AudioHardwareDestroyProcessTap(tapID)
}

// MARK: file

guard let format = AVAudioFormat(streamDescription: &asbd) else { fail("unsupported tap format") }
let settings: [String: Any] = [
    AVFormatIDKey: kAudioFormatLinearPCM,
    AVSampleRateKey: format.sampleRate,
    AVNumberOfChannelsKey: format.channelCount,
    AVLinearPCMBitDepthKey: 32,
    AVLinearPCMIsFloatKey: true,
    AVLinearPCMIsNonInterleaved: false,
]
let file: AVAudioFile
do {
    file = try AVAudioFile(forWriting: URL(fileURLWithPath: outPath), settings: settings,
                           commonFormat: .pcmFormatFloat32, interleaved: format.isInterleaved)
} catch { cleanup(); fail("cannot open \(outPath): \(error)") }

FileHandle.standardError.write(Data(
    "recording \(bundleID ?? "system audio") at \(Int(format.sampleRate)) Hz, \(format.channelCount) ch -> \(outPath)\n".utf8))

var framesWritten: AVAudioFramePosition = 0
var peak: Float = 0
let queue = DispatchQueue(label: "brasscribe.capture")
var procID: AudioDeviceIOProcID?
check(AudioDeviceCreateIOProcIDWithBlock(&procID, aggID, queue) { _, inInputData, _, _, _ in
    guard let buf = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: inInputData, deallocator: nil) else { return }
    if let ch = buf.floatChannelData {
        let n = Int(buf.frameLength) * (format.isInterleaved ? Int(format.channelCount) : 1)
        for i in 0..<n { peak = max(peak, abs(ch[0][i])) }
    }
    try? file.write(from: buf)
    framesWritten += AVAudioFramePosition(buf.frameLength)
}, "AudioDeviceCreateIOProcIDWithBlock")
check(AudioDeviceStart(aggID, procID), "AudioDeviceStart")

func stop() {
    AudioDeviceStop(aggID, procID)
    queue.sync {}
    if let procID { AudioDeviceDestroyIOProcID(aggID, procID) }
    cleanup()
    file.close()
    let secs = Double(framesWritten) / format.sampleRate
    FileHandle.standardError.write(Data(String(format: "wrote %.1f s, peak %.3f\n", secs, peak).utf8))
    if peak == 0 { FileHandle.standardError.write(Data("warning: silence captured (permission denied or nothing playing?)\n".utf8)) }
    exit(0)
}

var signalSources: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler { stop() }
    src.resume()
    signalSources.append(src)
}
if seconds > 0 { DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { stop() } }
dispatchMain()

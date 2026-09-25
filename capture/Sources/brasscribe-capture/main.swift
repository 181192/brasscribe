// brasscribe-capture: record system or per-app audio via a Core Audio process tap.
//
// Usage: brasscribe-capture --out file.wav [--seconds N] [--bundle-id com.spotify.client]
//        brasscribe-capture --list
// Without --bundle-id it records a global stereo mixdown of everything playing.
// Stops after N seconds, on SIGINT, or on SIGTERM.

import AudioCapture
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data("error: \(msg)\n".utf8))
    exit(1)
}

func log(_ msg: String) { FileHandle.standardError.write(Data((msg + "\n").utf8)) }

var outPath: String?
var seconds: Double = 0
var bundleID: String?
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--out": outPath = it.next()
    case "--seconds": seconds = Double(it.next() ?? "") ?? 0
    case "--bundle-id": bundleID = it.next()
    case "--list":
        for app in ProcessTapRecorder.audioApps() { print("\(app.isPlaying ? "playing" : "idle   ")  \(app.bundleID)") }
        exit(0)
    default: fail("unknown argument \(a)")
    }
}
guard let outPath else { fail("--out is required") }

let recorder = ProcessTapRecorder(source: bundleID.map { .app(bundleID: $0) } ?? .system,
                                  outputURL: URL(fileURLWithPath: outPath))
do { try recorder.start() } catch { fail("\(error)") }
log("recording \(bundleID ?? "system audio") at \(Int(recorder.sampleRate)) Hz, \(recorder.channelCount) ch -> \(outPath)")

func stop() -> Never {
    do {
        let r = try recorder.stop()
        log(String(format: "wrote %.1f s, peak %.3f", r.seconds, r.peak))
        if r.isSilent { log("warning: silence captured (permission denied, nothing playing, or protected content?)") }
        exit(0)
    } catch { fail("\(error)") }
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

// Builds a PlaybackEngine the way the app opens a score: in a fresh process, on a background
// thread, before anything has registered the in-process audio units. PlaybackKitTests runs it
// inside a sandbox, where an audio unit that is not marked sandbox-safe cannot be instantiated.
// Exit 0: the engine was built. Exit 1: it failed with a Swift error. A crash means an
// Objective-C exception escaped.
import AVFoundation
import Foundation
import PlaybackKit
import ScoreKit

let xml = """
<?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
<clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note></measure></part></score-partwise>
"""

/// A one-sample stereo impulse, so the convolution reverb is built too.
func impulse() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appending(path: "probe-ir-\(ProcessInfo.processInfo.processIdentifier).wav")
    let fmt = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
    let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: 64)!
    buf.frameLength = 64
    buf.floatChannelData![0][0] = 1
    buf.floatChannelData![1][0] = 1
    let file = try AVAudioFile(forWriting: url, settings: fmt.settings)
    try file.write(from: buf)
    return url
}

let done = DispatchSemaphore(value: 0)
var status: Int32 = 0
Thread.detachNewThread {
    do {
        let score = try MusicXMLParser.parse(Data(xml.utf8))
        let ir = try impulse()
        defer { try? FileManager.default.removeItem(at: ir) }
        let engine = try PlaybackEngine(score: score, soundBank: SoundBank(general: nil, perPart: [:]), roomIR: ir,
                                        offlineFormat: PlaybackEngine.offlineFormat())
        let stages = [engine.outputStage != nil, engine.recordingStage != nil, engine.usesRoomIR]
        print("engine built off the main thread: output stage, recording stage, room IR = \(stages)")
        status = stages.allSatisfy { $0 } ? 0 : 1
    } catch {
        print("engine failed: \(error)")
        status = 1
    }
    done.signal()
}
done.wait()
exit(status)

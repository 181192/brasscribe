// Render the sound-check phrases through AVAudioUnitSampler with the band SoundFont, one WAV per part.
//
//   swiftc -O -o data/sounds/tools/bin/avsampler_render sounds/tools/avsampler_render.swift
//   data/sounds/tools/bin/avsampler_render SF2 data/sounds/phrases/phrases.json sounds/mapping.json OUT_DIR \
//       [--channel-gain] [--program-change] [--unison] [--stream]
//
// Each part gets its own AVAudioUnitSampler loaded with the part's band preset (bankMSB 0x79,
// bankLSB = bank; drums 0x78/0), exactly as PlaybackKit loads it. Notes come from phrases.json
// (seconds) and are started and stopped between 32-frame render slices, so timing is within
// 0.7 ms. Output: OUT_DIR/<slug>.wav, 44.1 kHz stereo float, the slug as in sounds/soundcheck.py.
//   --channel-gain    set overallGain = band_soundfont.channel_gain_db (the app's balance path)
//   --program-change  send a MIDI program change for the part's GM program after loading, as a
//                     sequencer track written by ScoreKit's MIDIWriter does
//   --stream          keep AUSampler's default disk streaming (by default samples are loaded into
//                     memory with kMusicDeviceProperty_StreamFromDisk = 0, as PlaybackKit does)
//   --unison          instead of the phrases: two parts (Solo Cornet, Repiano Cornet) play the same
//                     pitch with staggered note-offs through two samplers on the same MIDI channel;
//                     writes unison.wav plus unison-a.wav / unison-b.wav (each part alone)
import AVFoundation
import AudioToolbox

let args = CommandLine.arguments
guard args.count >= 5 else {
    FileHandle.standardError.write("usage: avsampler_render SF2 phrases.json mapping.json OUT_DIR [--channel-gain] [--program-change] [--unison]\n".data(using: .utf8)!)
    exit(2)
}
let sf2 = URL(fileURLWithPath: args[1])
let phrases = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[2]))) as! [String: Any]
let mapping = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[3]))) as! [String: Any]
let out = URL(fileURLWithPath: args[4])
let channelGain = args.contains("--channel-gain")
let programChange = args.contains("--program-change")
let unison = args.contains("--unison")
let stream = args.contains("--stream")  // leave AUSampler's default disk streaming on
try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
let parts = mapping["parts"] as! [String: [String: Any]]
let sampleRate = 44100.0
let slice: AVAudioFrameCount = 32

func slug(_ s: String) -> String { s.replacingOccurrences(of: "♭", with: "b").replacingOccurrences(of: " ", with: "-").lowercased() }

struct Voice { let part: String; let notes: [(Double, Double, UInt8, UInt8)] }
struct Event { let frame: Int; let on: Bool; let sampler: Int; let note: UInt8; let vel: UInt8 }

func render(_ voices: [Voice], to url: URL, channel: UInt8 = 0) throws {
    let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2)!
    let engine = AVAudioEngine()
    try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096)
    var samplers: [AVAudioUnitSampler] = []
    var channels: [UInt8] = []
    var events: [Event] = []
    for (i, v) in voices.enumerated() {
        let bs = parts[v.part]!["band_soundfont"] as! [String: Any]
        let bank = (bs["bank"] as! NSNumber).intValue, program = (bs["program"] as! NSNumber).intValue
        let s = AVAudioUnitSampler()
        engine.attach(s)
        engine.connect(s, to: engine.mainMixerNode, format: nil)
        let drums = bank == 128
        if !stream {
            // load every sample into memory: streamed samples drop out when the disk read is late
            var off: UInt32 = 0
            AudioUnitSetProperty(s.audioUnit, kMusicDeviceProperty_StreamFromDisk, kAudioUnitScope_Global, 0, &off, UInt32(MemoryLayout<UInt32>.size))
        }
        try s.loadSoundBankInstrument(at: sf2, program: UInt8(program),
                                      bankMSB: UInt8(drums ? kAUSampler_DefaultPercussionBankMSB : kAUSampler_DefaultMelodicBankMSB),
                                      bankLSB: UInt8(drums ? 0 : bank))
        if channelGain { s.overallGain = Float((bs["channel_gain_db"] as? NSNumber)?.doubleValue ?? 0) }
        samplers.append(s)
        channels.append(drums ? 9 : channel)
        for (a, b, p, vel) in v.notes {
            events.append(Event(frame: Int((a * sampleRate).rounded()), on: true, sampler: i, note: p, vel: vel))
            events.append(Event(frame: Int((b * sampleRate).rounded()), on: false, sampler: i, note: p, vel: 0))
        }
    }
    // note-offs before note-ons at the same frame, so a repeated note retriggers
    events.sort { $0.frame != $1.frame ? $0.frame < $1.frame : (!$0.on && $1.on) }
    try engine.start()
    if programChange {
        for (i, v) in voices.enumerated() {
            let bs = parts[v.part]!["band_soundfont"] as! [String: Any]
            if (bs["bank"] as! NSNumber).intValue != 128 {
                samplers[i].sendProgramChange(UInt8((bs["program"] as! NSNumber).intValue), onChannel: channel)
            }
        }
    }
    let end = (events.last?.frame ?? 0) + Int(2 * sampleRate)
    let file = try AVAudioFile(forWriting: url, settings: format.settings, commonFormat: .pcmFormatFloat32, interleaved: false)
    let buf = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: 4096)!
    var frame = 0, k = 0
    while frame < end {
        while k < events.count && events[k].frame <= frame {
            let e = events[k]
            let ch = channels[e.sampler]
            if e.on { samplers[e.sampler].startNote(e.note, withVelocity: e.vel, onChannel: ch) }
            else { samplers[e.sampler].stopNote(e.note, onChannel: ch) }
            k += 1
        }
        let next = k < events.count ? events[k].frame : end
        let n = AVAudioFrameCount(max(1, min(Int(4096), next - frame, end - frame)))
        let status = try engine.renderOffline(max(n, min(slice, AVAudioFrameCount(end - frame))), to: buf)
        guard status == .success else { throw NSError(domain: "render", code: status.rawValue) }
        try file.write(from: buf)
        frame += Int(buf.frameLength)
    }
    engine.stop()
}

func notes(_ raw: Any?) -> [(Double, Double, UInt8, UInt8)] {
    ((raw as? [[NSNumber]]) ?? []).map { ($0[0].doubleValue, $0[1].doubleValue, UInt8($0[2].intValue), UInt8($0[3].intValue)) }
}

if unison {
    // Solo Cornet holds 65 from 0.5 to 3.0 s, Repiano Cornet the same pitch from 0.8 to 2.0 s,
    // then the reverse order of note-offs, then a fast unison with 20 ms staggered offs.
    typealias N = (Double, Double, UInt8, UInt8)
    var a: [N] = [(0.5, 3.0, 65, 80), (4.0, 5.0, 65, 80)]
    var b: [N] = [(0.8, 2.0, 65, 80), (3.5, 5.7, 65, 80)]
    for i in 0..<8 {
        let t = 6.0 + Double(i) * 0.25
        a.append((t, t + 0.2, 65, 80))
        b.append((t + 0.01, t + 0.22, 65, 80))
    }
    try render([Voice(part: "Solo Cornet", notes: a), Voice(part: "Repiano Cornet", notes: b)], to: out.appending(path: "unison.wav"))
    try render([Voice(part: "Solo Cornet", notes: a)], to: out.appending(path: "unison-a.wav"))
    try render([Voice(part: "Repiano Cornet", notes: b)], to: out.appending(path: "unison-b.wav"))
    print("unison: \(out.path)")
    exit(0)
}

let ps = phrases["parts"] as! [String: [String: Any]]
for (name, p) in ps.sorted(by: { $0.key < $1.key }) {
    guard parts[name] != nil else { continue }
    try render([Voice(part: name, notes: notes(p["notes"]))], to: out.appending(path: "\(slug(name)).wav"))
    print("  avsampler: \(slug(name)).wav")
}

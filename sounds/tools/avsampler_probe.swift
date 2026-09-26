// Load every preset of a SoundFont into AVAudioUnitSampler and render one note offline.
//
//   swiftc -O -o data/sounds/tools/bin/avsampler_probe sounds/tools/avsampler_probe.swift
//   data/sounds/tools/bin/avsampler_probe data/sounds/band/brasscribe-band.sf2 PROBE.tsv
//
// PROBE.tsv lines: bank <TAB> program <TAB> note <TAB> label. Melodic banks are addressed as
// bankMSB = kAUSampler_DefaultMelodicBankMSB (0x79), bankLSB = SF2 bank; bank 128 as
// bankMSB = kAUSampler_DefaultPercussionBankMSB (0x78), bankLSB = 0. Prints the RMS of a
// 1 s render per preset, or the load error. Exit status 1 if any preset fails or is silent.
import AVFoundation
import AudioToolbox

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write("usage: avsampler_probe FILE.sf2 PROBE.tsv\n".data(using: .utf8)!)
    exit(2)
}
let url = URL(fileURLWithPath: args[1])
let lines = try String(contentsOfFile: args[2], encoding: .utf8).split(separator: "\n")
let sampleRate = 44100.0
let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2)!
var failures = 0

for line in lines {
    let f = line.split(separator: "\t").map(String.init)
    guard f.count >= 4, let bank = Int(f[0]), let program = UInt8(f[1]), let note = UInt8(f[2]) else { continue }
    let engine = AVAudioEngine()
    let sampler = AVAudioUnitSampler()
    engine.attach(sampler)
    engine.connect(sampler, to: engine.mainMixerNode, format: format)
    do {
        try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096)
        let msb = bank == 128 ? UInt8(kAUSampler_DefaultPercussionBankMSB) : UInt8(kAUSampler_DefaultMelodicBankMSB)
        let lsb = bank == 128 ? UInt8(0) : UInt8(bank)
        try sampler.loadSoundBankInstrument(at: url, program: program, bankMSB: msb, bankLSB: lsb)
        try engine.start()
        sampler.startNote(note, withVelocity: 80, onChannel: 0)
        let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: 4096)!
        var sum = 0.0, n = 0.0, rendered = 0
        while rendered < Int(sampleRate) {
            let status = try engine.renderOffline(4096, to: buffer)
            guard status == .success else { break }
            for c in 0..<Int(format.channelCount) {
                let p = buffer.floatChannelData![c]
                for i in 0..<Int(buffer.frameLength) { sum += Double(p[i] * p[i]); n += 1 }
            }
            rendered += Int(buffer.frameLength)
        }
        sampler.stopNote(note, onChannel: 0)
        engine.stop()
        let rms = n > 0 ? (sum / n).squareRoot() : 0
        let db = 20 * log10(max(rms, 1e-9))
        let ok = rms > 1e-4
        if !ok { failures += 1 }
        print("\(ok ? "ok  " : "FAIL") bank \(bank) program \(program) note \(note) \(f[3]): rms \(String(format: "%.1f", db)) dBFS")
    } catch {
        failures += 1
        print("FAIL bank \(bank) program \(program) \(f[3]): \(error)")
    }
}
print("\(lines.count - failures)/\(lines.count) presets load and sound in AVAudioUnitSampler")
exit(failures == 0 ? 0 : 1)

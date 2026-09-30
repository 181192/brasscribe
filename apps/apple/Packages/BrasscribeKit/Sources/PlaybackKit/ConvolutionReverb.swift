import Accelerate
import AudioToolbox
import AVFoundation
import Foundation

/// Stereo convolution reverb as an Audio Unit effect: uniformly partitioned overlap-save
/// FFT convolution (vDSP), one IR channel per output channel, 512-sample blocks (11.6 ms
/// latency at 44.1 kHz). The room IR has the direct sound removed, so the dry signal comes
/// from the placement path and this unit adds only the reverberant field.
///
/// Calibration (sounds/render.py): with a unit-energy IR the wet energy equals the input
/// energy, so `wetGainDB` is the wet-to-direct ratio at the listener. The sound reference
/// uses +4.5 dB at the audience seat.
public final class ConvolutionReverbAU: AUAudioUnit {
    /// Sandbox-safe: the Mac app runs in the App Sandbox, where a registered unit without the flag
    /// cannot be instantiated (AudioComponentInstanceNew fails with -3000).
    public static let componentDescription = AudioComponentDescription(
        componentType: kAudioUnitType_Effect, componentSubType: fourCC("bcrv"), componentManufacturer: fourCC("Brsc"),
        componentFlags: AudioComponentFlags.sandboxSafe.rawValue, componentFlagsMask: 0)

    static let registered: Void = {
        AUAudioUnit.registerSubclass(ConvolutionReverbAU.self, as: componentDescription, name: "Brasscribe: Convolution Reverb", version: 1)
    }()

    private var inputBus: AUAudioUnitBus!
    private var outputBus: AUAudioUnitBus!
    private var inBusArray: AUAudioUnitBusArray!
    private var outBusArray: AUAudioUnitBusArray!
    let kernel = ConvolutionKernel()

    public override init(componentDescription: AudioComponentDescription, options: AudioComponentInstantiationOptions = []) throws {
        try super.init(componentDescription: componentDescription, options: options)
        let fmt = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
        inputBus = try AUAudioUnitBus(format: fmt)
        outputBus = try AUAudioUnitBus(format: fmt)
        inBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .input, busses: [inputBus])
        outBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .output, busses: [outputBus])
        maximumFramesToRender = 4096
    }

    public override var inputBusses: AUAudioUnitBusArray { inBusArray }
    public override var outputBusses: AUAudioUnitBusArray { outBusArray }
    public override var canProcessInPlace: Bool { false }

    public override func allocateRenderResources() throws {
        try super.allocateRenderResources()
        kernel.prepare(sampleRate: outputBus.format.sampleRate, channels: Int(outputBus.format.channelCount),
                       maxFrames: Int(maximumFramesToRender))
    }

    public override var internalRenderBlock: AUInternalRenderBlock {
        let kernel = self.kernel
        return { _, timestamp, frameCount, _, outputData, _, pullInputBlock in
            guard let pull = pullInputBlock else { return kAudioUnitErr_NoConnection }
            // the input buffers hold maximumFramesToRender frames
            guard Int(frameCount) <= kernel.maxFrames else { return kAudioUnitErr_TooManyFramesToProcess }
            var flags = AudioUnitRenderActionFlags()
            kernel.resetInput(frames: Int(frameCount))
            let status = pull(&flags, timestamp, frameCount, 0, kernel.inputList)
            if status != noErr { return status }
            kernel.process(frames: Int(frameCount), output: UnsafeMutableAudioBufferListPointer(outputData))
            return noErr
        }
    }
}

/// The DSP state, set up outside the render thread; the render path does no allocation.
final class ConvolutionKernel: @unchecked Sendable {
    static let block = 512
    var wetGain: Float = 1
    var enabled = true
    private(set) var ir: [[Float]] = []          // per channel, at the render rate
    private var irRate: Double = 0
    private var channels = 2
    private var fft: FFTSetup?
    private let log2n = vDSP_Length(10)          // 2 * block = 1024
    private var partitions = 0
    // per channel: IR spectra (partitions x N/2), input spectra ring, time buffers
    private var hRe: [[Float]] = [], hIm: [[Float]] = []
    private var xRe: [[Float]] = [], xIm: [[Float]] = []
    private var ringPos = 0
    private var timeIn: [[Float]] = []           // last 2B input samples
    private var inFifo: [[Float]] = [], outFifo: [[Float]] = []
    private var fifoFill = 0
    private var accRe = [Float](), accIm = [Float](), work = [Float]()
    private var inBuffers: [UnsafeMutablePointer<Float>] = []
    private var abl: UnsafeMutableAudioBufferListPointer?
    var inputList: UnsafeMutablePointer<AudioBufferList> { abl!.unsafeMutablePointer }
    private(set) var maxFrames = 0
    private var rawIR: [[Float]] = [], rawRate: Double = 0
    private var sampleRate: Double = 44_100

    /// Set the impulse response (one array per channel) at its sample rate.
    func setIR(_ channels: [[Float]], sampleRate: Double, normalize: Bool = false) {
        rawIR = channels; rawRate = sampleRate
        if normalize {
            // unit energy per channel, so wetGain is the wet-to-input energy ratio
            rawIR = channels.map { ch in
                let e = ch.reduce(0) { $0 + Double($1) * Double($1) }
                let s = e > 0 ? Float(1 / e.squareRoot()) : 1
                return ch.map { $0 * s }
            }
        }
        if irRate != 0 { prepare(sampleRate: self.sampleRate, channels: self.channels, maxFrames: maxFrames) }
    }

    func prepare(sampleRate: Double, channels: Int, maxFrames: Int) {
        self.sampleRate = sampleRate
        self.channels = channels
        self.maxFrames = maxFrames
        irRate = sampleRate
        let b = Self.block, n = 2 * b, half = n / 2
        if fft == nil { fft = vDSP_create_fftsetup(log2n, FFTRadix(kFFTRadix2)) }
        ir = (0..<channels).map { c in
            guard !rawIR.isEmpty else { return [] }
            let src = rawIR[min(c, rawIR.count - 1)]
            return rawRate == sampleRate ? src : resample(src, from: rawRate, to: sampleRate)
        }
        let irLength = ir.map(\.count).max() ?? 0
        partitions = max(1, (irLength + b - 1) / b)
        hRe = []; hIm = []
        for c in 0..<channels {
            var re = [Float](repeating: 0, count: partitions * half), im = re
            for p in 0..<partitions {
                var frame = [Float](repeating: 0, count: n)
                let lo = p * b
                if lo < ir[c].count {
                    let hi = min(ir[c].count, lo + b)
                    for i in lo..<hi { frame[i - lo] = ir[c][i] }
                }
                forward(frame, &re, &im, offset: p * half)
            }
            hRe.append(re); hIm.append(im)
        }
        xRe = Array(repeating: [Float](repeating: 0, count: partitions * half), count: channels)
        xIm = xRe
        ringPos = 0
        timeIn = Array(repeating: [Float](repeating: 0, count: n), count: channels)
        inFifo = Array(repeating: [Float](repeating: 0, count: b), count: channels)
        outFifo = Array(repeating: [Float](repeating: 0, count: b), count: channels)
        fifoFill = 0
        accRe = [Float](repeating: 0, count: half); accIm = accRe; work = [Float](repeating: 0, count: n)
        for p in inBuffers { p.deallocate() }
        inBuffers = (0..<channels).map { _ in UnsafeMutablePointer<Float>.allocate(capacity: maxFrames) }
        // AudioBufferList.allocate's memory is freed with free()
        if let old = abl { free(old.unsafeMutablePointer) }
        let list = AudioBufferList.allocate(maximumBuffers: channels)
        for c in 0..<channels {
            list[c] = AudioBuffer(mNumberChannels: 1, mDataByteSize: UInt32(maxFrames * 4), mData: UnsafeMutableRawPointer(inBuffers[c]))
        }
        abl = list
    }

    deinit {
        for p in inBuffers { p.deallocate() }
        if let abl { free(abl.unsafeMutablePointer) }
        if let fft { vDSP_destroy_fftsetup(fft) }
    }

    /// Packed real FFT of a 2B frame into re/im at offset (vDSP zrip layout: DC and Nyquist
    /// in element 0).
    private func forward(_ frame: [Float], _ re: inout [Float], _ im: inout [Float], offset: Int) {
        let half = Self.block
        var r = [Float](repeating: 0, count: half), i = r
        r.withUnsafeMutableBufferPointer { rp in
            i.withUnsafeMutableBufferPointer { ip in
                var sc = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
                frame.withUnsafeBufferPointer { fp in
                    fp.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) { vDSP_ctoz($0, 2, &sc, 1, vDSP_Length(half)) }
                }
                vDSP_fft_zrip(fft!, &sc, 1, log2n, FFTDirection(kFFTDirection_Forward))
            }
        }
        for k in 0..<half { re[offset + k] = r[k]; im[offset + k] = i[k] }
    }

    func resetInput(frames: Int) {
        guard let abl else { return }
        for c in 0..<channels {
            abl[c].mData = UnsafeMutableRawPointer(inBuffers[c])
            abl[c].mDataByteSize = UInt32(frames * 4)
        }
    }

    func process(frames: Int, output: UnsafeMutableAudioBufferListPointer) {
        let b = Self.block, half = b
        let outChannels = min(output.count, channels)
        for f in 0..<frames {
            for c in 0..<channels { inFifo[c][fifoFill] = inBuffers[c][f] }
            for c in 0..<outChannels {
                output[c].mData!.assumingMemoryBound(to: Float.self)[f] = enabled ? outFifo[c][fifoFill] * wetGain : 0
            }
            fifoFill += 1
            if fifoFill == b {
                fifoFill = 0
                runBlock(half: half)
            }
        }
    }

    private func runBlock(half: Int) {
        let b = Self.block, n = 2 * b
        let scale = 1 / Float(4 * n)
        for c in 0..<channels {
            // slide: timeIn = [previous block, new block]
            for i in 0..<b { timeIn[c][i] = timeIn[c][i + b]; timeIn[c][i + b] = inFifo[c][i] }
            guard !ir.isEmpty, !ir[c].isEmpty else { for i in 0..<b { outFifo[c][i] = 0 }; continue }
            let off = ringPos * half
            timeIn[c].withUnsafeBufferPointer { tp in
                xRe[c].withUnsafeMutableBufferPointer { rp in
                    xIm[c].withUnsafeMutableBufferPointer { ip in
                        var sc = DSPSplitComplex(realp: rp.baseAddress! + off, imagp: ip.baseAddress! + off)
                        tp.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) { vDSP_ctoz($0, 2, &sc, 1, vDSP_Length(half)) }
                        vDSP_fft_zrip(fft!, &sc, 1, log2n, FFTDirection(kFFTDirection_Forward))
                    }
                }
            }
            // Y = sum_p X[k - p] H[p]; element 0 holds two real values (DC, Nyquist)
            vDSP_vclr(&accRe, 1, vDSP_Length(half)); vDSP_vclr(&accIm, 1, vDSP_Length(half))
            var dc: Float = 0, ny: Float = 0
            for p in 0..<partitions {
                let slot = ((ringPos - p) % partitions + partitions) % partitions
                let xo = slot * half, ho = p * half
                dc += xRe[c][xo] * hRe[c][ho]; ny += xIm[c][xo] * hIm[c][ho]
                xRe[c].withUnsafeMutableBufferPointer { xr in xIm[c].withUnsafeMutableBufferPointer { xi in
                    hRe[c].withUnsafeMutableBufferPointer { hr in hIm[c].withUnsafeMutableBufferPointer { hi in
                        accRe.withUnsafeMutableBufferPointer { ar in accIm.withUnsafeMutableBufferPointer { ai in
                            var x = DSPSplitComplex(realp: xr.baseAddress! + xo, imagp: xi.baseAddress! + xo)
                            var h = DSPSplitComplex(realp: hr.baseAddress! + ho, imagp: hi.baseAddress! + ho)
                            var a = DSPSplitComplex(realp: ar.baseAddress!, imagp: ai.baseAddress!)
                            vDSP_zvma(&x, 1, &h, 1, &a, 1, &a, 1, vDSP_Length(half))
                        }}
                    }}
                }}
            }
            accRe[0] = dc; accIm[0] = ny
            accRe.withUnsafeMutableBufferPointer { ar in accIm.withUnsafeMutableBufferPointer { ai in
                var a = DSPSplitComplex(realp: ar.baseAddress!, imagp: ai.baseAddress!)
                vDSP_fft_zrip(fft!, &a, 1, log2n, FFTDirection(kFFTDirection_Inverse))
                work.withUnsafeMutableBufferPointer { wp in
                    wp.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) { vDSP_ztoc(&a, 1, $0, 2, vDSP_Length(half)) }
                }
            }}
            // overlap-save: the second half is valid
            for i in 0..<b { outFifo[c][i] = work[b + i] * scale }
        }
        ringPos = (ringPos + 1) % partitions
    }
}

func resample(_ x: [Float], from: Double, to: Double) -> [Float] {
    let src = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: from, channels: 1, interleaved: false)!
    let dst = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: to, channels: 1, interleaved: false)!
    guard let conv = AVAudioConverter(from: src, to: dst),
          let inBuf = AVAudioPCMBuffer(pcmFormat: src, frameCapacity: AVAudioFrameCount(x.count)),
          let outBuf = AVAudioPCMBuffer(pcmFormat: dst, frameCapacity: AVAudioFrameCount(Double(x.count) * to / from + 1024)) else { return x }
    inBuf.frameLength = AVAudioFrameCount(x.count)
    x.withUnsafeBufferPointer { inBuf.floatChannelData![0].update(from: $0.baseAddress!, count: x.count) }
    var fed = false
    _ = conv.convert(to: outBuf, error: nil) { _, st in
        if fed { st.pointee = .endOfStream; return nil }
        fed = true; st.pointee = .haveData; return inBuf
    }
    return Array(UnsafeBufferPointer(start: outBuf.floatChannelData![0], count: Int(outBuf.frameLength)))
}

func fourCC(_ s: String) -> FourCharCode { s.utf8.reduce(0) { $0 << 8 | FourCharCode($1) } }

/// Loads a room IR (WAV, one channel per ear) for the convolution reverb.
public enum RoomIR {
    public static func load(_ url: URL) throws -> (channels: [[Float]], sampleRate: Double) {
        let f = try AVAudioFile(forReading: url)
        guard let buf = AVAudioPCMBuffer(pcmFormat: f.processingFormat, frameCapacity: AVAudioFrameCount(f.length)) else {
            throw PlaybackError.render("IR buffer")
        }
        try f.read(into: buf)
        let n = Int(buf.frameLength)
        let chans = (0..<Int(f.processingFormat.channelCount)).map { Array(UnsafeBufferPointer(start: buf.floatChannelData![$0], count: n)) }
        return (chans, f.processingFormat.sampleRate)
    }

    /// `BRASSCRIBE_SOUNDS/data/sounds/built/rooms/central-hall.wav`, when present.
    public static func locate() -> URL? {
        guard let root = ProcessInfo.processInfo.environment["BRASSCRIBE_SOUNDS"] else { return nil }
        let u = URL(fileURLWithPath: root).appending(path: "data/sounds/built/rooms/central-hall.wav")
        return FileManager.default.fileExists(atPath: u.path) ? u : nil
    }
}

import AudioToolbox
import AVFoundation
import Foundation

/// The output stage: a gain, then a memoryless soft limiter, the same curve on every Play app
/// (sounds/playback-levels.json, docs/research/12-band-sound.md §11). The band presets are
/// level-matched to a quiet reference (−24 LUFS body level), so the band needs make-up gain to play
/// at a normal level; the original recording gets its own stage, gained to the same loudness.
///
/// The limiter is linear up to `threshold` and bends above it with tanh towards `ceiling`, which is
/// below full scale, so nothing ever clips. It has no attack or release: it cannot pump when the
/// music stops or fades, and below the threshold the level of every part is exactly the gain, so
/// muting or soloing parts keeps their balance.
public final class OutputStageAU: AUAudioUnit {
    public static let componentDescription = AudioComponentDescription(
        componentType: kAudioUnitType_Effect, componentSubType: fourCC("bout"), componentManufacturer: fourCC("Brsc"),
        componentFlags: 0, componentFlagsMask: 0)

    static let registered: Void = {
        AUAudioUnit.registerSubclass(OutputStageAU.self, as: componentDescription, name: "Brasscribe: Output Stage", version: 1)
    }()

    private var inBusArray: AUAudioUnitBusArray!
    private var outBusArray: AUAudioUnitBusArray!
    let kernel = OutputStageKernel()

    public override init(componentDescription: AudioComponentDescription, options: AudioComponentInstantiationOptions = []) throws {
        try super.init(componentDescription: componentDescription, options: options)
        let fmt = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
        inBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .input, busses: [try AUAudioUnitBus(format: fmt)])
        outBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .output, busses: [try AUAudioUnitBus(format: fmt)])
        maximumFramesToRender = 4096
    }

    public override var inputBusses: AUAudioUnitBusArray { inBusArray }
    public override var outputBusses: AUAudioUnitBusArray { outBusArray }
    public override var canProcessInPlace: Bool { true }

    public override var internalRenderBlock: AUInternalRenderBlock {
        let kernel = self.kernel
        return { _, timestamp, frameCount, _, outputData, _, pullInputBlock in
            guard let pull = pullInputBlock else { return kAudioUnitErr_NoConnection }
            var flags = AudioUnitRenderActionFlags()
            // in place: the input lands in the output buffers (or they are pointed at it)
            let status = pull(&flags, timestamp, frameCount, 0, outputData)
            if status != noErr { return status }
            for buf in UnsafeMutableAudioBufferListPointer(outputData) {
                guard let d = buf.mData?.assumingMemoryBound(to: Float.self) else { continue }
                kernel.process(d, count: min(Int(frameCount), Int(buf.mDataByteSize) / 4))
            }
            return noErr
        }
    }
}

/// Gain and limiter curve; read on the render thread, set from anywhere (single floats).
public final class OutputStageKernel: @unchecked Sendable {
    /// Where the limiter starts to bend (−1.9 dBFS).
    public static let threshold = Float(PlaybackLevels.limiterThreshold)
    /// What the limiter never reaches (−0.18 dBFS).
    public static let ceiling = Float(PlaybackLevels.limiterCeiling)

    public var gain: Float = 1

    /// The limiter curve for one sample (gain already applied).
    @inline(__always) public static func limit(_ x: Float) -> Float {
        let a = abs(x)
        guard a > threshold else { return x }
        let knee = ceiling - threshold
        // tanh rounds to exactly 1 for large arguments, so the result stays at the ceiling
        let y = threshold + knee * tanh((a - threshold) / knee)
        return x < 0 ? -y : y
    }

    func process(_ d: UnsafeMutablePointer<Float>, count: Int) {
        let g = gain
        for i in 0..<count { d[i] = Self.limit(d[i] * g) }
    }
}

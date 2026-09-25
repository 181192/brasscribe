import AVFoundation
import Foundation
import Observation

enum MediaTools {
    /// Audio track of a video as AAC in a temporary .m4a file.
    static func extractAudio(from video: URL) async throws -> URL {
        let asset = AVURLAsset(url: video)
        guard let export = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        let out = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString + ".m4a")
        try await export.export(to: out, as: .m4a)
        return out
    }

    static func configureSession(recording: Bool) {
        #if os(iOS)
        let s = AVAudioSession.sharedInstance()
        try? s.setCategory(recording ? .playAndRecord : .playback, mode: recording ? .measurement : .default,
                           options: recording ? [.defaultToSpeaker, .allowBluetoothA2DP] : [])
        try? s.setActive(true)
        #endif
    }
}

/// Microphone recording with AVAudioEngine, written as 32-bit float WAV.
@Observable @MainActor
final class MicRecorder {
    private(set) var isRecording = false
    private(set) var level: Float = 0
    private(set) var peak: Float = 0
    private(set) var seconds: Double = 0
    private(set) var permissionDenied = false
    private var engine: AVAudioEngine?
    private var file: AVAudioFile?
    private var timer: Timer?
    private var start = Date()
    private(set) var url: URL?

    func requestPermission() async -> Bool {
        let ok = await AVAudioApplication.requestRecordPermission()
        permissionDenied = !ok
        return ok
    }

    func start() async throws {
        guard await requestPermission() else { return }
        MediaTools.configureSession(recording: true)
        let e = AVAudioEngine()
        let input = e.inputNode
        let fmt = input.outputFormat(forBus: 0)
        let out = FileManager.default.temporaryDirectory.appending(path: "recording-\(UUID().uuidString).wav")
        let f = try AVAudioFile(forWriting: out, settings: fmt.settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        file = f
        url = out
        peak = 0
        let box = LevelBox()
        input.installTap(onBus: 0, bufferSize: 4096, format: fmt) { buf, _ in
            try? f.write(from: buf)
            if let d = buf.floatChannelData {
                var p: Float = 0
                for i in 0..<Int(buf.frameLength) { p = max(p, abs(d[0][i])) }
                box.set(p)
            }
        }
        try e.start()
        engine = e
        isRecording = true
        start = Date()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                let l = box.take()
                self.level = l
                self.peak = max(self.peak, l)
                self.seconds = Date().timeIntervalSince(self.start)
            }
        }
    }

    @discardableResult
    func stop() -> URL? {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        file = nil
        timer?.invalidate()
        isRecording = false
        MediaTools.configureSession(recording: false)
        return url
    }
}

/// Thread-safe running peak from the audio thread.
final class LevelBox: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Float = 0
    func set(_ v: Float) { lock.lock(); value = max(value, v); lock.unlock() }
    func take() -> Float { lock.lock(); defer { value = 0; lock.unlock() }; return value }
}

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
///
/// When the system takes the microphone away (a call, another input device, a media-services reset)
/// the take ends there: `endedEarly` is set and the view hands the take on as if Stop was pressed.
@Observable @MainActor
final class MicRecorder {
    enum RecordingError: LocalizedError {
        case noMicrophone
        var errorDescription: String? { String(localized: "No microphone was found. Connect one and try again.") }
    }

    private(set) var isRecording = false
    /// The recording stopped on its own because the audio system changed.
    private(set) var endedEarly = false
    private(set) var level: Float = 0
    private(set) var peak: Float = 0
    private(set) var seconds: Double = 0
    private(set) var permissionDenied = false
    private var engine: AVAudioEngine?
    private var file: AVAudioFile?
    private var timer: Timer?
    private var start = Date()
    private var observers: [NSObjectProtocol] = []
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
        // no input device: installTap would raise an Objective-C exception on a 0 Hz, 0-channel format
        guard fmt.sampleRate > 0, fmt.channelCount > 0 else {
            MediaTools.configureSession(recording: false)
            throw RecordingError.noMicrophone
        }
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
        do { try e.start() } catch {
            input.removeTap(onBus: 0)
            file = nil
            try? FileManager.default.removeItem(at: out)
            url = nil
            MediaTools.configureSession(recording: false)
            throw error
        }
        engine = e
        isRecording = true
        endedEarly = false
        start = Date()
        observe(e)
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

    private func observe(_ e: AVAudioEngine) {
        let nc = NotificationCenter.default
        let end: @Sendable (Notification) -> Void = { [weak self] _ in
            MainActor.assumeIsolated { self?.endEarly() }
        }
        observers.append(nc.addObserver(forName: .AVAudioEngineConfigurationChange, object: e, queue: .main, using: end))
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        observers.append(nc.addObserver(forName: AVAudioSession.interruptionNotification, object: session, queue: .main) { [weak self] n in
            guard let raw = n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  AVAudioSession.InterruptionType(rawValue: raw) == .began else { return }
            MainActor.assumeIsolated { self?.endEarly() }
        })
        observers.append(nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: session, queue: .main, using: end))
        #endif
    }

    private func endEarly() {
        guard isRecording else { return }
        stop()
        endedEarly = true
    }

    /// Stops and deletes the take (Cancel, or the sheet closed while recording).
    func discard() {
        stop()
        if let url { try? FileManager.default.removeItem(at: url) }
        url = nil
    }

    @discardableResult
    func stop() -> URL? {
        for o in observers { NotificationCenter.default.removeObserver(o) }
        observers = []
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

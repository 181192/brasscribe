// Runs in the macOS VM (scripts/mac-vm.sh): the last frame of each screen recording XCTest kept for
// a failing test, as <recording>-last.png beside it. The recordings stay in the VM.
import AVFoundation
import AppKit

for path in CommandLine.arguments.dropFirst() {
    let asset = AVURLAsset(url: URL(fileURLWithPath: path))
    let gen = AVAssetImageGenerator(asset: asset)
    gen.requestedTimeToleranceBefore = .positiveInfinity
    gen.requestedTimeToleranceAfter = .zero
    let done = DispatchSemaphore(value: 0)
    Task {
        defer { done.signal() }
        guard let duration = try? await asset.load(.duration),
              let (image, _) = try? await gen.image(at: duration) else { print("no frame in \(path)"); return }
        let rep = NSBitmapImageRep(cgImage: image)
        let out = URL(fileURLWithPath: path).deletingPathExtension().path + "-last.png"
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: out))
    }
    done.wait()
}

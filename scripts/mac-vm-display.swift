// Runs in the macOS VM (scripts/mac-vm.sh): switch the main display to WIDTHxHEIGHT points, HiDPI
// when offered, and keep it across restarts. Tart's --display sets the panel; the image's saved
// display mode (1024 x 768) would otherwise stay.
import CoreGraphics
import Foundation

let size = (CommandLine.arguments.dropFirst().first ?? "").split(separator: "x").compactMap { Int($0) }
guard size.count == 2 else { print("usage: mac-vm-display.swift WIDTHxHEIGHT"); exit(2) }
let id = CGMainDisplayID()
let options = [kCGDisplayShowDuplicateLowResolutionModes: true] as CFDictionary
let modes = CGDisplayCopyAllDisplayModes(id, options) as? [CGDisplayMode] ?? []
guard let mode = modes.filter({ $0.width == size[0] && $0.height == size[1] }).max(by: { $0.pixelWidth < $1.pixelWidth }) else {
    print("no \(size[0])x\(size[1]) mode; the display offers \(modes.map { "\($0.width)x\($0.height)" })")
    exit(1)
}
var config: CGDisplayConfigRef?
CGBeginDisplayConfiguration(&config)
CGConfigureDisplayWithDisplayMode(config, id, mode, nil)
let err = CGCompleteDisplayConfiguration(config, .permanently)
guard err == .success else { print("display change failed: \(err.rawValue)"); exit(1) }
print("display \(mode.width) x \(mode.height) pt (\(mode.pixelWidth) x \(mode.pixelHeight) px)")

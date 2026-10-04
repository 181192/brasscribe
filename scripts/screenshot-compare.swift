// What changed between two sets of an Apple app's screen catalogue screenshots (the apps' scripts/screenshots.sh compare).
//
//   xcrun swift scripts/screenshot-compare.swift <before dir> <after dir> <report dir>
//
// Writes <report dir>/index.html (before, the difference and after, for each screen that changed), summary.md (the same
// as a list) and result.json, and exits 1 when a screen changed, appeared or went away. Without a before dir (the commit
// compared with had no catalogue) nothing counts as new. Both sets are taken on the same machine in the same run, so the
// same drawing gives the same pixels: a pixel differs when a channel differs by more than `tolerance`, and a screen
// changed when more than `floorPixels` of its pixels differ.
import AppKit
import Foundation

let tolerance = 2
let floorPixels = 4

let args = CommandLine.arguments
guard args.count == 4 else {
    FileHandle.standardError.write("usage: screenshot-compare.swift <before dir> <after dir> <report dir>\n".data(using: .utf8)!)
    exit(2)
}
let before = URL(fileURLWithPath: args[1], isDirectory: true)
let after = URL(fileURLWithPath: args[2], isDirectory: true)
let report = URL(fileURLWithPath: args[3], isDirectory: true)
let images = report.appending(path: "images", directoryHint: .isDirectory)
let fm = FileManager.default
try fm.createDirectory(at: images, withIntermediateDirectories: true)

func pngs(_ dir: URL) -> [String] {
    ((try? fm.contentsOfDirectory(atPath: dir.path)) ?? []).filter { $0.hasSuffix(".png") }.sorted()
}

/// RGBA, 8 bits a channel, `width` × `height` (the image drawn at its top left, the rest transparent).
func pixels(_ url: URL, width: Int, height: Int) -> [UInt8]? {
    guard let image = NSImage(contentsOf: url)?.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    var data = [UInt8](repeating: 0, count: width * height * 4)
    let ok = data.withUnsafeMutableBytes { buf -> Bool in
        guard let ctx = CGContext(data: buf.baseAddress, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return false }
        ctx.draw(image, in: CGRect(x: 0, y: height - image.height, width: image.width, height: image.height))
        return true
    }
    return ok ? data : nil
}

func size(_ url: URL) -> (Int, Int)? {
    guard let rep = NSImage(contentsOf: url)?.representations.first else { return nil }
    return (rep.pixelsWide, rep.pixelsHigh)
}

/// Before, the difference (the after picture faded, what differs in red) and after, side by side.
func strip(_ a: [UInt8], _ b: [UInt8], width w: Int, height h: Int) -> Data? {
    var diff = [UInt8](repeating: 0, count: w * h * 4)
    for i in stride(from: 0, to: w * h * 4, by: 4) {
        let differs = (0..<4).contains { abs(Int(a[i + $0]) - Int(b[i + $0])) > tolerance }
        if differs {
            diff[i] = 230; diff[i + 1] = 0; diff[i + 2] = 0; diff[i + 3] = 255
        } else {
            let lum = (Int(b[i]) * 299 + Int(b[i + 1]) * 587 + Int(b[i + 2]) * 114) / 1000
            let faded = UInt8(255 - (255 - lum) / 4)
            diff[i] = faded; diff[i + 1] = faded; diff[i + 2] = faded; diff[i + 3] = 255
        }
    }
    let gap = 16
    let total = w * 3 + gap * 2
    var out = [UInt8](repeating: 255, count: total * h * 4)
    for (k, src) in [a, diff, b].enumerated() {
        for y in 0..<h {
            let from = y * w * 4
            let to = (y * total + k * (w + gap)) * 4
            out.replaceSubrange(to..<(to + w * 4), with: src[from..<(from + w * 4)])
        }
    }
    return out.withUnsafeMutableBytes { buf -> Data? in
        guard let ctx = CGContext(data: buf.baseAddress, width: total, height: h, bitsPerComponent: 8, bytesPerRow: total * 4,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let image = ctx.makeImage() else { return nil }
        return NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
    }
}

let hadCatalogue = fm.fileExists(atPath: before.path)
let had = Set(pngs(before)), now = pngs(after)
var changed: [(String, String, Double)] = [], added: [String] = []
for name in now {
    let a = before.appending(path: name), b = after.appending(path: name)
    guard had.contains(name) else {
        if hadCatalogue {
            try? fm.removeItem(at: images.appending(path: name))
            try fm.copyItem(at: b, to: images.appending(path: name))
            added.append(name)
        }
        continue
    }
    guard let (wa, ha) = size(a), let (wb, hb) = size(b) else { exit(2) }
    let w = max(wa, wb), h = max(ha, hb)
    guard let pa = pixels(a, width: w, height: h), let pb = pixels(b, width: w, height: h) else { exit(2) }
    var n = 0
    for i in stride(from: 0, to: w * h * 4, by: 4) where (0..<4).contains(where: { abs(Int(pa[i + $0]) - Int(pb[i + $0])) > tolerance }) { n += 1 }
    guard n > floorPixels || (wa, ha) != (wb, hb) else { continue }
    let shown = name.replacingOccurrences(of: ".png", with: "-compare.png")
    try strip(pa, pb, width: w, height: h)?.write(to: images.appending(path: shown))
    changed.append((name, shown, Double(n) / Double(w * h)))
}
let gone = hadCatalogue && !now.isEmpty ? had.subtracting(now).sorted() : []

var lines = ["Screenshots: \(now.count) screens, \(changed.count) changed, \(added.count) new, \(gone.count) gone."]
if !hadCatalogue { lines.append("The commit compared with has no screen catalogue: there was nothing to compare with.") }
lines += changed.map { "- changed: `\($0.0)` (\(String(format: "%.2f", $0.2 * 100)) % of its pixels)" }
lines += added.map { "- new: `\($0)`" } + gone.map { "- gone: `\($0)`" }
try (lines.joined(separator: "\n") + "\n").write(to: report.appending(path: "summary.md"), atomically: true, encoding: .utf8)

func esc(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
        .replacingOccurrences(of: "'", with: "&#39;").replacingOccurrences(of: "\"", with: "&quot;")
}
func block(_ title: String, _ rows: String) -> String { rows.isEmpty ? "" : "<h2>\(esc(title))</h2>\(rows)" }
let page = [
    "<!doctype html><meta charset=utf-8><title>Screenshots</title>",
    "<style>body{font:16px system-ui;margin:16px}img{max-width:100%;border:1px solid #ccc}</style>",
    "<h1>Screenshots</h1><p>\(esc(lines[0]))</p>",
    "<p>Each changed screen: before, the difference, after.</p>",
    block("Changed", changed.map { "<h3>\(esc($0.0))</h3><img src='images/\(esc($0.1))'>" }.joined()),
    block("New", added.map { "<h3>\(esc($0))</h3><img src='images/\(esc($0))'>" }.joined()),
    block("Gone", gone.map { "<p>\(esc($0))</p>" }.joined()),
].joined(separator: "\n")
try page.write(to: report.appending(path: "index.html"), atomically: true, encoding: .utf8)

let any = !(changed.isEmpty && added.isEmpty && gone.isEmpty)
try "{\"any\": \(any), \"changed\": \(changed.count), \"new\": \(added.count), \"gone\": \(gone.count)}\n"
    .write(to: report.appending(path: "result.json"), atomically: true, encoding: .utf8)
print(lines.joined(separator: "\n"))
exit(any ? 1 : 0)

import CoreGraphics
import Foundation

// Prints the id of the largest on-screen window of a process: swift window-of-pid.swift <pid>
let pid = Int(CommandLine.arguments[1])!
let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
let mine = list.filter { ($0[kCGWindowOwnerPID as String] as? Int) == pid && ($0[kCGWindowLayer as String] as? Int) == 0 }
func area(_ w: [String: Any]) -> Double {
    let b = w[kCGWindowBounds as String] as? [String: Double] ?? [:]
    return (b["Width"] ?? 0) * (b["Height"] ?? 0)
}
guard let best = mine.max(by: { area($0) < area($1) }), area(best) > 200_000 else { exit(1) }
print(best[kCGWindowNumber as String]!)

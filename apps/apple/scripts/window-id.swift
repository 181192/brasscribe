// Prints the CGWindowID of the first on-screen window owned by a process whose name
// contains the argument (default "Brasscribe"), for `screencapture -l`.
import CoreGraphics
import Foundation

let needle = CommandLine.arguments.dropFirst().first ?? "Brasscribe"
let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in list where (w[kCGWindowOwnerName as String] as? String)?.contains(needle) == true {
    if let layer = w[kCGWindowLayer as String] as? Int, layer != 0 { continue }
    print(w[kCGWindowNumber as String] ?? "")
    exit(0)
}
exit(1)

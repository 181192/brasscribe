// Prints the CGWindowID of an on-screen window of "Brasscribe Bandroom" whose title contains the
// argument (any normal window when empty; "popover" for the menu-bar panel), for `screencapture -l`.
import CoreGraphics
import Foundation

let title = CommandLine.arguments.dropFirst().first ?? ""
let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in list where (w[kCGWindowOwnerName as String] as? String) == "Brasscribe Bandroom" {
    let name = w[kCGWindowName as String] as? String ?? ""
    let layer = w[kCGWindowLayer as String] as? Int ?? 0
    if title == "popover" {
        if layer > 0 && name.isEmpty { print(w[kCGWindowNumber as String] ?? ""); exit(0) }
        continue
    }
    if !title.isEmpty && !name.contains(title) { continue }
    if layer != 0 && title.isEmpty { continue }
    print(w[kCGWindowNumber as String] ?? "")
    exit(0)
}
exit(1)

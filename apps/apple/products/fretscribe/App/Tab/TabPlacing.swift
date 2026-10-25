import CoreGraphics
import Foundation
import TabKit

/// How large the page is set: alphaTab's scale from the system's text size, the zoom and the room there is.
enum TabSize {
    /// The scale at the ordinary text size and 100 %: fret numbers about one and a half times body text.
    static let base = 1.2
    /// The narrowest page, in alphaTab's units (points at scale 1): the tab clef, a time signature and a bar of a few
    /// notes. Past that a bar no longer fits the width, and alphaTab presses its notes together.
    static let minPageUnits = 140.0

    /// alphaTab's scale at `percent` zoom, with text `fontScale` times its ordinary size, on a page `width` points wide.
    static func scale(percent: Int, fontScale: Double, width: Double) -> Double {
        let wanted = base * fontScale * Double(percent) / 100
        return width > 0 ? min(wanted, width / minPageUnits) : wanted
    }

    static let zoomMin = Int(FretscribeDesign.Tab.zoomMin)
    static let zoomMax = Int(FretscribeDesign.Tab.zoomMax)
    static let zoomStep = Int(FretscribeDesign.Tab.zoomStep)
}

/// Where a mark's button goes over the page: at least `target` points each way, from the mark down over its column's
/// numerals, centred on the column.
enum MarkTarget {
    static func frame(_ box: TabMarkBox, target: Double = 44) -> CGRect {
        let tall = box.columnBottom - box.top
        let wide = max(target, box.width)
        let top = tall >= target ? box.top : box.top - (target - tall) / 2
        return CGRect(x: box.x - wide / 2, y: top, width: wide, height: max(target, tall))
    }
}

/// How the page follows the recording.
enum TabFollow {
    /// The line `bar` is on.
    static func line(of bar: Int, in lines: [TabLine]) -> TabLine? { lines.first { (bar >= $0.first) && (bar <= $0.last) } }

    /// Where to scroll to (the top of the line `now` is on, `pageTop` down the scroll) so the cursor is in view, or nil to
    /// stay. While the recording plays the page follows it from line to line, the line being played at the top; when the
    /// player moved the song (`moved`) it goes there if that is out of view. `shown` is the part of the scroll in view.
    static func scrollTarget(now: Int, last: Int?, playing: Bool, moved: Bool, lines: [TabLine], pageTop: Double,
                             shown: ClosedRange<Double>) -> Double? {
        guard let line = line(of: now, in: lines) else { return nil }
        let newLine = last.map { $0 < line.first || $0 > line.last } ?? false
        let top = pageTop + line.top
        let inView = top >= shown.lowerBound && pageTop + line.bottom <= shown.upperBound
        if (newLine && playing) || (moved && !inView) { return max(top, 0) }
        return nil
    }
}

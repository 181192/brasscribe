import Foundation
import NotationKit
import Observation
import ScoreKit
import SwiftUI

/// The music stand (design/music-stand.md): the score alone, in pages, for playing from a stand.
///
/// The score is engraved with a fixed number of bars per system as one long page
/// (`ScoreRenderer.Layout.barsPerSystem`). The stand cuts that page into screen-sized windows of
/// whole systems. Single pages overlap by one system, so a turn keeps the last line in view; two
/// pages side by side turn one page at a time, so the right page moves to the left.
@Observable @MainActor
final class MusicStand {
    /// Where the stand was opened from; leaving puts focus back there.
    enum Opener: Equatable { case toolbar, library(String) }
    /// The three layouts of the spec's §4.1.
    enum Form: Equatable { case phoneUpright, phoneSide, wide }

    struct StandPage: Equatable, Sendable {
        /// System indices on this page.
        let systems: ClosedRange<Int>
        /// Bars on this page, 0-based.
        let bars: ClosedRange<Int>
    }

    let opener: Opener
    /// Your part alone (on by default); off shows the parts shown before.
    var onlyMine: Bool
    var form: Form = .phoneUpright
    /// The music area, in points.
    private(set) var viewport: CGSize = .zero
    /// The height the control layer covers at the bottom of the music area (0 when hidden).
    var obscured: CGFloat = 0
    /// Text size steps above the default (Dynamic Type): fewer bars per system, larger staves.
    var largerText = 0
    /// First page on screen (0-based); a spread shows this page and the next.
    private(set) var pageIndex = 0
    var layerShown: Bool
    var rotationLocked = false
    /// "Tap the music to show the controls.", shown once, the first time the layer hides.
    var showHint = false
    /// Bumped by every touch or key in the stand; the auto-hide timer starts again from it.
    var interaction = 0
    private var lastBar = -1

    init(opener: Opener, onlyMine: Bool, layerShown: Bool) {
        self.opener = opener
        self.onlyMine = onlyMine
        self.layerShown = layerShown
    }

    // MARK: layout

    /// Two pages side by side: a tablet on its side, or a wide window.
    var twoUp: Bool { form == .wide && viewport.width > viewport.height * 1.1 && viewport.width >= 900 && !singlePage }

    /// A spread whose music fits on one page shows that page alone, at the full width, instead of
    /// half the screen next to an empty half. Set after an engraving; a new music area clears it.
    private(set) var singlePage = false

    /// After an engraving: a spread of one page becomes one page. Returns true to engrave again.
    func settleSpread(_ model: PracticeModel) -> Bool {
        guard twoUp, pages(model).count < 2 else { return false }
        singlePage = true
        return true
    }

    /// The sizing contract (§3): 3 bars upright on a phone, else 4; fewer as the text grows.
    var barsPerSystem: Int {
        if let n = LaunchOptions.standBars { return n }
        return max(2, (form == .phoneUpright ? 3 : 4) - (largerText >= 2 ? 1 : 0))
    }

    /// The width one page is engraved to.
    var columnWidth: CGFloat { max(280, twoUp ? (viewport.width - Space.s4 * 3) / 2 : viewport.width - Space.s2 * 2) }

    /// Staves in a system: 1 for your part, every part otherwise.
    private(set) var staves = 1

    /// The staff size follows from the bars per system and the width, and at least two systems of
    /// one part fit a page (one system about 100 pt at zoom 1, and about 70 more per extra staff);
    /// a system of every part always fits the screen.
    var zoom: CGFloat {
        let perBar = columnWidth / CGFloat(barsPerSystem)
        let usable = viewport.height - Self.pad - Self.topPad
        let fits = staves == 1 ? usable / 2 / 100 : usable / (100 + 70 * CGFloat(staves - 1))
        return max(staves == 1 ? 0.7 : 0.2, min(2.4, perBar / 112, fits) * fitFactor) * (largerText >= 1 ? 1.1 : 1)
    }

    /// Set after an engraving whose tallest system did not fit the screen (a system of every part).
    private var fitFactor: CGFloat = 1

    /// After an engraving: when a system is taller than the music area above the controls, shrink
    /// the staves to fit and return true (engrave again).
    func refit(_ model: PracticeModel) -> Bool {
        guard let tallest = systems(model).map(\.frame.height).max(), tallest > 0 else { return false }
        let usable = viewport.height - Self.pad - Self.topPad - obscured
        guard tallest > usable, usable > 100 else { return false }
        let f = usable / tallest * 0.97
        guard f < 0.97, zoom * f > (staves == 1 ? 0.7 : 0.2) else { return false }
        fitFactor *= f
        return true
    }

    func layout(parts: Set<String>?, pitch: PitchMode, staves: Int) -> ScoreRenderer.Layout {
        if max(1, staves) != self.staves { fitFactor = 1 }
        self.staves = max(1, staves)
        return ScoreRenderer.Layout(width: columnWidth, zoom: zoom, parts: parts, pitch: pitch, height: max(300, viewport.height),
                                    barsPerSystem: barsPerSystem)
    }

    /// A new music area: returns true when the score must be engraved again.
    func setViewport(_ size: CGSize, form: Form, largerText: Int) -> Bool {
        let before = (columnWidth, barsPerSystem, zoom, twoUp)
        let hadSize = viewport != .zero
        if size != viewport { fitFactor = 1; singlePage = false }
        viewport = size
        self.form = form
        self.largerText = largerText
        let after = (columnWidth, barsPerSystem, zoom, twoUp)
        return !hadSize || abs(before.0 - after.0) > 8 || before.1 != after.1 || abs(before.2 - after.2) > 0.02 || before.3 != after.3
    }

    // MARK: pages

    /// Space kept below the last system on a page.
    nonisolated static let pad: CGFloat = 16
    /// Space kept above the first system: room for the "?" marks the app draws above a staff, which
    /// grow with the staff size.
    nonisolated static let topPad: CGFloat = 36
    var topPad: CGFloat { max(Self.topPad, 34 * zoom) }

    /// The page's systems, from the engraving.
    func systems(_ model: PracticeModel) -> [ScoreRenderer.System] { model.pages.first?.systems ?? [] }

    func pages(_ model: PracticeModel) -> [StandPage] {
        Self.paginate(systems(model), height: viewport.height, overlap: !twoUp, bars: barIndex(model), topPad: topPad)
    }

    private func barIndex(_ model: PracticeModel) -> [String: Int] {
        Dictionary(uniqueKeysWithValues: (model.renderer?.measureIDs ?? []).enumerated().map { ($1, $0) })
    }

    /// Whole systems per page, greedily; with `overlap`, the next page starts with the last
    /// system of this one.
    nonisolated static func paginate(_ systems: [ScoreRenderer.System], height: CGFloat, overlap: Bool, bars: [String: Int],
                                      topPad: CGFloat = MusicStand.topPad) -> [StandPage] {
        guard !systems.isEmpty else { return [] }
        var out: [StandPage] = []
        var i = 0
        while i < systems.count {
            var j = i
            while j + 1 < systems.count, systems[j + 1].frame.maxY - systems[i].frame.minY + pad + topPad <= height { j += 1 }
            let barsOn = systems[i...j].flatMap(\.measureIDs).compactMap { bars[$0] }
            out.append(StandPage(systems: i...j, bars: (barsOn.min() ?? 0)...(barsOn.max() ?? 0)))
            if j == systems.count - 1 { break }
            i = overlap && j > i ? j : j + 1
        }
        return out
    }

    /// The system holding a bar.
    func systemIndex(ofBar bar: Int, _ model: PracticeModel) -> Int? {
        guard let ids = model.renderer?.measureIDs, ids.indices.contains(bar) else { return nil }
        return systems(model).firstIndex { $0.measureIDs.contains(ids[bar]) }
    }

    /// The pages on screen: one, or two side by side.
    func shown(_ model: PracticeModel) -> [Int] {
        let n = pages(model).count
        guard n > 0 else { return [] }
        let p = min(pageIndex, maxIndex(n))
        return twoUp && p + 1 < n ? [p, p + 1] : [p]
    }

    private func maxIndex(_ n: Int) -> Int { max(0, twoUp ? n - 2 : n - 1) }

    var canGoBack: Bool { pageIndex > 0 }
    func canGoForward(_ model: PracticeModel) -> Bool { pageIndex < maxIndex(pages(model).count) }

    /// Turn to a page. The player's own turns are announced; playback's are not.
    func turn(to index: Int, _ model: PracticeModel, byPlayer: Bool) {
        let all = pages(model)
        let p = max(0, min(index, maxIndex(all.count)))
        guard p != pageIndex else {
            // a turn past either end says so
            if byPlayer, index != pageIndex {
                AccessibilityNotifier.announce(index < pageIndex ? String(localized: "First page.") : String(localized: "Last page."), polite: true)
            }
            return
        }
        pageIndex = p
        if byPlayer, let first = shown(model).first, let last = shown(model).last {
            let bars = all[first].bars.lowerBound...all[last].bars.upperBound
            AccessibilityNotifier.announce(String(localized: "Page \(p + 1) of \(all.count), bars \(bars.lowerBound + 1) to \(bars.upperBound + 1)."),
                                           polite: true)
        }
    }

    func nextPage(_ model: PracticeModel) { turn(to: pageIndex + 1, model, byPlayer: true) }
    func previousPage(_ model: PracticeModel) { turn(to: pageIndex - 1, model, byPlayer: true) }

    /// A new engraving: show the current bar's page.
    func reset(_ model: PracticeModel) {
        lastBar = -1
        pageIndex = 0
        follow(model, force: true)
    }

    /// Called on every position update. While playing (and "Turn the pages while playing" is
    /// on) the page turns when the cursor reaches the start of the last system on the page, or
    /// of the right-hand page. When the current bar is not on screen at all (a seek, a bar
    /// button), the stand goes to it.
    func follow(_ model: PracticeModel, force: Bool = false) {
        let bar = model.currentBar
        guard force || bar != lastBar else { return }
        lastBar = bar
        let all = pages(model)
        guard !all.isEmpty, let s = systemIndex(ofBar: bar, model) else { return }
        let on = shown(model)
        let visible = (all[on.first ?? 0].systems.lowerBound)...(all[on.last ?? 0].systems.upperBound)
        if !visible.contains(s) {
            // the first page that has it; with overlap that page may have it last, so turn once more
            let p = all.firstIndex { $0.systems.contains(s) } ?? 0
            turn(to: twoUp ? min(p, maxIndex(all.count)) : p, model, byPlayer: false)
        }
        guard model.isPlaying, UserDefaults.standard.object(forKey: StandSettings.followKey) as? Bool ?? true else { return }
        let now = shown(model)
        if twoUp {
            if let right = now.dropFirst().first, s >= all[right].systems.lowerBound { turn(to: pageIndex + 1, model, byPlayer: false) }
        } else if let p = now.first, s >= all[p].systems.upperBound, all[p].systems.count > 1, p + 1 < all.count {
            turn(to: p + 1, model, byPlayer: false)
        }
    }

    /// The window onto the long page for a page on screen: from above its first system to below
    /// its last. When the layer would cover the current system, the window moves down (the
    /// layout stays) so that system sits above the card (§4.3).
    func window(page index: Int, _ model: PracticeModel) -> CGRect {
        let sys = systems(model)
        let all = pages(model)
        guard all.indices.contains(index) else { return .zero }
        let pg = all[index]
        var top = sys[pg.systems.lowerBound].frame.minY - topPad
        if pg.systems.lowerBound > 0 { top = max(top, sys[pg.systems.lowerBound - 1].frame.maxY + 1) }
        var shift: CGFloat = 0
        if obscured > 0, let s = systemIndex(ofBar: model.currentBar, model), pg.systems.contains(s) {
            let limit = top + viewport.height - obscured
            shift = max(0, sys[s].frame.maxY + Self.pad - limit)
            shift = min(shift, max(0, sys[s].frame.minY - topPad - top))
        }
        var bottom = sys[pg.systems.upperBound].frame.maxY + Self.pad
        // nothing of the next system (its bar number) peeks in under the page
        if sys.indices.contains(pg.systems.upperBound + 1) {
            bottom = max(sys[pg.systems.upperBound].frame.maxY + 2, min(bottom, sys[pg.systems.upperBound + 1].frame.minY - topPad))
        }
        bottom += shift
        return CGRect(x: 0, y: top + shift, width: model.pages.first?.svg.size.width ?? 0, height: max(0, bottom - top - shift))
    }

    // MARK: text

    /// "Solo Cornet (you)", the part's name, or "All parts".
    func partLine(_ model: PracticeModel) -> String {
        guard let id = model.layoutPart, let p = model.score.part(id: id) else { return String(localized: "All parts") }
        return id == model.myPart ? String(localized: "\(p.displayName) (you)") : p.displayName
    }

    /// "page 4 of 33", or "pages 1–2 of 6" for a spread.
    func pageText(_ model: PracticeModel) -> String {
        let n = max(1, pages(model).count)
        let on = shown(model)
        if on.count == 2 { return String(localized: "pages \(on[0] + 1)–\(on[1] + 1) of \(n)") }
        return String(localized: "page \((on.first ?? 0) + 1) of \(n)")
    }

    /// Auto-hide (§4.2): 4 s after the last touch, only while the music plays, and never while
    /// assistive technology, the keyboard or the setting needs the controls.
    nonisolated static func autoHides(playing: Bool, voiceOver: Bool, switchControl: Bool, fullKeyboardAccess: Bool,
                          focusInLayer: Bool, keepVisible: Bool) -> Bool {
        playing && !voiceOver && !switchControl && !fullKeyboardAccess && !focusInLayer && !keepVisible
    }
    static let hideAfter: Duration = .seconds(4)
}

/// Display settings for the stand.
enum StandSettings {
    static let followKey = "standTurnPages"
    static let keepControlsKey = "standKeepControls"
    static let hintKey = "standHintShown"
}

extension PracticeModel {
    var isStandOpen: Bool { stand != nil }

    /// Open the stand, on your part when there is one (owner decision 1).
    func enterStand(from opener: MusicStand.Opener) {
        guard stand == nil else { return }
        let s = MusicStand(opener: opener, onlyMine: myPart != nil, layerShown: !isPlaying)
        stand = s
        let part = s.partLine(self)
        var text = String(localized: "Music stand. \(part), bar \(currentBar + 1) of \(score.measures.count).")
        if !AccessibilityNotifier.screenReaderRunning { text += " " + String(localized: "Tap the music to show the controls.") }
        AccessibilityNotifier.announce(text, polite: true)
    }

    /// Leave the stand; the score view engraves itself again when it comes back.
    func leaveStand() {
        guard stand != nil else { return }
        stand = nil
        AccessibilityNotifier.announce(String(localized: "Music stand closed."), polite: true)
    }

    func toggleStand() { if stand == nil { enterStand(from: .toolbar) } else { leaveStand() } }

    /// The ← → keys and the Playback menu: pages in the stand, bars outside it.
    func nextBarOrPage() { if let stand { stand.nextPage(self) } else { nextBar() } }
    func previousBarOrPage() { if let stand { stand.previousPage(self) } else { previousBar() } }

    /// Only my part on or off: engrave again with the other parts.
    func setOnlyMine(_ on: Bool) {
        guard let stand, stand.onlyMine != on else { return }
        stand.onlyMine = on
        relayout()
    }
}

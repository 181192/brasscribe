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
    var twoUp: Bool { form == .wide && viewport.width > viewport.height * 1.1 && viewport.width >= 900 }

    /// The sizing contract (§3): 3 bars upright on a phone, else 4; fewer as the text grows.
    var barsPerSystem: Int {
        if let n = LaunchOptions.standBars { return n }
        return max(2, (form == .phoneUpright ? 3 : 4) - (largerText >= 2 ? 1 : 0))
    }

    /// The width one page is engraved to.
    var columnWidth: CGFloat { max(280, twoUp ? (viewport.width - Space.s4 * 3) / 2 : viewport.width - Space.s2 * 2) }

    /// The staff size follows from the bars per system and the width.
    var zoom: CGFloat {
        let perBar = columnWidth / CGFloat(barsPerSystem)
        return min(2.4, max(0.7, perBar / 112)) * (largerText >= 1 ? 1.1 : 1)
    }

    func layout(parts: Set<String>?, pitch: PitchMode) -> ScoreRenderer.Layout {
        ScoreRenderer.Layout(width: columnWidth, zoom: zoom, parts: parts, pitch: pitch, height: max(300, viewport.height),
                             barsPerSystem: barsPerSystem)
    }

    /// A new music area: returns true when the score must be engraved again.
    func setViewport(_ size: CGSize, form: Form, largerText: Int) -> Bool {
        let before = (columnWidth, barsPerSystem, zoom, twoUp)
        let hadSize = viewport != .zero
        viewport = size
        self.form = form
        self.largerText = largerText
        let after = (columnWidth, barsPerSystem, zoom, twoUp)
        return !hadSize || abs(before.0 - after.0) > 8 || before.1 != after.1 || abs(before.2 - after.2) > 0.02 || before.3 != after.3
    }

    // MARK: pages

    /// Space kept above the first system and below the last one on a page.
    nonisolated static let pad: CGFloat = 12

    /// The page's systems, from the engraving.
    func systems(_ model: PracticeModel) -> [ScoreRenderer.System] { model.pages.first?.systems ?? [] }

    func pages(_ model: PracticeModel) -> [StandPage] {
        Self.paginate(systems(model), height: viewport.height, overlap: !twoUp, bars: barIndex(model))
    }

    private func barIndex(_ model: PracticeModel) -> [String: Int] {
        Dictionary(uniqueKeysWithValues: (model.renderer?.measureIDs ?? []).enumerated().map { ($1, $0) })
    }

    /// Whole systems per page, greedily; with `overlap`, the next page starts with the last
    /// system of this one.
    nonisolated static func paginate(_ systems: [ScoreRenderer.System], height: CGFloat, overlap: Bool, bars: [String: Int]) -> [StandPage] {
        guard !systems.isEmpty else { return [] }
        var out: [StandPage] = []
        var i = 0
        while i < systems.count {
            var j = i
            while j + 1 < systems.count, systems[j + 1].frame.maxY - systems[i].frame.minY + 2 * pad <= height { j += 1 }
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
        let top = sys[pg.systems.lowerBound].frame.minY - Self.pad
        var shift: CGFloat = 0
        if obscured > 0, let s = systemIndex(ofBar: model.currentBar, model), pg.systems.contains(s) {
            let limit = top + viewport.height - obscured
            shift = max(0, sys[s].frame.maxY + Self.pad - limit)
            shift = min(shift, max(0, sys[s].frame.minY - Self.pad - top))
        }
        let bottom = sys[pg.systems.upperBound].frame.maxY + Self.pad + shift
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

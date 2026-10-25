import SwiftUI
import TabKit
import TranscriptionKit

/// The size the tab is read at, while the app runs: the screen comes back to it after a visit to Check the song.
@MainActor enum TabPlaces {
    static var zoom = 100
}

/// The page of one tab screen, made once for it: a screen's view is made again whenever the stack around it changes.
@MainActor final class TabPageHolder {
    lazy var page = TabPage()
}

/// The bar (counted from 0) and the beat the recording is at, for the player's line.
struct PlayPlace: Equatable {
    var bar: Int
    var beat: Int
}

/// The tab (design/brands/fretscribe/system.md §3), to read: the page engraved full width, the tuning in a chip above
/// it, and beside that what there is to check. A "?" stands over every note Fretscribe is not sure of and a boxed "!"
/// over a note with no place; each is a button that says which note it is and opens a note about it.
///
/// It is also where the song is practised (design/brands/fretscribe/flows.md §9): the recording is the sound, a cursor
/// stands at the beat it is at and the page follows it, and the player under the tab slows it down and repeats the bars
/// chosen. Space plays and pauses; with the tab in focus the left arrow goes back to the start of the repeat (a bar back
/// when nothing is repeated) and the right arrow a bar on. In full screen the tab has the whole screen and a tap on it
/// brings the controls back.
struct TabScreen: View {
    let song: TabSong
    @Environment(FretscribeModel.self) private var model
    @Environment(\.self) private var environment
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @ScaledMetric(relativeTo: .body) private var bodySize: CGFloat = 17

    @State private var holder = TabPageHolder()
    @State private var sheet: TabSheet?
    @State private var unreadable = false
    @State private var clock: TabClock?
    @State private var zoom = TabPlaces.zoom
    @State private var width: CGFloat = 0
    @State private var engraved: Double?
    /// The column whose note is open under the tab.
    @State private var told: Int?
    @State private var focus: TabFocus
    @State private var touches = 0
    @State private var place: PlayPlace?
    @State private var scroll = ScrollPosition(edge: .top)
    @State private var visible: CGRect = .zero
    @State private var followed: Int?
    @State private var jumpsSeen = 0
    @FocusState private var tabFocused: Bool

    /// `focus`: the screen opens in full screen with it on (the screen catalogue).
    init(song: TabSong, focus: TabFocus = TabFocus()) {
        self.song = song
        _focus = State(initialValue: focus)
    }

    private var page: TabPage { holder.page }
    private var practice: PracticeModel { model.practice }
    private var canPlay: Bool { clock != nil && practice.recording == .here }
    private var inFocus: Bool { focus.on && (sheet?.index.bars ?? 0) > 0 }
    private var assistive: Bool { AccessibilityNotifier.screenReaderRunning }
    private var palette: TabPalette { TabColours.palette(in: environment) }
    private var fontScale: Double { Double(bodySize) / 17 }
    private var scale: Double { TabSize.scale(percent: zoom, fontScale: fontScale, width: Double(width)) }
    private var canFetch: Bool { song.jobID != nil && !model.useFixtureService && model.computerThere }

    var body: some View {
        content
            .pageBackground()
            .navigationTitle(song.title)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(inFocus ? .hidden : .visible, for: .navigationBar)
            .navigationBarBackButtonHidden(inFocus)
            .statusBarHidden(inFocus)
            .persistentSystemOverlays(inFocus ? .hidden : .automatic)
            #else
            .toolbar(inFocus ? .hidden : .visible, for: .windowToolbar)
            #endif
            .toolbar {
                if !inFocus, let sheet, sheet.index.bars > 0 {
                    ToolbarItemGroup(placement: .primaryAction) {
                        Button { focus = focus.enter() } label: {
                            Label("Full screen", systemImage: "arrow.up.left.and.arrow.down.right")
                        }
                        .accessibilityIdentifier("fs-tab-full-screen")
                        zoomButtons(large: false)
                    }
                }
            }
            .task { await open() }
            .onDisappear {
                practice.endSlowly()
                practice.leave()
                setIdle(playing: false)
            }
            .onChange(of: told) { practice.endSlowly() }
            .onChange(of: scenePhase) { _, phase in if phase == .background { practice.pause() } }
            .onChange(of: practice.playing) { _, playing in setIdle(playing: playing) }
            .onChange(of: inFocus) { _, on in
                AccessibilityNotifier.announce(on ? String(localized: "Full screen") : String(localized: "Left full screen"))
            }
            .task(id: HideKey(focus: focus, playing: practice.playing, touches: touches)) {
                // The controls over the tab step aside again while the recording plays, a while after the last touch.
                guard focus.autoHides(playing: practice.playing, assistive: assistive) else { return }
                try? await Task.sleep(for: TabFocus.hideAfter)
                if !Task.isCancelled { focus = focus.tapped() }
            }
    }

    @ViewBuilder private var content: some View {
        if let sheet {
            if sheet.index.bars == 0 || page.unavailable != nil {
                VStack(alignment: .leading, spacing: Space.s4) {
                    header(sheet)
                    NoticeBox(systemImage: PlayIcon.info.systemName, text: String(localized: "This tab can't be shown. Go back and open it again."))
                        .accessibilityIdentifier("fs-tab-failed")
                    Spacer()
                }
                .padding(Space.s4)
            } else {
                VStack(spacing: 0) {
                    if !inFocus { header(sheet).padding(.horizontal, Space.s4).padding(.vertical, Space.s2) }
                    ZStack {
                        tab(sheet)
                        if inFocus { focusControls(sheet) }
                    }
                    if !inFocus { player(sheet) }
                    note(sheet)
                }
            }
        } else if unreadable {
            NoticeBox(systemImage: PlayIcon.info.systemName, text: String(localized: "This tab can't be shown. Go back and open it again."))
                .padding(Space.s4)
                .accessibilityIdentifier("fs-tab-failed")
                .frame(maxHeight: .infinity, alignment: .top)
        } else {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text("Opening the tab…").font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                ProgressView().progressViewStyle(.linear).tint(Color.Scribe.brand)
            }
            .padding(Space.s4)
            .frame(maxHeight: .infinity, alignment: .top)
        }
    }

    // MARK: opening

    private func open() async {
        if sheet == nil {
            let song = song
            guard let read = await Task.detached(priority: .userInitiated, operation: { TabSheet.read(song) }).value else {
                unreadable = true
                return
            }
            sheet = read
            clock = TabClock.of(read.index, tab: read.data, saved: nil)
        }
        practice.open(song: song.id.uuidString, job: song.jobID, clock: clock, inHand: song.recording,
                      songs: Set(model.local.compactMap(\.jobID)))
    }

    private func fetch() {
        guard let service = model.service() as? CompanionService else { return }
        practice.fetch { job, into in
            do { try await service.jobInput(jobID: job, into: into) } catch let e as TranscriptionError { throw TabFetch.error(e) }
        }
    }

    private func setIdle(playing: Bool) {
        // The screen stays on while the recording plays: the hands are on the instrument.
        #if os(iOS)
        UIApplication.shared.isIdleTimerDisabled = playing
        #endif
    }

    /// Check the song is where the tab was opened from, or it is opened over the tab.
    private func checkTheSong() {
        if model.path.dropLast().last == .check(song) { model.path.removeLast() } else { model.path.append(.check(song)) }
    }

    // MARK: the header

    private func header(_ sheet: TabSheet) -> some View {
        FlowLayout(spacing: Space.s4, lineSpacing: Space.s1) {
            // The tuning chip: a button whose name reads the whole state. It opens Check the song.
            Button(action: checkTheSong) {
                Text(TabWords.chip(sheet))
                    .font(Font.Scribe.label)
                    .foregroundStyle(Color.Scribe.text)
                    .padding(.horizontal, Space.s4)
                    .frame(minHeight: 44)
                    .background(Color.Scribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.md))
                    .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Scribe.borderStrong, lineWidth: 1))
                    .contentShape(RoundedRectangle(cornerRadius: Radius.md))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(TabWords.chipName(sheet))
            .accessibilityIdentifier("fs-tab-tuning")
            // The tempo, which the page's own header would say: the page keeps the music.
            if let tempo = sheet.tempo {
                Text(TabWords.tempo(tempo))
                    .font(Font.Scribe.body)
                    .foregroundStyle(Color.Scribe.textMuted)
                    .accessibilityLabel(TabWords.tempoSpoken(tempo))
                    .accessibilityIdentifier("fs-tab-tempo")
            }
            if sheet.marks.doubtful > 0 {
                // To the first "?" on the page, with its note open.
                Button { if let first = sheet.marks.doubts.first { show(first, in: sheet, say: true) } else { checkTheSong() } } label: {
                    HStack(spacing: Space.s2) {
                        Text(TabWords.markedLine(sheet.marks.doubtful))
                        Image(systemName: PlayIcon.open.systemName).accessibilityHidden(true)
                    }
                    .font(Font.Scribe.callout)
                    .foregroundStyle(Color.Scribe.textMuted)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("fs-tab-marked")
            }
            if sheet.marks.noPlace > 0 {
                Text(TabWords.noPlaceLine(sheet.marks.noPlace))
                    .font(Font.Scribe.callout)
                    .foregroundStyle(Color.Scribe.textMuted)
                    .accessibilityIdentifier("fs-tab-no-place")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Zoom out and in, with the size as their value. `large`: 44 pt icons of the screen's own (over the tab in full screen),
    /// else the toolbar's.
    @ViewBuilder private func zoomButtons(large: Bool) -> some View {
        let size = String(localized: "Size \(zoom)%")
        zoomButton("Zoom out", PlayIcon.zoomOut, large: large) { setZoom(max(zoom - TabSize.zoomStep, TabSize.zoomMin)) }
            .disabled(zoom <= TabSize.zoomMin)
            .accessibilityValue(size)
            .accessibilityIdentifier("fs-tab-zoom-out")
        zoomButton("Zoom in", PlayIcon.zoomIn, large: large) { setZoom(min(zoom + TabSize.zoomStep, TabSize.zoomMax)) }
            .disabled(zoom >= TabSize.zoomMax || TabSize.scale(percent: zoom + TabSize.zoomStep, fontScale: fontScale, width: Double(width)) <= scale)
            .accessibilityValue(size)
            .accessibilityIdentifier("fs-tab-zoom-in")
    }

    @ViewBuilder private func zoomButton(_ name: LocalizedStringKey, _ icon: PlayIcon, large: Bool, action: @escaping () -> Void) -> some View {
        if large {
            Button(action: action) {
                Image(systemName: icon.systemName).frame(width: 44, height: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.Scribe.text)
            .accessibilityLabel(Text(name))
        } else {
            Button(action: action) { Label(name, systemImage: icon.systemName) }
        }
    }

    private func setZoom(_ to: Int) {
        zoom = to
        TabPlaces.zoom = to
    }

    // MARK: the tab

    private func tab(_ sheet: TabSheet) -> some View {
        let engraving = page.engraving
        return ScrollView {
            ZStack(alignment: .topLeading) {
                TabPageView(page: page).allowsHitTesting(false)
                // Over the page: the tab as one element, and what takes a tap (in full screen a tap shows the controls),
                // the wheel and the drags, so the web view under it takes none.
                Color.clear
                    .contentShape(Rectangle())
                    .frame(maxWidth: .infinity)
                    .frame(height: max(engraving?.height ?? 0, 1))
                    .onTapGesture {
                        if inFocus { focus = focus.tapped(); touches += 1 }
                    }
                    .accessibilityElement()
                    .accessibilityLabel(TabWords.summary(title: song.title, sheet))
                    .accessibilityAddTraits(.isImage)
                    .accessibilitySortPriority(1)
                    .accessibilityIdentifier("fs-tab")
                // Each mark is an element of its own, in reading order, at least 44 pt, from the mark down over its numerals.
                if let engraving {
                    ForEach(engraving.marks, id: \.mark) { box in
                        if let column = sheet.marks.columns[safe: box.mark] {
                            mark(column, box: box, index: box.mark, in: sheet)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .accessibilityElement(children: .contain)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        }
        .scrollPosition($scroll)
        .onScrollGeometryChange(for: CGRect.self) { $0.visibleRect } action: { _, rect in visible = rect }
        .focusable()
        .focused($tabFocused)
        .defaultFocus($tabFocused, true)
        .onKeyPress(.leftArrow) {
            guard canPlay else { return .ignored }
            if practice.repeating != nil { practice.toStart() } else { practice.step(-1) }
            return .handled
        }
        .onKeyPress(.rightArrow) {
            guard canPlay else { return .ignored }
            practice.step(1)
            return .handled
        }
        .task(id: EngraveKey(scale: scale, palette: palette, ready: width > 0)) { await engrave(sheet) }
        .task(id: CursorKey(canPlay: canPlay, playing: practice.playing, jumps: practice.jumps, at: practice.at,
                            engraving: engraving?.height ?? 0, bars: engraving?.bars.count ?? 0)) { await follow() }
    }

    private func mark(_ column: TabColumn, box: TabMarkBox, index: Int, in sheet: TabSheet) -> some View {
        let frame = MarkTarget.frame(box)
        let glyph = max(box.bottom - box.top, 12)
        return Button { show(index, in: sheet, say: false) } label: {
            ZStack {
                Group {
                    if column.kind == .noPlace {
                        Text(verbatim: "!")
                            .font(.system(size: glyph * 0.75, weight: .bold))
                            .foregroundStyle(Color.Scribe.ink)
                            .frame(width: glyph * 0.8, height: glyph)
                            .overlay(Rectangle().strokeBorder(Color.Scribe.ink, lineWidth: 1.5))
                    } else {
                        Text(verbatim: "?")
                            .font(.system(size: glyph * 0.9, weight: .bold))
                            .foregroundStyle(Color.Scribe.uncertain)
                    }
                }
                .position(x: frame.width / 2, y: (box.top + box.bottom) / 2 - frame.minY)
            }
            .frame(width: frame.width, height: frame.height)
            .contentShape(Rectangle())
            .overlay {
                if told == index {
                    RoundedRectangle(cornerRadius: 6).strokeBorder(Color.Scribe.focus, lineWidth: FretscribeDesign.Tab.focusWidth)
                }
            }
        }
        .buttonStyle(.plain)
        .position(x: frame.midX, y: frame.midY)
        .accessibilityLabel(TabWords.describe(column))
        .accessibilityIdentifier("fs-tab-mark-\(index)")
    }

    /// Engraves the page at the size and in the colours there are: a new size is a new engraving, new colours alone are
    /// the same page drawn again. Several steps of the zoom in a row are one engraving.
    private func engrave(_ sheet: TabSheet) async {
        guard width > 0 else { return }
        let palette = palette, scale = scale
        if let engraved, engraved == scale {
            _ = try? await page.palette(palette)
            return
        }
        if engraved != nil {
            try? await Task.sleep(for: .milliseconds(250))
            if Task.isCancelled { return }
        }
        let xml = Data(TabIndex.forRenderer(sheet.musicXML, header: sheet.index.header).utf8)
        let staff = sheet.layout == .tabAndNotation && sheet.index.staves == 1 ? "both" : "tab"
        if (try? await page.show(musicXML: xml, palette: palette, scale: scale, staff: staff, marks: sheet.spots,
                                 markStaff: sheet.index.markStaff)) != nil {
            engraved = scale
        }
    }

    /// The cursor at the beat the recording is at. It moves from beat to beat, and only while the recording plays or the
    /// player moved it; the page follows it from line to line, and goes to where the player moved the song.
    private func follow() async {
        guard canPlay, let clock, page.engraving != nil else {
            _ = try? await page.cursor(bar: nil)
            place = nil
            return
        }
        await showCursor(clock, moved: practice.playing || practice.jumps != jumpsSeen)
        jumpsSeen = practice.jumps
        while practice.playing && !Task.isCancelled {
            try? await Task.sleep(for: .milliseconds(30))
            if Task.isCancelled { return }
            await showCursor(clock, moved: false)
        }
    }

    private func showCursor(_ clock: TabClock, moved: Bool) async {
        let now = clock.placeAt(practice.now())
        _ = try? await page.cursor(bar: now.bar, tick: now.tick)
        let said = PlayPlace(bar: now.bar, beat: clock.beatAt(now))
        if place != said { place = said }
        if let lines = page.engraving?.lines,
           let y = TabFollow.scrollTarget(now: now.bar, last: followed, playing: practice.playing, moved: moved, lines: lines,
                                          pageTop: 0, shown: Double(visible.minY)...Double(max(visible.maxY, visible.minY))) {
            scrollTo(y)
        }
        followed = now.bar
    }

    private func scrollTo(_ y: Double) {
        if reduceMotion { scroll.scrollTo(y: y) } else { withAnimation(.easeInOut(duration: 0.25)) { scroll.scrollTo(y: y) } }
    }

    /// Opens the note of column `index`, and brings the mark into view when it is not, a third of the way down.
    private func show(_ index: Int, in sheet: TabSheet, say: Bool) {
        told = index
        if say, let column = sheet.marks.columns[safe: index] { AccessibilityNotifier.announce(TabWords.describe(column), polite: true) }
        guard let box = page.engraving?.marks.first(where: { $0.mark == index }) else { return }
        let viewport = Double(visible.height)
        let top = box.top, bottom = box.columnBottom
        if top < Double(visible.minY) || bottom > Double(visible.maxY) {
            scrollTo(max(min(max(top - viewport / 3, bottom - viewport), top), 0))
        }
    }

    // MARK: the player and the note

    private func player(_ sheet: TabSheet) -> some View {
        PracticeBar(practice: practice, measures: sheet.index.measures, place: place.map { ($0.bar, $0.beat) },
                    follows: clock != nil, canFetch: canFetch, onFetch: fetch)
    }

    /// The note about a mark, under the tab and the player: what the note is, and until it can be fixed here, its bar to
    /// listen to slowly and the next "?". Next ? stays at the last one, dimmed and saying so, so the focus is not lost.
    @ViewBuilder private func note(_ sheet: TabSheet) -> some View {
        if let at = told, let column = sheet.marks.columns[safe: at] {
            let doubts = sheet.marks.doubts
            let next = doubts.first { $0 > at }
            let showNext = next != nil || doubts.count > 1
            let words = TabWords.describe(column)
            let slowly = String(localized: "Play this bar slowly")
            let nextName = String(localized: "Next uncertain note")
            let then = [canPlay ? slowly : nil, next != nil ? nextName : nil].compactMap { $0 }
            VStack(alignment: .leading, spacing: Space.s2) {
                Divider().overlay(Color.Scribe.border)
                HStack(alignment: .top, spacing: Space.s2) {
                    Text(words)
                        .font(Font.Scribe.body)
                        .foregroundStyle(Color.Scribe.text)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityLabel(then.isEmpty ? words : words + " " + String(localized: "Then: \(then.joined(separator: ", "))."))
                        .accessibilityIdentifier("fs-tab-note")
                    Button { told = nil } label: {
                        Image(systemName: PlayIcon.close.systemName).frame(width: 44, height: 44).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.Scribe.text)
                    .accessibilityLabel(String(localized: "Close"))
                    .accessibilityIdentifier("fs-tab-note-close")
                }
                FlowLayout(spacing: Space.s2, lineSpacing: Space.s1) {
                    if canPlay {
                        Button { practice.playBarSlowly(column.bar) } label: { Label(slowly, systemImage: PlayIcon.play.systemName) }
                            .buttonStyle(.outline)
                            .accessibilityIdentifier("fs-tab-note-slowly")
                    }
                    if showNext {
                        Button { if let next { show(next, in: sheet, say: true) } } label: { Text("Next ?") }
                            .buttonStyle(.plainText)
                            .opacity(next == nil ? 0.38 : 1)
                            .accessibilityLabel(nextName)
                            .accessibilityValue(next == nil ? String(localized: "Last uncertain note") : "")
                            .accessibilityIdentifier("fs-tab-note-next")
                    }
                }
            }
            .padding(.horizontal, Space.s4)
            .padding(.bottom, Space.s2)
            .background(Color.Scribe.bg)
        }
    }

    // MARK: full screen

    private func focusControls(_ sheet: TabSheet) -> some View {
        let leave = Button { focus = focus.leave() } label: {
            Image(systemName: "arrow.down.right.and.arrow.up.left").frame(width: 44, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(Color.Scribe.text)
        .keyboardShortcut(.cancelAction)
        .accessibilityLabel(String(localized: "Leave full screen"))
        .accessibilityIdentifier("fs-tab-full-screen-leave")
        // Any touch on the controls keeps them up a while longer.
        let touched = TapGesture().onEnded { touches += 1 }
        return Group {
            if focus.controlsShown(assistive: assistive) {
                VStack(spacing: 0) {
                    HStack(spacing: Space.s1) {
                        leave
                        Spacer()
                        zoomButtons(large: true)
                    }
                    .padding(.horizontal, Space.s2)
                    .background(Color.Scribe.bg)
                    .simultaneousGesture(touched)
                    .accessibilityIdentifier("fs-tab-focus-controls")
                    Spacer(minLength: 0)
                    player(sheet).simultaneousGesture(touched)
                }
            } else {
                // Only the small buttons: Play or Pause when there is a recording, and Leave full screen.
                HStack(spacing: 0) {
                    if canPlay {
                        Button(action: practice.toggle) {
                            Image(systemName: (practice.playing ? PlayIcon.pause : PlayIcon.play).systemName)
                                .frame(width: 44, height: 44).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.Scribe.text)
                        .keyboardShortcut(.space, modifiers: [])
                        .accessibilityLabel(practice.playing ? String(localized: "Pause") : String(localized: "Play"))
                        .accessibilityIdentifier("fs-tab-focus-play")
                    }
                    leave
                }
                .padding(.horizontal, Space.s1)
                .background(Color.Scribe.bg, in: Capsule())
                .overlay(Capsule().strokeBorder(Color.Scribe.borderStrong, lineWidth: 1))
                .padding(Space.s2)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                .accessibilityIdentifier("fs-tab-focus-minimal")
            }
        }
    }
}

private struct EngraveKey: Equatable {
    var scale: Double
    var palette: TabPalette
    var ready: Bool
}

private struct CursorKey: Equatable {
    var canPlay: Bool
    var playing: Bool
    var jumps: Int
    var at: Double
    var engraving: Double
    var bars: Int
}

private struct HideKey: Equatable {
    var focus: TabFocus
    var playing: Bool
    var touches: Int
}

/// What went wrong asking the computer for a recording, as practice reads it.
enum TabFetch {
    static func error(_ e: TranscriptionError) -> any Error {
        switch e {
        case .http(let code, _): RecordingFetchError.status(code)
        case .interfaceMismatch(.app): RecordingFetchError.updateApp
        case .interfaceMismatch(.computer): RecordingFetchError.updateComputer
        default: e
        }
    }
}

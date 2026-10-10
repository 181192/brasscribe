import AVKit
import ScoreKit
import SwiftUI

/// Score, parts and practice: notation with cursor, the player, the parts panel (mute or
/// only this), repeat, speed, count-in, metronome, play-along and band-or-recording with
/// synced video.
struct ScoreScreen: View {
    @Environment(AppModel.self) private var app
    let piece: Piece
    @State private var model: PracticeModel?
    @State private var error: String?

    var body: some View {
        screenContent
            .navigationTitle(currentTitle)
            .toolbar { editToolbar }
            .task { await loadModel() }
            .onDisappear { model?.stopAll() }
            // "Open on the music stand" for the score that is already open: the path does not change,
            // so no new screen loads to take the request
            .onChange(of: app.openOnStand) { _, row in
                guard let row, row == piece.id.uuidString, let model else { return }
                app.openOnStand = nil
                if model.stand == nil { model.enterStand(from: .library(row)) }
            }
    }

    @ViewBuilder private var screenContent: some View {
        Group {
            if let model {
                if let stand = model.stand {
                    MusicStandView(model: model, stand: stand)
                } else {
                    PracticeView(model: model)
                }
            } else if let error {
                ProblemContent(title: String(localized: "This score can't be opened"), lead: nil,
                               reasons: [String(localized: "The file may be damaged. Your recording is safe.")], hint: nil, detail: error) {
                    EmptyView()
                }
            } else {
                ProgressView()
            }
        }
        .pageBackground()
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private var currentTitle: String {
        app.pieces.first(where: { $0.id == piece.id })?.displayTitle ?? piece.displayTitle
    }

    private var editToolbar: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Button { model?.stopAll(); app.path.append(.review(piece)) } label: {
                Label("Check the notes", systemImage: BrasscribeIcon.nextUncertain.systemName)
            }
            .accessibilityIdentifier("checkNotes")
        }
    }

    /// The score opens off the main thread (`PracticeModel.open`); the spinner shows meanwhile.
    private func loadModel() async {
        guard model == nil else { return }
        do {
            let loaded = try await PracticeModel.open(piece)
            guard model == nil, !Task.isCancelled else { loaded.stopAll(); return }
            if LaunchOptions.screen?.hasPrefix("part") == true { loaded.shownPart = loaded.myPart }
            if let id = app.showPartOnOpen { app.showPartOnOpen = nil; loaded.openedOnMyPart = true; loaded.shownPart = id }
            model = loaded
            // "This small band has no 1st Baritone…": said once, politely, when the score opens
            if let notice = loaded.seatNotice { AccessibilityNotifier.announce(notice, polite: true) }
            ScreenshotScenes.stage(loaded)
            // "Open on the music stand" from the library
            if let row = app.openOnStand {
                app.openOnStand = nil
                loaded.enterStand(from: .library(row))
            } else if LaunchOptions.screen?.hasPrefix("stand") == true {
                loaded.enterStand(from: .toolbar)
                ScreenshotScenes.stageStand(loaded)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct PracticeView: View {
    @Bindable var model: PracticeModel
    @Environment(AppModel.self) private var app
    @State private var showParts = false
    // the parts panel starts open on the Mac; on iPad it's one tap away, so the score keeps its width
    #if os(macOS)
    @State private var showInspector = true
    #else
    @State private var showInspector = false
    #endif
    @State private var showTalking = false
    @State private var showExport = LaunchOptions.screen == "export"
    @State private var showVideo = true
    @State private var toCheck = 0
    @FocusState private var focused: Bool
    @Environment(\.horizontalSizeClass) private var hsize
    @AccessibilityFocusState private var standButtonA11y: Bool
    /// The screen's height under the navigation bar. The bands above and below the score take at
    /// most 40 % of it, so the score keeps at least 55 % of the safe area with the navigation bar
    /// counted in (ScoreHeightUITests).
    @State private var screenHeight: CGFloat = 0
    #if os(macOS)
    // the Mac: the bands scroll only in a short window, so no content makes the window taller than the screen
    static let headerShare: CGFloat = 0.3
    static let playerShare: CGFloat = 0.35
    #else
    static let headerShare: CGFloat = 0.15
    static let playerShare: CGFloat = 0.25
    #endif

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    #if os(macOS)
    /// The parts column's width, and the screen width from which the score and the column both fit.
    static let partsWidth: CGFloat = 320
    static let partsFitWidth: CGFloat = 820
    @State private var partsFit = true

    /// Parts: shows or hides the column; where it doesn't fit, opens the parts in a sheet.
    private var partsShown: Binding<Bool> {
        Binding(get: { showInspector && partsFit }, set: { on in if partsFit { showInspector = on } else if on { showParts = true } })
    }
    #else
    private var partsShown: Binding<Bool> { $showInspector }
    #endif

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 0) {
                ScoreToolbar(model: model, wide: wide, showParts: $showParts, showInspector: partsShown,
                             showTalking: $showTalking, showVideo: $showVideo)
                // phone: the count scrolls with the music (NotationView), so the score keeps the screen
                if wide { StatusLine(model: model, toCheck: toCheck, wide: wide) { app.path.append(.review(model.piece)) } }
            }
            .dynamicTypeSize(wide ? DynamicTypeSize.xSmall ... DynamicTypeSize.accessibility5 : DynamicTypeSize.xSmall ... DynamicTypeSize.accessibility2)
            .heightShare(Self.headerShare, of: screenHeight)
            .accessibilitySortPriority(StackedAccessibility.header)
            Divider().overlay(Color.Brasscribe.border)
            ZStack(alignment: .bottomTrailing) {
                NotationView(model: model)
                VStack(alignment: .trailing, spacing: Space.s3) {
                    if let player = model.video, showVideo {
                        VideoPiP(player: player)
                            .frame(width: wide ? 280 : 160, height: wide ? 158 : 90)
                            .clipShape(RoundedRectangle(cornerRadius: Radius.sm))
                            .shadow(color: .black.opacity(0.15), radius: 4)
                            .accessibilityLabel(Text("Video of the performance, synced to the score"))
                            .accessibilitySortPriority(StackedAccessibility.overlay)
                    }
                }
                .padding(Space.s3)
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                if let missing = model.bandSoundsMissing { BandSoundsMissingLine(details: missing.details) }
                PlayerBar(model: model, wide: wide)
            }
            // the phone's chrome grows to about twice the default text size; past that the music keeps its room
            .dynamicTypeSize(wide ? DynamicTypeSize.xSmall ... DynamicTypeSize.accessibility5 : DynamicTypeSize.xSmall ... DynamicTypeSize.accessibility2)
            .heightShare(Self.playerShare, of: screenHeight)
            .background(Color.Brasscribe.surface.ignoresSafeArea(edges: .bottom))
            .accessibilityElement(children: .contain)
            // the score's scroll content runs on under the band: see `StackedAccessibility`
            .accessibilitySortPriority(StackedAccessibility.overlay)
            .accessibilityIdentifier("playerArea")
        }
        #if os(macOS)
        // The parts sit in a column of the screen's own, not an inspector: an inspector adds its width
        // to the window's minimum. Where the score and the column don't both fit, the column steps
        // aside and Parts opens them in a sheet.
        .sidePanel(shown: showInspector && partsFit, width: Self.partsWidth) { PartsPanel(model: model).layoutProbe("partsColumn") }
        .onGeometryChange(for: Bool.self) { $0.size.width >= Self.partsFitWidth } action: { partsFit = $0 }
        #else
        .inspector(isPresented: Binding(get: { wide && showInspector }, set: { showInspector = $0 })) {
            PartsPanel(model: model)
                .inspectorColumnWidth(min: 260, ideal: 320, max: 400)
        }
        #endif
        .toolbar {
            if !wide {
                // phone: the music stand sits in the navigation bar, so the part row keeps its room
                ToolbarItem(placement: .primaryAction) {
                    Button { model.enterStand(from: .toolbar) } label: {
                        Label("Music stand", systemImage: "arrow.up.left.and.arrow.down.right")
                    }
                    .accessibilityFocused($standButtonA11y)
                    .accessibilityIdentifier("musicStand")
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button { showExport = true } label: { Label("Share or print", systemImage: BrasscribeIcon.export.systemName).labelStyle(.titleAndIcon) }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
                    .accessibilityIdentifier("shareOrPrint")
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { screenHeight = $0 }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(model.piece.title))
        .accessibilityIdentifier("practiceScreen")
        // The score's scroll view takes arrow keys for scrolling, so bar navigation is
        // handled here, on the focused practice screen, before it reaches the scroll view.
        .focusable()
        .focusEffectDisabled()
        .focused($focused)
        .onAppear {
            focused = true
            refreshToCheck()
            // back from the music stand on a phone: focus returns to the navigation bar's button
            if !wide, model.focusStandButton {
                model.focusStandButton = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { standButtonA11y = true }
            }
        }
        .focusedSceneValue(\.practice, model)
        .onKeyPress(.rightArrow) { model.nextBar(); return .handled }
        .onKeyPress(.leftArrow) { model.previousBar(); return .handled }
        .onKeyPress(",") { model.changeSpeed(by: -5); return .handled }
        .onKeyPress(".") { model.changeSpeed(by: 5); return .handled }
        .sheet(isPresented: $showParts) {
            NavigationStack {
                ScrollView { PartsPanel(model: model) }
                    .pageBackground()
                    .navigationTitle(Text("Parts and sound"))
                    #if os(iOS)
                    .navigationBarTitleDisplayMode(.inline)
                    #endif
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showParts = false } } }
            }
            .presentationDetents([.medium, .large])
            #if os(macOS)
            // a narrow window's parts: the list scrolls inside the sheet
            .sheetSize(minWidth: 380, idealWidth: 420, maxWidth: 520, minHeight: 420)
            #endif
            .appAppearance()
        }
        .sheet(isPresented: $showTalking) { TalkingScoreView(model: model).appAppearance() }
        .sheet(isPresented: $showExport) { ExportView(model: model).appAppearance() }
        .alert(String(localized: "The sound can't play"), isPresented: Binding(get: { model.loadError != nil }, set: { if !$0 { model.dismissLoadError() } })) {
            Button("OK") {}
        } message: { Text("The score is still here to read. Try closing and opening it again.") }
    }

    private func refreshToCheck() {
        let items = ReviewList.items(score: model.score, composition: model.composition, uncertainty: model.uncertainty)
        let checked = model.piece.loadChecked()
        toCheck = items.filter { !checked.contains($0.id) }.count
        model.toCheck = toCheck
    }
}

/// "9 notes marked ? · Check them", and the ad lib note when those bars are near.
struct StatusLine: View {
    @Bindable var model: PracticeModel
    let toCheck: Int
    let wide: Bool
    let check: () -> Void

    var body: some View {
        let free = model.freeTimeBars.first { $0.lowerBound - 2 <= model.currentBar && model.currentBar <= $0.upperBound + 2 }
        if toCheck > 0 || free != nil {
            VStack(alignment: .leading, spacing: Space.s1) {
                if toCheck > 0 {
                    let count = wide ? (toCheck == 1 ? String(localized: "1 note marked ? (boxed ? = very unsure)") : String(localized: "\(toCheck) notes marked ? (boxed ? = very unsure)"))
                                     : (toCheck == 1 ? String(localized: "1 note marked ?") : String(localized: "\(toCheck) notes marked ?"))
                    // one button, one wrapping line: "? 9 notes marked ? · Check them"
                    Button(action: check) {
                        HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
                            UncertainMark(level: .uncertain)
                            Text("\(Text(count).foregroundStyle(Color.Brasscribe.textMuted)) \(Text(verbatim: "·").foregroundStyle(Color.Brasscribe.textMuted)) \(Text("Check them").underline().foregroundStyle(Color.Brasscribe.text))")
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(Text("\(count). Check them"))
                    .accessibilityIdentifier("checkThem")
                }
                if let free {
                    HelperLine(systemImage: BrasscribeIcon.info.systemName,
                               text: free.count == 1
                                ? String(localized: "Bar \(free.lowerBound + 1) has no steady beat (ad lib.). Its rhythms are approximate.")
                                : String(localized: "Bars \(free.lowerBound + 1)–\(free.upperBound + 1) have no steady beat (ad lib.). Their rhythms are approximate."))
                }
            }
            .font(Font.Brasscribe.callout)
            .padding(.horizontal, Space.s5)
            .padding(.bottom, Space.s1)
            // wrapping text measured at zero width is endlessly tall; a floor keeps the window its size
            .frame(minWidth: 300, maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct ScoreToolbar: View {
    @Bindable var model: PracticeModel
    @Environment(AppModel.self) private var app
    @State private var explainSource: PartSourceKind?
    @Environment(\.dynamicTypeSize) private var typeSize
    @AccessibilityFocusState private var standButtonA11y: Bool
    @FocusState private var standButtonKeys: Bool
    let wide: Bool
    @Binding var showParts: Bool
    @Binding var showInspector: Bool
    @Binding var showTalking: Bool
    @Binding var showVideo: Bool

    /// "As written for B♭" names the key of the part shown; all parts is just "As written".
    private var writtenLabel: String {
        let keys = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
        guard let id = model.shownPart, let p = model.score.part(id: id) else { return String(localized: "As written") }
        let k = ((p.transposeSemitones % 12) + 12) % 12
        return k == 0 ? String(localized: "As written") : String(localized: "As written for \(keys[k])")
    }

    /// "Written (B♭)" in the phone's View menu; the full wording is the section's note.
    private var shortWrittenLabel: String {
        let keys = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
        guard let id = model.shownPart, let p = model.score.part(id: id) else { return String(localized: "Written") }
        let k = ((p.transposeSemitones % 12) + 12) % 12
        return k == 0 ? String(localized: "Written") : String(localized: "Written (\(keys[k]))")
    }

    var body: some View {
        Group {
            if !wide && typeSize >= .accessibility1 {
                // the largest sizes: the part's name keeps the row (cut at its end); the source label
                // sits above the music, where it can wrap
                HStack(spacing: Space.s2) { parts.frame(maxWidth: .infinity, alignment: .leading); view }
            } else if !wide {
                // phone: one row, the part and where it comes from, then View (pitch, zoom, the stand)
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s2) { parts; sourcePill; Spacer(minLength: 0); view }
                    // a longer part name: View keeps only its icon, so the pill stays on the row
                    HStack(spacing: Space.s2) { parts; sourcePill; Spacer(minLength: 0); viewMenu(iconOnly: true) }
                    VStack(alignment: .leading, spacing: Space.s1) {
                        HStack(spacing: Space.s2) { parts; Spacer(minLength: 0); view }
                        sourcePill
                    }
                    VStack(alignment: .leading, spacing: Space.s1) { parts; sourcePill; view }
                }
            } else if typeSize >= .accessibility1 {
                // the largest text sizes: one control per row, nothing squeezed
                VStack(alignment: .leading, spacing: Space.s2) { parts; sourcePill; pitch; standButton; view; inspectorToggle }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s3) { controls }
                    VStack(alignment: .leading, spacing: Space.s2) {
                        HStack(spacing: Space.s3) { parts; sourcePill; Spacer(minLength: 0); view; inspectorToggle }
                        HStack(spacing: Space.s3) { pitch; standButton }
                    }
                }
            }
        }
        .padding(.horizontal, Space.s5).padding(.vertical, wide ? Space.s2 : Space.s1)
        .onAppear {
            // back from the music stand: focus returns to the button that opened it
            guard wide, model.focusStandButton else { return }
            model.focusStandButton = false
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { standButtonA11y = true; standButtonKeys = true }
        }
    }

    /// Music stand: the score alone, for playing from the stand (F).
    private var standButton: some View {
        Button { model.enterStand(from: .toolbar) } label: {
            Label("Music stand", systemImage: "arrow.up.left.and.arrow.down.right").labelStyle(.titleAndIcon)
        }
        .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 44))
        .fixedSize()
        .padShortcut("f")
        .help(Text("The music alone, for playing from the stand (F)"))
        .accessibilityFocused($standButtonA11y)
        .focused($standButtonKeys)
        .accessibilityIdentifier("musicStand")
    }

    @ViewBuilder private var inspectorToggle: some View {
        if wide {
            Toggle(isOn: $showInspector) { Label("Parts", systemImage: BrasscribeIcon.parts.systemName) }
                .toggleStyle(.button)
                .accessibilityHint(Text("Shows or hides the list of parts, where you can mute them."))
        }
    }

    /// Where the part shown comes from: a small outline pill that explains itself.
    @ViewBuilder private var sourcePill: some View {
        if let id = model.shownPart, let kind = model.partSources[id] { SourceLabel(kind: kind, compact: true) }
    }

    @ViewBuilder private var controls: some View {
        parts
        sourcePill
        pitch
        if wide { ZoomButtons(model: model, vertical: false) }
        Spacer(minLength: Space.s2)
        standButton
        view
        inspectorToggle
    }

    @ViewBuilder private var parts: some View {
        if !wide {
            // phone: a menu whose label wraps at large text sizes instead of running off the screen
            Menu {
                partChoices.pickerStyle(.inline)
            } label: {
                HStack(spacing: Space.s1) {
                    Text(shownTitle).lineLimit(1).truncationMode(.tail)
                    Image(systemName: "chevron.up.chevron.down").font(.footnote.weight(.semibold)).accessibilityHidden(true)
                }
                .font(Font.Brasscribe.body)
                .foregroundStyle(Color.Brasscribe.text)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(Text("Parts"))
            .accessibilityValue(Text(shownTitle))
            .accessibilityIdentifier("partPicker")
        } else {
            partChoices
                .pickerStyle(.menu)
                .labelsHidden()
                .menuTint()
                .accessibilityIdentifier("partPicker")
                .frame(minHeight: 44)
                .fixedSize()
        }
    }

    private var partChoices: some View {
        Picker(selection: $model.shownPart) {
            Text("All parts").tag(String?.none)
            ForEach(model.score.parts) { p in
                Text(p.id == model.myPart ? String(localized: "\(p.displayName) (you)") : p.displayName).tag(String?.some(p.id))
            }
        } label: { Label("Parts", systemImage: BrasscribeIcon.parts.systemName) }
    }

    private var shownTitle: String {
        guard let id = model.shownPart, let p = model.score.part(id: id) else { return String(localized: "All parts") }
        return id == model.myPart ? String(localized: "\(p.displayName) (you)") : p.displayName
    }

    private var pitch: some View {
        Segmented(label: String(localized: "Pitch"), selection: $model.pitchMode,
                  options: [(PitchMode.written, writtenLabel),
                            (PitchMode.concert, String(localized: "Concert pitch"))])
        .accessibilityIdentifier("pitchMode")
        .help(Text("Written is what you read on your part. Concert is how it sounds on a piano."))
    }

    private var view: some View { viewMenu(iconOnly: false) }

    private func viewMenu(iconOnly: Bool) -> some View {
        Menu {
            if !wide, typeSize >= .accessibility1, let id = model.shownPart, let kind = model.partSources[id] {
                // the largest sizes: where the part comes from, whole, with its explanation
                Section {
                    Button { explainSource = kind } label: { Label(kind.title, systemImage: kind.icon.systemName) }
                        .accessibilityIdentifier("sourceLabel")
                }
            }
            if !wide {
                // phone: the pitch and the zoom live here, so the music keeps the screen
                Section {
                    Picker(selection: $model.pitchMode) {
                        Text(shortWrittenLabel).tag(PitchMode.written)
                        Text("Concert").tag(PitchMode.concert)
                    } label: { Text("Pitch") }
                    .pickerStyle(.inline)
                } header: { Text("Written is what you read on your part. Concert is how it sounds on a piano.") }
                Section {
                    Button { model.zoom = min(4, model.zoom + 0.25) } label: { Label("Zoom in", systemImage: BrasscribeIcon.zoomIn.systemName) }
                    Button { model.zoom = max(0.5, model.zoom - 0.25) } label: { Label("Zoom out", systemImage: BrasscribeIcon.zoomOut.systemName) }
                }
            }
            Button { model.enterStand(from: .toolbar) } label: { Label("Music stand", systemImage: "arrow.up.left.and.arrow.down.right") }
            Button { showTalking = true } label: { Label("Read aloud", systemImage: BrasscribeIcon.talkingScore.systemName) }
                .keyboardShortcut("t", modifiers: [.command, .shift])
            if model.video != nil {
                Toggle(isOn: $showVideo) { Label("Show video", systemImage: BrasscribeIcon.video.systemName) }
            }
            if model.piece.profile == .solo {
                // a friend played it: Choose output's "Who played this?"
                Button { model.stopAll(); app.path.append(.output(model.piece)) } label: {
                    Label("Write for another instrument…", systemImage: BrasscribeIcon.parts.systemName)
                }
                .accessibilityIdentifier("writeForAnother")
            } else if model.composition != nil {
                // How should the score be? again: what its "You can change this later" promises
                Button { model.stopAll(); app.path.append(.output(model.piece)) } label: {
                    Label("Band, difficulty and key…", systemImage: BrasscribeIcon.parts.systemName)
                }
                .accessibilityIdentifier("changeOutput")
            }
            if !wide {
                Button { showParts = true } label: { Label("Parts and sound", systemImage: BrasscribeIcon.parts.systemName) }
                    .keyboardShortcut("p", modifiers: [.command, .shift])
            }
        } label: {
            if iconOnly || (!wide && typeSize >= .accessibility1) {
                Label("View", systemImage: BrasscribeIcon.more.systemName).labelStyle(.iconOnly).frame(minWidth: 44)
            } else {
                Label("View", systemImage: BrasscribeIcon.more.systemName)
            }
        }
        .menuStyle(.button)
        .tint(Color.Brasscribe.text)
        .frame(minHeight: 44)
        .fixedSize()
        .accessibilityIdentifier("viewMenu")
        .alert(explainSource?.title ?? "", isPresented: Binding(get: { explainSource != nil }, set: { if !$0 { explainSource = nil } })) {
            Button("OK") {}
        } message: { Text(explainSource?.explanation ?? "") }
    }
}

struct ZoomButtons: View {
    @Bindable var model: PracticeModel
    let vertical: Bool

    var body: some View {
        let layout = vertical ? AnyLayout(VStackLayout(spacing: 0)) : AnyLayout(HStackLayout(spacing: Space.s1))
        layout {
            if vertical { zoomIn; zoomOut } else {
                zoomOut
                Text(percentText(model.zoom * 100)).monospacedDigit().frame(minWidth: 48)
                    .accessibilityLabel(Text("Zoom \(percentText(model.zoom * 100))"))
                zoomIn
            }
        }
        .foregroundStyle(Color.Brasscribe.text)
        .background(Color.Brasscribe.secondary, in: RoundedRectangle(cornerRadius: Radius.md))
        .fixedSize()
    }

    private var zoomIn: some View {
        Button { model.zoom = min(4, model.zoom + 0.25) } label: { Image(systemName: BrasscribeIcon.zoomIn.systemName).frame(width: 48, height: 48) }
            .buttonStyle(.plain)
            .contentShape(Rectangle())
            .accessibilityLabel(Text("Zoom in"))
            .keyboardShortcut("+", modifiers: .command)
    }
    private var zoomOut: some View {
        Button { model.zoom = max(0.5, model.zoom - 0.25) } label: { Image(systemName: BrasscribeIcon.zoomOut.systemName).frame(width: 48, height: 48) }
            .buttonStyle(.plain)
            .contentShape(Rectangle())
            .accessibilityLabel(Text("Zoom out"))
            .keyboardShortcut("-", modifiers: .command)
    }
}

/// The player: Play first, previous/next bar, the position with the beat counter beside
/// it, the tempo, band or recording, then the practice controls. The practice controls wrap
/// onto more rows and never clip.
/// Shown above the player when the band sounds are not installed: what to do next, and where
/// they were looked for under the tech-person details.
struct BandSoundsMissingLine: View {
    let details: String
    @State private var showing = false

    var body: some View {
        Button { showing = true } label: {
            HStack(spacing: Space.s2) {
                Image(systemName: BrasscribeIcon.info.systemName).accessibilityHidden(true)
                Text("The band sounds are missing.").lineLimit(1)
                Spacer(minLength: Space.s2)
                Text("Details").underline()
            }
            .font(Font.Brasscribe.callout)
            .foregroundStyle(Color.Brasscribe.text)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(.horizontal, Space.s4)
            .background(Color.Brasscribe.surface)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text("The band sounds are missing. Details"))
        .accessibilityIdentifier("bandSoundsMissing")
        .sheet(isPresented: $showing) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.s4) {
                        Text("The band sounds are missing. Reinstall Brasscribe Play to hear the band.")
                            .font(Font.Brasscribe.body)
                            .fixedSize(horizontal: false, vertical: true)
                        if !details.isEmpty {
                            SectionLabel(String(localized: "Details for the band's tech person"))
                            Text(details).font(.footnote.monospaced()).foregroundStyle(Color.Brasscribe.textMuted).textSelection(.enabled)
                        }
                    }
                    .padding(Space.s5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .pageBackground()
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showing = false } } }
            }
            .presentationDetents([.medium, .large])
            .appAppearance()
        }
    }
}

struct PlayerBar: View {
    @Bindable var model: PracticeModel
    let wide: Bool
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var editRepeat = false

    var body: some View {
        Group {
            if wide {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s5) { transport; position; hear; Divider().frame(height: 48); practiceWide }
                    VStack(alignment: .leading, spacing: Space.s3) {
                        HStack(spacing: Space.s5) { transport; position; Spacer(minLength: 0); hear }
                        practiceWide
                    }
                }
                .padding(.horizontal, Space.s6)
                .padding(.vertical, Space.s3)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.Brasscribe.surface)
                .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
            } else if typeSize >= .accessibility1 {
                // the largest text sizes: the transport, the bar, and one menu with the practice controls
                VStack(alignment: .leading, spacing: Space.s1) {
                    HStack(spacing: Space.s3) {
                        transport
                        Text("Bar \(model.currentBar + 1)").font(Font.Brasscribe.headline).monospacedDigit().lineLimit(1)
                            .accessibilityLabel(Text(model.positionDescription))
                            .accessibilityIdentifier("position")
                        Spacer(minLength: 0)
                    }
                    practiceMenuAll
                }
                .padding(.horizontal, Space.s4)
                .padding(.vertical, Space.s1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.Brasscribe.surface)
                .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
            } else {
                VStack(alignment: .leading, spacing: Space.s1) {
                    HStack(spacing: Space.s3) { transport; position; Spacer(minLength: 0) }
                    chipsPhone
                }
                .padding(.horizontal, Space.s4)
                .padding(.vertical, Space.s1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.Brasscribe.surface)
                .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
            }
        }
        .labelStyle(.titleAndIcon)
    }

    // MARK: transport

    private var transport: some View {
        HStack(spacing: Space.s1) {
            Button { model.previousBar() } label: { Image(systemName: BrasscribeIcon.previousBar.systemName).frame(width: 48, height: 48).contentShape(Rectangle()) }
                .buttonStyle(.plain)
                .accessibilityLabel(Text("Previous bar"))
                .accessibilityIdentifier("previousBar")
            Button { model.togglePlay() } label: {
                Image(systemName: model.isPlaying ? BrasscribeIcon.pause.systemName : BrasscribeIcon.play.systemName)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(Color.Brasscribe.onPrimary)
                    .frame(width: wide ? 56 : 48, height: wide ? 56 : 48)
                    .background(Color.Brasscribe.primary, in: Circle())
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(model.isPlaying ? Text("Pause") : Text("Play"))
            .accessibilitySortPriority(10)
            .padShortcut(.space)
            .accessibilityIdentifier("playPause")
            Button { model.nextBar() } label: { Image(systemName: BrasscribeIcon.nextBar.systemName).frame(width: 48, height: 48).contentShape(Rectangle()) }
                .buttonStyle(.plain)
                .accessibilityLabel(Text("Next bar"))
                .accessibilityIdentifier("nextBar")
        }
        .foregroundStyle(Color.Brasscribe.text)
    }

    private var position: some View {
        let (bar, beat) = model.score.position(atTick: Int(model.position * Double(Score.ticksPerQuarter)))
        let beats = model.score.measures.indices.contains(bar - 1) ? model.score.measures[bar - 1].beats : 4
        let bpm = model.score.tempo(atTick: Int(model.position * Double(Score.ticksPerQuarter)))
        return VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: Space.s3) {
                Group {
                    if let b = model.countInBeat {
                        Text("Count-in \(b)")
                    } else if wide {
                        Text("Bar \(bar), beat \(Int(beat))")
                    } else {
                        Text("\(Text("Bar \(bar)").font(Font.Brasscribe.headline)) \(Text("of \(model.score.measures.count)").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted))")
                    }
                }
                .font(Font.Brasscribe.headline)
                .monospacedDigit()
                BeatCounter(beats: beats, current: Int(beat))
            }
            if wide {
                Text(model.speedPercent == 100 ? String(localized: "of \(model.score.measures.count) · ♩ = \(Int(bpm.rounded()))")
                     : String(localized: "of \(model.score.measures.count) · ♩ = \(Int((bpm * model.speedPercent / 100).rounded())) (slowed from \(Int(bpm.rounded())))"))
                    .font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted).monospacedDigit()
            }
        }
        .fixedSize()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(model.countInBeat.map { String(localized: "Count-in \($0)") } ?? model.positionDescription))
        .accessibilityIdentifier("position")
        .accessibilityValue(Text("\(model.currentBar + 1)"))
        .accessibilityAddTraits(.updatesFrequently)
    }

    @ViewBuilder private var hear: some View {
        if model.hasOriginal {
            Segmented(label: String(localized: "Hear the band or the recording"), selection: $model.hearOriginal,
                      options: [(false, String(localized: "Hear the band")), (true, String(localized: "Recording"))], wraps: false)
            .accessibilityHint(Text("Switch between the score and the recording at the same place."))
            .accessibilityIdentifier("originalToggle")
        }
    }

    // MARK: practice, desktop and tablet

    @ViewBuilder private var practiceWide: some View {
        let layout = AnyLayout(FlowLayout(spacing: Space.s3))
        layout {
            speedSlider
            repeatFields
            Toggle(isOn: $model.countIn) { Label("Count-in", systemImage: BrasscribeIcon.countIn.systemName) }
                .toggleStyle(.chip).fixedSize().padShortcut("c")
                .help(Text("One bar of clicks before the music starts."))
            Toggle(isOn: $model.metronome) { Label("Metronome", systemImage: BrasscribeIcon.metronome.systemName) }
                .toggleStyle(.chip).fixedSize().padShortcut("m")
            if model.myPart != nil { muteMyPart.fixedSize() }
        }
    }

    private var speedSlider: some View {
        HStack(spacing: Space.s2) {
            Text("Speed").font(Font.Brasscribe.label)
            Slider(value: $model.speedPercent, in: 25...150, step: 5) { Text("Speed") }
                .labelsHidden()
                .macControlSize(.large)
                .frame(width: 140)
                .accessibilityValue(Text(percentText(model.speedPercent)))
                .accessibilityIdentifier("speed")
            Text(percentText(model.speedPercent)).monospacedDigit().frame(minWidth: 48, alignment: .trailing).accessibilityHidden(true)
        }
        .frame(minHeight: 48)
    }

    private var repeatFields: some View {
        let last = model.score.measures.count - 1
        return HStack(spacing: Space.s2) {
            Image(systemName: BrasscribeIcon.loop.systemName).accessibilityHidden(true)
            Text("Repeat bars")
            Stepper(value: $model.loopFrom, in: 0...last) { Text("\(model.loopFrom + 1)").monospacedDigit().frame(minWidth: 28) }
                .accessibilityLabel(Text("Repeat from bar"))
                .accessibilityValue(Text("\(model.loopFrom + 1)"))
                .onChange(of: model.loopFrom) { if model.looping { model.setLoop(true) } }
            Text("to")
            Stepper(value: $model.loopTo, in: 0...last) { Text("\(model.loopTo + 1)").monospacedDigit().frame(minWidth: 28) }
                .accessibilityLabel(Text("Repeat to bar"))
                .accessibilityValue(Text("\(model.loopTo + 1)"))
                .onChange(of: model.loopTo) { if model.looping { model.setLoop(true) } }
            if model.looping {
                Button { model.setLoop(false) } label: { Text("Stop repeating") }
                    .buttonStyle(.plainText)
                    .accessibilityIdentifier("loopToggle")
            } else {
                Button { model.setLoop(true) } label: { Text("Repeat") }
                    .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 44))
                    .keyboardShortcut("l", modifiers: [.shift])
                    .accessibilityIdentifier("loopToggle")
            }
            // hidden button so plain L repeats the current bar on iPad
            Button("") { model.toggleLoopCurrentBar() }.padShortcut("l").hidden().frame(width: 0).accessibilityHidden(true)
        }
        .font(Font.Brasscribe.label)
        .frame(minHeight: 48)
        .fixedSize()
    }

    private var muteMyPart: some View {
        Toggle(isOn: $model.playAlong) { Label("Mute my part", systemImage: BrasscribeIcon.playAlong.systemName) }
            .toggleStyle(.chip)
            .padShortcut("a")
            .accessibilityHint(Text("Mutes your part so you can play it with the band."))
            .accessibilityIdentifier("muteMyPart")
    }

    // MARK: practice, phone

    /// Two rows that fit a phone at the default text size: Speed and Repeat, then Mute my part and
    /// Practice (count-in, metronome, the recording). At large text sizes they stack.
    @ViewBuilder private var chipsPhone: some View {
        ViewThatFits(in: .horizontal) {
            VStack(spacing: Space.s2) {
                HStack(spacing: Space.s2) { speedChip; repeatChip }
                HStack(spacing: Space.s2) { if model.myPart != nil { muteMyPart }; practiceMenu.fixedSize(horizontal: model.myPart != nil, vertical: false) }
            }
            .lineLimit(1)
            VStack(alignment: .leading, spacing: Space.s2) { speedChip; repeatChip; if model.myPart != nil { muteMyPart }; practiceMenu }
        }
    }

    @ViewBuilder private var speedChip: some View {
        Menu {
            ForEach([50.0, 60, 70, 75, 80, 90, 100, 110, 125], id: \.self) { s in
                Button { model.speedPercent = s } label: {
                    if model.speedPercent == s { Label(percentText(s), systemImage: "checkmark") } else { Text(percentText(s)) }
                }
            }
        } label: {
            ChipLabel(title: String(localized: "Speed \(percentText(model.speedPercent))"), systemImage: BrasscribeIcon.speed.systemName,
                      active: model.speedPercent != 100)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("speedMenu")
        .accessibilityValue(Text(percentText(model.speedPercent)))
        .accessibilityAdjustableAction { d in model.changeSpeed(by: d == .increment ? 5 : -5) }

    }

    @ViewBuilder private var repeatChip: some View {
        Menu {
            Button { model.loopFrom = model.currentBar; model.loopTo = model.currentBar; model.setLoop(true) } label: {
                Text("Repeat this bar")
            }
            Button { editRepeat = true } label: { Text("Repeat bars \(model.loopFrom + 1) to \(model.loopTo + 1)…") }
            if model.looping { Button(role: .destructive) { model.setLoop(false) } label: { Text("Stop repeating") } }
        } label: {
            ChipLabel(title: String(localized: "Repeat"), systemImage: BrasscribeIcon.loop.systemName, active: model.looping)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("loopToggle")
        .accessibilityValue(model.looping ? Text("Bars \(min(model.loopFrom, model.loopTo) + 1) to \(max(model.loopFrom, model.loopTo) + 1)") : Text("Off"))
        .sheet(isPresented: $editRepeat) { RepeatSheet(model: model).appAppearance() }

    }

    /// Every practice control in one menu, for the largest text sizes.
    private var practiceMenuAll: some View {
        Menu {
            Picker(selection: $model.speedPercent) {
                ForEach([50.0, 60, 70, 75, 80, 90, 100, 110, 125], id: \.self) { s in Text(percentText(s)).tag(s) }
            } label: { Label("Speed \(percentText(model.speedPercent))", systemImage: BrasscribeIcon.speed.systemName) }
            .pickerStyle(.menu)
            Button { model.loopFrom = model.currentBar; model.loopTo = model.currentBar; model.setLoop(true) } label: {
                Label("Repeat this bar", systemImage: BrasscribeIcon.loop.systemName)
            }
            Button { editRepeat = true } label: { Text("Repeat bars \(model.loopFrom + 1) to \(model.loopTo + 1)…") }
            if model.looping { Button(role: .destructive) { model.setLoop(false) } label: { Text("Stop repeating") } }
            if model.myPart != nil {
                Toggle(isOn: $model.playAlong) { Label("Mute my part", systemImage: BrasscribeIcon.playAlong.systemName) }
                    .accessibilityIdentifier("muteMyPart")
            }
            Toggle(isOn: $model.countIn) { Label("Count-in", systemImage: BrasscribeIcon.countIn.systemName) }
            Toggle(isOn: $model.metronome) { Label("Metronome", systemImage: BrasscribeIcon.metronome.systemName) }
            if model.hasOriginal {
                Toggle(isOn: $model.hearOriginal) { Label("Hear the recording", systemImage: BrasscribeIcon.listenBar.systemName) }
            }
        } label: {
            ChipLabel(title: String(localized: "Practice"), systemImage: BrasscribeIcon.more.systemName,
                      active: model.playAlong || model.looping || model.speedPercent != 100 || model.countIn || model.metronome || model.hearOriginal, menu: true)
                .lineLimit(1)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("practiceMenu")
        .sheet(isPresented: $editRepeat) { RepeatSheet(model: model).appAppearance() }
    }

    /// The practice switches used less often, in one menu.
    private var practiceMenu: some View {
        Menu {
            Toggle(isOn: $model.countIn) { Label("Count-in", systemImage: BrasscribeIcon.countIn.systemName) }
            Toggle(isOn: $model.metronome) { Label("Metronome", systemImage: BrasscribeIcon.metronome.systemName) }
            if model.hasOriginal {
                // "Hear the recording": the words say it plays, never that it records
                Toggle(isOn: $model.hearOriginal) { Label("Hear the recording", systemImage: BrasscribeIcon.listenBar.systemName) }
                    .accessibilityIdentifier("originalToggle")
            }
        } label: {
            ChipLabel(title: String(localized: "Practice"), systemImage: BrasscribeIcon.more.systemName,
                      active: model.countIn || model.metronome || model.hearOriginal, menu: true)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("practiceMenu")
        // plain C and M still switch them on iPad
        .background {
            Button("") { model.countIn.toggle() }.padShortcut("c").hidden().accessibilityHidden(true)
            Button("") { model.metronome.toggle() }.padShortcut("m").hidden().accessibilityHidden(true)
        }
    }
}

/// "Repeat bars [12] to [13]" on the phone.
struct RepeatSheet: View {
    @Bindable var model: PracticeModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        let last = model.score.measures.count - 1
        NavigationStack {
            Form {
                Stepper(value: $model.loopFrom, in: 0...last) { Text("From bar \(model.loopFrom + 1)").monospacedDigit() }
                Stepper(value: $model.loopTo, in: 0...last) { Text("To bar \(model.loopTo + 1)").monospacedDigit() }
                Text("Plays these bars over and over.").foregroundStyle(Color.Brasscribe.textMuted)
            }
            .navigationTitle(Text("Repeat bars"))
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Repeat") { model.setLoop(true); dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }
}

/// "1 2 3 4" with the current beat bold and underlined. It never flashes.
struct BeatCounter: View {
    let beats: Int
    let current: Int
    var body: some View {
        HStack(spacing: Space.s2) {
            ForEach(1...max(1, min(beats, 12)), id: \.self) { b in
                Text(verbatim: "\(b)")
                    .font(b == current ? Font.Brasscribe.headline : Font.Brasscribe.callout)
                    .underline(b == current)
                    .foregroundStyle(b == current ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
            }
        }
        .monospacedDigit()
        .accessibilityHidden(true)
    }
}

/// Every part with labelled Mute and Only this toggles; your own part is bold with a
/// leading bar and says "your part". Then the sound settings.
struct PartsPanel: View {
    @Bindable var model: PracticeModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s4) {
                SectionLabel(String(localized: "Parts"))
                VStack(spacing: Space.s1) {
                    ForEach(model.score.parts) { p in row(p) }
                }
                Text("Your part is muted with “Mute my part”, so you can play along. “Only this” plays one part alone.")
                    .font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)

                SectionLabel(String(localized: "Sound"))
                VStack(alignment: .leading, spacing: Space.s3) {
                    Picker(selection: Binding(get: { model.myPart }, set: { model.makeMine($0) })) {
                        if model.myPart == nil { Text("None").tag(String?.none) }
                        ForEach(model.score.parts) { p in Text(p.displayName).tag(String?.some(p.id)) }
                    } label: { Text("My part") }
                    .pickerStyle(.menu)
                    .menuTint()
                    Stepper(value: $model.transpose, in: -12...12) {
                        Text(model.transpose == 0 ? String(localized: "Pitch as written")
                             : String(localized: "Move the pitch \(model.transpose > 0 ? "+" : "")\(model.transpose) semitones"))
                    }
                    Toggle(isOn: $model.room) { Text("Concert hall sound") }
                    if !model.soundDescription.isEmpty {
                        Text(model.soundDescription).font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
                    }
                }
            }
            .padding(Space.s4)
        }
        .background(Color.Brasscribe.surface)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Parts and sound"))
    }

    private func row(_ p: Part) -> some View {
        let mine = p.id == model.myPart
        return HStack(spacing: Space.s2) {
            Rectangle().fill(mine ? Color.Brasscribe.text : Color.clear).frame(width: 3).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                Text(mine ? String(localized: "\(p.displayName) (you)") : p.displayName)
                    .font(mine ? Font.Brasscribe.headline : Font.Brasscribe.body)
                if let kind = model.partSources[p.id] { SourceCaption(kind: kind) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Toggle(isOn: Binding(get: { model.isMuted(p.id) }, set: { model.setMuted(p.id, $0) })) {
                Label("Mute", systemImage: BrasscribeIcon.mute.systemName)
            }
            .toggleStyle(SmallToggleStyle())
            .accessibilityLabel(Text("Mute \(p.displayName)"))
            Toggle(isOn: Binding(get: { model.isSoloed(p.id) }, set: { model.setSoloed(p.id, $0) })) {
                Label("Only this", systemImage: BrasscribeIcon.solo.systemName)
            }
            .toggleStyle(SmallToggleStyle())
            .accessibilityLabel(Text("Only \(p.displayName)"))
            .layoutProbe("onlyThis-\(p.id)")
            .help(Text("Only this: hear this part alone."))
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .contain)
    }
}

/// The compact on/off used in the parts list: outline when off, tonal fill + ink edge + ✓
/// when on. 44 pt on touch, 36 pt with a pointer.
struct SmallToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: 4) {
                if configuration.isOn { Image(systemName: "checkmark").font(.caption.weight(.bold)) }
                configuration.label.labelStyle(.titleAndIcon)
            }
            // the part's name wraps; the toggles never do
            .lineLimit(1)
            .fixedSize()
            .font(labelFont)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, Space.s2)
            .frame(minHeight: minHeight)
            .background {
                RoundedRectangle(cornerRadius: Radius.sm)
                    .fill(configuration.isOn ? Color.Brasscribe.secondary : Color.clear)
                    .overlay(RoundedRectangle(cornerRadius: Radius.sm)
                        .strokeBorder(configuration.isOn ? Color.Brasscribe.text : Color.Brasscribe.borderStrong, lineWidth: configuration.isOn ? 1.5 : 1))
            }
            .contentShape(RoundedRectangle(cornerRadius: Radius.sm))
        }
        .buttonStyle(.plain)
        .accessibilityRepresentation { Toggle(isOn: configuration.$isOn) { configuration.label } }
    }

    private var labelFont: Font {
        #if os(iOS)
        Font.Brasscribe.caption.weight(.semibold)
        #else
        .system(size: 13, weight: .semibold)
        #endif
    }

    private var minHeight: CGFloat {
        #if os(iOS)
        44
        #else
        30
        #endif
    }
}

/// Lays children out left to right and wraps onto the next row, so nothing clips.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let widest = subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        let width = max(proposal.width ?? .infinity, widest)
        let rows = arrange(width, subviews)
        let h = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(0, rows.count - 1))
        let w = rows.map(\.width).max() ?? 0
        return CGSize(width: min(width, w), height: h)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(bounds.width, subviews) {
            var x = bounds.minX
            for i in row.items {
                let s = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (row.height - s.height) / 2), proposal: ProposedViewSize(s))
                x += s.width + spacing
            }
            y += row.height + spacing
        }
    }

    private func arrange(_ width: CGFloat, _ subviews: Subviews) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var rows: [(items: [Int], width: CGFloat, height: CGFloat)] = []
        var cur: [Int] = [], w: CGFloat = 0, h: CGFloat = 0
        for (i, v) in subviews.enumerated() {
            let s = v.sizeThatFits(.unspecified)
            if !cur.isEmpty, w + spacing + s.width > width {
                rows.append((cur, w, h)); cur = []; w = 0; h = 0
            }
            w += (cur.isEmpty ? 0 : spacing) + s.width
            h = max(h, s.height)
            cur.append(i)
        }
        if !cur.isEmpty { rows.append((cur, w, h)) }
        return rows
    }
}

/// Muted, synced video of the original performance in a player layer, with system
/// picture in picture (AVPictureInPictureController) and a labelled button to start it.
/// The video stays muted; the app's audio engine plays.
struct VideoPiP: View {
    let player: AVPlayer
    @State private var pip = PiPModel()

    var body: some View {
        ZStack(alignment: .topTrailing) {
            PlayerLayerView(player: player, pip: pip)
            Button {
                pip.toggle()
            } label: {
                Image(systemName: pip.active ? "pip.exit" : BrasscribeIcon.pictureInPicture.systemName)
                    .padding(8)
                    .background(.ultraThinMaterial, in: Circle())
                    .hitTarget()
            }
            .buttonStyle(.plain)
            .disabled(!pip.possible)
            .accessibilityLabel(pip.active ? Text("Stop picture in picture") : Text("Picture in picture"))
            .accessibilityValue(Text(pip.possible ? "available" : "unavailable"))
            .accessibilityIdentifier("pipButton")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("videoPlayer")
    }
}

@Observable @MainActor
final class PiPModel: NSObject, AVPictureInPictureControllerDelegate {
    var controller: AVPictureInPictureController?
    var possible = false
    var active = false
    private var observation: NSKeyValueObservation?

    func attach(_ layer: AVPlayerLayer) {
        guard controller == nil, AVPictureInPictureController.isPictureInPictureSupported(),
              let c = AVPictureInPictureController(playerLayer: layer) else { return }
        c.delegate = self
        controller = c
        observation = c.observe(\.isPictureInPicturePossible, options: [.initial, .new]) { [weak self] c, _ in
            let p = c.isPictureInPicturePossible
            Task { @MainActor in self?.possible = p }
        }
    }

    func toggle() {
        guard let c = controller else { return }
        if c.isPictureInPictureActive { c.stopPictureInPicture() } else { c.startPictureInPicture() }
    }

    nonisolated func pictureInPictureControllerDidStartPictureInPicture(_ c: AVPictureInPictureController) {
        Task { @MainActor in self.active = true }
    }
    nonisolated func pictureInPictureControllerDidStopPictureInPicture(_ c: AVPictureInPictureController) {
        Task { @MainActor in self.active = false }
    }
}

#if os(iOS)
final class PlayerLayerUIView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

struct PlayerLayerView: UIViewRepresentable {
    let player: AVPlayer
    let pip: PiPModel
    func makeUIView(context: Context) -> PlayerLayerUIView {
        let v = PlayerLayerUIView()
        v.playerLayer.player = player
        v.playerLayer.videoGravity = .resizeAspect
        v.backgroundColor = .black
        pip.attach(v.playerLayer)
        return v
    }
    func updateUIView(_ v: PlayerLayerUIView, context: Context) { v.playerLayer.player = player }
}
#else
final class PlayerLayerNSView: NSView {
    let playerLayer = AVPlayerLayer()
    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = playerLayer
        playerLayer.backgroundColor = NSColor.black.cgColor
        playerLayer.videoGravity = .resizeAspect
    }
    required init?(coder: NSCoder) { fatalError() }
}

struct PlayerLayerView: NSViewRepresentable {
    let player: AVPlayer
    let pip: PiPModel
    func makeNSView(context: Context) -> PlayerLayerNSView {
        let v = PlayerLayerNSView()
        v.playerLayer.player = player
        pip.attach(v.playerLayer)
        return v
    }
    func updateNSView(_ v: PlayerLayerNSView, context: Context) { v.playerLayer.player = player }
}
#endif

/// Sort priorities for controls drawn over the score. On the Mac, SwiftUI's accessibility hit test
/// (VoiceOver's pointer, Switch Control, XCUITest's `isHittable`) returns the first element in
/// accessibility order whose frame holds the point, whatever is drawn on top. The score comes
/// first in the view tree, and its frame (with the scroll view's content, which runs on past the
/// visible part) covers the player band, the stand's controls and the video, so a pointer on Play
/// found the score. Ordering the overlaid controls before the score makes the hit test find them;
/// the header keeps its place at the top of the reading order.
enum StackedAccessibility {
    static let header: Double = 2
    static let overlay: Double = 1
}

extension View {
    /// At least 44 × 44 pt to hit (WCAG 2.5.8 asks for 24; Apple's guideline is 44).
    func hitTarget() -> some View { frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }

    /// A single-key shortcut on iPad (off when the musician turns single-key shortcuts off
    /// in Settings). On macOS the Playback menu carries these keys, so they work wherever
    /// focus is and are not registered twice.
    @ViewBuilder func padShortcut(_ key: KeyEquivalent) -> some View {
        #if os(iOS)
        keyboardShortcut(UserDefaults.standard.object(forKey: "singleKeyShortcuts") as? Bool ?? true ? KeyboardShortcut(key, modifiers: []) : nil)
        #else
        self
        #endif
    }
}

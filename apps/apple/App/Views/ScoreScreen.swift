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
            .task { loadModel() }
            .onDisappear { model?.stopAll() }
    }

    @ViewBuilder private var screenContent: some View {
        Group {
            if let model {
                PracticeView(model: model)
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

    private func loadModel() {
        guard model == nil else { return }
        do {
            let loaded = try PracticeModel(piece: piece)
            if LaunchOptions.screen == "part" { loaded.shownPart = loaded.myPart }
            loaded.start()
            model = loaded
            ScreenshotScenes.stage(loaded)
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

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        VStack(spacing: 0) {
            ScoreToolbar(model: model, wide: wide, showParts: $showParts, showInspector: $showInspector,
                         showTalking: $showTalking, showVideo: $showVideo)
            StatusLine(model: model, toCheck: toCheck, wide: wide) { app.path.append(.review(model.piece)) }
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
                    }
                    if !wide { ZoomButtons(model: model, vertical: true) }
                }
                .padding(Space.s3)
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            PlayerBar(model: model, wide: wide)
        }
        .inspector(isPresented: Binding(get: { wide && showInspector }, set: { showInspector = $0 })) {
            PartsPanel(model: model)
                .inspectorColumnWidth(min: 260, ideal: 320, max: 400)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showExport = true } label: { Label("Share or print", systemImage: BrasscribeIcon.export.systemName).labelStyle(.titleAndIcon) }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
                    .accessibilityIdentifier("shareOrPrint")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(model.piece.title))
        // The score's scroll view takes arrow keys for scrolling, so bar navigation is
        // handled here, on the focused practice screen, before it reaches the scroll view.
        .focusable()
        .focusEffectDisabled()
        .focused($focused)
        .onAppear { focused = true; refreshToCheck() }
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
        }
        .sheet(isPresented: $showTalking) { TalkingScoreView(model: model) }
        .sheet(isPresented: $showExport) { ExportView(model: model) }
        .alert(String(localized: "The sound can't play"), isPresented: Binding(get: { model.loadError != nil }, set: { _ in })) {
            Button("OK") {}
        } message: { Text("The score is still here to read. Try closing and opening it again.") }
    }

    private func refreshToCheck() {
        let items = ReviewList.items(score: model.score, composition: model.composition, uncertainty: model.uncertainty)
        let checked = model.piece.loadChecked()
        toCheck = items.filter { !checked.contains($0.id) }.count
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
    @Environment(\.dynamicTypeSize) private var typeSize
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

    var body: some View {
        Group {
            if typeSize >= .accessibility1 {
                // the largest text sizes: one control per row, nothing squeezed
                VStack(alignment: .leading, spacing: Space.s2) { parts; pitch; view; inspectorToggle }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s3) { controls }
                    VStack(alignment: .leading, spacing: Space.s2) {
                        HStack(spacing: Space.s3) { parts; Spacer(minLength: 0); view; inspectorToggle }
                        pitch
                    }
                }
            }
        }
        .padding(.horizontal, Space.s5).padding(.vertical, Space.s2)
    }

    @ViewBuilder private var inspectorToggle: some View {
        if wide {
            Toggle(isOn: $showInspector) { Label("Parts", systemImage: BrasscribeIcon.parts.systemName) }
                .toggleStyle(.button)
                .accessibilityHint(Text("Shows or hides the list of parts, where you can mute them."))
        }
    }

    @ViewBuilder private var controls: some View {
        parts
        pitch
        if wide { ZoomButtons(model: model, vertical: false) }
        Spacer(minLength: Space.s2)
        view
        inspectorToggle
    }

    private var parts: some View {
        Picker(selection: $model.shownPart) {
            Text("All parts").tag(String?.none)
            ForEach(model.score.parts) { p in Text(p.displayName).tag(String?.some(p.id)) }
        } label: { Label("Parts", systemImage: BrasscribeIcon.parts.systemName) }
        .pickerStyle(.menu)
        .labelsHidden()
        .menuTint()
        .accessibilityIdentifier("partPicker")
        .frame(minHeight: 44)
        .fixedSize()
    }

    private var pitch: some View {
        Segmented(label: String(localized: "Pitch"), selection: $model.pitchMode,
                  options: [(PitchMode.written, writtenLabel),
                            (PitchMode.concert, String(localized: "Concert pitch"))])
        .accessibilityIdentifier("pitchMode")
        .help(Text("Written is what you read on your part. Concert is how it sounds on a piano."))
    }

    private var view: some View {
        Menu {
            Button { showTalking = true } label: { Label("Read aloud", systemImage: BrasscribeIcon.talkingScore.systemName) }
                .keyboardShortcut("t", modifiers: [.command, .shift])
            if model.video != nil {
                Toggle(isOn: $showVideo) { Label("Show video", systemImage: BrasscribeIcon.video.systemName) }
            }
            if !wide {
                Button { showParts = true } label: { Label("Parts and sound", systemImage: BrasscribeIcon.parts.systemName) }
                    .keyboardShortcut("p", modifiers: [.command, .shift])
            }
        } label: {
            Label("View", systemImage: BrasscribeIcon.more.systemName)
        }
        .menuStyle(.button)
        .tint(Color.Brasscribe.text)
        .frame(minHeight: 44)
        .fixedSize()
        .accessibilityIdentifier("viewMenu")
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
struct PlayerBar: View {
    @Bindable var model: PracticeModel
    let wide: Bool
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
            } else {
                VStack(alignment: .leading, spacing: Space.s3) {
                    HStack(spacing: Space.s3) { transport; position; Spacer(minLength: 0) }
                    hear
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: Space.s2)], spacing: Space.s2) { chipsPhone }
                }
                .card(padding: Space.s4)
                .padding(.horizontal, Space.s5)
                .padding(.vertical, Space.s2)
                .background(Color.Brasscribe.bg)
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
                    .frame(width: 56, height: 56)
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
                      options: [(false, String(localized: "Hear the band")), (true, String(localized: "Recording"))])
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
            muteMyPart.fixedSize()
        }
    }

    private var speedSlider: some View {
        HStack(spacing: Space.s2) {
            Text("Speed").font(Font.Brasscribe.label)
            Slider(value: $model.speedPercent, in: 25...150, step: 5) { Text("Speed") }
                .labelsHidden()
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

    @ViewBuilder private var chipsPhone: some View {
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
        .sheet(isPresented: $editRepeat) { RepeatSheet(model: model) }

        Toggle(isOn: $model.countIn) { Label("Count-in", systemImage: BrasscribeIcon.countIn.systemName) }.toggleStyle(.chip).padShortcut("c")
        Toggle(isOn: $model.metronome) { Label("Metronome", systemImage: BrasscribeIcon.metronome.systemName) }.toggleStyle(.chip).padShortcut("m")
        muteMyPart
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
                    Picker(selection: $model.myPart) {
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
                Text(p.displayName).font(mine ? Font.Brasscribe.headline : Font.Brasscribe.body)
                if mine { Text("your part").font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted) }
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

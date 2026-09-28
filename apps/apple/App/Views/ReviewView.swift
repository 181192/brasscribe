import NotationKit
import ScoreKit
import SwiftUI
import TranscriptionKit

/// "Check the notes" (design/system.md, Review list): one uncertain note at a time with its bars,
/// how sure Brasscribe is, what each transcriber heard, Listen / Change note…, then Skip or Keep.
struct ReviewView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    let piece: Piece

    @State private var model: PracticeModel?
    @State private var xml = ""
    @State private var items: [ReviewItem] = []
    @State private var checked: Set<String> = []
    @State private var current: ReviewItem.ID?
    @State private var evidence: NoteEvidence?
    @State private var composition: Composition?
    @State private var changing: ReviewItem?
    @State private var confirmLater = LaunchOptions.screen == "finish-later"
    @State private var loadError: String?
    @State private var filter: Filter = .mine

    /// Triage: your own part first (very unsure first), then the other parts, then all.
    enum Filter: Hashable { case mine, others, all }

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        horizontalSizeClass == .regular
        #endif
    }

    /// Every note still to check, in every part.
    private var allOpen: [ReviewItem] { items.filter { !checked.contains($0.id) } }
    private var myPartID: String? { model?.myPart }
    /// Your part was arranged from the band's harmony: it has no notes of yours to check, and Review
    /// says so instead of showing an empty list.
    private var myPartArranged: Bool { model?.mySource == .arranged || model?.mySource == .empty }
    private var mine: [ReviewItem] { myPartArranged ? [] : allOpen.filter { $0.partID == myPartID } }

    /// The notes still to check under the chosen filter; in your part the very unsure come first.
    private var open: [ReviewItem] {
        switch filter {
        case .mine:
            return mine
                .sorted { ($0.level == .veryUncertain ? 0 : 1, $0.bar, $0.tick) < ($1.level == .veryUncertain ? 0 : 1, $1.bar, $1.tick) }
        case .others: return Self.veryUnsureFirst(allOpen.filter { $0.partID != myPartID })
        case .all: return Self.veryUnsureFirst(allOpen)
        }
    }

    /// Very unsure notes first, then in score order (part, bar, onset).
    static func veryUnsureFirst(_ items: [ReviewItem]) -> [ReviewItem] {
        items.enumerated().sorted { a, b in
            let ka = a.element.level == .veryUncertain ? 0 : 1, kb = b.element.level == .veryUncertain ? 0 : 1
            return ka != kb ? ka < kb : a.offset < b.offset
        }.map(\.element)
    }

    private func count(_ f: Filter) -> Int {
        switch f {
        case .mine: return mine.count
        case .others: return allOpen.filter { $0.partID != myPartID }.count
        case .all: return allOpen.count
        }
    }

    private var item: ReviewItem? { open.first { $0.id == current } ?? open.first }

    var body: some View {
        Group {
            if let loadError {
                ContentUnavailableView("Couldn't open the notes", systemImage: "exclamationmark.triangle", description: Text(loadError))
            } else if model == nil {
                ProgressView()
            } else if allOpen.isEmpty {
                allChecked
            } else if wide {
                HStack(spacing: 0) {
                    noteList.frame(width: 280)
                    Divider()
                    ScrollView { detail.padding(Space.s8).layoutProbe("pageColumn").readingColumn() }
                }
            } else {
                ScrollView { VStack(alignment: .leading, spacing: Space.s5) { detail; stillToCheck }.padding(Space.s5) }
            }
        }
        .pageBackground()
        .navigationTitle(Text("Check the notes"))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            if !allOpen.isEmpty, wide {
                ToolbarItem(placement: .primaryAction) {
                    Button("Finish later (\(open.count) left)") { confirmLater = true }
                        .accessibilityIdentifier("openScore")
                }
            }
        }
        .bottomActions { if !allOpen.isEmpty, item != nil { actionBar } }
        .alert("Finish checking later?", isPresented: $confirmLater) {
            Button("Finish later") { finish() }
            Button("Keep checking", role: .cancel) {}
        } message: {
            Text("\(allOpen.count) notes keep their ? marks. You can check them any time from the score: tap “Check them”.")
        }
        .sheet(item: $changing) { target in
            ChangeNoteSheet(piece: piece, target: target, xml: xml, evidence: evidenceFor(target)) { reload(keeping: target) }
                .appAppearance()
        }
        .task { load() }
        // choosing another note stops the bar that is playing
        .onChange(of: item?.id) { _, _ in model?.stopListening(announce: false) }
        .onDisappear { model?.stopAll() }
    }

    // MARK: list

    private var noteList: some View {
        List(selection: Binding(get: { item?.id }, set: { current = $0 })) {
            Section {
                UncertaintyLegend().font(Font.Brasscribe.callout)
            } header: {
                SectionLabel(items.count == 1 ? String(localized: "1 note to check") : String(localized: "\(items.count) notes to check"))
            }
            ForEach(Dictionary(grouping: items, by: \.partIndex).sorted { $0.key < $1.key }, id: \.key) { _, group in
                Section(group[0].partName) {
                    ForEach(group) { it in
                        HStack(spacing: Space.s3) {
                            if checked.contains(it.id) {
                                Image(systemName: BrasscribeIcon.done.systemName).foregroundStyle(Color.Brasscribe.textMuted).frame(width: 24)
                            } else {
                                UncertainMark(level: it.level).frame(width: 24)
                            }
                            Text("\(barLabel(it)) · \(pitchName(it))")
                                .foregroundStyle(checked.contains(it.id) ? Color.Brasscribe.textMuted : Color.Brasscribe.text)
                        }
                        .frame(minHeight: 44)
                        .tag(it.id)
                        .accessibilityLabel(Text("\(barLabel(it)), \(pitchName(it)), \(levelWords(it))"))
                    }
                }
            }
        }
        #if os(macOS)
        .listStyle(.sidebar)
        #endif
    }

    private var stillToCheck: some View {
        let rest = open.filter { $0.id != item?.id }
        return Group {
            if !rest.isEmpty {
                VStack(alignment: .leading, spacing: Space.s2) {
                    SectionLabel(String(localized: "Still to check"))
                    VStack(spacing: 0) {
                        ForEach(Array(rest.prefix(4).enumerated()), id: \.element.id) { i, it in
                            if i > 0 { Divider().overlay(Color.Brasscribe.border) }
                            Button { current = it.id } label: {
                                HStack(spacing: Space.s3) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(barLabel(it)).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                                        Text("\(it.partName) · \(noteWords(it))").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                                    }
                                    Spacer()
                                    UncertainMark(level: it.level)
                                }
                                .padding(.horizontal, Space.s4).frame(minHeight: 60).contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                        if rest.count > 4 {
                            Divider().overlay(Color.Brasscribe.border)
                            Text("+ \(rest.count - 4) more").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                                .padding(.horizontal, Space.s4).frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                        }
                    }
                    .card(padding: 0)
                }
            }
        }
    }

    // MARK: the note

    @ViewBuilder private var detail: some View {
        if item == nil, filter == .mine, myPartArranged, let model, let id = myPartID, let part = model.score.part(id: id) {
            VStack(alignment: .leading, spacing: wide ? Space.s4 : Space.s3) {
                triage
                ArrangedNotice(part: part.displayName, empty: model.mySource == .empty) { filter = .others } show: {
                    model.stopAll()
                    finishToScore(showing: id)
                }
            }
        } else if let it = item, let model {
            let index = (open.firstIndex { $0.id == it.id } ?? 0) + 1
            VStack(alignment: .leading, spacing: wide ? Space.s4 : Space.s3) {
                triage
                HStack(alignment: .firstTextBaseline) {
                    Text(barLabel(it)).font(wide ? Font.Brasscribe.display(34) : Font.Brasscribe.title2)
                        .accessibilityAddTraits(.isHeader)
                    Spacer()
                    Text("\(index) of \(open.count) · \(it.partName)")
                        .font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                BarSnippet(xml: xml, partID: it.partID, bar: it.bar, lastBar: it.lastBar ?? it.bar, noteTick: it.tick, level: it.level, score: model.score)
                    .card(padding: Space.s2)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Space.s1) {
                    Text(it.noteCount > 1 ? String(localized: "\(it.noteCount) notes from written \(noteWords(it))") : String(localized: "Written \(noteWords(it))"))
                        .font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    Text(levelSentence(it))
                        .font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // Listen and Change note come straight after the note, before anything that scrolls
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s3) { listenButton(it); changeButton(it) }
                    VStack(spacing: Space.s3) { listenButton(it); changeButton(it) }
                }
                if restOfBar(it) > 0 {
                    Button { keepRestOfBar(it) } label: {
                        Text(restOfBar(it) == 1 ? String(localized: "Keep the other note in this bar")
                                                : String(localized: "Keep the other \(restOfBar(it)) notes in this bar"))
                    }
                    .buttonStyle(.plainText)
                    .accessibilityIdentifier("keepRestOfBar")
                }
                // Mac: Skip and Keep follow the note, before the evidence
                if PageActions.followContent { actionButtons.padding(.top, Space.s2).layoutProbe("pageActions") }
                EvidencePanel(note: evidenceFor(it), fifths: fifths(it), part: model.score.parts[it.partIndex])
            }
            .accessibilityElement(children: .contain)
        }
    }

    /// "Check your part first: 12 notes in Solo Cornet, 4 very unsure", and which notes to show.
    private var triage: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            if open.count > 50 {
                // Until the engine marks fewer notes: say so, and point at the ones that matter.
                let v = open.filter { $0.level == .veryUncertain }.count
                // When most are very unsure, "most of these are probably right" would not be true.
                Text(v * 2 > open.count ? String(localized: "Start with the \(v) very unsure ones.")
                     : v > 0 ? String(localized: "Most of these are probably right. Start with the \(v) very unsure ones.")
                     : String(localized: "Most of these are probably right. Listen to a bar, then keep the rest of it."))
                    .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("reviewLead")
            } else if filter == .mine, let id = myPartID, let part = model?.score.part(id: id), count(.mine) > 0 {
                let n = count(.mine), v = open.filter { $0.level == .veryUncertain }.count
                Text(v == 0 ? String(localized: "Your part first: \(n) notes in \(part.displayName).")
                            : String(localized: "Your part first: \(n) notes in \(part.displayName), \(v) very unsure first."))
                    .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
            }
            Segmented(label: String(localized: "Which notes"), selection: $filter,
                      options: wide
                        ? [(Filter.mine, myPartArranged ? String(localized: "Your part (arranged)") : String(localized: "Your part (\(count(.mine)))")),
                           (Filter.others, String(localized: "Other parts (\(count(.others)))")),
                           (Filter.all, String(localized: "All parts (\(count(.all)))"))]
                        : [(Filter.mine, myPartArranged ? String(localized: "Yours (arranged)") : String(localized: "Yours (\(count(.mine)))")),
                           (Filter.others, String(localized: "Others (\(count(.others)))")),
                           (Filter.all, String(localized: "All (\(count(.all)))"))])
            .accessibilityIdentifier("reviewFilter")
        }
    }

    private func bars(_ it: ReviewItem) -> ClosedRange<Int> { it.bar...max(it.bar, it.lastBar ?? it.bar) }

    private func toggleListen(_ it: ReviewItem) { model?.toggleListen(bars: bars(it), original: true) }

    /// "Listen to this bar", and "Stop" in the same place and size while it plays.
    private func listenButton(_ it: ReviewItem) -> some View {
        let playing = model?.listening == bars(it)
        return Button { toggleListen(it) } label: {
            ListenStopLabel(playing: playing).frame(maxWidth: .infinity)
        }
        .buttonStyle(SecondaryButtonStyle(minHeight: 48))
        .keyboardShortcut(.space, modifiers: [])
        .onKeyPress(.return) { toggleListen(it); return .handled }
        .accessibilityLabel(playing ? Text("Stop") : Text("Listen to this bar"))
        .accessibilityIdentifier("listenBar")
    }

    private func changeButton(_ it: ReviewItem) -> some View {
        Button { model?.stopListening(announce: false); changing = it } label: {
            Label("Change note…", systemImage: "pencil").frame(maxWidth: .infinity)
        }
        .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 48))
        .accessibilityIdentifier("changeNote")
    }

    private var actionBar: some View {
        VStack(spacing: Space.s1) {
            if !wide {
                Button("Finish later (\(open.count) left)") { confirmLater = true }
                    .buttonStyle(.plainText)
                    .accessibilityIdentifier("openScore")
            }
            actionButtons
        }
        .padding(.horizontal, wide ? Space.s8 : Space.s5)
        .padding(.vertical, wide ? Space.s3 : Space.s2)
        .background(Color.Brasscribe.bg)
    }

    private var actionButtons: some View {
        HStack(spacing: Space.s3) {
            if wide {
                // the keys, where there's room beside the buttons
                ViewThatFits(in: .horizontal) {
                    Text(model?.listening != nil ? "Space stops · K keeps" : "Space listens · K keeps")
                        .font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize()
                    Color.clear.frame(width: 0, height: 0)
                }
                Spacer(minLength: 0)
            }
            Button { skip() } label: { Label("Skip", systemImage: BrasscribeIcon.skip.systemName) }
                .buttonStyle(SecondaryButtonStyle(fullWidth: !wide, minHeight: 48))
            Button { keep() } label: { Label("Keep, go to next", systemImage: BrasscribeIcon.markChecked.systemName) }
                .buttonStyle(PrimaryButtonStyle(fullWidth: !wide))
                .keyboardShortcut("k", modifiers: [])
                .accessibilityIdentifier("keepNext")
        }
    }

    private var allChecked: some View {
        VStack(spacing: Space.s4) {
            ContentUnavailableView("All notes checked", systemImage: BrasscribeIcon.done.systemName,
                                   description: Text("The ? marks are gone. Your score is ready to practise."))
            Button { finish() } label: { Text("Continue") }.buttonStyle(.primary)
                .accessibilityIdentifier("openScore")
        }
        .padding(Space.s8)
    }

    // MARK: actions

    private func keep() {
        guard let it = item else { return }
        keepInComposition([it])
        checked.insert(it.id)
        piece.saveChecked(checked, remaining: allOpen.count)
        app.refresh()
        advance(from: it)
    }

    /// Kept notes get confidence 1 in the Composition, so they stay kept when the score is arranged again.
    private func keepInComposition(_ kept: [ReviewItem]) {
        guard var comp = composition else { return }
        for k in kept { if let lead = note(k) { CompositionEdit.keep(&comp, item: k, lead: lead) } }
        guard comp != composition else { return }
        try? piece.saveComposition(comp)
        composition = comp
    }

    private func skip() { if let it = item { advance(from: it) } }

    /// Open notes in the same part and bar as this one (not counting it).
    private func restOfBar(_ it: ReviewItem) -> Int {
        allOpen.filter { $0.partID == it.partID && $0.bar == it.bar && $0.id != it.id }.count
    }

    /// "Keep the rest of this bar": this note and every other open note in the bar.
    private func keepRestOfBar(_ it: ReviewItem) {
        let bar = allOpen.filter { $0.partID == it.partID && $0.bar == it.bar }
        keepInComposition(bar)
        for o in bar { checked.insert(o.id) }
        piece.saveChecked(checked, remaining: allOpen.count)
        app.refresh()
        advance(from: it)
        AccessibilityNotifier.announce(String(localized: "Kept the notes in \(barLabel(it))."))
    }

    private func advance(from it: ReviewItem) {
        model?.stopListening(announce: false)
        if open.filter({ $0.id != it.id }).isEmpty, !allOpen.filter({ $0.id != it.id }).isEmpty { filter = .all }
        let list = open
        let i = list.firstIndex { $0.id == it.id } ?? 0
        let after = i + 1 <= list.count ? Array(list[min(i + 1, list.count)...] + list[..<min(i, list.count)]) : list
        current = after.first { !checked.contains($0.id) && $0.id != it.id }?.id
    }

    /// "Show my part": the score, on your part.
    private func finishToScore(showing id: String) {
        piece.saveChecked(checked, remaining: allOpen.count)
        app.refresh()
        app.showPartOnOpen = id
        if app.path.count >= 2, case .score = app.path[app.path.count - 2] {
            app.path.removeLast()
        } else {
            app.open(piece)
        }
    }

    /// Back to the score if Review was opened from it, otherwise on to "How should the score be?".
    private func finish() {
        model?.stopAll()
        piece.saveChecked(checked, remaining: allOpen.count)
        app.refresh()
        if app.path.count >= 2, case .score = app.path[app.path.count - 2] {
            app.path.removeLast()
        } else if let i = app.path.lastIndex(of: .review(piece)) {
            app.path[i] = .output(piece)
        } else {
            app.path.append(.output(piece))
        }
    }

    // MARK: data

    private func load() {
        guard model == nil else { return }
        do {
            let m = try PracticeModel(piece: piece)
            m.start()
            model = m
            xml = try piece.musicXML()
            composition = piece.loadComposition()
            evidence = piece.loadEvidence()
            checked = piece.loadChecked()
            items = ReviewList.items(score: m.score, composition: m.composition, uncertainty: m.uncertainty)
            // an arranged part keeps "Yours" chosen, so its notice shows (and is said) once
            if count(.mine) == 0, !myPartArranged { filter = .all }
            if myPartArranged, let id = m.myPart, let part = m.score.part(id: id) {
                let body = ArrangedNotice.body(part.displayName, empty: m.mySource == .empty)
                AccessibilityNotifier.announce(m.mySource == .empty ? String(localized: "Your part is empty. \(body)")
                                               : String(localized: "Your part is arranged. \(body)"), polite: true)
            }
            piece.saveChecked(checked, remaining: allOpen.count)
            app.refresh()
            // screenshots: the button as it looks while the bar plays
            if LaunchOptions.screen == "review-listening", let it = item { m.holdListening(bars: bars(it)) }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func reload(keeping target: ReviewItem) {
        model?.stopAll()
        model = nil
        load()
        current = items.first { $0.partID == target.partID && $0.tick == target.tick }?.id ?? open.first?.id
    }

    // MARK: words

    private func note(_ it: ReviewItem) -> ScoreNote? {
        guard let part = model?.score.parts[safe: it.partIndex], part.notes.indices.contains(it.noteIndex) else { return nil }
        return part.notes[it.noteIndex]
    }

    private func fifths(_ it: ReviewItem) -> Int {
        guard let part = model?.score.parts[safe: it.partIndex] else { return 0 }
        return part.measureFifths.indices.contains(it.bar) ? part.measureFifths[it.bar] : part.writtenFifths
    }

    private func evidenceFor(_ it: ReviewItem) -> NoteEvidence.Note? {
        guard let n = note(it), let p = n.midiPitch else { return nil }
        return evidence?.note(atScoreTick: n.startTick, concertPitch: p, ticksPerBeat: composition?.ticksPerBeat ?? 24)
    }

    private func barLabel(_ it: ReviewItem) -> String {
        if let last = it.lastBar, last > it.bar { return String(localized: "Bars \(it.bar + 1)–\(last + 1)") }
        return model?.barLabel(it.bar) ?? String(localized: "Bar \(it.bar + 1)")
    }

    private func pitchName(_ it: ReviewItem) -> String {
        guard let n = note(it), case .pitched(let p) = n.kind else { return "?" }
        return ReviewWords.name(p)
    }

    private func noteWords(_ it: ReviewItem) -> String {
        guard let n = note(it), let talk = model?.talking else { return pitchName(it) }
        return "\(pitchName(it)), \(ReviewWords.value(type: n.type, dots: n.dots) ?? talk.durationName(type: n.type, dots: n.dots, ticks: n.durTicks))"
    }

    private func levelWords(_ it: ReviewItem) -> String {
        it.level == .veryUncertain ? String(localized: "Very uncertain") : String(localized: "Uncertain")
    }

    /// "Very uncertain: it could also be an A." — the alternative comes from the transcribers that disagree.
    private func levelSentence(_ it: ReviewItem) -> String {
        guard let shift = evidenceFor(it)?.alternativeShift, let n = note(it), case .pitched(let p) = n.kind else {
            return "\(levelWords(it)). " + String(localized: "Listen to the original and the score side by side.")
        }
        let alt = ReviewWords.name(SpelledPitch.spelling(midi: p.midi + shift, fifths: fifths(it)))
        return "\(levelWords(it)): " + String(localized: "it could also be \(ReviewWords.withArticle(alt)).")
    }
}

/// How sure Brasscribe is, and what each transcriber heard at this note.
struct EvidencePanel: View {
    let note: NoteEvidence.Note?
    let fifths: Int
    let part: Part

    var body: some View {
        if let note {
            VStack(alignment: .leading, spacing: Space.s3) {
                HStack(alignment: .firstTextBaseline) {
                    Text("How sure Brasscribe is").font(Font.Brasscribe.headline)
                    Spacer()
                    Text(percentText(note.confidence * 100)).font(Font.Brasscribe.headline.monospacedDigit())
                }
                ProgressView(value: note.confidence)
                    .tint(Color.Brasscribe.text)
                    .accessibilityLabel(Text("How sure Brasscribe is"))
                    .accessibilityValue(Text(percentText(note.confidence * 100)))
                if !note.models.isEmpty {
                    Divider().overlay(Color.Brasscribe.border)
                    Text("What each transcriber heard").font(Font.Brasscribe.headline)
                    ForEach(note.models, id: \.model) { m in
                        HStack(spacing: Space.s3) {
                            Image(systemName: m.agrees ? BrasscribeIcon.done.systemName : BrasscribeIcon.info.systemName)
                                .foregroundStyle(Color.Brasscribe.textMuted)
                                .frame(width: 20)
                                .accessibilityHidden(true)
                            Text(m.name).font(Font.Brasscribe.body)
                            Spacer()
                            Text(heardText(m)).font(Font.Brasscribe.body.weight(m.agrees ? .regular : .semibold))
                        }
                        .frame(minHeight: 32)
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            .card()
        }
    }

    private func heardText(_ m: NoteEvidence.Heard) -> String {
        guard let pitch = m.pitch else { return String(localized: "No note") }
        let written = SpelledPitch.spelling(midi: pitch - part.transposeSemitones, fifths: fifths)
        return m.agrees ? String(localized: "Same, \(ReviewWords.name(written))") : ReviewWords.name(written)
    }
}

/// Two bars of the note's part, drawn like the score: ink notes, the "?" mark and an ink ring on the note.
struct BarSnippet: View {
    let xml: String
    let partID: String
    let bar: Int
    /// The last bar of a review group; one bar of context follows a single-bar item.
    var lastBar: Int
    let noteTick: Int
    let level: UncertaintyLevel
    let score: Score
    @State private var page: ScoreRenderer.Page?
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        GeometryReader { geo in
            Group {
                if let page {
                    Canvas { ctx, size in
                        let doc = page.svg
                        let s = min(1, size.width / max(1, doc.size.width))
                        ctx.scaleBy(x: s, y: s)
                        let env = ctx.environment
                        let ink = Color.Brasscribe.ink.resolve(in: env).cgColor
                        let target = targetNoteID(page)
                        let f = target.flatMap { doc.frames[$0] }
                        let lines = page.staffLines.values.first ?? f ?? .zero
                        let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Brasscribe.uncertain
                        // selected: a tint column behind the note and a caret under the staff (a box would read as the boxed "?")
                        var column = CGRect.zero
                        if let f {
                            column = CGRect(x: f.minX - 4, y: min(lines.minY, f.minY) - 4, width: f.width + 8,
                                            height: max(lines.maxY, f.maxY) - min(lines.minY, f.minY) + 8)
                            ctx.fill(Path(roundedRect: column, cornerRadius: 3), with: .color(.Brasscribe.selectionTint))
                            ctx.stroke(Path(roundedRect: column, cornerRadius: 3), with: .color(.Brasscribe.selectionEdge),
                                       lineWidth: BrasscribeDesign.Score.selectionEdgeWidth)
                        }
                        var highlight: [String: CGColor] = [:]
                        if let target { highlight[target] = color.resolve(in: env).cgColor }
                        ctx.withCGContext { cg in doc.draw(in: cg, ink: ink, highlight: highlight, keepDocumentColors: false) }
                        if let f {
                            var caret = Path()
                            let y = column.maxY + 3
                            caret.move(to: CGPoint(x: f.midX, y: y)); caret.addLine(to: CGPoint(x: f.midX - 5, y: y + 7))
                            caret.addLine(to: CGPoint(x: f.midX + 5, y: y + 7)); caret.closeSubpath()
                            ctx.fill(caret, with: .color(.Brasscribe.text))
                            // the "?" at 1.6 staff spaces, above the staff, as in the score
                            let space = max(3, lines.height / 4)
                            let size = space * BrasscribeDesign.Score.markSizeStaffSpaces
                            let centre = CGPoint(x: f.midX, y: min(lines.minY, f.minY) - space * 0.5 - size * 0.6)
                            ctx.draw(Text(verbatim: "?").font(.system(size: size, weight: .bold)).foregroundStyle(color), at: centre)
                            if level == .veryUncertain {
                                ctx.stroke(Path(roundedRect: CGRect(x: centre.x - size * 0.45, y: centre.y - size * 0.62, width: size * 0.9, height: size * 1.24),
                                                cornerRadius: 1.5), with: .color(color), lineWidth: max(1.5, size / 11))
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .task(id: "\(partID)-\(bar)-\(lastBar)-\(noteTick)-\(Int(geo.size.width))") {
                let first = max(1, bar + 1), last = min(score.measures.count, max(lastBar + 1, bar + 2))
                let xml = PartNames.localized(self.xml), partID = self.partID, width = geo.size.width
                page = await Task.detached { ScoreRenderer.snippet(musicXML: xml, partID: partID, bars: first...last, width: width) }.value
            }
        }
        .frame(height: 108)
    }

    /// The Verovio note at the reviewed onset: same order within the first bar as the parsed notes.
    private func targetNoteID(_ page: ScoreRenderer.Page) -> String? {
        guard let part = score.part(id: partID) else { return nil }
        let inBar = part.notes.filter { $0.measureIndex == bar && !$0.isRest }
        guard let i = inBar.firstIndex(where: { $0.startTick == noteTick }) else { return nil }
        let ids = page.notesByStaff.values.first ?? []
        return ids.indices.contains(i) ? ids[i] : nil
    }
}

enum ReviewWords {
    static var norwegian: Bool { ["nb", "no", "nn"].contains(Locale.current.language.languageCode?.identifier ?? "") }

    /// "B♭" in English; the German-derived Norwegian names in Norwegian (B♭ = B, B = H, E♭ = Ess, F♯ = Fiss).
    static func name(_ p: SpelledPitch) -> String {
        if norwegian {
            let letter = p.step == "B" ? "H" : p.step
            switch (p.step, p.alter) {
            case ("B", -1): return "B"
            case ("E", -1): return "Ess"
            case ("A", -1): return "Ass"
            case (_, -1): return letter + "ess"
            case (_, 1): return letter + "iss"
            case (_, 2): return letter + " dobbeltkryss"
            case (_, -2): return letter + " dobbelt-b"
            default: return letter
            }
        }
        let accidental = p.alter == 1 ? "♯" : p.alter == -1 ? "♭" : p.alter == 2 ? "𝄪" : p.alter == -2 ? "𝄫" : ""
        return "\(p.step)\(accidental)"
    }

    /// Note values as a brass band says them: crotchet, quaver (en-GB); the talking score's
    /// names elsewhere (nil).
    static func value(type: String?, dots: Int) -> String? {
        guard !norwegian, let type else { return nil }
        let gb = ["breve": String(localized: "breve"), "whole": String(localized: "semibreve"), "half": String(localized: "minim"),
                  "quarter": String(localized: "crotchet"), "eighth": String(localized: "quaver"), "16th": String(localized: "semiquaver"),
                  "32nd": String(localized: "demisemiquaver")]
        guard let base = gb[type] else { return nil }
        return dots == 0 ? base : dots == 1 ? String(localized: "dotted \(base)") : String(localized: "double-dotted \(base)")
    }

    /// "an A", "a B" in English; Norwegian names the note bare.
    static func withArticle(_ name: String) -> String {
        norwegian ? name : (["A", "E", "F"].contains(String(name.prefix(1))) ? "an " : "a ") + name
    }
}

private extension Collection {
    subscript(safe index: Index) -> Element? { indices.contains(index) ? self[index] : nil }
}

/// "Your part is arranged": in place of an empty Yours list. Nobody played the part on its own, so
/// there is nothing of the player's to check.
struct ArrangedNotice: View {
    let part: String
    var empty = false
    let others: () -> Void
    let show: () -> Void

    static func title(empty: Bool) -> String {
        empty ? String(localized: "Your part is empty") : String(localized: "Your part is arranged")
    }

    static func body(_ part: String, empty: Bool = false) -> String {
        empty ? String(localized: "Nothing in the recording gave the \(part) part any notes, so there is nothing of yours to check.")
            : String(localized: "Nobody played the \(part) part on its own in the recording, so Brasscribe wrote it from the chords it heard. There are no notes of yours to check.")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s4) {
            DisplayTitle(text: Self.title(empty: empty), size: 34)
            SourceLabel(kind: empty ? .empty : .arranged)
            Text(Self.body(part, empty: empty))
                .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                .fixedSize(horizontal: false, vertical: true)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Space.s3) { othersButton; showButton }
                VStack(alignment: .leading, spacing: Space.s3) { othersButton; showButton }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("arrangedNotice")
    }

    private var othersButton: some View {
        Button(action: others) { Text("Check the other parts") }.buttonStyle(.primary)
            .accessibilityIdentifier("checkOthers")
    }

    private var showButton: some View {
        Button(action: show) { Text("Show my part") }.buttonStyle(.tonal)
            .accessibilityIdentifier("showMyPart")
    }
}

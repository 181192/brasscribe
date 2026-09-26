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
    @State private var confirmLater = false
    @State private var loadError: String?

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        horizontalSizeClass == .regular
        #endif
    }

    private var open: [ReviewItem] { items.filter { !checked.contains($0.id) } }
    private var item: ReviewItem? { items.first { $0.id == current } ?? open.first }

    var body: some View {
        Group {
            if let loadError {
                ContentUnavailableView("Couldn't open the notes", systemImage: "exclamationmark.triangle", description: Text(loadError))
            } else if model == nil {
                ProgressView()
            } else if open.isEmpty {
                allChecked
            } else if wide {
                HStack(spacing: 0) {
                    noteList.frame(width: 280)
                    Divider()
                    ScrollView { detail.padding(Space.s8).readingColumn() }
                }
            } else {
                ScrollView { VStack(alignment: .leading, spacing: Space.s5) { detail; stillToCheck }.padding(Space.s5) }
            }
        }
        .pageBackground()
        .navigationTitle(Text("\(piece.title) · Check the notes"))
        .toolbar {
            if !open.isEmpty {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Finish later (\(open.count) left)") { confirmLater = true }
                }
            }
        }
        .safeAreaInset(edge: .bottom) { if !open.isEmpty, item != nil { actionBar } }
        .alert("Finish checking later?", isPresented: $confirmLater) {
            Button("Finish later") { app.path = [.score(piece)] }
            Button("Keep checking", role: .cancel) {}
        } message: {
            Text("\(open.count) notes keep their ? marks. You can check them any time from the score.")
        }
        .sheet(item: $changing) { target in
            ChangeNoteSheet(piece: piece, target: target, xml: xml, evidence: evidenceFor(target)) { reload(keeping: target) }
        }
        .task { load() }
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
        if let it = item, let model {
            let index = (items.firstIndex { $0.id == it.id } ?? 0) + 1
            VStack(alignment: .leading, spacing: Space.s4) {
                SectionLabel(String(localized: "\(index) of \(items.count) · \(it.partName) · \(open.count) left"))
                DisplayTitle(text: barLabel(it))
                BarSnippet(xml: xml, partID: it.partID, bar: it.bar, noteTick: it.tick, level: it.level, score: model.score)
                    .card(padding: Space.s3)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Space.s1) {
                    Text("Written \(noteWords(it))")
                        .font(Font.Brasscribe.title2).foregroundStyle(Color.Brasscribe.text)
                    Text(levelSentence(it))
                        .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                EvidencePanel(note: evidenceFor(it), fifths: fifths(it), part: model.score.parts[it.partIndex])
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Space.s3) { listenButton(it); changeButton(it) }
                    VStack(spacing: Space.s3) { listenButton(it); changeButton(it) }
                }
            }
            .accessibilityElement(children: .contain)
        }
    }

    private func listenButton(_ it: ReviewItem) -> some View {
        Button { model?.listen(toBar: it.bar, original: true) } label: {
            Label("Listen to this bar", systemImage: BrasscribeIcon.listenBar.systemName).frame(maxWidth: .infinity)
        }
        .buttonStyle(SecondaryButtonStyle(minHeight: 48))
        .keyboardShortcut(.space, modifiers: [])
    }

    private func changeButton(_ it: ReviewItem) -> some View {
        Button { model?.stopAll(); changing = it } label: {
            Label("Change note…", systemImage: "pencil").frame(maxWidth: .infinity)
        }
        .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 48))
        .accessibilityIdentifier("changeNote")
    }

    private var actionBar: some View {
        HStack(spacing: Space.s3) {
            if wide {
                Text("Space listens · K keeps").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                Spacer()
            }
            Button { skip() } label: { Label("Skip", systemImage: BrasscribeIcon.skip.systemName) }
                .buttonStyle(SecondaryButtonStyle(fullWidth: !wide, minHeight: 48))
            Button { keep() } label: { Label("Keep, go to next", systemImage: BrasscribeIcon.markChecked.systemName) }
                .buttonStyle(PrimaryButtonStyle(fullWidth: !wide))
                .keyboardShortcut("k", modifiers: [])
                .accessibilityIdentifier("keepNext")
        }
        .padding(.horizontal, wide ? Space.s8 : Space.s5)
        .padding(.vertical, Space.s3)
        .background(Color.Brasscribe.bg.opacity(0.97))
    }

    private var allChecked: some View {
        VStack(spacing: Space.s4) {
            ContentUnavailableView("All notes checked", systemImage: BrasscribeIcon.done.systemName,
                                   description: Text("The ? marks are gone. Your score is ready to practise."))
            Button { app.path = [.score(piece)] } label: { Text("Show the score") }.buttonStyle(.primary)
        }
        .padding(Space.s8)
    }

    // MARK: actions

    private func keep() {
        guard let it = item else { return }
        checked.insert(it.id)
        piece.saveChecked(checked, remaining: open.count)
        app.refresh()
        advance(from: it)
    }

    private func skip() { if let it = item { advance(from: it) } }

    private func advance(from it: ReviewItem) {
        model?.stopAll()
        model?.setLoop(false)
        let i = items.firstIndex { $0.id == it.id } ?? 0
        current = (items[(i + 1)...] + items[..<i]).first { !checked.contains($0.id) && $0.id != it.id }?.id
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
            items = ReviewList.items(score: m.score, uncertainty: m.uncertainty)
            piece.saveChecked(checked, remaining: open.count)
            app.refresh()
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

    private func barLabel(_ it: ReviewItem) -> String { model?.barLabel(it.bar) ?? "Bar \(it.bar + 1)" }

    private func pitchName(_ it: ReviewItem) -> String {
        guard let n = note(it), case .pitched(let p) = n.kind else { return "?" }
        return ReviewWords.name(p)
    }

    private func noteWords(_ it: ReviewItem) -> String {
        guard let n = note(it), let talk = model?.talking else { return pitchName(it) }
        return "\(pitchName(it)), \(talk.durationName(type: n.type, dots: n.dots, ticks: n.durTicks))"
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
                        let ink = CGColor(gray: scheme == .dark ? 0.95 : 0.07, alpha: 1)
                        ctx.withCGContext { cg in doc.draw(in: cg, ink: ink, keepDocumentColors: false) }
                        if let id = targetNoteID(page), let f = doc.frames[id] {
                            let color: Color = level == .veryUncertain ? .Brasscribe.veryUncertain : .Brasscribe.uncertain
                            ctx.stroke(Path(roundedRect: f.insetBy(dx: -4, dy: -4), cornerRadius: 4), with: .color(.Brasscribe.text), lineWidth: 2)
                            let size = max(12, f.height * 1.4)
                            let centre = CGPoint(x: f.midX, y: f.minY - size)
                            ctx.draw(Text(verbatim: "?").font(.system(size: size, weight: .bold)).foregroundStyle(color), at: centre)
                            if level == .veryUncertain {
                                ctx.stroke(Path(roundedRect: CGRect(x: centre.x - size * 0.45, y: centre.y - size * 0.62, width: size * 0.9, height: size * 1.24),
                                                cornerRadius: 1.5), with: .color(color), lineWidth: 1.5)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .task(id: "\(partID)-\(bar)-\(Int(geo.size.width))") {
                let first = max(1, bar + 1), last = min(score.measures.count, bar + 2)
                let xml = self.xml, partID = self.partID, width = geo.size.width
                page = await Task.detached { ScoreRenderer.snippet(musicXML: xml, partID: partID, bars: first...last, width: width) }.value
            }
        }
        .frame(height: 170)
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

    /// "an A", "a B" in English; Norwegian names the note bare.
    static func withArticle(_ name: String) -> String {
        norwegian ? name : (["A", "E", "F"].contains(String(name.prefix(1))) ? "an " : "a ") + name
    }
}

private extension Collection {
    subscript(safe index: Index) -> Element? { indices.contains(index) ? self[index] : nil }
}

import ScoreKit
import TranscriptionKit
import SwiftUI

/// Check the notes: one uncertain note at a time, with Listen, Skip and the primary
/// "Keep, go to next". Leaving early is "Finish later (N left)" and confirms first; the
/// score view's "Check them" line brings the musician back.
struct ReviewView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    let piece: Piece
    @State private var model: PracticeModel?
    @State private var items: [ReviewItem] = []
    @State private var checked: Set<String> = []
    @State private var skipped: Set<String> = []
    @State private var currentID: String?
    @State private var confirmLeave = false
    @State private var showAll = false
    @AccessibilityFocusState private var headingFocused: Bool

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    private var remaining: [ReviewItem] { items.filter { !checked.contains($0.id) } }
    private var current: ReviewItem? {
        if let currentID, let i = items.first(where: { $0.id == currentID }), !checked.contains(i.id) { return i }
        return remaining.first { !skipped.contains($0.id) } ?? remaining.first
    }

    var body: some View {
        Group {
            if let model {
                if wide {
                    HStack(spacing: 0) {
                        sidebar(model)
                            .frame(width: BrasscribeDesign.Size.sidebarWidth)
                        Divider()
                        ScrollView { detail(model).padding(Space.s8).readingColumn() }
                    }
                } else {
                    ScrollView { detail(model).padding(.horizontal, Space.s5).padding(.vertical, Space.s4) }
                        .safeAreaInset(edge: .bottom) { phoneActions(model) }
                }
            } else {
                ProgressView()
            }
        }
        .pageBackground()
        .navigationTitle(Text(piece.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    if remaining.isEmpty { finish() } else { confirmLeave = true }
                } label: {
                    Text(remaining.isEmpty ? String(localized: "Continue") : String(localized: "Finish later (\(remaining.count) left)"))
                }
                .accessibilityIdentifier("openScore")
            }
        }
        .alert(String(localized: "Finish checking later?"), isPresented: $confirmLeave) {
            Button(String(localized: "Finish later")) { finish() }
            Button(String(localized: "Keep checking"), role: .cancel) {}
        } message: {
            Text(remaining.count == 1
                 ? String(localized: "1 note keeps its ? mark. You can check it any time from the score: tap “Check them”.")
                 : String(localized: "\(remaining.count) notes keep their ? marks. You can check them any time from the score: tap “Check them”."))
        }
        .task {
            guard model == nil, let m = try? PracticeModel(piece: piece) else { return }
            m.start()
            model = m
            items = ReviewList.items(score: m.score, uncertainty: m.uncertainty)
            checked = piece.loadChecked()
            headingFocused = true
        }
        .onDisappear { model?.stopAll() }
        .onKeyPress(.space) { if let c = current, let model { listen(c, model) }; return .handled }
        .onKeyPress("k") { if let c = current { keep(c) }; return .handled }
        .onKeyPress(.downArrow) { move(1); return .handled }
        .onKeyPress(.upArrow) { move(-1); return .handled }
    }

    // MARK: detail

    @ViewBuilder private func detail(_ model: PracticeModel) -> some View {
        VStack(alignment: .leading, spacing: Space.s5) {
            VStack(alignment: .leading, spacing: Space.s2) {
                DisplayTitle(text: remaining.isEmpty ? String(localized: "Every note is checked")
                             : remaining.count == 1 ? String(localized: "Check 1 note") : String(localized: "Check \(remaining.count) notes"))
                    .accessibilityFocused($headingFocused)
                Text(remaining.isEmpty ? String(localized: "Next, choose how the score should be.")
                     : String(localized: "Brasscribe wasn't sure about these. Listen, then keep each one or skip it."))
                    .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                if !items.isEmpty && !wide { UncertaintyLegend().font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted) }
            }

            if let c = current {
                noteCard(c, model)
                if wide { wideActions(c, model) }
                if !wide { stillToCheck(model) }
            } else if items.isEmpty {
                NoticeBox(systemImage: BrasscribeIcon.done.systemName, text: String(localized: "Brasscribe was sure about every note."))
            }

            if let free = model.freeTimeBars.first {
                HelperLine(systemImage: BrasscribeIcon.info.systemName, text: freeTimeText(free))
            }
            if wide {
                Text("Keyboard: Space listens, K keeps, the arrow keys move between notes.")
                    .font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
            }
        }
    }

    private func noteCard(_ c: ReviewItem, _ model: PracticeModel) -> some View {
        VStack(alignment: .leading, spacing: Space.s4) {
            HStack(alignment: .firstTextBaseline) {
                Text("\(model.barLabel(c.bar)) · \(c.partName)").font(Font.Brasscribe.title2)
                Spacer()
                if let i = remaining.firstIndex(of: c) {
                    Text("\(i + 1) of \(remaining.count)").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted).monospacedDigit()
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: Space.s3) {
                UncertainMark(level: c.level)
                Text("\(Text(noteText(c, model)).foregroundStyle(Color.Brasscribe.text)) \(Text(c.level == .veryUncertain ? String(localized: "Very uncertain.") : String(localized: "Uncertain.")).foregroundStyle(Color.Brasscribe.textMuted))")
                    .font(Font.Brasscribe.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !wide {
                ViewThatFits {
                    HStack(spacing: Space.s3) { listenButtons(c, model) }
                    VStack(spacing: Space.s3) { listenButtons(c, model) }
                }
            }
        }
        .card(padding: Space.s5)
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private func listenButtons(_ c: ReviewItem, _ model: PracticeModel) -> some View {
        Button { listen(c, model) } label: { Label("Listen to bar", systemImage: BrasscribeIcon.listenBar.systemName) }
            .buttonStyle(SecondaryButtonStyle(fullWidth: !wide, minHeight: 48))
            .accessibilityHint(model.hasOriginal ? Text("Plays this bar from the recording, again and again.") : Text("Plays this bar from the score, again and again."))
        if model.hasOriginal {
            Button { model.listen(toBar: c.bar, original: false) } label: { Label("Hear the score", systemImage: BrasscribeIcon.score.systemName) }
                .buttonStyle(SecondaryButtonStyle(outline: true, fullWidth: !wide, minHeight: 48))
        }
    }

    private func wideActions(_ c: ReviewItem, _ model: PracticeModel) -> some View {
        VStack(alignment: .leading, spacing: Space.s4) {
            HStack(spacing: Space.s3) { listenButtons(c, model) }
            Divider().overlay(Color.Brasscribe.border)
            HStack(spacing: Space.s3) {
                Spacer()
                Button { confirmLeave = true } label: { Text("Finish later (\(remaining.count) left)") }.buttonStyle(.plainText)
                Button { skip(c) } label: { Label("Skip", systemImage: BrasscribeIcon.skip.systemName) }
                    .buttonStyle(SecondaryButtonStyle(minHeight: 48))
                Button { keep(c) } label: { Label("Keep, go to next", systemImage: BrasscribeIcon.markChecked.systemName) }
                    .buttonStyle(.primary)
                    .accessibilityIdentifier("keepNote")
            }
        }
    }

    private func phoneActions(_ model: PracticeModel) -> some View {
        HStack(spacing: Space.s3) {
            if let c = current {
                Button { skip(c) } label: { Text("Skip") }
                    .buttonStyle(SecondaryButtonStyle(minHeight: 52))
                Button { keep(c) } label: { Label("Keep, go to next", systemImage: BrasscribeIcon.markChecked.systemName) }
                    .buttonStyle(.primaryWide)
                    .accessibilityIdentifier("keepNote")
            } else {
                Button { finish() } label: { Text("Continue") }.buttonStyle(.primaryWide)
            }
        }
        .padding(.horizontal, Space.s5)
        .padding(.vertical, Space.s3)
        .background(Color.Brasscribe.bg.opacity(0.95))
    }

    @ViewBuilder private func stillToCheck(_ model: PracticeModel) -> some View {
        let rest = remaining.filter { $0.id != current?.id }
        if !rest.isEmpty {
            VStack(alignment: .leading, spacing: Space.s3) {
                SectionLabel(String(localized: "Still to check"))
                VStack(spacing: 0) {
                    let shown = showAll ? rest : Array(rest.prefix(3))
                    ForEach(Array(shown.enumerated()), id: \.element.id) { i, item in
                        if i > 0 { Divider().overlay(Color.Brasscribe.border) }
                        Button { currentID = item.id } label: { row(item, model) }.buttonStyle(.plain)
                    }
                    if !showAll, rest.count > 3 {
                        Divider().overlay(Color.Brasscribe.border)
                        Button { showAll = true } label: {
                            HStack {
                                Text("+ \(rest.count - 3) more").font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                                Spacer()
                                Image(systemName: BrasscribeIcon.open.systemName).foregroundStyle(Color.Brasscribe.textMuted)
                            }
                            .padding(.horizontal, Space.s4).frame(minHeight: 56).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .card(padding: 0)
            }
        }
    }

    private func row(_ item: ReviewItem, _ model: PracticeModel) -> some View {
        HStack(spacing: Space.s3) {
            Text(model.barLabel(item.bar)).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
            Text("\(item.partName) · \(noteText(item, model))").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                .lineLimit(2)
            Spacer(minLength: Space.s2)
            UncertainMark(level: item.level)
        }
        .padding(.horizontal, Space.s4)
        .frame(minHeight: 56)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityValue(item.level == .veryUncertain ? Text("Very uncertain") : Text("Uncertain"))
    }

    // MARK: desktop sidebar

    private func sidebar(_ model: PracticeModel) -> some View {
        List(selection: Binding(get: { current?.id }, set: { currentID = $0 })) {
            Section {
                UncertaintyLegend().font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
            } header: {
                Text(remaining.count == 1 ? String(localized: "1 note to check") : String(localized: "\(remaining.count) notes to check"))
            }
            ForEach(partsWithItems, id: \.self) { part in
                Section {
                    ForEach(items.filter { $0.partName == part }) { item in
                        HStack(spacing: Space.s2) {
                            if checked.contains(item.id) {
                                Image(systemName: BrasscribeIcon.markChecked.systemName).foregroundStyle(Color.Brasscribe.textMuted)
                                    .accessibilityLabel(Text("Kept"))
                            } else {
                                UncertainMark(level: item.level)
                            }
                            Text("\(model.barLabel(item.bar)) · \(pitchName(item, model))")
                                .foregroundStyle(checked.contains(item.id) ? Color.Brasscribe.textMuted : Color.Brasscribe.text)
                        }
                        .tag(item.id)
                    }
                } header: { Text(part) }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.Brasscribe.surface)
    }

    private var partsWithItems: [String] {
        var seen = Set<String>()
        return items.map(\.partName).filter { seen.insert($0).inserted }
    }

    // MARK: actions

    private func listen(_ c: ReviewItem, _ model: PracticeModel) {
        model.listen(toBar: c.bar, original: model.hasOriginal)
    }

    private func keep(_ c: ReviewItem) {
        checked.insert(c.id)
        advance(from: c)
        piece.saveChecked(checked, remaining: remaining.count)
        app.refresh()
        if remaining.isEmpty { AccessibilityNotifier.announce(String(localized: "Every note is checked.")) }
    }

    private func skip(_ c: ReviewItem) {
        skipped.insert(c.id)
        advance(from: c)
    }

    private func advance(from c: ReviewItem) {
        model?.stop()
        let rest = remaining
        guard !rest.isEmpty else { currentID = nil; return }
        let after = items.drop { $0.id != c.id }.dropFirst().first { !checked.contains($0.id) && !skipped.contains($0.id) }
        currentID = (after ?? rest.first { !skipped.contains($0.id) } ?? rest.first)?.id
    }

    private func move(_ d: Int) {
        let list = remaining
        guard let c = current, let i = list.firstIndex(of: c) else { return }
        let j = max(0, min(list.count - 1, i + d))
        currentID = list[j].id
    }

    /// Back to the score if Review was opened from it, otherwise on to the score options.
    private func finish() {
        model?.stopAll()
        piece.saveChecked(checked, remaining: remaining.count)
        app.refresh()
        if app.path.count >= 2, case .score = app.path[app.path.count - 2] {
            app.path.removeLast()
        } else if let i = app.path.lastIndex(of: .review(piece)) {
            app.path[i] = .output(piece)
        } else {
            app.path.append(.output(piece))
        }
    }

    // MARK: text

    private func freeTimeText(_ r: ClosedRange<Int>) -> String {
        r.count == 1 ? String(localized: "Bar \(r.lowerBound + 1) has no steady beat (ad lib.). Its rhythms are approximate.")
                     : String(localized: "Bars \(r.lowerBound + 1)–\(r.upperBound + 1) have no steady beat (ad lib.). Their rhythms are approximate.")
    }

    private func note(_ c: ReviewItem, _ model: PracticeModel) -> ScoreNote? {
        guard let part = model.score.part(id: c.partID), part.notes.indices.contains(c.noteIndex) else { return nil }
        return part.notes[c.noteIndex]
    }

    private func pitchName(_ c: ReviewItem, _ model: PracticeModel) -> String {
        guard let n = note(c, model), case .pitched(let p) = n.kind else { return "" }
        return NoteWords.pitch(p)
    }

    /// "Written G, minim" (en-GB), "G, half note" (en-US), "Notert G, halvnote" (nb).
    private func noteText(_ c: ReviewItem, _ model: PracticeModel) -> String {
        guard let n = note(c, model), case .pitched(let p) = n.kind else { return "" }
        let t = model.talking
        let value = NoteWords.value(type: n.type ?? "", dots: n.dots) ?? t.durationName(type: n.type, dots: n.dots, ticks: n.durTicks)
        return String(localized: "Written \(NoteWords.pitch(p)), \(value)")
    }
}

/// Note names and values in the musician's words.
enum NoteWords {
    static var norwegian: Bool { ScoreLanguage.current == .norwegian }
    static var american: Bool { Locale.current.region == .unitedStates }

    static func pitch(_ p: SpelledPitch) -> String {
        if norwegian {
            switch (p.step, p.alter) {
            case ("B", -1): return "B"
            case ("B", 0): return "H"
            case ("E", -1): return "Ess"
            case ("A", -1): return "Ass"
            case (let s, 1): return s + "iss"
            case (let s, -1): return s + "ess"
            case (let s, _): return s
            }
        }
        let acc = ["-2": "𝄫", "-1": "♭", "1": "♯", "2": "𝄪"]["\(p.alter)"] ?? ""
        return p.step + acc
    }

    static func value(type: String, dots: Int) -> String? {
        let gb = ["breve": String(localized: "breve"), "whole": String(localized: "semibreve"), "half": String(localized: "minim"),
                  "quarter": String(localized: "crotchet"), "eighth": String(localized: "quaver"), "16th": String(localized: "semiquaver"),
                  "32nd": String(localized: "demisemiquaver")]
        guard !norwegian, !american, let base = gb[type] else { return nil }
        return dots == 0 ? base : dots == 1 ? String(localized: "dotted \(base)") : String(localized: "double-dotted \(base)")
    }
}

/// "How should the score be?": which band, how hard, and the key. Nothing re-arranges
/// until Show the score is pressed; unchanged choices open the score as it is.
struct OutputView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    let piece: Piece
    @State private var lineup: Lineup = .fullBand
    @State private var difficulty: Difficulty = .faithful
    @State private var semitones = 0
    @State private var recordedFifths: Int?
    @State private var busy = false
    @State private var failure: String?

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s6) {
                VStack(alignment: .leading, spacing: Space.s2) {
                    if wide { SectionLabel(String(localized: "Last step")) }
                    DisplayTitle(text: String(localized: "How should the score be?"))
                    Text("You can change this later. Nothing is lost.")
                        .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                }
                if wide {
                    HStack(alignment: .top, spacing: Space.s8) {
                        band.frame(maxWidth: .infinity)
                        VStack(alignment: .leading, spacing: Space.s6) { hard; key }.frame(maxWidth: .infinity)
                    }
                } else {
                    band; hard; key
                }
                if let failure {
                    NoticeBox(systemImage: BrasscribeIcon.error.systemName, text: failure)
                }
            }
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s6)
            .frame(maxWidth: wide ? 880 : .infinity, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .pageBackground()
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: Space.s3) {
                if wide {
                    Spacer()
                    Button { app.path.removeLast() } label: { Text("Back") }.buttonStyle(.plainText)
                }
                Button { Task { await show() } } label: {
                    if busy { ProgressView().controlSize(.small).tint(Color.Brasscribe.onPrimary) } else { Text("Show the score") }
                }
                .buttonStyle(PrimaryButtonStyle(fullWidth: !wide))
                .disabled(busy)
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("showScore")
            }
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s3)
            .frame(maxWidth: wide ? 880 : .infinity)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(Text(piece.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            let chosen = piece.output ?? OutputChoice()
            lineup = chosen.lineup
            difficulty = chosen.difficulty
            recordedFifths = piece.loadComposition()?.keys.first?.fifths
            if let target = chosen.keyFifths, let from = recordedFifths { semitones = Self.semitones(from: from, to: target) }
        }
    }

    private var band: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Which band?").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            radio(String(localized: "Full brass band"), String(localized: "About 25 players"), lineup == .fullBand) { lineup = .fullBand }
            radio(String(localized: "Small band"), String(localized: "10–15 players, parts doubled up"), lineup == .minimalBand) { lineup = .minimalBand }
        }
    }

    private var hard: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("How hard?").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            Segmented(label: String(localized: "How hard?"), selection: $difficulty,
                      options: [(Difficulty.easier, String(localized: "Easier")), (Difficulty.standard, String(localized: "A bit easier")),
                                (Difficulty.faithful, String(localized: "As played"))])
            HelperLine(systemImage: BrasscribeIcon.info.systemName, text: String(localized: "Easier keeps the tune but avoids high notes and fast runs."))
        }
    }

    private var key: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Key").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            HStack(spacing: Space.s3) {
                Button { semitones = max(-6, semitones - 1) } label: { Image(systemName: "minus").frame(width: 48, height: 48) }
                    .buttonStyle(SecondaryButtonStyle(minHeight: 48))
                    .accessibilityLabel(Text("Lower"))
                    .disabled(recordedFifths == nil || semitones <= -6)
                VStack(alignment: .leading, spacing: 2) {
                    Text(keyName).font(Font.Brasscribe.headline)
                    Text(keyDetail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                .padding(.horizontal, Space.s4)
                .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.borderStrong))
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("keyPicker")
                .accessibilityAdjustableAction { d in
                    if d == .increment { semitones = min(6, semitones + 1) } else if d == .decrement { semitones = max(-6, semitones - 1) }
                }
                Button { semitones = min(6, semitones + 1) } label: { Image(systemName: "plus").frame(width: 48, height: 48) }
                    .buttonStyle(SecondaryButtonStyle(minHeight: 48))
                    .accessibilityLabel(Text("Higher"))
                    .disabled(recordedFifths == nil || semitones >= 6)
            }
        }
    }

    private var targetFifths: Int? {
        guard let from = recordedFifths else { return nil }
        var f = from + 7 * semitones
        while f > 6 { f -= 12 }
        while f < -6 { f += 12 }
        return f
    }

    private var keyName: String {
        guard let f = targetFifths else { return String(localized: "As recorded") }
        return KeyNames.name(fifths: f)
    }

    private var keyDetail: String {
        switch semitones {
        case 0: return String(localized: "As recorded · concert pitch")
        case 1: return String(localized: "1 semitone up")
        case -1: return String(localized: "1 semitone down")
        case let s where s > 0: return String(localized: "\(s) semitones up")
        default: return String(localized: "\(-semitones) semitones down")
        }
    }

    static func semitones(from: Int, to: Int) -> Int {
        // the key change in semitones, -6…6, that turns `from` fifths into `to`
        for s in -6...6 {
            var f = from + 7 * s
            while f > 6 { f -= 12 }
            while f < -6 { f += 12 }
            if f == to { return s }
        }
        return 0
    }

    private func radio(_ title: String, _ detail: String, _ on: Bool, _ pick: @escaping () -> Void) -> some View {
        Button(action: pick) {
            HStack(spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    Text(detail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                Spacer()
                Image(systemName: on ? "largecircle.fill.circle" : "circle").font(.title2)
                    .foregroundStyle(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong)
                    .accessibilityHidden(true)
            }
            .padding(Space.s4)
            .frame(minHeight: 64)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong, lineWidth: on ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: Radius.lg))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isSelected] : [])
    }

    private func show() async {
        let choice = OutputChoice(lineup: lineup, difficulty: difficulty, keyFifths: semitones == 0 ? nil : targetFifths)
        let before = piece.output ?? OutputChoice()
        guard choice != before else { app.open(piece); return }
        guard let comp = piece.loadComposition() else {
            failure = String(localized: "This score can't be arranged again on this device. It opens as it is.")
            app.open(piece)
            return
        }
        busy = true
        defer { busy = false }
        do {
            try app.rearrange(piece, composition: comp, output: choice)
        } catch {
            failure = String(localized: "The score couldn't be arranged this way. Try another choice.")
        }
    }
}

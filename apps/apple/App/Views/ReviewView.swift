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
    @State private var filter: Filter = .mine
    @State private var changing: ReviewItem?
    @State private var changeFailed = false
    @State private var snippetVersion = 0

    /// Triage: your own part first (very unsure first), then the other parts, then all.
    enum Filter: Hashable { case mine, others, all }
    @AccessibilityFocusState private var headingFocused: Bool

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    /// Every note still to check, in every part.
    private var allRemaining: [ReviewItem] { items.filter { !checked.contains($0.id) } }

    private var myPartID: String? { model?.myPart }

    /// The notes still to check under the chosen filter. In your part the very unsure come first.
    private var remaining: [ReviewItem] {
        switch filter {
        case .mine:
            return allRemaining.filter { $0.partID == myPartID }
                .sorted { ($0.level == .veryUncertain ? 0 : 1, $0.bar, $0.tick) < ($1.level == .veryUncertain ? 0 : 1, $1.bar, $1.tick) }
        case .others: return allRemaining.filter { $0.partID != myPartID }
        case .all: return allRemaining
        }
    }

    private func count(_ f: Filter) -> Int {
        switch f {
        case .mine: return allRemaining.filter { $0.partID == myPartID }.count
        case .others: return allRemaining.filter { $0.partID != myPartID }.count
        case .all: return allRemaining.count
        }
    }
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
                    if allRemaining.isEmpty { finish() } else { confirmLeave = true }
                } label: {
                    Text(allRemaining.isEmpty ? String(localized: "Continue") : String(localized: "Finish later (\(allRemaining.count) left)"))
                }
                .accessibilityIdentifier("openScore")
            }
        }
        .alert(String(localized: "Finish checking later?"), isPresented: $confirmLeave) {
            Button(String(localized: "Finish later")) { finish() }
            Button(String(localized: "Keep checking"), role: .cancel) {}
        } message: {
            Text(allRemaining.count == 1
                 ? String(localized: "1 note keeps its ? mark. You can check it any time from the score: tap “Check them”.")
                 : String(localized: "\(allRemaining.count) notes keep their ? marks. You can check them any time from the score: tap “Check them”."))
        }
        .task {
            guard model == nil, let m = try? PracticeModel(piece: piece) else { return }
            m.start()
            model = m
            items = ReviewList.items(score: m.score, uncertainty: m.uncertainty)
            checked = piece.loadChecked()
            if count(.mine) == 0 { filter = .all }
            headingFocused = true
        }
        .onDisappear { model?.stopAll() }
        .sheet(item: $changing) { c in
            ChangeNoteSheet(current: pitchName(c, model!), options: changeOptions(c)) { delta in change(c, by: delta) }
        }
        .alert(String(localized: "The note couldn't be changed"), isPresented: $changeFailed) {
            Button("OK") {}
        } message: { Text("The score is as it was. Try again, or keep the note and fix it later.") }
        .onKeyPress(.space) { if let c = current, let model { listen(c, model) }; return .handled }
        .onKeyPress("k") { if let c = current { keep(c) }; return .handled }
        .onKeyPress(.downArrow) { move(1); return .handled }
        .onKeyPress(.upArrow) { move(-1); return .handled }
    }

    // MARK: detail

    @ViewBuilder private func detail(_ model: PracticeModel) -> some View {
        VStack(alignment: .leading, spacing: Space.s5) {
            VStack(alignment: .leading, spacing: Space.s2) {
                DisplayTitle(text: headline)
                    .accessibilityFocused($headingFocused)
                Text(subline(model))
                    .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
                if !allRemaining.isEmpty {
                    Segmented(label: String(localized: "Which notes"), selection: $filter,
                              options: [(Filter.mine, String(localized: "Your part (\(count(.mine)))")),
                                        (Filter.others, String(localized: "Other parts (\(count(.others)))")),
                                        (Filter.all, String(localized: "All parts (\(count(.all)))"))])
                    .accessibilityIdentifier("reviewFilter")
                }
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

    private var headline: String {
        if allRemaining.isEmpty { return String(localized: "Every note is checked") }
        if filter == .mine, count(.mine) > 0 { return String(localized: "Check your part first") }
        return remaining.count == 1 ? String(localized: "Check 1 note") : String(localized: "Check \(remaining.count) notes")
    }

    private func subline(_ model: PracticeModel) -> String {
        if allRemaining.isEmpty { return String(localized: "Next, choose how the score should be.") }
        if filter == .mine, let id = myPartID, let part = model.score.part(id: id), count(.mine) > 0 {
            let n = count(.mine), v = remaining.filter { $0.level == .veryUncertain }.count
            let notes = n == 1 ? String(localized: "1 note in \(part.displayName)") : String(localized: "\(n) notes in \(part.displayName)")
            return v == 0 ? notes + "." : notes + ", " + (v == 1 ? String(localized: "1 very unsure, first.") : String(localized: "\(v) very unsure, first."))
        }
        return String(localized: "Brasscribe wasn't sure about these. Listen, then keep, change or skip each one.")
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
            BarSnippet(piece: piece, partID: c.partID, bar: c.bar, tick: c.tick)
                .id(snippetVersion)
            HStack(alignment: .firstTextBaseline, spacing: Space.s3) {
                UncertainMark(level: c.level)
                Text("\(Text(noteText(c, model) + ".").foregroundStyle(Color.Brasscribe.text)) \(Text(c.level == .veryUncertain ? String(localized: "Very uncertain.") : String(localized: "Uncertain.")).foregroundStyle(Color.Brasscribe.textMuted))")
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
        Button { changing = c } label: { Text("Change note…") }
            .buttonStyle(SecondaryButtonStyle(outline: true, fullWidth: !wide, minHeight: 48))
            .accessibilityIdentifier("changeNote")
    }

    private func wideActions(_ c: ReviewItem, _ model: PracticeModel) -> some View {
        VStack(alignment: .leading, spacing: Space.s4) {
            HStack(spacing: Space.s3) { listenButtons(c, model) }
            Divider().overlay(Color.Brasscribe.border)
            HStack(spacing: Space.s3) {
                Spacer()
                Button { confirmLeave = true } label: { Text("Finish later (\(allRemaining.count) left)") }.buttonStyle(.plainText)
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
        let names = items.map(\.partName).filter { seen.insert($0).inserted }
        let mine = items.first { $0.partID == myPartID }?.partName
        return (mine.map { [$0] } ?? []) + names.filter { $0 != mine }
    }

    // MARK: actions

    /// A semitone and an octave either way, named as written on the part.
    private func changeOptions(_ c: ReviewItem) -> [(delta: Int, title: String)] {
        guard let model, let n = note(c, model), case .pitched(let p) = n.kind,
              let part = model.score.part(id: c.partID) else { return [] }
        let fifths = part.measureFifths.indices.contains(n.measureIndex) ? part.measureFifths[n.measureIndex] : part.writtenFifths
        func name(_ d: Int) -> String { NoteWords.pitch(SpelledPitch.spelling(midi: p.midi + d, fifths: fifths)) }
        return [(1, String(localized: "\(name(1)), a semitone higher")), (-1, String(localized: "\(name(-1)), a semitone lower")),
                (12, String(localized: "\(name(12)), an octave higher")), (-12, String(localized: "\(name(-12)), an octave lower"))]
    }

    private func change(_ c: ReviewItem, by delta: Int) {
        guard let model, let n = note(c, model), let part = model.score.part(id: c.partID) else { return }
        let fifths = part.measureFifths.indices.contains(n.measureIndex) ? part.measureFifths[n.measureIndex] : part.writtenFifths
        model.stopAll()
        do {
            try app.changeNote(piece, item: c, note: n, delta: delta, fifths: fifths)
            checked.insert(c.id)
            BarSnippet.forget(piece)
            snippetVersion += 1
            let m = try PracticeModel(piece: piece)
            m.start()
            self.model = m
            items = ReviewList.items(score: m.score, uncertainty: m.uncertainty)
            advance(from: c)
            piece.saveChecked(checked, remaining: allRemaining.count)
            app.refresh()
            AccessibilityNotifier.announce(String(localized: "Changed. The parts are arranged again."))
        } catch {
            changeFailed = true
        }
    }

    private func listen(_ c: ReviewItem, _ model: PracticeModel) {
        model.listen(toBar: c.bar, original: model.hasOriginal)
    }

    private func keep(_ c: ReviewItem) {
        checked.insert(c.id)
        advance(from: c)
        piece.saveChecked(checked, remaining: allRemaining.count)
        app.refresh()
        if allRemaining.isEmpty { AccessibilityNotifier.announce(String(localized: "Every note is checked.")) }
    }

    private func skip(_ c: ReviewItem) {
        skipped.insert(c.id)
        advance(from: c)
    }

    private func advance(from c: ReviewItem) {
        model?.stop()
        if remaining.isEmpty, !allRemaining.isEmpty { filter = .all }
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
        piece.saveChecked(checked, remaining: allRemaining.count)
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
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Space.s3) { lowerButton; keyBox; higherButton }
                VStack(alignment: .leading, spacing: Space.s3) { keyBox; HStack(spacing: Space.s3) { lowerButton; higherButton } }
            }
        }
    }

    private var lowerButton: some View {
        Button { semitones = max(-6, semitones - 1) } label: { Label("Lower", systemImage: "minus") }
            .buttonStyle(SecondaryButtonStyle(minHeight: 48))
            .help(Text("One semitone lower"))
            .disabled(recordedFifths == nil || semitones <= -6)
    }

    private var higherButton: some View {
        Button { semitones = min(6, semitones + 1) } label: { Label("Higher", systemImage: "plus") }
            .buttonStyle(SecondaryButtonStyle(minHeight: 48))
            .help(Text("One semitone higher"))
            .disabled(recordedFifths == nil || semitones >= 6)
    }

    private var keyBox: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(keyName).font(Font.Brasscribe.headline)
            Text(keyDetail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s2)
        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.borderStrong))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("keyPicker")
        .accessibilityAdjustableAction { d in
            if d == .increment { semitones = min(6, semitones + 1) } else if d == .decrement { semitones = max(-6, semitones - 1) }
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
        return String(localized: "\(KeyNames.name(fifths: f)) (concert)")
    }

    /// The same key as a B♭ and an E♭ player read it on their part.
    private var writtenKeys: String? {
        guard let f = targetFifths else { return nil }
        func wrap(_ x: Int) -> Int { var v = x; while v > 6 { v -= 12 }; while v < -6 { v += 12 }; return v }
        return String(localized: "\(KeyNames.name(fifths: wrap(f + 2))) for B♭ · \(KeyNames.name(fifths: wrap(f + 3))) for E♭ instruments")
    }

    private var keyDetail: String {
        let change: String
        switch semitones {
        case 0: change = String(localized: "As recorded")
        case 1: change = String(localized: "1 semitone up")
        case -1: change = String(localized: "1 semitone down")
        case let s where s > 0: change = String(localized: "\(s) semitones up")
        default: change = String(localized: "\(-semitones) semitones down")
        }
        return [writtenKeys, change].compactMap { $0 }.joined(separator: " · ")
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

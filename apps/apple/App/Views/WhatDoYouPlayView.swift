import BrasscribeCore
import SwiftUI

/// "What do you play?": the instrument, then which part, then for low brass the clef. Nothing is
/// chosen for the player (a 3rd cornet is never quietly filed as Solo Cornet) and nothing is saved
/// until Continue. The first run's second step, and Settings › What you play.
struct WhatDoYouPlayView: View {
    enum Mode { case firstRun, settings }
    let mode: Mode
    /// Continue or "I conduct or listen" with the answer; "Not now" with nil.
    let done: (SeatChoice?) -> Void

    @State private var instrumentID: String?
    @State private var seatID: String?
    @State private var reads: String?
    @Environment(\.dynamicTypeSize) private var typeSize
    @AccessibilityFocusState private var titleFocused: Bool
    @Environment(\.dismiss) private var dismiss

    init(mode: Mode, initial: SeatChoice = .notSet, done: @escaping (SeatChoice?) -> Void) {
        self.mode = mode
        self.done = done
        if case .seat(let id, let r) = initial, let s = Seats.info(id) {
            _instrumentID = State(initialValue: Seats.instrument(of: id)?.id)
            _seatID = State(initialValue: id)
            _reads = State(initialValue: r ?? s.reads.first)
        }
        // `-screen what-do-you-play-chosen`: the screen half answered, for the screenshots
        if LaunchOptions.screen == "what-do-you-play-chosen" { _instrumentID = State(initialValue: "baritone") }
    }

    private var instruments: [Seats.Instrument] { Seats.instruments }
    private var instrument: Seats.Instrument? { instruments.first { $0.id == instrumentID } }
    private var seat: SeatInfo? { seatID.flatMap { Seats.info($0) } }
    private var oneColumn: Bool { typeSize >= .accessibility1 }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s6) {
                VStack(alignment: .leading, spacing: Space.s2) {
                    DisplayTitle(text: String(localized: "What do you play?"))
                        .accessibilityFocused($titleFocused)
                    Text("Brasscribe shows your part first and mutes it when you play along. You can change it in Settings.")
                        .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                instrumentGroup
                if let instrument, instrument.seats.count > 1 { partGroup(instrument) }
                if let seat, seat.reads.count > 1 { readsGroup(seat) }
            }
            .padding(.horizontal, Space.s5)
            .padding(.vertical, Space.s6)
            .readingColumn()
        }
        .pageBackground()
        .safeAreaInset(edge: .bottom) { actions }
        .toolbar {
            if mode == .firstRun {
                ToolbarItem(placement: .primaryAction) {
                    Button { finish(nil) } label: { Text("Not now") }
                        .accessibilityIdentifier("seatNotNow")
                }
            }
        }
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(mode == .firstRun)
        #endif
        .onAppear { titleFocused = true }
    }

    // MARK: groups

    private var instrumentGroup: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Instrument").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: Space.s2), count: oneColumn ? 1 : 2), spacing: Space.s2) {
                ForEach(instruments) { i in tile(i) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(Text("Instrument"))
        }
    }

    private func tile(_ i: Seats.Instrument) -> some View {
        let on = i.id == instrumentID
        return Button { pick(i) } label: {
            HStack(spacing: Space.s2) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(i.title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    if let d = i.detail { Text(d).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted) }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                if on { Image(systemName: "checkmark").font(.body.weight(.semibold)).accessibilityHidden(true) }
            }
            .padding(.horizontal, Space.s4)
            .padding(.vertical, Space.s2)
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.md))
            .overlay(RoundedRectangle(cornerRadius: Radius.md)
                .strokeBorder(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong, lineWidth: on ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(i.accessibilityName))
        .accessibilityAddTraits(on ? [.isSelected] : [])
        .accessibilityIdentifier("instrument-\(i.id)")
    }

    private func partGroup(_ i: Seats.Instrument) -> some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Which part?").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            ChoiceSegments(label: String(localized: "Which part?"), selection: seatID,
                           options: i.seats.map { ($0.id, Seats.name($0), Seats.name($0).spokenFlats) }) { id in
                seatID = id
                reads = Seats.info(id)?.reads.first
            }
        }
    }

    private func readsGroup(_ s: SeatInfo) -> some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("You read").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            ChoiceSegments(label: String(localized: "You read"), selection: reads,
                           options: s.reads.map { r in (r, Seats.readingTitle(r, seat: s), Seats.readingTitle(r, seat: s).spokenFlats) }) { reads = $0 }
        }
    }

    // MARK: actions

    private var hint: String? {
        guard seat == nil else { return nil }
        return instrument == nil ? String(localized: "Choose your instrument, or “I conduct or listen”.")
                                 : String(localized: "Choose which part you play.")
    }

    private var actions: some View {
        VStack(spacing: Space.s1) {
            Button { if let s = seat { finish(.seat(s.id, reads: reads == s.reads.first ? nil : reads)) } } label: { Text("Continue") }
                .buttonStyle(.primaryWide)
                .disabled(seat == nil)
                .accessibilityHint(hint.map { Text($0) } ?? Text(""))
                .accessibilityIdentifier("seatContinue")
            if let hint {
                Text(hint).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityHidden(true)
            }
            Button { finish(.conductor) } label: { Text("I conduct or listen") }
                .buttonStyle(.plainText)
                .accessibilityIdentifier("seatConductor")
        }
        .padding(.horizontal, Space.s5)
        .padding(.vertical, Space.s3)
        .frame(maxWidth: BrasscribeDesign.Size.contentMaxWidth)
        .frame(maxWidth: .infinity)
        .background(Color.Brasscribe.bg.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
    }

    /// Settings goes back to the What you play row, which then shows the answer.
    private func finish(_ answer: SeatChoice?) {
        done(answer)
        if mode == .settings { dismiss() }
    }

    /// Choosing an instrument only shows the next question (3.2.2). One part: it is the answer.
    private func pick(_ i: Seats.Instrument) {
        guard i.id != instrumentID else { return }
        instrumentID = i.id
        if i.seats.count == 1 {
            seatID = i.seats[0].id
            reads = i.seats[0].reads.first
        } else {
            seatID = nil
            reads = nil
        }
    }
}

/// A radio row with nothing chosen until the player chooses: the chosen segment gets a tonal fill,
/// an ink edge and a ✓. A vertical list when the row doesn't fit (large text, long names).
struct ChoiceSegments: View {
    let label: String
    let selection: String?
    /// (value, title, spoken title)
    let options: [(String, String, String)]
    let pick: (String) -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        Group {
            if typeSize >= .accessibility1 {
                row(vertical: true)
            } else {
                ViewThatFits(in: .horizontal) { row(vertical: false); row(vertical: true) }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(label))
    }

    private func row(vertical: Bool) -> some View {
        let layout = vertical ? AnyLayout(VStackLayout(spacing: Space.s2)) : AnyLayout(HStackLayout(spacing: Space.s2))
        return layout {
            ForEach(options, id: \.0) { o in
                let on = o.0 == selection
                Button { pick(o.0) } label: {
                    HStack(spacing: Space.s2) {
                        if on { Image(systemName: "checkmark").font(.body.weight(.semibold)).accessibilityHidden(true) }
                        Text(o.1).font(on ? Font.Brasscribe.label : Font.Brasscribe.body)
                            .fixedSize(horizontal: !vertical, vertical: true)
                        if vertical { Spacer(minLength: 0) }
                    }
                    .foregroundStyle(on ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
                    .padding(.horizontal, Space.s3)
                    .frame(maxWidth: .infinity, minHeight: 48, alignment: vertical ? .leading : .center)
                    .background(on ? Color.Brasscribe.secondary : Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.md))
                    .overlay(RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong, lineWidth: on ? 1.5 : 1))
                    .contentShape(RoundedRectangle(cornerRadius: Radius.md))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(o.2))
                .accessibilityAddTraits(on ? [.isSelected] : [])
                .accessibilityIdentifier("choice-\(o.0)")
            }
        }
    }
}

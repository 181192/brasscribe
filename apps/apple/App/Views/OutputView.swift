import BrasscribeCore
import ScoreKit
import SwiftUI
import TranscriptionKit

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
    /// A quartet needs harmony: false for a solo take, which has one line and nothing for the other parts.
    @State private var quartetPossible = true
    /// The full band is written only for a take with layers: not for a Brass band or Pop or rock recording.
    @State private var fullBandPossible = true
    @State private var busy = false
    @State private var failure: String?
    /// Who played a solo take (a seat id), or whose part a band take is for: the score's seat, else yours.
    @State private var seatID: String?
    @State private var reads: String?
    /// "Who plays the tune?": "seat" puts it on your part.
    @State private var tuneOnMine = false
    /// The recording has a soloist (a solo layer beside the band).
    @State private var hasSoloist = false

    private var isSolo: Bool { piece.profile == .solo }
    private var seat: SeatInfo? { seatID.flatMap { Seats.info($0) } }

    /// Your part's name in a lineup (the core's table); for a solo take with a seat, the seat's own.
    private func yourPart(_ l: Lineup) -> String? {
        guard let seatID else { return nil }
        if isSolo { return Seats.info(seatID)?.name }
        return Seats.part(seatID, in: l)?.part
    }

    /// "Who plays the tune?" only for a soloist recording with a band lineup, when your part isn't
    /// the lead and your instrument can carry a tune.
    private var asksWhoPlaysTune: Bool {
        guard !isSolo, hasSoloist, lineup != .quartet, let seat, Seats.canCarryTune(seat),
              let part = yourPart(lineup) else { return false }
        // a seat that takes the lead part (a trumpet) has the tune already
        if let seatID, Seats.part(seatID, in: lineup)?.takes != nil { return false }
        return part != lineup.lead
    }

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
                        .font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                }
                if wide {
                    HStack(alignment: .top, spacing: Space.s8) {
                        VStack(alignment: .leading, spacing: Space.s6) { who; band }.frame(maxWidth: .infinity)
                        VStack(alignment: .leading, spacing: Space.s6) { hard; key }.frame(maxWidth: .infinity)
                    }
                } else {
                    who; band; hard; key
                }
                if let failure {
                    NoticeBox(systemImage: BrasscribeIcon.error.systemName, text: failure)
                }
                if PageActions.followContent { actionButtons.layoutProbe("pageActions") }
            }
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s6)
            .frame(maxWidth: wide ? 880 : .infinity, alignment: .leading)
            .layoutProbe("pageColumn")
            .frame(maxWidth: .infinity)
        }
        .pageBackground()
        .bottomActions {
            actionButtons
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s3)
            .frame(maxWidth: wide ? 880 : .infinity)
            .frame(maxWidth: .infinity)
            // An opaque band down to the screen edge, with a hairline, so the choices scroll under it
            // rather than showing through; the inset keeps the last row (and a focused one) above it.
            .background(Color.Scribe.bg.ignoresSafeArea(edges: .bottom))
            .overlay(alignment: .top) { Divider().overlay(Color.Scribe.border) }
        }
        .navigationTitle(Text(piece.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            let chosen = piece.output ?? OutputChoice()
            let comp = piece.loadComposition()
            fullBandPossible = piece.fullBandPossible(comp)
            lineup = chosen.lineup == .fullBand && !fullBandPossible ? .minimalBand : chosen.lineup
            difficulty = chosen.difficulty
            seatID = chosen.seat ?? app.seat.id
            reads = chosen.seat != nil ? chosen.reads : app.seat.reads
            tuneOnMine = chosen.lead == "seat" && !isSolo
            hasSoloist = piece.profile == .orchestraWithSoloist
                || (comp?.voices.contains { $0.layer == "solo" && !$0.notes.isEmpty } == true
                    && comp?.voices.contains { $0.layer != "solo" && !$0.notes.isEmpty } == true)
            recordedFifths = comp?.keys.first?.fifths
            quartetPossible = piece.canArrangeQuartet(comp)
            if let target = chosen.keyFifths, let from = recordedFifths { semitones = Self.semitones(from: from, to: target) }
        }
    }

    private var actionButtons: some View {
        HStack(spacing: Space.s3) {
            if wide {
                Spacer()
                Button { app.path.removeLast() } label: { Text("Back") }.buttonStyle(.plainText)
            }
            Button { Task { await show() } } label: {
                if busy { ProgressView().controlSize(.small).tint(Color.Scribe.onPrimary) } else { Text("Show the score") }
            }
            .buttonStyle(PrimaryButtonStyle(fullWidth: !wide))
            .disabled(busy)
            .keyboardShortcut(.defaultAction)
            .accessibilityIdentifier("showScore")
        }
    }

    @ViewBuilder private var band: some View {
        if isSolo, seatID != nil {
            // a solo take with a seat is written for that one instrument: there is no band to choose
            HelperLine(systemImage: BrasscribeIcon.info.systemName, text: String(localized: "A solo recording gives one part: yours."))
                .accessibilityIdentifier("soloOnePart")
        } else {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text("Which band?").font(Font.Scribe.headline).accessibilityAddTraits(.isHeader)
                // Unavailable for a whole-band recording: only the small band or the quartet is made from it.
                radio(String(localized: "Full brass band"),
                      fullBandPossible ? withPart(String(localized: "About 25 players"), .fullBand) : String(localized: "Not yet for whole-band recordings"),
                      lineup == .fullBand, available: fullBandPossible) { if fullBandPossible { lineup = .fullBand } }
                    .accessibilityIdentifier("lineup-full")
                radio(String(localized: "Small band"), withPart(String(localized: "10–15 players, parts doubled up"), .minimalBand), lineup == .minimalBand) { lineup = .minimalBand }
                // Unavailable for a solo take: it stays reachable (VoiceOver reads the reason) and does nothing.
                radio(String(localized: "Quartet"),
                      quartetPossible ? withPart(String(localized: "4 players, one on each part"), .quartet) : String(localized: "Needs a recording of the whole group"),
                      lineup == .quartet, available: quartetPossible) { if quartetPossible { lineup = .quartet } }
                    .accessibilityIdentifier("lineup-quartet")
            }
            if asksWhoPlaysTune, let part = yourPart(lineup) {
                VStack(alignment: .leading, spacing: Space.s3) {
                    Text("Who plays the tune?").font(Font.Scribe.headline).accessibilityAddTraits(.isHeader)
                    radio(String(localized: "\(Seats.leadName(lineup)) (as usual)"), nil, !tuneOnMine) { tuneOnMine = false }
                        .accessibilityIdentifier("tuneLineup")
                    radio(String(localized: "You: \(PartNames.display(part))"), nil, tuneOnMine) { tuneOnMine = true }
                        .accessibilityIdentifier("tuneSeat")
                }
            }
        }
    }

    /// "About 25 players · your part: Euphonium": which part will be yours, before Show the score.
    private func withPart(_ detail: String, _ l: Lineup) -> String {
        guard let part = yourPart(l) else { return detail }
        return "\(detail) · " + String(localized: "your part: \(PartNames.display(part))")
    }

    /// "Who played this?" on a solo take: a friend may have played it. Changing it writes the part for
    /// another instrument, on Show the score.
    @ViewBuilder private var who: some View {
        if isSolo {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text("Who played this?").font(Font.Scribe.headline).accessibilityAddTraits(.isHeader)
                Picker(selection: Binding(get: { seatID }, set: { id in
                    seatID = id
                    reads = id != nil && id == app.seat.id ? app.seat.reads : nil
                })) {
                    if seatID == nil { Text("Not set").tag(String?.none) }
                    ForEach(Seats.all, id: \.id) { s in Text(Seats.name(s)).tag(String?.some(s.id)) }
                } label: { Text("Who played this?") }
                .pickerStyle(.menu)
                .menuTint()
                .frame(minHeight: 44)
                .accessibilityIdentifier("whoPlayed")
            }
        }
    }

    private var hard: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("How hard?").font(Font.Scribe.headline).accessibilityAddTraits(.isHeader)
            Segmented(label: String(localized: "How hard?"), selection: $difficulty,
                      options: [(Difficulty.easier, String(localized: "Easier")), (Difficulty.standard, String(localized: "A bit easier")),
                                (Difficulty.faithful, String(localized: "As played"))])
            HelperLine(systemImage: BrasscribeIcon.info.systemName, text: String(localized: "Easier keeps the tune but avoids high notes and fast runs."))
        }
    }

    private var key: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Key").font(Font.Scribe.headline).accessibilityAddTraits(.isHeader)
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
            .accessibilityIdentifier("keyLower")
    }

    private var higherButton: some View {
        Button { semitones = min(6, semitones + 1) } label: { Label("Higher", systemImage: "plus") }
            .buttonStyle(SecondaryButtonStyle(minHeight: 48))
            .help(Text("One semitone higher"))
            .disabled(recordedFifths == nil || semitones >= 6)
            .accessibilityIdentifier("keyHigher")
    }

    private var keyBox: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(keyName).font(Font.Scribe.headline)
            Text(keyDetail).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s2)
        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Scribe.borderStrong))
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

    /// The key as you read it on your part ("E major on your part"); with no seat, as a B♭ and an E♭
    /// player read it.
    private var writtenKeys: String? {
        guard let f = targetFifths else { return nil }
        func wrap(_ x: Int) -> Int { var v = x; while v > 6 { v -= 12 }; while v < -6 { v += 12 }; return v }
        if let part = yourPart(isSolo ? .fullBand : lineup) {
            let shift = Seats.partWrittenShift(part)
            // with nothing chosen the seat's own first clef: the bass trombone reads bass clef, as it sounds
            if Seats.reading(reads, seat: seat) == "bass" || shift == 0 { return String(localized: "\(KeyNames.name(fifths: f)), as it sounds") }
            return String(localized: "\(KeyNames.name(fifths: wrap(f + shift))) on your part")
        }
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

    private func radio(_ title: String, _ detail: String?, _ on: Bool, available: Bool = true, _ pick: @escaping () -> Void) -> some View {
        Button(action: pick) {
            HStack(spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Scribe.headline).foregroundStyle(available ? Color.Scribe.text : Color.Scribe.textMuted)
                    if let detail {
                        Text(detail).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer()
                Image(systemName: on ? "largecircle.fill.circle" : "circle").font(.title2)
                    .foregroundStyle(on ? Color.Scribe.text : Color.Scribe.borderStrong)
                    .accessibilityHidden(true)
            }
            .padding(Space.s4)
            .frame(minHeight: 64)
            .background(Color.Scribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(on ? Color.Scribe.text : Color.Scribe.borderStrong, lineWidth: on ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: Radius.lg))
        }
        .buttonStyle(.plain)
        .opacity(available ? 1 : 0.6)
        .accessibilityAddTraits(on ? [.isSelected] : [])
        .accessibilityValue(available ? Text("") : Text("Unavailable"))
    }

    private func show() async {
        let before = piece.output ?? OutputChoice()
        var choice = OutputChoice(lineup: lineup, difficulty: difficulty, keyFifths: semitones == 0 ? nil : targetFifths)
        if isSolo {
            // a solo take with a seat is written for it; the tune is always the seat's
            choice.seat = seatID
            choice.reads = seatID == nil ? nil : reads
            choice.lead = seatID == nil ? nil : "seat"
        } else {
            // a band take's notes don't follow the seat; it goes along for the tune and the clef
            let tune = asksWhoPlaysTune && tuneOnMine
            choice.seat = before.seat ?? (tune ? seatID : nil)
            choice.reads = before.seat != nil ? before.reads : (tune ? reads : nil)
            choice.lead = tune ? "seat" : nil
        }
        guard choice != before else { app.open(piece); return }
        guard let comp = piece.loadComposition() else {
            failure = String(localized: "This score can't be arranged again on this device. It opens as it is.")
            app.open(piece)
            return
        }
        busy = true
        defer { busy = false }
        do {
            try await app.rearrangeInBackground(piece, composition: comp, output: choice)
        } catch {
            failure = ErrorWords.specific(error) ?? String(localized: "The score couldn't be arranged this way. Try another choice.")
        }
    }
}

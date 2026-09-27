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
            // An opaque band down to the screen edge, with a hairline, so the choices scroll under it
            // rather than showing through; the inset keeps the last row (and a focused one) above it.
            .background(Color.Brasscribe.bg.ignoresSafeArea(edges: .bottom))
            .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
        }
        .navigationTitle(Text(piece.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            let chosen = piece.output ?? OutputChoice()
            lineup = chosen.lineup
            difficulty = chosen.difficulty
            let comp = piece.loadComposition()
            recordedFifths = comp?.keys.first?.fifths
            quartetPossible = piece.canArrangeQuartet(comp)
            if let target = chosen.keyFifths, let from = recordedFifths { semitones = Self.semitones(from: from, to: target) }
        }
    }

    private var band: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Text("Which band?").font(Font.Brasscribe.headline).accessibilityAddTraits(.isHeader)
            radio(String(localized: "Full brass band"), String(localized: "About 25 players"), lineup == .fullBand) { lineup = .fullBand }
            radio(String(localized: "Small band"), String(localized: "10–15 players, parts doubled up"), lineup == .minimalBand) { lineup = .minimalBand }
            // Unavailable for a solo take: it stays reachable (VoiceOver reads the reason) and does nothing.
            radio(String(localized: "Quartet"),
                  quartetPossible ? String(localized: "4 players, one on each part") : String(localized: "Needs a recording of the whole group"),
                  lineup == .quartet, available: quartetPossible) { if quartetPossible { lineup = .quartet } }
                .accessibilityIdentifier("lineup-quartet")
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

    private func radio(_ title: String, _ detail: String, _ on: Bool, available: Bool = true, _ pick: @escaping () -> Void) -> some View {
        Button(action: pick) {
            HStack(spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Brasscribe.headline).foregroundStyle(available ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
                    Text(detail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
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
        .opacity(available ? 1 : 0.6)
        .accessibilityAddTraits(on ? [.isSelected] : [])
        .accessibilityValue(available ? Text("") : Text("Unavailable"))
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

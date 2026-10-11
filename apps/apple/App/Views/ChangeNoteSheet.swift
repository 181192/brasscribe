import ScoreKit
import SwiftUI
import TranscriptionKit

/// "Change note…" from Check the notes: pick the written pitch, hear it against the bar, save it to the score.
struct ChangeNoteSheet: View {
    let piece: Piece
    let target: ReviewItem
    let xml: String
    let evidence: NoteEvidence.Note?
    /// The note was written, from the first pitch to the second; Review stays on it.
    let onSave: (SpelledPitch, SpelledPitch) -> Void
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var lead: ScoreNote?
    @State private var written: SpelledPitch?
    @State private var original: SpelledPitch?
    @State private var fifths = 0
    @State private var transpose = 0
    @State private var saveError: String?
    /// Plays the bar with the pitch chosen here, before it is saved.
    @State private var preview = NotePreview()

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Space.s5) {
                VStack(alignment: .leading, spacing: Space.s2) {
                    Text("\(target.partName) · Bar \(target.bar + 1)").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                    Text(written.map { "Written \(ReviewWords.name($0))\($0.octave)" } ?? "")
                        .font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text)
                        .accessibilityAddTraits(.updatesFrequently)
                }
                HStack(spacing: Space.s3) {
                    Button { shift(-1) } label: { Label("Down a semitone", systemImage: "minus") }
                        .buttonStyle(SecondaryButtonStyle(fullWidth: true, minHeight: 48))
                        .keyboardShortcut(.downArrow, modifiers: [])
                    Button { shift(1) } label: { Label("Up a semitone", systemImage: "plus") }
                        .buttonStyle(SecondaryButtonStyle(fullWidth: true, minHeight: 48))
                        .keyboardShortcut(.upArrow, modifiers: [])
                }
                let suggestions = heardPitches
                if !suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: Space.s2) {
                        SectionLabel(String(localized: "What the transcribers heard"))
                        HStack(spacing: Space.s2) {
                            ForEach(suggestions, id: \.pitch.midi) { s in
                                Button { written = s.pitch } label: { Text("\(ReviewWords.name(s.pitch))\(s.pitch.octave) · \(s.names)") }
                                    .buttonStyle(SecondaryButtonStyle(outline: written != s.pitch, minHeight: 44))
                                    .accessibilityAddTraits(written == s.pitch ? .isSelected : [])
                            }
                        }
                    }
                }
                previewButton
                Text("Save changes the note in the score. Listen to it, then keep it to take the ? mark away.")
                    .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            #if os(iOS)
            // the phone's sheet is taller than the content: it stays at the top
            .frame(maxHeight: .infinity, alignment: .top)
            #endif
            .padding(Space.s6)
            .modifier(ScrollsOnPhone())
            .pageBackground()
            .navigationTitle(Text("Change note"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.disabled(written == nil || written == original)
                }
            }
            .alert("Couldn't save the note", isPresented: Binding(get: { saveError != nil }, set: { if !$0 { saveError = nil } })) {
                Button("OK") { saveError = nil }
            } message: { Text(saveError ?? "") }
            .task { load() }
            .onChange(of: written) { preview.stop() }
            .onDisappear { preview.close() }
        }
        #if os(macOS)
        .sheetSize(minWidth: 420, idealWidth: 480, maxWidth: 560)
        #endif
    }

    /// "Play the bar with this note", and "Stop" in the same place while it plays: the bar with the pitch
    /// chosen here, on the band's sampler, before anything is saved.
    private var previewButton: some View {
        let playing = preview.isPlaying
        return Button { togglePreview() } label: {
            ListenStopLabel(playing: playing, listenText: "Play the bar with this note").frame(maxWidth: .infinity)
        }
        .buttonStyle(SecondaryButtonStyle(minHeight: 48))
        .keyboardShortcut(.space, modifiers: [])
        .disabled(written == nil)
        .accessibilityLabel(playing ? Text("Stop") : Text("Play the bar with this note"))
        .accessibilityIdentifier("previewNote")
    }

    private func togglePreview() {
        guard let written else { return }
        if preview.isPlaying { preview.stop(announce: true); return }
        let bars = target.bar...max(target.bar, target.lastBar ?? target.bar)
        Task { await preview.play(piece: piece, xml: xml, target: target, pitch: written, bars: bars) }
    }

    /// Model pitches, written for this part, grouped with the models that heard each one.
    private var heardPitches: [(pitch: SpelledPitch, names: String)] {
        let byPitch = Dictionary(grouping: evidence?.models.filter { $0.pitch != nil } ?? [], by: { $0.pitch! })
        return byPitch.sorted { $0.key < $1.key }.map { concert, models in
            (SpelledPitch.spelling(midi: concert - transpose, fifths: fifths), models.map(\.name).joined(separator: ", "))
        }
    }

    private func shift(_ semitones: Int) {
        guard let w = written else { return }
        written = SpelledPitch.spelling(midi: w.midi + semitones, fifths: fifths)
    }

    private func load() {
        guard let score = try? MusicXMLParser.parse(Data(xml.utf8)), let part = score.part(id: target.partID),
              part.notes.indices.contains(target.noteIndex), case .pitched(let w) = part.notes[target.noteIndex].kind else { return }
        fifths = part.measureFifths.indices.contains(target.bar) ? part.measureFifths[target.bar] : part.writtenFifths
        transpose = part.transposeSemitones
        lead = part.notes[target.noteIndex]
        original = w
        written = w
    }

    private func save() {
        guard let written, let original, let lead else { return }
        do {
            try ReviewChange.apply(piece: piece, app: app, xml: xml, target: target, lead: lead, from: original, to: written)
            onSave(original, written)
            dismiss()
        } catch {
            saveError = error.localizedDescription
        }
    }
}

/// Writes a changed note to the piece, which stays open in Review until it is kept.
enum ReviewChange {
    /// The note `lead` of `target` moves from `from` to `to`. The Composition changes and the core arranges
    /// the score again, so parts doubling the line follow; without the Composition only this printed note
    /// changes. `undo` puts back what Brasscribe wrote.
    @MainActor
    static func apply(piece: Piece, app: AppModel, xml: String, target: ReviewItem, lead: ScoreNote,
                      from: SpelledPitch, to: SpelledPitch, undo: Bool = false) throws {
        if var comp = piece.loadComposition(), let p = lead.midiPitch,
           let change = CompositionEdit.change(&comp, scoreTick: lead.startTick, concertPitch: p, by: to.midi - from.midi, undo: undo) {
            try piece.saveComposition(comp)
            if let e = piece.loadEvidence() { piece.saveEvidence(CompositionEdit.follow(e, change)) }
            try app.rearrange(piece, composition: comp, output: piece.output ?? OutputChoice(), open: false)
        } else {
            try piece.saveMusicXML(MusicXMLNoteEditor.replacingPitch(in: xml, partID: target.partID, noteIndex: target.noteIndex, with: to))
        }
    }
}

/// On the phone the sheet scrolls, so every control stays reachable at the largest text sizes.
private struct ScrollsOnPhone: ViewModifier {
    func body(content: Content) -> some View {
        #if os(iOS)
        ScrollView { content }
        #else
        content
        #endif
    }
}

/// Change note…'s preview: the score with the candidate pitch in place of the note, played on its own
/// sampler for the note's bars. Nothing is written; the model is kept while the pitch stays the same.
@MainActor @Observable
final class NotePreview {
    private(set) var model: PracticeModel?
    private var madeFor: Int?
    /// A model is being made for a press; a second press meanwhile stops it before it plays.
    private(set) var preparing = false
    /// Bumped by every press, stop and close: only the latest press's model may play.
    private var request = 0

    var isPlaying: Bool { preparing || model?.listening != nil }

    func play(piece: Piece, xml: String, target: ReviewItem, pitch: SpelledPitch, bars: ClosedRange<Int>) async {
        request += 1
        let mine = request
        if model == nil || madeFor != pitch.midi {
            model?.stopAll()
            model = nil
            preparing = true
            guard let candidate = try? MusicXMLNoteEditor.replacingPitch(in: xml, partID: target.partID, noteIndex: target.noteIndex, with: pitch),
                  let score = try? MusicXMLParser.parse(Data(candidate.utf8)) else { preparing = false; return }
            let m = await PracticeModel.open(piece, score: score, composition: piece.loadComposition())
            // stopped, or another pitch pressed, while it was being made: a slower older build never plays
            guard preparing, mine == request else { m.stopAll(); return }
            preparing = false
            model = m
            madeFor = pitch.midi
        }
        model?.listen(bars: bars, original: false)
    }

    func stop(announce: Bool = false) {
        request += 1
        preparing = false
        model?.stopListening(announce: announce)
    }

    /// The sheet has gone: the preview's engine goes with it.
    func close() {
        request += 1
        preparing = false
        model?.stopAll()
        model = nil
        madeFor = nil
    }
}

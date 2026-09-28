import ScoreKit
import SwiftUI
import TranscriptionKit

/// "Change note…" from Check the notes: pick the written pitch, hear it against the bar, save it to the score.
struct ChangeNoteSheet: View {
    let piece: Piece
    let target: ReviewItem
    let xml: String
    let evidence: NoteEvidence.Note?
    let onSave: () -> Void
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var lead: ScoreNote?
    @State private var written: SpelledPitch?
    @State private var original: SpelledPitch?
    @State private var fifths = 0
    @State private var transpose = 0
    @State private var saveError: String?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Space.s5) {
                VStack(alignment: .leading, spacing: Space.s2) {
                    Text("\(target.partName) · Bar \(target.bar + 1)").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                    Text(written.map { "Written \(ReviewWords.name($0))\($0.octave)" } ?? "")
                        .font(Font.Brasscribe.title2).foregroundStyle(Color.Brasscribe.text)
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
                Text("The ? mark goes when you save. Changes are kept with this score.")
                    .font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            #if os(iOS)
            // the phone's sheet is taller than the content: it stays at the top
            .frame(maxHeight: .infinity, alignment: .top)
            #endif
            .padding(Space.s6)
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
        }
        #if os(macOS)
        .sheetSize(minWidth: 420, idealWidth: 480, maxWidth: 560)
        #endif
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
        guard let written, let original else { return }
        do {
            var checked = piece.loadChecked()
            checked.insert(target.id)
            try? JSONEncoder().encode(checked).write(to: piece.checkedURL)
            // The Composition changes and the core arranges the score again, so parts doubling the line follow;
            // without the Composition only this printed note changes.
            if var comp = piece.loadComposition(), let lead, let p = lead.midiPitch,
               let change = CompositionEdit.change(&comp, scoreTick: lead.startTick, concertPitch: p, by: written.midi - original.midi) {
                try piece.saveComposition(comp)
                if let e = piece.loadEvidence() { piece.saveEvidence(CompositionEdit.follow(e, change)) }
                try app.rearrange(piece, composition: comp, output: piece.output ?? OutputChoice(), open: false)
            } else {
                let updated = try MusicXMLNoteEditor.replacingPitch(in: xml, partID: target.partID, noteIndex: target.noteIndex, with: written)
                try piece.saveMusicXML(updated)
                piece.saveChecked(checked, remaining: max(0, (piece.toCheck ?? 1) - 1))
            }
            onSave()
            dismiss()
        } catch {
            saveError = error.localizedDescription
        }
    }
}

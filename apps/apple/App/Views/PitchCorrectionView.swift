import ScoreKit
import SwiftUI

struct PitchCorrectionView: View {
    private struct Address: Hashable {
        let partID: String
        let noteIndex: Int
        let fifths: Int
    }

    let piece: Piece
    let onSave: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var xml: String
    @State private var score: Score?
    @State private var partID: String?
    @State private var pitches: [Address: Int] = [:]
    @State private var saveError: String?

    init(piece: Piece, onSave: @escaping () -> Void) {
        self.piece = piece
        self.onSave = onSave
        let xml = (try? piece.musicXML()) ?? ""
        _xml = State(initialValue: xml)
        _score = State(initialValue: try? MusicXMLParser.parse(Data(xml.utf8)))
    }

    var body: some View {
        NavigationStack {
            Group {
                if let score {
                    Form {
                        Section("Part") {
                            Picker("Part", selection: $partID) {
                                ForEach(score.parts) { part in Text(part.name).tag(Optional(part.id)) }
                            }
                        }
                        if let part = score.parts.first(where: { $0.id == partID }) {
                            Section("Notes") {
                                ForEach(Array(part.notes.enumerated()), id: \.offset) { index, note in
                                    if case .pitched(let written) = note.kind {
                                        let address = Address(partID: part.id, noteIndex: index,
                                                              fifths: part.measureFifths.indices.contains(note.measureIndex)
                                                                  ? part.measureFifths[note.measureIndex] : part.writtenFifths)
                                        Stepper(value: Binding(
                                            get: { pitches[address] ?? written.midi },
                                            set: { pitches[address] = $0 }
                                        ), in: 0...127) {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text("Bar \(note.measureIndex + 1) · \(pitchName(pitches[address] ?? written.midi))")
                                                Text("Beat \(beatDescription(note.startTick, in: score.measures[note.measureIndex]))")
                                                    .font(.caption).foregroundStyle(.secondary)
                                            }
                                        }
                                        .accessibilityIdentifier("pitch-\(part.id)-\(index)")
                                    }
                                }
                            }
                        }
                    }
                } else {
                    ContentUnavailableView("Couldn't open the score", systemImage: "exclamationmark.triangle")
                }
            }
            .navigationTitle("Correct notes")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.disabled(pitches.isEmpty)
                }
            }
            .alert("Couldn't save corrections", isPresented: Binding(get: { saveError != nil }, set: { if !$0 { saveError = nil } })) {
                Button("OK") { saveError = nil }
            } message: { Text(saveError ?? "") }
        }
    }

    private func save() {
        do {
            var updated = xml
            for (address, midi) in pitches {
                updated = try MusicXMLNoteEditor.replacingPitch(
                    in: updated, partID: address.partID, noteIndex: address.noteIndex,
                    with: SpelledPitch.spelling(midi: midi, fifths: address.fifths))
            }
            try piece.saveMusicXML(updated)
            xml = updated
            score = try MusicXMLParser.parse(Data(updated.utf8))
            pitches.removeAll()
            onSave()
            dismiss()
        } catch {
            saveError = error.localizedDescription
        }
    }

    private func pitchName(_ midi: Int) -> String {
        let pitch = SpelledPitch.spelling(midi: midi, fifths: 0)
        let accidental = pitch.alter == 1 ? "♯" : pitch.alter == -1 ? "♭" : ""
        return "\(pitch.step)\(accidental)\(pitch.octave)"
    }

    private func beatDescription(_ tick: Int, in measure: Measure) -> String {
        let beat = Double(tick - measure.startTick) / Double(measure.beatTicks) + 1
        return String(format: "%.2g", beat)
    }
}
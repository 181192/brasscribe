import Foundation
import ScoreKit

public typealias NoteEvidence = CompanionService.Evidence

extension CompanionService.Evidence {
    public static let empty = NoteEvidence(models: [], notes: [])

    /// One transcriber's raw notes, in seconds of the recording.
    public struct ModelNotes: Sendable {
        public var model: String
        public var name: String
        public var notes: [DetectedPitch]
        public init(model: String, name: String, notes: [DetectedPitch]) { self.model = model; self.name = name; self.notes = notes }
    }

    public struct DetectedPitch: Sendable, Equatable {
        public var onset: Double
        public var offset: Double
        public var pitch: Int
        public init(onset: Double, offset: Double, pitch: Int) { self.onset = onset; self.offset = offset; self.pitch = pitch }
    }

    /// The engine's `/v1/jobs/{id}/evidence`, computed on this device for its own transcriptions.
    public static func build(composition: Composition, models: [ModelNotes], uncertainBelow: Double = 0.7,
                             onsetWindow: Double = 0.12) -> NoteEvidence {
        var notes: [Note] = []
        for voice in composition.voices where voice.role == .melody {
            for n in voice.notes where n.confidence < uncertainBelow {
                let heard = n.onsetS.map { onset in models.map { m in heardAt(m, onset: onset, pitch: n.pitch) } } ?? []
                notes.append(Note(voice: voice.id, start: n.start, pitch: n.pitch, confidence: n.confidence, onsetS: n.onsetS, models: heard))
            }
        }
        let used = models.filter { m in notes.contains { $0.models.contains { $0.model == m.model } } }
        return NoteEvidence(models: used.map { Model(model: $0.model, name: $0.name) }, notes: notes)
    }

    static func heardAt(_ m: ModelNotes, onset: Double, pitch: Int, window: Double = 0.12) -> Heard {
        let near = m.notes.filter { abs($0.onset - onset) <= window }
        // In a polyphonic layer the melody's rival is the nearest pitch, not the lowest one sounding.
        if let best = near.min(by: { (abs($0.pitch - pitch), abs($0.onset - onset)) < (abs($1.pitch - pitch), abs($1.onset - onset)) }) {
            return Heard(model: m.model, name: m.name, pitch: best.pitch, agrees: best.pitch == pitch)
        }
        let held = m.notes.first { $0.onset <= onset && onset < $0.offset }
        return Heard(model: m.model, name: m.name, pitch: held?.pitch, agrees: held?.pitch == pitch)
    }

    /// The evidence behind an arranged note: same onset and pitch class as a transcribed note.
    public func note(atScoreTick tick: Int, concertPitch: Int, ticksPerBeat: Int) -> Note? {
        let t = Int((Double(tick) * Double(ticksPerBeat) / Double(Score.ticksPerQuarter)).rounded())
        let pc = ((concertPitch % 12) + 12) % 12
        return notes.first { $0.start == t && (($0.pitch % 12) + 12) % 12 == pc }
    }
}

extension CompanionService.Evidence.Note {
    /// The pitch the disagreeing models heard most often, as a shift from the written note.
    public var alternativeShift: Int? {
        let others = models.compactMap { $0.agrees ? nil : $0.pitch }
        guard let top = Dictionary(grouping: others, by: { $0 }).max(by: { ($0.value.count, -abs($0.key - pitch)) < ($1.value.count, -abs($1.key - pitch)) })
        else { return nil }
        return top.key - pitch
    }
}

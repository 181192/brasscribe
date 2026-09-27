import Foundation
import ScoreKit
import TranscriptionKit

/// Edits the musician makes in Review, written to the Composition (the transcription itself),
/// so they survive arranging the score again: a changed note gets the new pitch, confidence 1
/// and the source "player"; a kept note or group gets confidence 1.
enum CompositionEdit {
    /// The Composition note behind an arranged note: same onset, same pitch class; the least
    /// certain one when several voices match.
    static func noteIndex(in comp: Composition, scoreTick: Int, concertPitch: Int) -> (voice: Int, note: Int)? {
        let t = Int((Double(scoreTick) * Double(comp.ticksPerBeat) / Double(Score.ticksPerQuarter)).rounded())
        let pc = ((concertPitch % 12) + 12) % 12
        var best: (voice: Int, note: Int, confidence: Double)?
        for (v, voice) in comp.voices.enumerated() {
            for (i, n) in voice.notes.enumerated() where n.start == t && ((n.pitch % 12) + 12) % 12 == pc {
                if best == nil || n.confidence < best!.confidence { best = (v, i, n.confidence) }
            }
        }
        return best.map { ($0.voice, $0.note) }
    }

    struct Change: Equatable { let voice: String; let start: Int; let from: Int; let to: Int }

    /// "Change note…": the note moves by `semitones`, and the player's pitch is certain.
    static func change(_ comp: inout Composition, scoreTick: Int, concertPitch: Int, by semitones: Int) -> Change? {
        guard let (v, i) = noteIndex(in: comp, scoreTick: scoreTick, concertPitch: concertPitch) else { return nil }
        let old = comp.voices[v].notes[i].pitch
        comp.voices[v].notes[i].pitch = max(0, min(127, old + semitones))
        comp.voices[v].notes[i].confidence = 1
        if !comp.voices[v].notes[i].sources.contains("player") { comp.voices[v].notes[i].sources.append("player") }
        return Change(voice: comp.voices[v].id, start: comp.voices[v].notes[i].start, from: old, to: comp.voices[v].notes[i].pitch)
    }

    /// The evidence follows the note: the musician's pitch is now the one each transcriber is compared to.
    static func follow(_ e: NoteEvidence, _ c: Change) -> NoteEvidence {
        NoteEvidence(models: e.models, notes: e.notes.map { n in
            guard n.voice == c.voice, n.start == c.start, n.pitch == c.from else { return n }
            return .init(voice: n.voice, start: n.start, pitch: c.to, confidence: n.confidence, onsetS: n.onsetS,
                         models: n.models.map { .init(model: $0.model, name: $0.name, pitch: $0.pitch, agrees: $0.pitch == c.to) })
        })
    }

    /// "Keep": the review item's notes are certain, so it stays kept after arranging again.
    /// A group keeps every note of its voice in its span; a single note keeps that note.
    static func keep(_ comp: inout Composition, item: ReviewItem, lead: ScoreNote) {
        let q = Double(comp.ticksPerBeat) / Double(Score.ticksPerQuarter)
        if let end = item.endTick,
           let g = comp.review.first(where: { Int((Double($0.start) / q).rounded()) <= item.tick && Int((Double($0.end) / q).rounded()) == end }),
           let v = comp.voices.firstIndex(where: { $0.id == g.voice }) {
            for i in comp.voices[v].notes.indices where comp.voices[v].notes[i].start >= g.start && comp.voices[v].notes[i].start < g.end {
                comp.voices[v].notes[i].confidence = 1
            }
            return
        }
        if let p = lead.midiPitch, let (v, i) = noteIndex(in: comp, scoreTick: lead.startTick, concertPitch: p) {
            comp.voices[v].notes[i].confidence = 1
        }
    }

    /// Whether a review group still has a note to check (all kept or changed: it's done).
    static func isOpen(_ g: Composition.ReviewGroup, in comp: Composition) -> Bool {
        guard let voice = comp.voices.first(where: { $0.id == g.voice }) else { return true }
        return voice.notes.contains { $0.start >= g.start && $0.start < g.end && $0.confidence < UncertaintyIndex.threshold }
    }
}

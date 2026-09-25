import Foundation

/// One note event ready for playback or export: concert pitch, tie chains merged.
public struct PlaybackNote: Sendable, Equatable {
    public var pitch: Int
    public var startTick: Int
    public var durTicks: Int
    public var velocity: Int
}

public extension Part {
    /// Notes to sound, with tied notes merged into one and rests dropped.
    var playbackNotes: [PlaybackNote] {
        var out: [PlaybackNote] = []
        var open: [Int: Int] = [:] // pitch -> index in out of a note awaiting a tie stop
        for n in notes.sorted(by: { $0.startTick < $1.startTick }) {
            guard let p = n.midiPitch, n.durTicks > 0 else { continue }
            if n.tieStop, let i = open[p], out[i].startTick + out[i].durTicks == n.startTick {
                out[i].durTicks += n.durTicks
                if !n.tieStart { open[p] = nil }
                continue
            }
            out.append(PlaybackNote(pitch: p, startTick: n.startTick, durTicks: n.durTicks,
                                    velocity: isPercussion ? 90 : 80))
            if n.tieStart { open[p] = out.count - 1 } else { open[p] = nil }
        }
        return out
    }
}

/// Writes Standard MIDI Files (format 1) from a `Score`.
///
/// Track 0 carries tempo and meter; then one track per part in score order; optionally a
/// final metronome track (GM percussion, high wood block on beat 1, low on other beats).
public enum MIDIWriter {
    public struct Options: Sendable {
        public var parts: Set<String>?
        public var transposeSemitones: Int
        public var includeMetronome: Bool
        /// Ticks of silence (in `Score.ticksPerQuarter` units) before bar 1.
        public var leadInTicks: Int
        public init(parts: Set<String>? = nil, transposeSemitones: Int = 0, includeMetronome: Bool = false, leadInTicks: Int = 0) {
            self.parts = parts; self.transposeSemitones = transposeSemitones
            self.includeMetronome = includeMetronome; self.leadInTicks = leadInTicks
        }
    }

    public static let metronomeHigh = 76
    public static let metronomeLow = 77

    /// Channel (0-based) for each part: percussion on 9; pitched parts share a channel per
    /// GM program so 18 band parts fit into 16 channels.
    public static func channels(for score: Score) -> [String: Int] {
        var byProgram: [Int: Int] = [:]
        var next = 0
        var out: [String: Int] = [:]
        for p in score.parts {
            if p.isPercussion { out[p.id] = 9; continue }
            let prog = p.midiProgram ?? 1
            if let c = byProgram[prog] { out[p.id] = c; continue }
            let c = next
            next += 1
            if next == 9 { next = 10 }
            if next > 15 { next = 15 }
            byProgram[prog] = c
            out[p.id] = c
        }
        return out
    }

    public static func data(for score: Score, options: Options = Options()) -> Data {
        let chans = channels(for: score)
        let parts = score.parts.filter { options.parts?.contains($0.id) ?? true }
        var tracks: [[UInt8]] = []

        // Tempo / meter track
        var t0 = TrackBuilder()
        t0.meta(0, type: 0x03, Array(score.title.utf8.prefix(120)))
        let mpq = Int((60_000_000 / score.tempoBPM).rounded())
        t0.meta(0, type: 0x51, [UInt8((mpq >> 16) & 0xFF), UInt8((mpq >> 8) & 0xFF), UInt8(mpq & 0xFF)])
        var lastMeter: (Int, Int)?
        for m in score.measures where lastMeter.map({ $0 != (m.beats, m.beatType) }) ?? true {
            let dd = UInt8(max(0, Int(log2(Double(m.beatType)))))
            t0.meta(m.startTick + options.leadInTicks, type: 0x58, [UInt8(m.beats), dd, 24, 8])
            lastMeter = (m.beats, m.beatType)
        }
        tracks.append(t0.finish())

        for p in parts {
            var tb = TrackBuilder()
            let ch = UInt8(chans[p.id] ?? 0)
            tb.meta(0, type: 0x03, Array(p.name.utf8))
            if !p.isPercussion { tb.event(0, [0xC0 | ch, UInt8(max(0, min(127, (p.midiProgram ?? 1) - 1)))]) }
            var events: [(Int, [UInt8])] = []
            for n in p.playbackNotes {
                let pitch = p.isPercussion ? n.pitch : n.pitch + options.transposeSemitones
                guard (0...127).contains(pitch) else { continue }
                let s = n.startTick + options.leadInTicks
                events.append((s, [0x90 | ch, UInt8(pitch), UInt8(n.velocity)]))
                events.append((s + n.durTicks, [0x80 | ch, UInt8(pitch), 0]))
            }
            // note-offs before note-ons at the same tick so repeated notes retrigger
            events.sort { $0.0 != $1.0 ? $0.0 < $1.0 : ($0.1[0] & 0xF0) < ($1.1[0] & 0xF0) }
            for (t, e) in events { tb.event(t, e) }
            tracks.append(tb.finish())
        }

        if options.includeMetronome {
            var tb = TrackBuilder()
            tb.meta(0, type: 0x03, Array("Metronome".utf8))
            for m in score.measures {
                for b in 0..<m.beats {
                    let t = m.startTick + b * m.beatTicks + options.leadInTicks
                    let key = UInt8(b == 0 ? metronomeHigh : metronomeLow)
                    tb.event(t, [0x99, key, b == 0 ? 110 : 80])
                    tb.event(t + m.beatTicks / 4, [0x89, key, 0])
                }
            }
            tracks.append(tb.finish())
        }

        var out: [UInt8] = Array("MThd".utf8) + be32(6) + be16(1) + be16(tracks.count) + be16(Score.ticksPerQuarter)
        for t in tracks { out += Array("MTrk".utf8) + be32(t.count) + t }
        return Data(out)
    }
}

private struct TrackBuilder {
    var bytes: [UInt8] = []
    var last = 0

    mutating func delta(_ t: Int) {
        let d = max(0, t - last)
        last = max(last, t)
        bytes += vlq(d)
    }

    mutating func event(_ t: Int, _ e: [UInt8]) { delta(t); bytes += e }

    mutating func meta(_ t: Int, type: UInt8, _ payload: [UInt8]) {
        delta(t); bytes += [0xFF, type] + vlq(payload.count) + payload
    }

    mutating func finish() -> [UInt8] { bytes + [0x00, 0xFF, 0x2F, 0x00] }
}

private func vlq(_ v: Int) -> [UInt8] {
    var v = v
    var out: [UInt8] = [UInt8(v & 0x7F)]
    v >>= 7
    while v > 0 { out.insert(UInt8(v & 0x7F) | 0x80, at: 0); v >>= 7 }
    return out
}

private func be32(_ v: Int) -> [UInt8] { [UInt8((v >> 24) & 0xFF), UInt8((v >> 16) & 0xFF), UInt8((v >> 8) & 0xFF), UInt8(v & 0xFF)] }
private func be16(_ v: Int) -> [UInt8] { [UInt8((v >> 8) & 0xFF), UInt8(v & 0xFF)] }

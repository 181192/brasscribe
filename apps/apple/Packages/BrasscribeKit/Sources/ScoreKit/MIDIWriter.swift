import Foundation

/// One note event ready for playback or export: concert pitch, tie chains merged, velocity from the
/// score's dynamics (`Dynamics`).
public struct PlaybackNote: Sendable, Equatable {
    public var pitch: Int
    public var startTick: Int
    public var durTicks: Int
    public var velocity: Int
}

public extension Part {
    /// Ticks of one trill note: alphaTab's 32nds, so every player trills at the same rate.
    static let trillTicks = Score.ticksPerQuarter / 8

    /// Notes to sound, with tied notes merged into one and rests dropped. As alphaTab plays them: a staccato
    /// note sounds half its value (and its tie is not followed), and a trill alternates the note and its written
    /// auxiliary in 32nds over the whole tie chain, starting on the note.
    var playbackNotes: [PlaybackNote] {
        var out: [PlaybackNote] = []
        var trills: [Int: Int] = [:] // index in out -> semitones to the auxiliary
        var open: [Int: Int] = [:] // pitch -> index in out of a note awaiting a tie stop
        for n in notes.sorted(by: { $0.startTick < $1.startTick }) {
            guard let p = n.midiPitch, n.durTicks > 0 else { continue }
            if n.tieStop, let i = open[p], out[i].startTick + out[i].durTicks == n.startTick {
                out[i].durTicks += n.durTicks
                if !n.tieStart { open[p] = nil }
                continue
            }
            if n.staccato {
                out.append(PlaybackNote(pitch: p, startTick: n.startTick, durTicks: max(1, n.durTicks / 2), velocity: n.velocity))
                open[p] = nil
                continue
            }
            out.append(PlaybackNote(pitch: p, startTick: n.startTick, durTicks: n.durTicks, velocity: n.velocity))
            if n.trill != 0 && !isPercussion { trills[out.count - 1] = n.trill }
            if n.tieStart { open[p] = out.count - 1 } else { open[p] = nil }
        }
        guard !trills.isEmpty else { return out }
        var expanded: [PlaybackNote] = []
        for (i, n) in out.enumerated() {
            guard let up = trills[i] else { expanded.append(n); continue }
            var tick = n.startTick, main = true
            let end = n.startTick + n.durTicks
            // alphaTab's loop: a last piece of 10 ticks or less is not played
            while tick + 10 < end {
                let len = min(Self.trillTicks, end - tick)
                expanded.append(PlaybackNote(pitch: main ? n.pitch : n.pitch + up, startTick: tick, durTicks: len, velocity: n.velocity))
                main.toggle()
                tick += len
            }
        }
        return expanded
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
        /// Maps each note's velocity for a particular synth (velocity, percussion part); nil writes the
        /// score's velocities, as a MIDI file should.
        public var velocityMap: (@Sendable (Int, Bool) -> Int)?
        /// The group of each drum of a percussion part, by key, for a player that levels the kit on one sampler per
        /// group: the part's track keeps its first group, and every other group gets a track of its own after the
        /// metronome's (`drumGroupTracks`). Nil writes one track per part, as a MIDI file should.
        public var drumGroup: (@Sendable (Int) -> Int)?
        public init(parts: Set<String>? = nil, transposeSemitones: Int = 0, includeMetronome: Bool = false, leadInTicks: Int = 0,
                    velocityMap: (@Sendable (Int, Bool) -> Int)? = nil, drumGroup: (@Sendable (Int) -> Int)? = nil) {
            self.parts = parts; self.transposeSemitones = transposeSemitones
            self.includeMetronome = includeMetronome; self.leadInTicks = leadInTicks
            self.velocityMap = velocityMap
            self.drumGroup = drumGroup
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

    /// The drum groups of each percussion part (`Options.drumGroup`), in order: the first plays on the part's own
    /// track, the others on tracks after the metronome's.
    public static func drumGroups(for score: Score, options: Options) -> [String: [Int]] {
        guard let group = options.drumGroup else { return [:] }
        var out: [String: [Int]] = [:]
        for p in score.parts where p.isPercussion && (options.parts?.contains(p.id) ?? true) {
            out[p.id] = Set(p.playbackNotes.map { group($0.pitch) }).sorted()
        }
        return out
    }

    /// The extra drum-group tracks `data` writes after the metronome's, in order: (part id, group).
    public static func drumGroupTracks(for score: Score, options: Options) -> [(part: String, group: Int)] {
        let groups = drumGroups(for: score, options: options)
        return score.parts.filter { groups[$0.id] != nil }.flatMap { p in groups[p.id]!.dropFirst().map { (p.id, $0) } }
    }

    public static func data(for score: Score, options: Options = Options()) -> Data {
        let chans = channels(for: score)
        let parts = score.parts.filter { options.parts?.contains($0.id) ?? true }
        let groups = drumGroups(for: score, options: options)
        var tracks: [[UInt8]] = []

        // Tempo / meter track
        var t0 = TrackBuilder()
        t0.meta(0, type: 0x03, Array(score.title.utf8.prefix(120)))
        var meta: [(Int, UInt8, [UInt8])] = []
        for t in score.tempos {
            let mpq = Int((60_000_000 / t.bpm).rounded())
            meta.append((t.tick == 0 ? 0 : t.tick + options.leadInTicks, 0x51,
                         [UInt8((mpq >> 16) & 0xFF), UInt8((mpq >> 8) & 0xFF), UInt8(mpq & 0xFF)]))
        }
        var lastMeter: (Int, Int)?
        for m in score.measures where lastMeter.map({ $0 != (m.beats, m.beatType) }) ?? true {
            let dd = UInt8(max(0, Int(log2(Double(m.beatType)))))
            meta.append((m.startTick + options.leadInTicks, 0x58, [UInt8(m.beats), dd, 24, 8]))
            lastMeter = (m.beats, m.beatType)
        }
        for (t, type, payload) in meta.sorted(by: { $0.0 < $1.0 }) { t0.meta(t, type: type, payload) }
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
                let v = max(1, min(127, options.velocityMap?(n.velocity, p.isPercussion) ?? n.velocity))
                if p.isPercussion, let g = options.drumGroup?(pitch), g != groups[p.id]?.first { continue }
                events.append((s, [0x90 | ch, UInt8(pitch), UInt8(v)]))
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

        for (id, g) in drumGroupTracks(for: score, options: options) {
            guard let p = score.parts.first(where: { $0.id == id }), let group = options.drumGroup else { continue }
            var tb = TrackBuilder()
            let ch = UInt8(chans[p.id] ?? 9)
            tb.meta(0, type: 0x03, Array("\(p.name) \(g)".utf8))
            var events: [(Int, [UInt8])] = []
            for n in p.playbackNotes where group(n.pitch) == g && (0...127).contains(n.pitch) {
                let s = n.startTick + options.leadInTicks
                let v = max(1, min(127, options.velocityMap?(n.velocity, true) ?? n.velocity))
                events.append((s, [0x90 | ch, UInt8(n.pitch), UInt8(v)]))
                events.append((s + n.durTicks, [0x80 | ch, UInt8(n.pitch), 0]))
            }
            events.sort { $0.0 != $1.0 ? $0.0 < $1.0 : ($0.1[0] & 0xF0) < ($1.1[0] & 0xF0) }
            for (t, e) in events { tb.event(t, e) }
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

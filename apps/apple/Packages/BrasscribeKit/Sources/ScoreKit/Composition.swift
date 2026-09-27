import Foundation

/// The canonical symbolic score produced by transcription, at concert pitch in integer
/// ticks. Mirrors `brasscribe_music.score_model.Composition` and the engine's
/// `Composition` schema field for field, so the same JSON decodes on every platform.
public struct Composition: Codable, Sendable, Equatable {
    public enum VoiceRole: String, Codable, Sendable {
        case melody, countermelody, harmony, bass, rhythm
    }

    public struct Note: Codable, Sendable, Equatable {
        public var pitch: Int
        public var start: Int
        public var dur: Int
        public var confidence: Double
        public var sources: [String]
        public var onsetS: Double?
        public var offsetS: Double?
        /// Performed length in ticks, when known (notated `dur` may be shorter or longer).
        public var performedDur: Int?
        /// `staccato`, `tenuto`, `accent` …
        public var articulations: [String]

        public var end: Int { start + dur }

        enum CodingKeys: String, CodingKey {
            case pitch, start, dur, confidence, sources, articulations
            case onsetS = "onset_s"
            case offsetS = "offset_s"
            case performedDur = "performed_dur"
        }

        public init(pitch: Int, start: Int, dur: Int, confidence: Double = 1, sources: [String] = [],
                    onsetS: Double? = nil, offsetS: Double? = nil) {
            self.pitch = pitch; self.start = start; self.dur = dur; self.confidence = confidence
            self.sources = sources; self.onsetS = onsetS; self.offsetS = offsetS
            self.performedDur = nil; self.articulations = []
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            pitch = try c.decode(Int.self, forKey: .pitch)
            start = try c.decode(Int.self, forKey: .start)
            dur = try c.decode(Int.self, forKey: .dur)
            confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 1
            sources = try c.decodeIfPresent([String].self, forKey: .sources) ?? []
            onsetS = try c.decodeIfPresent(Double.self, forKey: .onsetS)
            offsetS = try c.decodeIfPresent(Double.self, forKey: .offsetS)
            performedDur = try c.decodeIfPresent(Int.self, forKey: .performedDur)
            articulations = try c.decodeIfPresent([String].self, forKey: .articulations) ?? []
        }
    }

    public struct Voice: Codable, Sendable, Equatable, Identifiable {
        public var id: String
        public var role: VoiceRole
        public var notes: [Note]
        public var instrumentHint: String?
        public var layer: String?

        enum CodingKeys: String, CodingKey {
            case id, role, notes, layer
            case instrumentHint = "instrument_hint"
        }
    }

    public struct Meter: Codable, Sendable, Equatable {
        public var tick: Int
        public var beats: Int
        public var beatUnit: Int
        enum CodingKeys: String, CodingKey { case tick, beats; case beatUnit = "beat_unit" }
        public init(tick: Int, beats: Int, beatUnit: Int = 4) { self.tick = tick; self.beats = beats; self.beatUnit = beatUnit }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            tick = try c.decode(Int.self, forKey: .tick)
            beats = try c.decode(Int.self, forKey: .beats)
            beatUnit = try c.decodeIfPresent(Int.self, forKey: .beatUnit) ?? 4
        }
    }

    public struct KeySig: Codable, Sendable, Equatable {
        public var tick: Int
        public var fifths: Int
        public var mode: String
    }

    /// A passage in free time (ad lib.): no beat grid was imposed on it.
    public struct FreeRegion: Codable, Sendable, Equatable {
        public var start: Int
        public var end: Int
        public var startS: Double
        public var endS: Double
        public var tempoBPM: Double
        public var notation: String
        public var label: String
        enum CodingKeys: String, CodingKey {
            case start, end, notation, label
            case startS = "start_s", endS = "end_s", tempoBPM = "tempo_bpm"
        }
    }

    public struct Dynamic: Codable, Sendable, Equatable {
        public var tick: Int
        public var layer: String
        public var mark: String
    }

    public struct Section: Codable, Sendable, Equatable {
        public var tick: Int
        public var label: String
    }

    public var title: String
    public var voices: [Voice]
    public var meters: [Meter]
    public var keys: [KeySig]
    public var beatTimes: [Double]
    public var firstDownbeat: Int
    public var ticksPerBeat: Int
    public var freeRegions: [FreeRegion]
    public var dynamics: [Dynamic]
    public var sections: [Section]
    /// Neighbouring uncertain notes of one voice, reviewed together (music/README.md,
    /// "Confidence and review marks"). Empty when the engine didn't group them.
    public var review: [ReviewGroup]

    public struct ReviewGroup: Codable, Sendable, Equatable {
        public var voice: String
        /// `[start, end)` in Composition ticks.
        public var start: Int
        public var end: Int
        /// Marked notes in the group.
        public var notes: Int
        /// Any of them very unsure.
        public var very: Bool
        public init(voice: String, start: Int, end: Int, notes: Int, very: Bool) {
            self.voice = voice; self.start = start; self.end = end; self.notes = notes; self.very = very
        }
    }

    enum CodingKeys: String, CodingKey {
        case title, voices, meters, keys, dynamics, sections, review
        case freeRegions = "free_regions"
        case beatTimes = "beat_times"
        case firstDownbeat = "first_downbeat"
        case ticksPerBeat = "ticks_per_beat"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try c.decode(String.self, forKey: .title)
        voices = try c.decode([Voice].self, forKey: .voices)
        meters = try c.decode([Meter].self, forKey: .meters)
        keys = try c.decode([KeySig].self, forKey: .keys)
        beatTimes = try c.decodeIfPresent([Double].self, forKey: .beatTimes) ?? []
        firstDownbeat = try c.decodeIfPresent(Int.self, forKey: .firstDownbeat) ?? 0
        ticksPerBeat = try c.decodeIfPresent(Int.self, forKey: .ticksPerBeat) ?? 24
        freeRegions = try c.decodeIfPresent([FreeRegion].self, forKey: .freeRegions) ?? []
        dynamics = try c.decodeIfPresent([Dynamic].self, forKey: .dynamics) ?? []
        sections = try c.decodeIfPresent([Section].self, forKey: .sections) ?? []
        review = try c.decodeIfPresent([ReviewGroup].self, forKey: .review) ?? []
    }

    public static func decode(_ data: Data) throws -> Composition {
        try JSONDecoder().decode(Composition.self, from: data)
    }

    public var endTick: Int { voices.flatMap(\.notes).map(\.end).max() ?? 0 }

    /// Median-interval tempo, like the Python reference.
    public var bpm: Double {
        guard beatTimes.count >= 2 else { return 120 }
        let diffs = zip(beatTimes.dropFirst(), beatTimes).map { $0 - $1 }.sorted()
        return 60 / diffs[diffs.count / 2]
    }

    public var tempoMap: TempoMap { TempoMap(composition: self) }
}

/// Maps score ticks to seconds in the original recording and back, using the beat times
/// the transcription found. Beats before the first or after the last detected beat are
/// extrapolated at the median beat length. This is what keeps "original vs score" and a
/// synced video at the same musical position even when the performance is not metronomic.
public struct TempoMap: Sendable, Equatable {
    public let beatTimes: [Double]
    public let firstDownbeat: Int
    public let ticksPerBeat: Int
    let medianBeat: Double

    public init(beatTimes: [Double], firstDownbeat: Int, ticksPerBeat: Int) {
        self.beatTimes = beatTimes
        self.firstDownbeat = firstDownbeat
        self.ticksPerBeat = ticksPerBeat
        if beatTimes.count >= 2 {
            let d = zip(beatTimes.dropFirst(), beatTimes).map { $0 - $1 }.sorted()
            medianBeat = d[d.count / 2]
        } else {
            medianBeat = 0.5
        }
    }

    public init(composition c: Composition) {
        self.init(beatTimes: c.beatTimes, firstDownbeat: c.firstDownbeat, ticksPerBeat: c.ticksPerBeat)
    }

    /// Seconds in the recording at a beat position counted from tick 0 (beat 0 = first downbeat).
    public func seconds(atBeat beat: Double) -> Double {
        guard !beatTimes.isEmpty else { return beat * medianBeat }
        let idx = beat + Double(firstDownbeat)
        if idx <= 0 { return beatTimes[0] + idx * medianBeat }
        let last = Double(beatTimes.count - 1)
        if idx >= last { return beatTimes[beatTimes.count - 1] + (idx - last) * medianBeat }
        let i = Int(idx.rounded(.down))
        let f = idx - Double(i)
        return beatTimes[i] + f * (beatTimes[i + 1] - beatTimes[i])
    }

    public func seconds(atTick tick: Int) -> Double { seconds(atBeat: Double(tick) / Double(ticksPerBeat)) }

    /// Inverse of `seconds(atBeat:)`.
    public func beat(atSeconds s: Double) -> Double {
        guard !beatTimes.isEmpty else { return s / medianBeat }
        let idx: Double
        if s <= beatTimes[0] {
            idx = (s - beatTimes[0]) / medianBeat
        } else if s >= beatTimes[beatTimes.count - 1] {
            idx = Double(beatTimes.count - 1) + (s - beatTimes[beatTimes.count - 1]) / medianBeat
        } else {
            var lo = 0, hi = beatTimes.count - 1
            while hi - lo > 1 {
                let mid = (lo + hi) / 2
                if beatTimes[mid] <= s { lo = mid } else { hi = mid }
            }
            idx = Double(lo) + (s - beatTimes[lo]) / (beatTimes[lo + 1] - beatTimes[lo])
        }
        return idx - Double(firstDownbeat)
    }
}

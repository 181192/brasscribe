using System.Text.Json;
using System.Text.Json.Serialization;

namespace Brasscribe.Play.Core.Scores;

/// <summary>
/// The canonical score (brasscribe_music.score_model.Composition): concert pitch, integer ticks.
/// Field names follow the JSON contract in music/README.md. Unknown fields are kept in
/// <see cref="Extra"/> so a round trip does not drop data written by a newer engine.
/// </summary>
public sealed class Composition
{
    public const int DefaultTicksPerBeat = 24;

    public required string Title { get; set; }
    public List<Voice> Voices { get; set; } = [];
    public List<Meter> Meters { get; set; } = [];
    public List<KeySig> Keys { get; set; } = [];
    /// <summary>Seconds of beat 0, 1, 2 ... (the tempo map).</summary>
    public List<double> BeatTimes { get; set; } = [];
    /// <summary>Index into <see cref="BeatTimes"/> of tick 0.</summary>
    public int FirstDownbeat { get; set; }
    public int TicksPerBeat { get; set; } = DefaultTicksPerBeat;
    /// <summary>Free-time (ad lib.) passages; empty in files written before free-time detection.</summary>
    public List<FreeRegion> FreeRegions { get; set; } = [];
    /// <summary>
    /// Neighbouring uncertain notes of one voice, reviewed together (music/README.md, Confidence and
    /// review marks); null in files written before review groups.
    /// </summary>
    public List<ReviewSpan>? Review { get; set; }

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; set; }

    [JsonIgnore]
    public int EndTick => Voices.SelectMany(v => v.Notes).Select(n => n.End).DefaultIfEmpty(0).Max();

    /// <summary>Median tempo of the beat map, 120 when there is no map (matches the Python reference).</summary>
    [JsonIgnore]
    public double Bpm
    {
        get
        {
            if (BeatTimes.Count < 2) return 120.0;
            var diffs = BeatTimes.Zip(BeatTimes.Skip(1), (a, b) => b - a).Order().ToList();
            return 60.0 / diffs[diffs.Count / 2];
        }
    }

    public IEnumerable<Voice> VoicesWith(VoiceRole role) => Voices.Where(v => v.Role == role);

    /// <summary>Seconds of a tick through the piecewise-linear beat map (extrapolates at both ends).</summary>
    public double SecondsAt(double tick)
    {
        double beat = FirstDownbeat + tick / TicksPerBeat;
        if (BeatTimes.Count == 0) return beat * 60.0 / 120.0;
        if (BeatTimes.Count == 1) return BeatTimes[0] + (beat) * 0.5;
        int i = (int)Math.Floor(beat);
        i = Math.Clamp(i, 0, BeatTimes.Count - 2);
        double frac = beat - i;
        return BeatTimes[i] + frac * (BeatTimes[i + 1] - BeatTimes[i]);
    }

    /// <summary>Tick of a time in seconds (inverse of <see cref="SecondsAt"/>).</summary>
    public double TickAt(double seconds)
    {
        if (BeatTimes.Count < 2) return (seconds * 2.0 - FirstDownbeat) * TicksPerBeat;
        int i = 0;
        while (i < BeatTimes.Count - 2 && BeatTimes[i + 1] <= seconds) i++;
        double span = BeatTimes[i + 1] - BeatTimes[i];
        double beat = i + (span > 0 ? (seconds - BeatTimes[i]) / span : 0);
        return (beat - FirstDownbeat) * TicksPerBeat;
    }

    public FreeRegion? FreeRegionAt(int tick) => FreeRegions.FirstOrDefault(r => tick >= r.Start && tick < r.End);
}

[JsonConverter(typeof(JsonStringEnumConverter<VoiceRole>))]
public enum VoiceRole
{
    [JsonStringEnumMemberName("melody")] Melody,
    [JsonStringEnumMemberName("countermelody")] Countermelody,
    [JsonStringEnumMemberName("harmony")] Harmony,
    [JsonStringEnumMemberName("bass")] Bass,
    [JsonStringEnumMemberName("rhythm")] Rhythm,
}

public sealed class Voice
{
    public required string Id { get; set; }
    public VoiceRole Role { get; set; }
    public List<Note> Notes { get; set; } = [];
    /// <summary>What the source instrument seemed to be; never binding.</summary>
    public string? InstrumentHint { get; set; }
    /// <summary>Textural layer: solo, strings, brass, keys, bass, drums.</summary>
    public string? Layer { get; set; }

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; set; }
}

public sealed class Note
{
    /// <summary>Uncertainty thresholds shared with the talking score and the review colours.</summary>
    public const double UncertainBelow = 0.7;
    public const double VeryUncertainBelow = 0.4;

    /// <summary>Concert MIDI pitch (GM drum number in a drums layer).</summary>
    public int Pitch { get; set; }
    /// <summary>Ticks from the first downbeat (negative in a pickup).</summary>
    public int Start { get; set; }
    /// <summary>Written duration in ticks.</summary>
    public int Dur { get; set; }
    public double Confidence { get; set; } = 1.0;
    public List<string> Sources { get; set; } = [];
    public double? OnsetS { get; set; }
    public double? OffsetS { get; set; }
    /// <summary>Performed length in ticks, null when unknown.</summary>
    public int? PerformedDur { get; set; }
    /// <summary>staccato, fermata.</summary>
    public List<string> Articulations { get; set; } = [];

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; set; }

    [JsonIgnore] public int End => Start + Dur;
    [JsonIgnore] public Certainty Certainty => CertaintyOf(Confidence);

    public static Certainty CertaintyOf(double confidence) =>
        confidence < VeryUncertainBelow ? Certainty.VeryUncertain
        : confidence < UncertainBelow ? Certainty.Uncertain
        : Certainty.Confident;
}

public enum Certainty { Confident, Uncertain, VeryUncertain }

public sealed class Meter
{
    public int Tick { get; set; }
    public int Beats { get; set; }
    public int BeatUnit { get; set; } = 4;
}

public sealed class KeySig
{
    public int Tick { get; set; }
    public int Fifths { get; set; }
    public string Mode { get; set; } = "major";
}

/// <summary>A passage in free time (ad lib., colla voce) where no beat grid is imposed.</summary>
public sealed class FreeRegion
{
    public int Start { get; set; }
    public int End { get; set; }
    public double StartS { get; set; }
    public double EndS { get; set; }
    public double TempoBpm { get; set; }
    /// <summary>proportional or tempo.</summary>
    public string Notation { get; set; } = "proportional";
    public string Label { get; set; } = "ad lib.";
}

/// <summary>One review group: marked notes of <see cref="Voice"/> in ticks [Start, End), <see cref="Very"/> when any is very unsure.</summary>
public sealed class ReviewSpan
{
    public required string Voice { get; set; }
    public int Start { get; set; }
    public int End { get; set; }
    public int Notes { get; set; }
    public bool Very { get; set; }
}

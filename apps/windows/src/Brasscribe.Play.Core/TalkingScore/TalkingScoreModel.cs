using System.Text.Json.Serialization;

namespace Brasscribe.Play.Core.TalkingScore;

// The TalkingScore JSON shape (docs/accessibility/talking-score-spec.md §6). The same types read
// the conformance vectors, so names follow that document exactly (snake_case on the wire).

public sealed record TsPitch(string Step, int Alter, int Octave);

/// <summary>Exact position inside a bar: beat number (1-based) plus num/den of a beat.</summary>
public sealed record TsPos(int Beat, int Num = 0, int Den = 1)
{
    public bool OnBeat => Num == 0;
}

public sealed record TsTieNext(int Bar, string Type, int Dots = 0);

public sealed record TsTie(bool Start = false, bool Stop = false, TsTieNext? Next = null, double? ChainBeats = null);

public sealed record TsTuplet(int Actual, int Normal, int Index);

public sealed record TsHeldFrom(int Bar, int Beat, int Num = 0, int Den = 1);

public sealed record TsChordPitch(TsPitch Written, TsPitch Concert);

public sealed record TsTime(int Beats, int BeatType);

public sealed record TsTranspose(int Chromatic, int Diatonic = 0, int Octave = 0);

public static class EventKind
{
    public const string Note = "note";
    public const string Rest = "rest";
    public const string BarRest = "bar-rest";
    public const string Chord = "chord";
    public const string Unpitched = "unpitched";
    public const string Held = "held";
    public const string ModeChange = "mode-change";
}

public sealed class TsEvent
{
    public string Kind { get; set; } = EventKind.Note;
    /// <summary>Ticks from the start of the bar (MusicXML divisions scaled to 24 per quarter).</summary>
    public int Tick { get; set; }
    public int MusicXmlNoteIndex { get; set; } = -1;
    [JsonIgnore] public string? CompositionVoiceId { get; set; }
    [JsonIgnore] public int? CompositionNoteStart { get; set; }
    /// <summary>Written length in ticks; not announced, used by navigation and highlighting.</summary>
    public int DurTicks { get; set; }
    public TsPos? Pos { get; set; }
    public string? Type { get; set; }
    public int Dots { get; set; }
    public TsTuplet? Tuplet { get; set; }
    public TsTie? Tie { get; set; }
    public TsPitch? Written { get; set; }
    public TsPitch? Concert { get; set; }
    public List<TsChordPitch>? Pitches { get; set; }
    public List<string>? Instruments { get; set; }
    public List<string>? InstrumentsNb { get; set; }
    public List<string> Articulations { get; set; } = [];
    public string? Dynamic { get; set; }
    public double? Confidence { get; set; }
    public List<string> Sources { get; set; } = [];
    public bool Checked { get; set; }
    public double? TimeS { get; set; }
    public double? PerformedS { get; set; }
    /// <summary>bar-rest: how many bars the rest covers.</summary>
    public int Bars { get; set; } = 1;
    public TsHeldFrom? HeldFrom { get; set; }

    [JsonIgnore]
    public bool IsUncertain => !Checked && Confidence is < Scores.Note.UncertainBelow;
}

public sealed class TsBar
{
    public int Number { get; set; }
    public int KeyFifths { get; set; }
    public TsTime Time { get; set; } = new(4, 4);
    public double? TempoBpm { get; set; }
    public string? Rehearsal { get; set; }
    public List<TsEvent> Events { get; set; } = [];
}

public sealed class TsPart
{
    public required string Id { get; set; }
    public required string Name { get; set; }
    public string? NameNb { get; set; }
    public string? Instrument { get; set; }
    public string? InstrumentNb { get; set; }
    public TsTranspose Transpose { get; set; } = new(0);
    public bool Percussion { get; set; }
    public List<TsBar> Bars { get; set; } = [];
}

public sealed class TsFreeRegion
{
    public int StartBar { get; set; }
    public int EndBar { get; set; }
    public double StartS { get; set; }
    public double EndS { get; set; }
    public double TempoBpm { get; set; }
    public string Notation { get; set; } = "proportional";
    public string Label { get; set; } = "ad lib.";
}

public sealed class TalkingScoreDocument
{
    public int Version { get; set; } = 1;
    public string Title { get; set; } = "";
    public int TotalBars { get; set; }
    public List<TsFreeRegion> FreeRegions { get; set; } = [];
    public List<TsPart> Parts { get; set; } = [];

    public TsFreeRegion? RegionAt(int bar) => FreeRegions.FirstOrDefault(r => bar >= r.StartBar && bar <= r.EndBar);
}

public enum Verbosity { Brief, Standard, Full }

public enum PitchMode { Written, Concert }

public enum OctaveStyle { Scientific, Helmholtz }

public sealed record TalkingScoreSettings(
    string Lang = "en",
    PitchMode PitchMode = PitchMode.Written,
    Verbosity Verbosity = Verbosity.Standard,
    OctaveStyle OctaveStyle = OctaveStyle.Scientific,
    bool AnnounceConfident = false)
{
    public bool Nb => Lang.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || Lang.StartsWith("no", StringComparison.OrdinalIgnoreCase);
}

/// <summary>What the previous announcement left behind; decides which parts get repeated.</summary>
public sealed record AnnounceContext(string? Part = null, int? Bar = null, PitchMode? PitchMode = null);

/// <summary>What an announcement is about, beyond the event itself.</summary>
public sealed record AnnounceBar(
    int Number,
    int KeyFifths,
    bool KeyChanged = false,
    TsTime? TimeChanged = null,
    double? TempoMarked = null,
    string? Rehearsal = null,
    TsFreeRegion? FreeRegion = null,
    bool EnteringRegion = false,
    bool ATempo = false,
    int TotalBars = 0);

public sealed record AnnouncePart(string Name, string? NameNb = null, string? Instrument = null, string? InstrumentNb = null,
    TsTranspose? Transpose = null);

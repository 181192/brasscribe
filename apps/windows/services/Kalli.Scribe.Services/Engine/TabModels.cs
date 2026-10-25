// The records document only the parameters that need it.
#pragma warning disable CS1573

using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Kalli.Scribe.Engine;

// The tab profile (and bass-tab, its id for a bass in older apps): the job's options and its result
// (GET /v1/jobs/{id}/tab, the engine's schemas.Tab). OpenApiContractTests checks the fields, their nullability
// and the enums against the vendored spec.

/// <summary>The profile ids that write a tab.</summary>
public static class TabProfiles
{
    /// <summary>One fretted instrument as tablature (bass, guitar, ukulele, mandolin).</summary>
    public const string Tab = "tab";

    /// <summary><see cref="Tab"/> with a bass, under the id older apps sent: jobs made by them still carry it.</summary>
    public const string BassTab = "bass-tab";

    /// <summary>The profile <paramref name="id"/> names writes a tab.</summary>
    public static bool WritesTab(string? id) => id is Tab or BassTab;
}

/// <summary>
/// The ids of a string enum of the API, read from <see cref="JsonStringEnumMemberNameAttribute"/> on its members.
/// The member without one (Unknown, the default) stands in for a value this client does not know and is never sent.
/// </summary>
public static class WireEnum<TEnum> where TEnum : struct, Enum
{
    private static readonly Dictionary<TEnum, string> Ids = typeof(TEnum).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(f => f.GetCustomAttribute<JsonStringEnumMemberNameAttribute>() is not null)
        .ToDictionary(f => (TEnum)f.GetValue(null)!, f => f.GetCustomAttribute<JsonStringEnumMemberNameAttribute>()!.Name);

    private static readonly Dictionary<string, TEnum> ById = Ids.ToDictionary(p => p.Value, p => p.Key);

    /// <summary>The members that are values of the API, in declaration order.</summary>
    public static IReadOnlyList<TEnum> Values { get; } = [.. Enum.GetValues<TEnum>().Where(Ids.ContainsKey)];

    /// <summary>What goes over the wire; null for the stand-in of an unknown value.</summary>
    public static string? IdOf(TEnum value) => Ids.GetValueOrDefault(value);

    /// <summary>The member <paramref name="id"/> names; the default (Unknown) for an id this client does not know.</summary>
    public static TEnum Of(string? id) => id is not null && ById.TryGetValue(id, out var v) ? v : default;

    /// <summary>The id to send; throws for the stand-in of an unknown value.</summary>
    public static string Wire(TEnum value) => IdOf(value) ?? throw new ArgumentException($"{value} is not a value to send", nameof(value));
}

/// <summary>Reads and writes a wire enum by its id. A value a newer engine added reads as Unknown instead of failing the whole answer.</summary>
public sealed class WireEnumConverter<TEnum> : JsonConverter<TEnum> where TEnum : struct, Enum
{
    public override TEnum Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        reader.TokenType == JsonTokenType.String ? WireEnum<TEnum>.Of(reader.GetString()) : default;

    public override void Write(Utf8JsonWriter writer, TEnum value, JsonSerializerOptions options) =>
        writer.WriteStringValue(WireEnum<TEnum>.Wire(value));
}

/// <summary>
/// The instrument a tab is written for. <see cref="FrettedInstruments"/> has the tunings the engine has for each
/// (its default first) and the preset ids of the core's <c>target-fretted</c> crate.
/// </summary>
[JsonConverter(typeof(WireEnumConverter<FrettedInstrument>))]
public enum FrettedInstrument
{
    Unknown,
    [JsonStringEnumMemberName("bass-4")] Bass4,
    [JsonStringEnumMemberName("bass-5")] Bass5,
    [JsonStringEnumMemberName("bass-6")] Bass6,
    [JsonStringEnumMemberName("guitar-6")] Guitar6,
    [JsonStringEnumMemberName("guitar-7")] Guitar7,
    [JsonStringEnumMemberName("guitar-8")] Guitar8,
    /// <summary>Soprano, concert and tenor: one tuning, with the fourth string high or low.</summary>
    [JsonStringEnumMemberName("ukulele")] Ukulele,
    [JsonStringEnumMemberName("ukulele-baritone")] UkuleleBaritone,
    [JsonStringEnumMemberName("mandolin")] Mandolin,
}

/// <summary>What each <see cref="FrettedInstrument"/> is: its tunings, its presets and how a job for it is taken.</summary>
public static class FrettedInstruments
{
    public const string StandardTuning = "standard";

    /// <summary>
    /// Family: the instrument's presets are "&lt;family&gt;-&lt;tuning&gt;", or the family alone for an instrument with
    /// one preset. AloneByDefault: the engine reads it from the guitar's part of a song (it can't tell the two apart
    /// there), so a job that does not say what was recorded is taken as the instrument alone.
    /// </summary>
    private sealed record Facts(IReadOnlyList<string> Tunings, string? Family, bool OnePreset = false, bool AloneByDefault = false);

    private static readonly Dictionary<FrettedInstrument, Facts> All = new()
    {
        [FrettedInstrument.Bass4] = new(["standard", "eb-standard", "d-standard", "drop-d", "bead"], "bass-4"),
        [FrettedInstrument.Bass5] = new(["standard", "drop-a"], "bass-5"),
        [FrettedInstrument.Bass6] = new(["standard"], "bass-6"),
        [FrettedInstrument.Guitar6] = new(["standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad",
            "open-g", "open-d", "open-e"], "guitar"),
        [FrettedInstrument.Guitar7] = new(["standard", "eb-standard"], "guitar-7"),
        [FrettedInstrument.Guitar8] = new(["standard"], "guitar-8"),
        [FrettedInstrument.Ukulele] = new(["high-g", "low-g"], "ukulele", AloneByDefault: true),
        [FrettedInstrument.UkuleleBaritone] = new(["standard"], "ukulele-baritone", OnePreset: true, AloneByDefault: true),
        [FrettedInstrument.Mandolin] = new(["standard"], "mandolin", OnePreset: true, AloneByDefault: true),
        [FrettedInstrument.Unknown] = new([], null),
    };

    /// <summary>The engine's id ("guitar-6"); null for <see cref="FrettedInstrument.Unknown"/>.</summary>
    public static string? Id(this FrettedInstrument kind) => WireEnum<FrettedInstrument>.IdOf(kind);

    /// <summary>The tunings the engine has for the instrument, its default first.</summary>
    public static IReadOnlyList<string> Tunings(this FrettedInstrument kind) => All[kind].Tunings;

    /// <summary>The tuning of a job that names none.</summary>
    public static string DefaultTuning(this FrettedInstrument kind) => kind.Tunings().FirstOrDefault() ?? StandardTuning;

    /// <summary>A bass: one line, and the only instruments the bass-tab profile takes.</summary>
    public static bool IsBass(this FrettedInstrument kind) => kind is FrettedInstrument.Bass4 or FrettedInstrument.Bass5 or FrettedInstrument.Bass6;

    /// <summary>A job that does not say what was recorded is taken as the instrument alone.</summary>
    public static bool AloneByDefault(this FrettedInstrument kind) => All[kind].AloneByDefault;

    /// <summary>What a job that does not say what was recorded is taken as.</summary>
    public static Recording DefaultRecording(this FrettedInstrument kind) => kind.AloneByDefault() ? Recording.Instrument : Recording.Song;

    /// <summary>The engine's preset id for this instrument in <paramref name="tuning"/>, as <see cref="TabResult.Preset"/> names it.</summary>
    public static string Preset(this FrettedInstrument kind, string? tuning = null)
    {
        var facts = All[kind];
        return facts.OnePreset ? facts.Family ?? "" : $"{facts.Family}-{tuning ?? kind.DefaultTuning()}";
    }

    /// <summary>The instrument and tuning a preset id names ("guitar-drop-d", "ukulele-baritone"); null for one this client does not know.</summary>
    public static (FrettedInstrument Kind, string Tuning)? OfPreset(string preset)
    {
        foreach (var kind in WireEnum<FrettedInstrument>.Values)
            foreach (var tuning in kind.Tunings())
                if (kind.Preset(tuning) == preset) return (kind, tuning);
        return null;
    }
}

/// <summary>Where the line sits on the neck.</summary>
[JsonConverter(typeof(WireEnumConverter<FingeringStyle>))]
public enum FingeringStyle
{
    Unknown,
    /// <summary>The cheapest playable fingering.</summary>
    [JsonStringEnumMemberName("as-played")] AsPlayed,
    /// <summary>Low frets and open strings.</summary>
    [JsonStringEnumMemberName("open-position")] OpenPosition,
    /// <summary>A phrase stays in one position.</summary>
    [JsonStringEnumMemberName("lead")] Lead,
}

/// <summary>What was recorded.</summary>
[JsonConverter(typeof(WireEnumConverter<Recording>))]
public enum Recording
{
    Unknown,
    /// <summary>A band or a record: the instrument is separated from it.</summary>
    [JsonStringEnumMemberName("song")] Song,
    /// <summary>The instrument alone: no separation.</summary>
    [JsonStringEnumMemberName("instrument")] Instrument,
}

/// <summary>The octave the notes are written in.</summary>
[JsonConverter(typeof(WireEnumConverter<Octave>))]
public enum Octave
{
    Unknown,
    /// <summary>An octave lower when the notes were heard an octave above where the instrument plays (a guitar: also higher when heard below it).</summary>
    [JsonStringEnumMemberName("auto")] Auto,
    /// <summary>As it was heard.</summary>
    [JsonStringEnumMemberName("0")] AsHeard,
    [JsonStringEnumMemberName("-12")] Down,
    [JsonStringEnumMemberName("+12")] Up,
}

/// <summary>What the page shows.</summary>
[JsonConverter(typeof(WireEnumConverter<TabLayout>))]
public enum TabLayout
{
    Unknown,
    /// <summary>The tab staff alone, with stems for the rhythm.</summary>
    [JsonStringEnumMemberName("tab")] Tab,
    /// <summary>A notation staff above the tab.</summary>
    [JsonStringEnumMemberName("tab-and-notation")] TabAndNotation,
    /// <summary>The notation staff alone.</summary>
    [JsonStringEnumMemberName("notation")] Notation,
}

/// <summary>What a chord holds. Not for a bass, whose line is one note at a time.</summary>
[JsonConverter(typeof(WireEnumConverter<TabChords>))]
public enum TabChords
{
    Unknown,
    /// <summary>The notes that were heard.</summary>
    [JsonStringEnumMemberName("heard")] Heard,
    /// <summary>Also a note the same chord has in the strums around it: marked <see cref="TabNote.Inferred"/>, with a "?".</summary>
    [JsonStringEnumMemberName("completed")] Completed,
}

/// <summary>The clef of an instrument's notation staff.</summary>
[JsonConverter(typeof(WireEnumConverter<NotationClef>))]
public enum NotationClef
{
    Unknown,
    /// <summary>Ukulele and mandolin.</summary>
    [JsonStringEnumMemberName("treble")] Treble,
    /// <summary>Guitar and baritone ukulele: written an octave above their sound.</summary>
    [JsonStringEnumMemberName("treble-8vb")] Treble8vb,
    /// <summary>Bass.</summary>
    [JsonStringEnumMemberName("bass-8vb")] Bass8vb,
}

/// <summary>Who decided <see cref="TabResult.OctaveShift"/>: the engine's octave check, or the job's octave option.</summary>
[JsonConverter(typeof(WireEnumConverter<OctaveSource>))]
public enum OctaveSource
{
    Unknown,
    [JsonStringEnumMemberName("auto")] Auto,
    [JsonStringEnumMemberName("chosen")] Chosen,
}

[JsonConverter(typeof(WireEnumConverter<KeyMode>))]
public enum KeyMode
{
    Unknown,
    [JsonStringEnumMemberName("major")] Major,
    [JsonStringEnumMemberName("minor")] Minor,
}

/// <summary>
/// The options of a tab job. One left null is not sent, and the engine uses its default: a six-string guitar (the
/// bass-tab profile: a four-string bass) in the instrument's first tuning with no capo, as played, separated from a
/// song (a ukulele or a mandolin: the instrument alone), the octave checked, the tab staff alone, the chords as heard.
/// </summary>
/// <param name="Tuning">One of the instrument's tunings.</param>
/// <param name="Capo">The capo's fret, 0 (none) to <see cref="MaxCapo"/>; frets in the tab are counted from it.</param>
/// <param name="Chords">Not for a bass: the engine refuses it there.</param>
public sealed record TabOptions(
    FrettedInstrument? Instrument = null,
    string? Tuning = null,
    int? Capo = null,
    FingeringStyle? Style = null,
    Recording? Recording = null,
    Octave? Octave = null,
    TabLayout? Layout = null,
    TabChords? Chords = null)
{
    public const int MaxCapo = 12;
}

public static class TabJobs
{
    /// <summary>
    /// <paramref name="request"/> with the tab options as the engine reads them: each option by its id, one left null
    /// not sent. Throws for an Unknown value, which is not one to send.
    /// </summary>
    public static JobCreate WithTab(this JobCreate request, TabOptions options) => request with
    {
        Instrument = Id(options.Instrument),
        Tuning = options.Tuning,
        Capo = options.Capo,
        Style = Id(options.Style),
        Recording = Id(options.Recording),
        Octave = Id(options.Octave),
        Layout = Id(options.Layout),
        Chords = Id(options.Chords),
    };

    /// <summary>A tab job for an uploaded recording, with the options the player chose.</summary>
    public static JobCreate Tab(string audioId, TabOptions? options = null, string? title = null) =>
        new JobCreate(audioId, TabProfiles.Tab, Title: title).WithTab(options ?? new TabOptions());

    private static string? Id<TEnum>(TEnum? value) where TEnum : struct, Enum => value is { } v ? WireEnum<TEnum>.Wire(v) : null;
}

/// <summary>A place on the neck.</summary>
/// <param name="String">1 is the highest line of the tab.</param>
/// <param name="Fret">Counted from the capo; 0 is the open string.</param>
public sealed record TabPosition(int String, int Fret);

/// <summary>One note of the tab: when it sounds, what was heard, and where it is played.</summary>
/// <param name="Pitch">Concert MIDI pitch, as written in the tab (after <see cref="TabResult.OctaveShift"/>).</param>
/// <param name="Start">Ticks from the first downbeat.</param>
/// <param name="Dur">Written duration in ticks.</param>
/// <param name="String">Null: the note has no place on the instrument.</param>
/// <param name="Alternatives">The other places that sound this pitch, cheapest first.</param>
/// <param name="OutOfRange">No string of the instrument sounds this pitch; the usual cause is another tuning or instrument than the player's.</param>
/// <param name="Confidence">0 to 1; below <see cref="Doubt"/> the note is one to check (the tab marks it "?").</param>
/// <param name="Pinned">The player chose this string.</param>
/// <param name="OctaveMoved">Written an octave below where the first transcriber heard it, where the second heard it. It gets no "?".</param>
/// <param name="Doubled">Heard once and written twice: a unison that a strummed open chord of a ukulele or a mandolin plays on two strings.</param>
/// <param name="Inferred">Not heard: added to its chord because the same chord around it has this note (<see cref="TabChords.Completed"/>).</param>
public sealed record TabNote(
    int Pitch,
    int Start,
    int Dur,
    int? String,
    IReadOnlyList<TabPosition> Alternatives,
    bool OutOfRange,
    int? Fret = null,
    double Confidence = 1.0,
    double? OnsetS = null,
    double? OffsetS = null,
    bool Pinned = false,
    bool OctaveMoved = false,
    bool Doubled = false,
    bool Inferred = false)
{
    public const double Doubt = 0.4;

    /// <summary>Where the note is played; null when it has no place on the instrument.</summary>
    [JsonIgnore]
    public TabPosition? Position => String is { } s && Fret is { } f ? new TabPosition(s, f) : null;

    /// <summary>One to check.</summary>
    [JsonIgnore]
    public bool Doubtful => Confidence < Doubt;
}

/// <param name="OpenPitch">MIDI pitch of the open string, without the capo.</param>
/// <param name="FirstFret">Where a short string starts (a banjo's fifth string); 0: at the nut.</param>
public sealed record TabString(int OpenPitch, int FirstFret = 0);

/// <param name="Name">Display name, e.g. Drop D.</param>
/// <param name="Strings">String 1 first.</param>
public sealed record TabTuning(string Name, IReadOnlyList<TabString> Strings);

/// <param name="Notation">The clef of the instrument's notation staff; null from an engine that does not say.</param>
public sealed record TabInstrument(string Name, TabTuning Tuning, int Frets, double ScaleLengthMm, int Capo = 0, NotationClef? Notation = null);

/// <summary>
/// A hard playability violation. Kind is shared-string, span-too-wide, fret-out-of-range, wrong-pitch,
/// pin-not-honoured, no-string, technique-string, technique-reach, bend-on-open-string or ring-cut; the other
/// fields depend on it (the engine's schema names only Kind) and name notes by their index in <see cref="TabResult.Notes"/>.
/// </summary>
/// <param name="Previous">The note a technique comes from.</param>
/// <param name="Frets">How far a technique reaches, in frets.</param>
/// <param name="Ringing">The let-ring note that still holds the string.</param>
public sealed record TabViolation(
    string Kind,
    int? Note = null,
    IReadOnlyList<int>? Notes = null,
    int? String = null,
    int? Fret = null,
    int? Previous = null,
    int? Frets = null,
    double? SpanMm = null,
    int? Ringing = null)
{
    /// <summary>Every note the violation names, as indices into <see cref="TabResult.Notes"/>.</summary>
    [JsonIgnore]
    public IReadOnlyList<int> NoteIndices =>
        [.. new[] { Note, Previous, Ringing }.OfType<int>().Concat(Notes ?? []).Distinct().Order()];
}

/// <summary>How well one tuning of the instrument fits the notes.</summary>
/// <param name="Preset">A preset id, e.g. bass-4-drop-d (<see cref="FrettedInstruments.OfPreset"/>).</param>
/// <param name="Tuning">Display name, e.g. Drop D.</param>
/// <param name="OutOfRange">Notes no string can sound.</param>
/// <param name="LowStringFits">The lowest note is exactly the lowest open string.</param>
/// <param name="OpenNotes">Notes an open string can play.</param>
/// <param name="HighFrets">Notes that can only be played above the 12th fret.</param>
/// <param name="Distance">Semitones from the standard tuning, summed over the strings.</param>
public sealed record TuningFit(string Preset, string Tuning, int OutOfRange, bool LowStringFits, int OpenNotes, int HighFrets, int Distance);

/// <param name="Name">Tonic and mode, e.g. G or Em.</param>
public sealed record TabKey(string Name, int Fifths, KeyMode Mode);

public sealed record TabMeter(int Beats, int BeatUnit = 4);

/// <param name="Cents">Offset of the recording from A = 440, -50 to 50; positive is sharp.</param>
/// <param name="Concentration">How well the recording agrees on it, 0 to 1.</param>
/// <param name="Retuned">The notes were transcribed from the recording retuned to A = 440.</param>
public sealed record ReferencePitch(double Cents, double Concentration, bool Retuned);

/// <summary>
/// The tab profile's result (the engine's schema <c>Tab</c>; bass-tab's too): every note with its string and fret,
/// and what the song check shows before the tab (tuning, reference pitch, capo, octave, key and tempo).
/// </summary>
/// <param name="Preset">The instrument and tuning the tab was made for, e.g. bass-4-standard (<see cref="FrettedInstruments.OfPreset"/>).</param>
/// <param name="Notes">In time order; violations name notes by their index here.</param>
/// <param name="Violations">Empty when the tab is playable as written.</param>
/// <param name="TuningSuggestions">The instrument's tunings ranked by fit to the notes, best first; when the first is not Preset, the song sounds like that tuning.</param>
/// <param name="Layout">What tab.musicxml (and the PDF made from it) shows.</param>
/// <param name="AdjustedNotes">Notes written at the nearest start or length a note value can spell; in tab.musicxml only, Notes are unchanged.</param>
/// <param name="OctaveShift">Semitones the whole line was moved after transcription: 0, -12 or -24 from the octave check, or the chosen 0, -12 or 12.</param>
/// <param name="ReferencePitch">Null when the recording's tuning could not be measured.</param>
/// <param name="BeatTimes">Seconds of beat 0, 1, 2 ...</param>
/// <param name="FirstDownbeat">Index into BeatTimes of tick 0; negative when the line starts before the first tracked downbeat (a pickup).</param>
/// <param name="OctaveNotesMoved">Single notes written an octave lower than they were heard (with the octave on auto).</param>
/// <param name="UnplayableDropped">Notes heard that are not in the tab because the instrument cannot play them with the others. Always 0 for a bass line.</param>
/// <param name="LeftoversDropped">Notes heard that are not in the tab because they were not played: overtones and notes heard very faintly.</param>
/// <param name="DoubledNotes">Notes written on a second string as the unison of a strummed chord; each has <see cref="TabNote.Doubled"/>.</param>
/// <param name="InferredNotes">Notes in the tab that were not heard (<see cref="TabChords.Completed"/>); each has <see cref="TabNote.Inferred"/>.</param>
public sealed record TabResult(
    string Preset,
    FingeringStyle Style,
    TabInstrument Instrument,
    IReadOnlyList<TabNote> Notes,
    IReadOnlyList<TabViolation> Violations,
    IReadOnlyList<TuningFit> TuningSuggestions,
    TabLayout Layout,
    int AdjustedNotes,
    int OctaveShift,
    OctaveSource OctaveSource,
    ReferencePitch? ReferencePitch,
    double TempoBpm,
    TabKey Key,
    TabMeter Meter,
    IReadOnlyList<double> BeatTimes,
    int FirstDownbeat,
    int OctaveNotesMoved = 0,
    int TicksPerBeat = 24,
    int UnplayableDropped = 0,
    int LeftoversDropped = 0,
    int DoubledNotes = 0,
    int InferredNotes = 0)
{
    /// <summary>The tuning the song sounds like when it is not the one the tab was made for; null when Preset fits best.</summary>
    [JsonIgnore]
    public TuningFit? SuggestedTuning => TuningSuggestions.FirstOrDefault() is { } best && best.Preset != Preset ? best : null;

    /// <summary>Reads tab.json; null when it is not a tab.</summary>
    public static TabResult? Parse(string json)
    {
        try { return JsonSerializer.Deserialize(json, EngineJsonContext.Default.TabResult); }
        catch (JsonException) { return null; }
    }

    public static string Serialize(TabResult tab) => JsonSerializer.Serialize(tab, EngineJsonContext.Default.TabResult);
}

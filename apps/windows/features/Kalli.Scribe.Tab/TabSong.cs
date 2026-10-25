using System.Globalization;
using System.Text.RegularExpressions;
using CommunityToolkit.Mvvm.ComponentModel;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;

namespace Kalli.Scribe.Tab;

/// <summary>
/// What the player answered for one recording: What is this? (<see cref="Recording"/>, null until it is answered),
/// and what Check the song asked for (<see cref="Again"/>: the options to write the same recording down with once more).
/// </summary>
public sealed record SongAnswer(Recording? Recording = null, TabOptions? Again = null);

/// <summary>
/// The answers for the recording in hand, kept while it is the one being worked on: another recording starts with
/// none. They are for this song only; Your instrument is never changed by them. A recording is told apart by its
/// object, not its contents: the same file opened again is another recording.
/// </summary>
public sealed class SongAnswers<TSource> : ObservableObject where TSource : class
{
    private TSource? _recording;
    private SongAnswer _answer = new();

    /// <summary>The answers for <paramref name="source"/>; none when it is another recording than the one asked about.</summary>
    public SongAnswer Of(TSource? source) => source is not null && ReferenceEquals(source, _recording) ? _answer : new SongAnswer();

    /// <summary>Every set is a change, also the same answer for another recording.</summary>
    public void Set(TSource? source, SongAnswer value)
    {
        _recording = source;
        _answer = value;
        OnPropertyChanged(string.Empty);
    }

    /// <summary><paramref name="from"/> is kept where <paramref name="to"/> is now (the same recording): its answers are <paramref name="to"/>'s.</summary>
    public void Moved(TSource from, TSource to)
    {
        if (ReferenceEquals(_recording, from)) Set(to, _answer);
    }
}

/// <summary>
/// The profile ids of this app's target that the computer in use says it has. What is this? and Check the song ask
/// when they open and whenever the computer changes; the answer is kept for that computer only, and is gone while
/// it is asked again.
/// </summary>
public sealed class ComputerProfiles : ObservableObject
{
    /// <summary>What is known of one computer: still <see cref="Asking"/>, or its answer (<see cref="Listed"/>; null when it could not be asked).</summary>
    public sealed record Known(string Computer, bool Asking, IReadOnlySet<string>? Listed);

    private Known? _answer;

    public Known? Answer
    {
        get => _answer;
        private set { if (SetProperty(ref _answer, value)) OnPropertyChanged(nameof(Listed)); }
    }

    /// <summary>The ids to choose a job's profile from; null while nothing is known.</summary>
    public IReadOnlySet<string>? Listed => Answer is { Asking: false } a ? a.Listed : null;

    /// <summary><paramref name="computer"/> is being asked: whatever was known, of it or of another computer, no longer counts.</summary>
    public void Asking(string computer) => Answer = new Known(computer, Asking: true, Listed: null);

    /// <summary><paramref name="computer"/> answered with <paramref name="listed"/>, or could not be asked (null). An answer that is no longer the one waited for is dropped.</summary>
    public void Answered(string computer, IReadOnlySet<string>? listed)
    {
        if (Answer?.Computer == computer) Answer = new Known(computer, Asking: false, listed);
    }

    /// <summary>No computer is there.</summary>
    public void Clear() => Answer = null;
}

/// <summary>A tab job as it is sent for a song.</summary>
public static class TabSong
{
    /// <summary>
    /// The <c>tab</c> job's options. A first job is for the player's instrument and what was answered for this song; a
    /// song written down again takes the options Check the song made for it.
    /// </summary>
    public static TabOptions Options(YourInstrument instrument, SongAnswer answer)
    {
        if (answer.Again is { } again) return again;
        var mine = instrument.Valid();
        return new TabOptions(
            Instrument: mine.Kind,
            Tuning: mine.Tuning,
            // A capo is this song's, not the instrument's: Check the song asks about it.
            Capo: 0,
            // The fingering style is left to the computer's default (as played).
            Style: null,
            // Continue needs an answer, so this is never the player's: an unanswered job is taken as the computer takes it.
            Recording: answer.Recording ?? mine.Kind.DefaultRecording(),
            Octave: Octave.Auto,
            Layout: mine.Reads.Layout() is var layout && layout != TabLayout.Unknown ? layout : TabLayout.Tab,
            // Chords are written as they were heard: the computer's default, so nothing is sent.
            Chords: null);
    }

    /// <summary>
    /// What is this? as it stands before the player has answered. A ukulele or a mandolin starts on "Just my
    /// instrument", as the computer takes it: in a song it only works when no guitar plays. A guitar or a bass starts
    /// with nothing chosen.
    /// </summary>
    public static Recording? StartingAnswer(YourInstrument instrument)
    {
        var kind = instrument.Valid().Kind;
        return kind.AloneByDefault() ? kind.DefaultRecording() : null;
    }

    /// <summary>
    /// The profile id a tab for <paramref name="kind"/> is sent under, on a computer that has the profiles
    /// <paramref name="listed"/> (null: not known). <c>tab</c> where the computer has it. A computer from before it
    /// knows <c>bass-tab</c> only, which is the same profile for a bass: a bass still goes there, under that id. Null:
    /// this computer cannot write a tab for the instrument, and nothing is sent.
    /// </summary>
    public static string? Profile(FrettedInstrument? kind, IReadOnlySet<string>? listed)
    {
        bool bass = kind?.IsBass() == true;
        // Not known: the id every computer that writes tab for the instrument has.
        if (listed is null) return bass ? TabProfiles.BassTab : TabProfiles.Tab;
        if (listed.Contains(TabProfiles.Tab)) return TabProfiles.Tab;
        if (bass && listed.Contains(TabProfiles.BassTab)) return TabProfiles.BassTab;
        return null;
    }

    /// <summary>
    /// <paramref name="request"/> as a tab job: the tab options, and none of the band's (a seat, a clef, who plays the
    /// tune), under the profile id the computer with <paramref name="listed"/> has for the instrument
    /// (<see cref="Profile"/>; the usual id when it has none, which the screens do not let through).
    /// </summary>
    public static JobCreate Job(JobCreate request, TabOptions options, IReadOnlySet<string>? listed = null) =>
        (request with { Profile = Profile(options.Instrument, listed) ?? TabProfiles.Tab, Seat = null, Reads = null, Lead = null }).WithTab(options);
}

/// <summary>One row of Check the song: what was heard, as the result tells it. The app words each kind of row.</summary>
public abstract record SongRow
{
    private SongRow() { }

    /// <summary>The tuning the tab is written for, and the one the notes fit better when there is one; Kind: the instrument, when it is known.</summary>
    public sealed record Tuning(string Written, string? SoundsLike, FrettedInstrument? Kind = null) : SongRow;

    /// <summary>The line was moved by Shift semitones, by the octave check or because the player Chosen it; or NotesMoved single notes were written an octave lower than they were heard.</summary>
    public sealed record Octave(int Shift, bool Chosen, int NotesMoved) : SongRow;

    /// <summary>The recording is tuned Cents away from A = 440 (positive is sharp); Retuned: the notes were read with that allowed for.</summary>
    public sealed record ReferencePitch(int Cents, bool Retuned) : SongRow;

    public sealed record KeyAndTempo(int Fifths, bool Minor, int Bpm, int Beats, int BeatUnit) : SongRow;

    /// <summary>Notes marked "?".</summary>
    public sealed record Doubtful(int Count) : SongRow;

    /// <summary>Notes no string of the instrument can play.</summary>
    public sealed record NoPlace(int Count) : SongRow;

    /// <summary>The capo the tab is written for, 0 for none. Frets are counted from it.</summary>
    public sealed record Capo(int Fret) : SongRow;

    /// <summary>Notes that were heard and are not in the tab: the instrument can't play them together with the others.</summary>
    public sealed record LeftOut(int Count) : SongRow;

    /// <summary>Notes in the tab that were not heard: added to complete a chord, each marked "?".</summary>
    public sealed record Added(int Count) : SongRow;
}

/// <summary>Check the song: the rows a result has something to say for, and the options it was made with.</summary>
public static class SongCheck
{
    /// <summary>A recording this far from A = 440 is worth a row; nearer than that is how any instrument is tuned.</summary>
    public const int ReferenceCents = 10;

    /// <summary>The frets a capo can be asked for: 0 is none.</summary>
    public static IReadOnlyList<int> CapoFrets { get; } = [.. Enumerable.Range(0, TabOptions.MaxCapo + 1)];

    /// <summary>The tuning id of a preset ("bass-4-drop-d" and "guitar-drop-d" are "drop-d"); null for a preset this version does not know.</summary>
    public static string? TuningOf(string preset) => FrettedInstruments.OfPreset(preset)?.Tuning;

    /// <summary>The instrument of a preset ("guitar-drop-d" is a six-string guitar); null for a preset this version does not know.</summary>
    public static FrettedInstrument? KindOf(string preset) => FrettedInstruments.OfPreset(preset)?.Kind;

    /// <summary>A capo is asked about for this tab: a guitar or a ukulele, or any tab that was written for one.</summary>
    public static bool AsksCapo(TabResult tab) =>
        tab.Instrument.Capo > 0 || (KindOf(tab.Preset) is { } kind && Instruments.Of(kind) is { } instrument && instrument.TakesCapo());

    /// <summary>
    /// The options <paramref name="tab"/> was made with, read back from the result and from <paramref name="stages"/> of
    /// its job (a full song was separated first). This is what a song is written down again with, one thing changed: it
    /// holds for a song opened from Your songs and after the app was restarted, when nothing else remembers the answers.
    /// </summary>
    public static TabOptions OptionsOf(TabResult tab, IReadOnlyList<string> stages)
    {
        var made = FrettedInstruments.OfPreset(tab.Preset);
        return new TabOptions(
            Instrument: made?.Kind,
            Tuning: made?.Tuning,
            Capo: tab.Instrument.Capo,
            Style: tab.Style == FingeringStyle.Unknown ? null : tab.Style,
            Recording: stages.Contains("stems") ? Recording.Song : Recording.Instrument,
            Octave: tab.OctaveSource != OctaveSource.Chosen ? Octave.Auto
                : tab.OctaveShift < 0 ? Octave.Down
                : tab.OctaveShift > 0 ? Octave.Up
                : Octave.AsHeard,
            Layout: tab.Layout == TabLayout.Unknown ? null : tab.Layout);
    }

    /// <summary>The rows the result has something to say for, in the order of the screen.</summary>
    public static IReadOnlyList<SongRow> Rows(TabResult tab)
    {
        var rows = new List<SongRow>
        {
            new SongRow.Tuning(TuningOf(tab.Preset) ?? tab.Preset, tab.SuggestedTuning is { } s ? TuningOf(s.Preset) : null, KindOf(tab.Preset)),
        };
        if (AsksCapo(tab)) rows.Add(new SongRow.Capo(tab.Instrument.Capo));
        bool chosen = tab.OctaveSource == OctaveSource.Chosen;
        if (tab.OctaveShift != 0 || tab.OctaveNotesMoved > 0 || chosen) rows.Add(new SongRow.Octave(tab.OctaveShift, chosen, tab.OctaveNotesMoved));
        if (tab.ReferencePitch is { } r && Math.Abs(r.Cents) > ReferenceCents) rows.Add(new SongRow.ReferencePitch(TabIndex.Round(r.Cents), r.Retuned));
        rows.Add(new SongRow.KeyAndTempo(tab.Key.Fifths, tab.Key.Mode == KeyMode.Minor, TabIndex.Round(tab.TempoBpm), tab.Meter.Beats, tab.Meter.BeatUnit));
        int doubtful = tab.Notes.Count(n => n.Doubtful);
        if (doubtful > 0) rows.Add(new SongRow.Doubtful(doubtful));
        int noPlace = tab.Notes.Count(n => n.OutOfRange || n.Position is null);
        if (noPlace > 0) rows.Add(new SongRow.NoPlace(noPlace));
        if (tab.UnplayableDropped > 0) rows.Add(new SongRow.LeftOut(tab.UnplayableDropped));
        if (tab.InferredNotes > 0) rows.Add(new SongRow.Added(tab.InferredNotes));
        return rows;
    }
}

/// <summary>What a saved song's row on Home says: read from the tab's MusicXML and its notes, as the library keeps them.</summary>
public sealed partial record SongFacts(int? Strings, string? Tuning, int ToCheck, FrettedInstrument? Kind = null)
{
    private static readonly Dictionary<char, int> Steps = new() { ['C'] = 0, ['D'] = 2, ['E'] = 4, ['F'] = 5, ['G'] = 7, ['A'] = 9, ['B'] = 11 };

    /// <summary>The open strings of each tuning, lowest first (core/targets/fretted/src/instrument.rs), in the crate's order.</summary>
    public static OrderedDictionary<string, IReadOnlyList<int>> OpenStrings { get; } = new()
    {
        ["guitar-standard"] = [40, 45, 50, 55, 59, 64],
        ["guitar-eb-standard"] = [39, 44, 49, 54, 58, 63],
        ["guitar-d-standard"] = [38, 43, 48, 53, 57, 62],
        ["guitar-c-standard"] = [36, 41, 46, 51, 55, 60],
        ["guitar-drop-d"] = [38, 45, 50, 55, 59, 64],
        ["guitar-drop-c"] = [36, 43, 48, 53, 57, 62],
        ["guitar-drop-b"] = [35, 42, 47, 52, 56, 61],
        ["guitar-dadgad"] = [38, 45, 50, 55, 57, 62],
        ["guitar-open-g"] = [38, 43, 50, 55, 59, 62],
        ["guitar-open-d"] = [38, 45, 50, 54, 57, 62],
        ["guitar-open-e"] = [40, 47, 52, 56, 59, 64],
        ["guitar-7-standard"] = [35, 40, 45, 50, 55, 59, 64],
        ["guitar-7-eb-standard"] = [34, 39, 44, 49, 54, 58, 63],
        ["guitar-8-standard"] = [30, 35, 40, 45, 50, 55, 59, 64],
        ["bass-4-standard"] = [28, 33, 38, 43],
        ["bass-4-eb-standard"] = [27, 32, 37, 42],
        ["bass-4-d-standard"] = [26, 31, 36, 41],
        ["bass-4-drop-d"] = [26, 33, 38, 43],
        ["bass-4-bead"] = [23, 28, 33, 38],
        ["bass-5-standard"] = [23, 28, 33, 38, 43],
        ["bass-5-drop-a"] = [21, 28, 33, 38, 43],
        ["bass-6-standard"] = [23, 28, 33, 38, 43, 48],
        ["ukulele-high-g"] = [60, 64, 67, 69],
        ["ukulele-low-g"] = [55, 60, 64, 69],
        ["ukulele-baritone"] = [50, 55, 59, 64],
        ["mandolin"] = [55, 62, 69, 76],
    };

    [GeneratedRegex(@"<staff-tuning\b[^>]*>(.*?)</staff-tuning>", RegexOptions.Singleline)]
    private static partial Regex StaffTuning();

    private static string? Field(string body, string name) =>
        Regex.Match(body, $@"<{name}>\s*([^<\s]+)\s*</{name}>") is { Success: true } m ? m.Groups[1].Value : null;

    /// <summary>The open strings a tab's MusicXML is written for (its staff tuning), lowest first; empty without one.</summary>
    public static IReadOnlyList<int> OpenStringsOf(string musicXml)
    {
        var open = new List<int>();
        foreach (Match m in StaffTuning().Matches(musicXml))
        {
            string body = m.Groups[1].Value;
            if (Field(body, "tuning-step") is not { Length: > 0 } stepText || !Steps.TryGetValue(stepText[0], out int step)) continue;
            if (!int.TryParse(Field(body, "tuning-octave"), NumberStyles.Integer, CultureInfo.InvariantCulture, out int octave)) continue;
            int alter = double.TryParse(Field(body, "tuning-alter"), NumberStyles.Float, CultureInfo.InvariantCulture, out double a) ? (int)a : 0;
            open.Add((octave + 1) * 12 + step + alter);
        }
        open.Sort();
        return open;
    }

    /// <param name="compositionJson">The notes with their confidence, as the computer wrote them.</param>
    public static SongFacts Of(string musicXml, string? compositionJson)
    {
        var open = OpenStringsOf(musicXml);
        string? preset = OpenStrings.FirstOrDefault(e => e.Value.SequenceEqual(open)).Key;
        int toCheck = 0;
        if (compositionJson is not null)
        {
            try { toCheck = CompositionJson.Parse(compositionJson).Voices.Sum(v => v.Notes.Count(n => n.Confidence < TabNote.Doubt)); }
            catch (Exception e) when (e is System.Text.Json.JsonException or InvalidOperationException or NullReferenceException) { toCheck = 0; }
        }
        return new SongFacts(open.Count > 0 ? open.Count : null, preset is null ? null : SongCheck.TuningOf(preset), toCheck,
            preset is null ? null : SongCheck.KindOf(preset));
    }
}

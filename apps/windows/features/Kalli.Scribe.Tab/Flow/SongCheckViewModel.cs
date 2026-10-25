using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tab;

/// <summary>What a row's button asks for: the recording written down again with one thing changed, after a choice when it has <see cref="Choices"/>.</summary>
public sealed record SongChange(string Label, string Tag, Func<TabOptions, TabOptions> Apply, string? Question = null,
    IReadOnlyList<Choice<int>>? Choices = null, int Selected = 0);

/// <summary>One finding of Check the song: its name, what was heard as shown and as spoken, and the change it offers.</summary>
public sealed record SongCheckRow(string Tag, string Label, string Shown, string Spoken, string? Caption, SongChange? Change)
{
    public bool HasChange => Change is not null;
    public bool HasCaption => Caption is not null;
    public string AccessibleName => Caption is null ? $"{Label}: {Spoken}" : $"{Label}: {Spoken}. {Caption}";
}

/// <summary>
/// "Check the song": what was heard, one row per finding the result has (tuning, capo, octave, reference pitch, key and
/// tempo, notes marked ?, notes with no place, notes left out and added), and Show the tab. A row's button writes the
/// recording down again with that one thing changed; the computer keeps what it already worked out.
/// </summary>
public sealed partial class SongCheckViewModel(IStrings strings, ComputerProfiles profiles) : ObservableObject
{
    private TabResult? _tab;
    private IReadOnlyList<string> _stages = [];

    /// <summary>The tab's facts are being read from the computer.</summary>
    [ObservableProperty] public partial bool IsReading { get; set; }

    /// <summary>Why the facts can't be had now; null when they are there or still read.</summary>
    [ObservableProperty] public partial string? MissingText { get; set; }

    public ObservableCollection<SongCheckRow> Rows { get; } = [];

    /// <summary>Why no row offers its change (the computer is away, or too old for this instrument); null when they do.</summary>
    [ObservableProperty] public partial string? NoChangeText { get; set; }

    /// <summary>"You can change this later." under the rows, when one offers a change.</summary>
    [ObservableProperty] public partial bool ShowsLater { get; set; }

    /// <summary>A change was chosen: the recording is written down again with these options.</summary>
    public event EventHandler<TabOptions>? WriteAgain;

    /// <summary>Show the tab.</summary>
    public event EventHandler? ShowTab;

    /// <summary>The facts are being read.</summary>
    public void Reading()
    {
        _tab = null;
        Rows.Clear();
        IsReading = true;
        MissingText = null;
        NoChangeText = null;
        ShowsLater = false;
    }

    /// <summary>The facts could not be had: <paramref name="why"/> says it in the app's words.</summary>
    public void Missing(string why)
    {
        IsReading = false;
        MissingText = strings.Format("Tab_Check_Missing", why);
    }

    /// <summary>The facts of the tab, and the stages of the job that made it.</summary>
    public void Show(TabResult tab, IReadOnlyList<string> stages, bool computerThere)
    {
        _tab = tab;
        _stages = stages;
        IsReading = false;
        MissingText = null;
        Update(computerThere);
    }

    /// <summary>The rows again, as the connection and the computer's profiles are now.</summary>
    public void Update(bool computerThere)
    {
        if (_tab is not { } tab) return;
        var made = SongCheck.KindOf(tab.Preset);
        bool asking = computerThere && profiles.Answer is not { Asking: false };
        bool tooOld = computerThere && !asking && TabSong.Profile(made, profiles.Listed) is null;
        bool canChange = computerThere && !asking && !tooOld;
        Rows.Clear();
        bool offers = false;
        foreach (var row in SongCheck.Rows(tab))
        {
            var change = ChangeFor(row);
            offers |= change is not null;
            Rows.Add(Words(row, canChange ? change : null));
        }
        NoChangeText = offers && !canChange && !asking
            ? tooOld ? strings[made is { } k && Instruments.Of(k) is { } i ? $"Tab_TooOld_{i}" : "Tab_TooOld_Bass"] : strings["Tab_Check_Connect"]
            : null;
        ShowsLater = offers && canChange;
    }

    [RelayCommand]
    private void Change(SongChange? change) => Choose(change, null);

    /// <summary>A change; for one with choices, the choice made (the one the tab has now changes nothing).</summary>
    public void Choose(SongChange? change, int? choice)
    {
        if (change is null || _tab is null) return;
        if (change.Choices is not null && (choice is not { } c || c == change.Selected)) return;
        var options = SongCheck.OptionsOf(_tab, _stages);
        var applied = change.Choices is not null ? options with { Capo = choice } : change.Apply(options);
        WriteAgain?.Invoke(this, applied);
    }

    [RelayCommand]
    private void Show() => ShowTab?.Invoke(this, EventArgs.Empty);

    private SongChange? ChangeFor(SongRow row) => row switch
    {
        SongRow.Tuning { SoundsLike: { } id } =>
            new SongChange(strings.Format("Tab_Check_Use", YourInstrumentViewModel.TuningName(id, strings)), "tuning", o => o with { Tuning = id }),
        SongRow.Capo capo => new SongChange(strings["Tab_Check_Capo_Change"], "capo", o => o, strings["Tab_Check_Capo"],
            [.. SongCheck.CapoFrets.Select(f => new Choice<int>(f, CapoName(f)))], capo.Fret),
        SongRow.Octave { Chosen: true } => new SongChange(strings["Tab_Check_Octave_Auto"], "octave", o => o with { Octave = Engine.Octave.Auto }),
        SongRow.Octave { Shift: not 0 } => new SongChange(strings["Tab_Check_AsHeard"], "octave", o => o with { Octave = Engine.Octave.AsHeard }),
        _ => null,
    };

    /// <summary>"No capo", "Capo on fret 2".</summary>
    public string CapoName(int fret) => fret == 0 ? strings["Tab_Check_Capo_None"] : strings.Format("Tab_Check_Capo_On", fret);

    private string Count(string key, int n) => strings.Format(n == 1 ? key + "_One" : key, n);

    private SongCheckRow Words(SongRow row, SongChange? change)
    {
        bool nb = strings.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase);
        (string tag, string label, string shown, string spoken) = row switch
        {
            SongRow.Tuning t => ("tuning", strings["Tab_Check_Tuning"],
                t.SoundsLike is { } s ? strings.Format("Tab_Check_SoundsLike", YourInstrumentViewModel.TuningName(s, strings), YourInstrumentViewModel.TuningName(t.Written, strings))
                    : YourInstrumentViewModel.TuningName(t.Written, strings), ""),
            SongRow.Capo c => ("capo", strings["Tab_Check_Capo"], CapoName(c.Fret), ""),
            SongRow.LeftOut l => ("left-out", strings["Tab_Check_LeftOut_Title"], Count("Tab_Check_LeftOut", l.Count), ""),
            SongRow.Added a => ("added", strings["Tab_Check_Added_Title"], Count("Tab_Check_Added", a.Count), ""),
            SongRow.Octave o => ("octave", strings["Tab_Check_Octave"], o switch
            {
                { Chosen: true, Shift: 0 } => strings["Tab_Check_Octave_AsHeard"],
                { Chosen: true, Shift: < 0 } => strings["Tab_Check_Octave_ChosenDown"],
                { Chosen: true } => strings["Tab_Check_Octave_ChosenUp"],
                { Shift: <= -24 } => strings["Tab_Check_Octave_TwoDown"],
                { Shift: < 0 } => strings["Tab_Check_Octave_Down"],
                { Shift: > 0 } => strings["Tab_Check_Octave_Up"],
                _ => Count("Tab_Check_Octave_Notes", o.NotesMoved),
            }, ""),
            SongRow.ReferencePitch r => ("reference", strings["Tab_Check_Reference"],
                strings.Format(r.Cents > 0 ? "Tab_Check_Reference_Sharp" : "Tab_Check_Reference_Flat", Math.Abs(r.Cents))
                    + (r.Retuned ? " " + strings["Tab_Check_Reference_Allowed"] : ""), ""),
            SongRow.KeyAndTempo k => ("key", strings["Tab_Check_KeyTempo"],
                strings.Format("Tab_Check_KeyTempo_Value", KeyNames.Name(KeyNames.TonicOf(k.Fifths, k.Minor), k.Minor, nb), k.Bpm, k.Beats, k.BeatUnit),
                strings.Format("Tab_Check_KeyTempo_Spoken", KeyNames.Name(KeyNames.TonicOf(k.Fifths, k.Minor), k.Minor, nb), k.Bpm, k.Beats, k.BeatUnit)),
            SongRow.Doubtful d => ("marked", strings["Tab_Check_Notes"], Count("Tab_Check_Marked", d.Count), ""),
            SongRow.NoPlace p => ("no-place", strings["Tab_Check_NoPlace_Title"], Count("Tab_Check_NoPlace", p.Count), ""),
            _ => ("", "", "", ""),
        };
        // A change of capo keeps the sound: the same notes, with the frets counted from the capo.
        string? caption = row is SongRow.Capo && change is not null ? strings["Tab_Check_Capo_Keeps"] : null;
        return new SongCheckRow(tag, label, shown, spoken.Length > 0 ? spoken : shown, caption, change);
    }
}

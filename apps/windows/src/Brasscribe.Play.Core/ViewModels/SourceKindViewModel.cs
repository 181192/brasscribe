using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>The four answers to "What is this?", each tied to an engine profile.</summary>
public enum SourceKind { Solo, BrassBand, OrchestraWithSoloist, PopRock }

public sealed partial class SourceKindOption(SourceKind kind, string profile, string label, string description) : ObservableObject
{
    public SourceKind Kind { get; } = kind;
    public string Profile { get; } = profile;
    public string Label { get; } = label;
    [ObservableProperty] public partial string Description { get; set; } = description;
    [ObservableProperty] public partial bool IsAvailable { get; set; } = true;
}

/// <summary>
/// "What is this?" The answer picks the pipeline profile; the app never guesses silently, so
/// Continue stays disabled until one is chosen.
/// </summary>
public sealed partial class SourceKindViewModel : ObservableObject
{
    public static readonly IReadOnlyDictionary<SourceKind, string> Profiles = new Dictionary<SourceKind, string>
    {
        [SourceKind.Solo] = "solo",
        [SourceKind.BrassBand] = "brass-band",
        [SourceKind.OrchestraWithSoloist] = "orchestra-with-soloist",
        [SourceKind.PopRock] = "pop-rock",
    };

    private readonly IStrings _s;

    public SourceKindViewModel(IStrings s)
    {
        _s = s;
        foreach (var (kind, profile) in Profiles)
            Options.Add(new SourceKindOption(kind, profile, s[$"Kind_{kind}_Label"], s[$"Kind_{kind}_Description"]));
    }

    public ObservableCollection<SourceKindOption> Options { get; } = [];

    [ObservableProperty] public partial SourceAudio? Source { get; set; }

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ContinueCommand))]
    public partial SourceKindOption? Selected { get; set; }

    public event EventHandler<(SourceAudio Source, SourceKindOption Kind)>? Chosen;

    /// <summary>Marks options whose profile the connected engine does not offer.</summary>
    public async Task RefreshFromEngineAsync(IEngineClient engine, CancellationToken ct = default)
    {
        try
        {
            var profiles = (await engine.ListProfilesAsync(ct)).Select(p => p.Name).ToHashSet();
            foreach (var o in Options) o.IsAvailable = profiles.Contains(o.Profile);
        }
        catch (EngineException)
        {
            // Offline: leave every option enabled; transcription will report the engine state.
        }
    }

    [RelayCommand(CanExecute = nameof(CanContinue))]
    private void Continue()
    {
        if (Source is not null && Selected is not null) Chosen?.Invoke(this, (Source, Selected));
    }

    private bool CanContinue() => Selected is { IsAvailable: true } && Source is not null;

    partial void OnSourceChanged(SourceAudio? value)
    {
        ContinueCommand.NotifyCanExecuteChanged();
        SourceLine = value is null ? "" : _s.Format("Kind_SourceLine", value.DisplayName, DurationText(value.Duration));
    }

    /// <summary>"Mikkel.m4a · 4 min 12 s".</summary>
    [ObservableProperty] public partial string SourceLine { get; set; } = "";

    /// <summary>Where the score is made: "Made on this PC. Nothing goes online."</summary>
    [ObservableProperty] public partial string WhereText { get; set; } = "";

    /// <summary>Sets <see cref="WhereText"/> for the engine address: this PC, or your other computer.</summary>
    public void SetWhere(Uri engine) =>
        WhereText = _s[engine.IsLoopback ? "Kind_WhereThisPc" : "Kind_WhereComputer"];

    private string DurationText(TimeSpan d) =>
        d.TotalMinutes >= 1 ? _s.Format("Duration_MinutesSeconds", (int)d.TotalMinutes, d.Seconds) : _s.Format("Duration_Seconds", Math.Max(1, (int)Math.Round(d.TotalSeconds)));
}

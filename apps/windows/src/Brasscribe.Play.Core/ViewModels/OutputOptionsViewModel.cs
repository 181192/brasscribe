using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public enum Lineup { FullBand, MinimalBand, Quartet }
public enum Difficulty { Faithful, Standard, Easier }

/// <summary>
/// "Choose output": lineup, difficulty and key. Apply tries, in order: the Rust core on the device
/// from the layered pipeline's stage files (all three options); a new engine job on the same
/// recording (the engine reuses every cached stage, so only the arrangement runs again); the Rust
/// core re-arranging the lineup of the Composition alone.
/// </summary>
public sealed partial class OutputOptionsViewModel(ICoreBridge core, IAnnouncer announcer, IStrings s) : ObservableObject
{
    /// <summary>Target keys as Brasscribe takes them (concert tonic, by semitone); null keeps the key as recorded.</summary>
    public static readonly string?[] Keys = [null, .. Scores.KeyNames.Tonics];

    [ObservableProperty] public partial Lineup Lineup { get; set; } = Lineup.FullBand;
    [ObservableProperty] public partial Difficulty Difficulty { get; set; } = Difficulty.Faithful;

    /// <summary>
    /// The take is one line (a solo recording): there is no harmony for a quartet to play, so the
    /// quartet card is shown dimmed with the reason and cannot be chosen.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(QuartetAvailable), nameof(QuartetDescription), nameof(QuartetHelpText))]
    public partial bool IsSoloTake { get; set; }

    partial void OnIsSoloTakeChanged(bool value)
    {
        if (value && Lineup == Lineup.Quartet) Lineup = Lineup.FullBand;
    }

    public bool QuartetAvailable => !IsSoloTake;

    /// <summary>
    /// A whole-band recording (brass band, pop or rock): it is arranged for the small band or the
    /// quartet only, so the full-band card is dimmed with the reason and a full band goes to the small band.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FullAvailable), nameof(FullDescription), nameof(FullHelpText), nameof(AppliedLineup))]
    public partial bool IsBandTake { get; set; }

    partial void OnIsBandTakeChanged(bool value)
    {
        if (value && Lineup == Lineup.FullBand) (Lineup, _fullPutBack) = (Lineup.MinimalBand, true);
        else if (!value && _fullPutBack && Lineup == Lineup.MinimalBand) Lineup = Lineup.FullBand;
        if (!value) _fullPutBack = false;
    }

    /// <summary>The full band was moved to the small band for a band take (not chosen), so the next take gets it back.</summary>
    private bool _fullPutBack;

    public bool FullAvailable => !IsBandTake;

    /// <summary>The full-band card's second line: what it is, or why it can't be chosen.</summary>
    public string FullDescription => IsBandTake ? s["Output_FullNotYet"] : s["Output_FullBody"];

    /// <summary>The reason for screen readers when the card can't be chosen; empty otherwise.</summary>
    public string FullHelpText => IsBandTake ? s["Output_FullNotYet"] : "";

    /// <summary>The lineup the arranger makes for <paramref name="lineup"/>: a band take never gets the full band.</summary>
    public Lineup Made(Lineup lineup) => IsBandTake && lineup == Lineup.FullBand ? Lineup.MinimalBand : lineup;

    /// <summary>The quartet card's second line: what it is, or why it can't be chosen.</summary>
    public string QuartetDescription => IsSoloTake ? s["Output_QuartetNeedsGroup"] : s["Output_QuartetBody"];

    /// <summary>The reason for screen readers when the card can't be chosen; empty otherwise.</summary>
    public string QuartetHelpText => IsSoloTake ? s["Output_QuartetNeedsGroup"] : "";

    /// <summary>
    /// A lineup card was chosen. The quartet on a solo take is refused with the reason said aloud;
    /// false tells the page to put the selection back.
    /// </summary>
    public bool TryChooseLineup(Lineup lineup)
    {
        if (lineup == Lineup.Quartet && !QuartetAvailable)
        {
            announcer.Announce(s["Output_QuartetNeedsGroup"], AnnouncementKind.Important);
            return false;
        }
        if (lineup == Lineup.FullBand && !FullAvailable)
        {
            announcer.Announce(s["Output_FullNotYet"], AnnouncementKind.Important);
            return false;
        }
        _fullPutBack = false;
        Lineup = lineup;
        return true;
    }

    /// <summary>Index into <see cref="Keys"/>.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyLabel), nameof(KeyDetail))]
    public partial int KeyIndex { get; set; }

    /// <summary>The key the recording is in (from the Composition), when known.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyLabel), nameof(KeyDetail))]
    public partial (int PitchClass, bool Minor)? RecordedKey { get; set; }

    /// <summary>The player's instrument: semitones from written to sounding (−2 for B♭ cornet), null for C instruments.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyDetail))]
    public partial int? InstrumentChromatic { get; set; }

    /// <summary>Sets the recorded key and the player's instrument from a loaded score.</summary>
    public void SetScoreContext(Scores.Composition? composition, int? chromatic)
    {
        RecordedKey = composition?.Keys.OrderBy(k => k.Tick).FirstOrDefault() is { } k
            ? (Scores.KeyNames.TonicOf(k.Fifths, k.Mode == "minor"), k.Mode == "minor")
            : null;
        InstrumentChromatic = chromatic is { } c && ((c % 12) + 12) % 12 != 0 ? c : null;
    }

    private bool Nb => s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || s.Language.StartsWith("no", StringComparison.OrdinalIgnoreCase);

    /// <summary>The concert key chosen (or recorded), when it can be said.</summary>
    private (int PitchClass, bool Minor)? ConcertKey =>
        Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)] is { } tonic
            ? (Scores.KeyNames.PitchClassOf(tonic), RecordedKey?.Minor ?? false)
            : RecordedKey;

    /// <summary>"C major (concert)", or "As recorded" when the recording's key is not known.</summary>
    public string KeyLabel => ConcertKey is { } k
        ? s.Format("Output_KeyConcert", Scores.KeyNames.Name(k.PitchClass, k.Minor, Nb))
        : s["Key_AsRecorded"];

    /// <summary>"As recorded · D major for B♭ instruments" (usability review 2, P2-3).</summary>
    public string KeyDetail
    {
        get
        {
            var parts = new List<string>();
            if (KeyIndex == 0) parts.Add(s["Key_AsRecorded"]);
            if (ConcertKey is { } k && InstrumentChromatic is { } c && Scores.KeyNames.InstrumentKey(c, Nb) is { } instrument)
                parts.Add(s.Format("Output_KeyWritten", Scores.KeyNames.Name(Scores.KeyNames.WrittenOf(k.PitchClass, c), k.Minor, Nb), instrument));
            return parts.Count > 0 ? string.Join(" · ", parts) : s["Output_KeyConcertDetail"];
        }
    }

    /// <summary>A semitone lower (the "Lower" button).</summary>
    [RelayCommand]
    private void KeyDown() => StepKey(-1);

    /// <summary>A semitone higher (the "Higher" button).</summary>
    [RelayCommand]
    private void KeyUp() => StepKey(+1);

    private void StepKey(int semitones)
    {
        int current = ConcertKey?.PitchClass ?? 0;
        int next = ((current + semitones) % 12 + 12) % 12;
        KeyIndex = RecordedKey is { } r && r.PitchClass == next ? 0 : 1 + next;
    }

    /// <summary>The options the shown score was arranged with; "Show the score" arranges only when these change.</summary>
    public ArrangementOptions Applied { get; set; } = ArrangementOptions.Default;

    /// <summary>The lineup of the score being shown (what <see cref="Applied"/> says).</summary>
    public Lineup AppliedLineup => Made(Lineups.Parse(Applied.Lineup) ?? Lineup.FullBand);

    /// <summary>
    /// A score was opened from "Your scores": the choices follow what it was arranged with, so
    /// "Show the score" and a changed note keep its lineup.
    /// </summary>
    public void ShowingSaved(Lineup? lineup, string? difficulty)
    {
        var chosen = lineup ?? Lineup.FullBand;
        if (chosen == Lineup.Quartet && IsSoloTake) chosen = Lineup.FullBand;
        Lineup = Made(chosen);
        _fullPutBack = Lineup != chosen;
        Difficulty = difficulty switch { "standard" => Difficulty.Standard, "easier" => Difficulty.Easier, _ => Difficulty.Faithful };
        KeyIndex = 0;
        Applied = Options;
    }

    /// <summary>Raised when the score can be shown as it is (nothing changed).</summary>
    public event EventHandler? ShowScoreRequested;

    /// <summary>"Show the score": arranges again only when a choice changed (WCAG 3.2.2), otherwise just shows it.</summary>
    [RelayCommand]
    private async Task ShowScore(Scores.Composition? composition)
    {
        if (Options == Applied)
        {
            ShowScoreRequested?.Invoke(this, EventArgs.Empty);
            return;
        }
        await ApplyCommand.ExecuteAsync(composition);
    }

    /// <summary>Set by the app when the score came from an engine job it can re-run.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DifficultyAvailable), nameof(KeyAvailable), nameof(UnavailableText))]
    public partial bool HasEngineJob { get; set; }

    /// <summary>
    /// Set by the app when the layered pipeline's stage files can be had (from the engine job or a
    /// local folder); with the native core they arrange on the device.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DifficultyAvailable), nameof(KeyAvailable), nameof(UnavailableText), nameof(CanArrangeOnDevice))]
    public partial Func<CancellationToken, Task<LayerInputs?>>? LayerSource { get; set; }

    /// <summary>Title the on-device arrangement writes into the score.</summary>
    public string Title { get; set; } = "Draft";

    public bool CanArrangeOnDevice => core.IsNative && LayerSource is not null;
    public bool CanArrange => core.IsNative || HasEngineJob;
    public bool DifficultyAvailable => HasEngineJob || CanArrangeOnDevice;
    public bool KeyAvailable => HasEngineJob || CanArrangeOnDevice;
    public string UnavailableText => DifficultyAvailable ? "" : s["Output_NeedsEngine"];

    [ObservableProperty] public partial string? StatusText { get; set; }

    public ArrangementOptions Options => new(
        Lineups.Engine(Lineup),
        Difficulty switch { Difficulty.Standard => "standard", Difficulty.Easier => "easier", _ => "faithful" },
        Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)] is { } tonic && RecordedKey is { Minor: true } ? tonic + "m" : Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)]);

    /// <summary>Raised with the options when the engine should arrange again.</summary>
    public event EventHandler<ArrangementOptions>? RearrangeRequested;

    /// <summary>Raised with MusicXML arranged on the device from the Composition.</summary>
    public event EventHandler<string>? Arranged;

    /// <summary>Raised with a score arranged on the device from the layer inputs (new MusicXML and Composition).</summary>
    public event EventHandler<BandArrangement>? ArrangedBand;

    [RelayCommand]
    private async Task Apply(Scores.Composition? composition)
    {
        if (CanArrangeOnDevice && await TryArrangeOnDeviceAsync()) return;
        if (HasEngineJob)
        {
            StatusText = s["Output_Rearranging"];
            announcer.Announce(StatusText);
            Applied = Options;
            RearrangeRequested?.Invoke(this, Options);
            return;
        }
        if (composition is null) return;
        if (!core.IsNative)
        {
            StatusText = s["Output_NeedsCore"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            return;
        }
        try
        {
            var options = Options;
            var xml = core.ArrangeMusicXmlWith(composition, options);
            if (xml is null) return;
            Applied = options;
            StatusText = s["Output_Ready"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            Arranged?.Invoke(this, xml);
        }
        catch (CoreBridgeException e)
        {
            StatusText = s.Format("Output_Failed", e.Message);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
    }

    /// <summary>False when the layer inputs cannot be had, so the next way is tried.</summary>
    private async Task<bool> TryArrangeOnDeviceAsync()
    {
        StatusText = s["Output_Rearranging"];
        announcer.Announce(StatusText);
        LayerInputs? inputs;
        try
        {
            inputs = await LayerSource!(CancellationToken.None);
        }
        catch (Exception e) when (e is EngineException or IOException or InvalidDataException or NotSupportedException or UnauthorizedAccessException)
        {
            inputs = null;
        }
        if (inputs is null) return false;
        try
        {
            var options = Options;
            var band = await Task.Run(() => core.ArrangeLayersBand(inputs, Title, options));
            if (band is null) return false;
            Applied = options;
            StatusText = s["Output_Ready"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            ArrangedBand?.Invoke(this, band);
        }
        catch (CoreBridgeException e)
        {
            StatusText = s.Format("Output_Failed", e.Message);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
        return true;
    }
}

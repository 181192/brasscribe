using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public enum Lineup { FullBand, MinimalBand }
public enum Difficulty { Faithful, Standard, Easier }

/// <summary>
/// "Choose output": lineup, difficulty and key. With the engine job behind the score, Apply runs a
/// new job on the same recording with these options (the engine reuses every cached stage, so only
/// the arrangement runs again). Without an engine job, the Rust core can re-arrange the lineup on
/// the device; difficulty and key need the engine.
/// </summary>
public sealed partial class OutputOptionsViewModel(ICoreBridge core, IAnnouncer announcer, IStrings s) : ObservableObject
{
    /// <summary>Target keys offered, as the engine takes them (concert tonic); null keeps the key as recorded.</summary>
    public static readonly string?[] Keys = [null, "Bb", "Eb", "F", "C", "Ab", "G", "D", "Db"];

    [ObservableProperty] public partial Lineup Lineup { get; set; } = Lineup.FullBand;
    [ObservableProperty] public partial Difficulty Difficulty { get; set; } = Difficulty.Faithful;

    /// <summary>Index into <see cref="Keys"/>.</summary>
    [ObservableProperty] public partial int KeyIndex { get; set; }

    /// <summary>Set by the app when the score came from an engine job it can re-run.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DifficultyAvailable), nameof(KeyAvailable), nameof(UnavailableText))]
    public partial bool HasEngineJob { get; set; }

    public bool CanArrange => core.IsNative || HasEngineJob;
    public bool DifficultyAvailable => HasEngineJob;
    public bool KeyAvailable => HasEngineJob;
    public string UnavailableText => HasEngineJob ? "" : s["Output_NeedsEngine"];

    [ObservableProperty] public partial string? StatusText { get; set; }

    public ArrangementOptions Options => new(
        Lineup == Lineup.MinimalBand ? "minimal" : "full",
        Difficulty switch { Difficulty.Standard => "standard", Difficulty.Easier => "easier", _ => "faithful" },
        Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)]);

    /// <summary>Raised with the options when the engine should arrange again.</summary>
    public event EventHandler<ArrangementOptions>? RearrangeRequested;

    /// <summary>Raised with MusicXML arranged on the device.</summary>
    public event EventHandler<string>? Arranged;

    [RelayCommand]
    private void Apply(Scores.Composition? composition)
    {
        if (HasEngineJob)
        {
            StatusText = s["Output_Rearranging"];
            announcer.Announce(StatusText);
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
            var xml = core.ArrangeMusicXml(composition, Lineup == Lineup.MinimalBand ? "minimal" : "layers");
            if (xml is null) return;
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
}

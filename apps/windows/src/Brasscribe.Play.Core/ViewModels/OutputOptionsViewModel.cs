using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public enum Lineup { FullBand, MinimalBand }
public enum Difficulty { Faithful, Standard, Easier }

/// <summary>
/// "Choose output": lineup, difficulty and key. Apply tries, in order: the Rust core on the device
/// from the layered pipeline's stage files (all three options); a new engine job on the same
/// recording (the engine reuses every cached stage, so only the arrangement runs again); the Rust
/// core re-arranging the lineup of the Composition alone.
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
        Lineup == Lineup.MinimalBand ? "minimal" : "full",
        Difficulty switch { Difficulty.Standard => "standard", Difficulty.Easier => "easier", _ => "faithful" },
        Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)]);

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

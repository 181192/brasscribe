using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public enum Lineup { FullBand, MinimalBand }
public enum Difficulty { Faithful, Standard, Easier }

/// <summary>
/// "Choose output": lineup, difficulty and key. Re-arranging runs in the Rust core on the device.
/// The arrangers take only a lineup today (full "layers" or "minimal"); difficulty and key are shown
/// but disabled with the reason, because neither the Python reference nor the core implements them yet.
/// </summary>
public sealed partial class OutputOptionsViewModel(ICoreBridge core, IAnnouncer announcer, IStrings s) : ObservableObject
{
    [ObservableProperty] public partial Lineup Lineup { get; set; } = Lineup.FullBand;
    [ObservableProperty] public partial Difficulty Difficulty { get; set; } = Difficulty.Faithful;
    [ObservableProperty] public partial int KeyShift { get; set; }

    public bool CanArrange => core.IsNative;
    public bool DifficultyAvailable => false;
    public bool KeyAvailable => false;
    public string UnavailableText => s["Output_NotYet"];
    public string ArrangeUnavailableText => s["Output_NeedsCore"];

    [ObservableProperty] public partial string? StatusText { get; set; }

    public event EventHandler<string>? Arranged;

    [RelayCommand]
    private void Apply(Scores.Composition? composition)
    {
        if (composition is null) return;
        if (!core.IsNative)
        {
            StatusText = ArrangeUnavailableText;
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

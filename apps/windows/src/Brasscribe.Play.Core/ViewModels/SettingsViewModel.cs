using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>Language, keyboard, motion, talking-score and engine settings, persisted through <see cref="ISettingsStore"/>.</summary>
public sealed partial class SettingsViewModel : ObservableObject
{
    private readonly ISettingsStore _store;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;

    public SettingsViewModel(ISettingsStore store, IAnnouncer announcer, IStrings strings)
    {
        _store = store;
        _announcer = announcer;
        _s = strings;
        Language = store.Get(nameof(Language), "system");
        SingleKeyShortcuts = store.Get(nameof(SingleKeyShortcuts), true);
        ReduceMotion = store.Get(nameof(ReduceMotion), false);
        Verbosity = store.Get(nameof(Verbosity), Verbosity.Standard);
        EngineAddress = store.Get(nameof(EngineAddress), EngineClient.DefaultBaseAddress.ToString());
        EngineToken = store.Get<string?>(nameof(EngineToken), null);
    }

    /// <summary>"system", "en-US" or "nb-NO".</summary>
    [ObservableProperty] public partial string Language { get; set; }
    [ObservableProperty] public partial bool SingleKeyShortcuts { get; set; }
    [ObservableProperty] public partial bool ReduceMotion { get; set; }
    [ObservableProperty] public partial Verbosity Verbosity { get; set; }
    [ObservableProperty] public partial string EngineAddress { get; set; }
    [ObservableProperty] public partial string? EngineToken { get; set; }
    [ObservableProperty] public partial string PairingCode { get; set; } = "";
    [ObservableProperty] public partial string? EngineStatus { get; set; }

    partial void OnLanguageChanged(string value) => _store.Set(nameof(Language), value);
    partial void OnSingleKeyShortcutsChanged(bool value) => _store.Set(nameof(SingleKeyShortcuts), value);
    partial void OnReduceMotionChanged(bool value) => _store.Set(nameof(ReduceMotion), value);
    partial void OnVerbosityChanged(Verbosity value) => _store.Set(nameof(Verbosity), value);
    partial void OnEngineAddressChanged(string value) => _store.Set(nameof(EngineAddress), value);
    partial void OnEngineTokenChanged(string? value) => _store.Set(nameof(EngineToken), value);

    public Uri EngineUri => Uri.TryCreate(EngineAddress, UriKind.Absolute, out var u) ? u : EngineClient.DefaultBaseAddress;

    /// <summary>Checks the engine and pairs when it asks for a code (LAN engines).</summary>
    [RelayCommand]
    private async Task ConnectAsync(IEngineClient? engine)
    {
        if (engine is null) return;
        try
        {
            var health = await engine.GetHealthAsync();
            if (health.AuthRequired && string.IsNullOrEmpty(EngineToken))
            {
                if (string.IsNullOrWhiteSpace(PairingCode))
                {
                    EngineStatus = _s["Settings_Engine_NeedsCode"];
                    _announcer.Announce(EngineStatus, AnnouncementKind.Important);
                    return;
                }
                EngineToken = await engine.PairAsync(PairingCode.Trim(), Environment.MachineName);
            }
            EngineStatus = _s.Format("Settings_Engine_Connected", health.Version, health.Device.ToUpperInvariant());
        }
        catch (EngineException e)
        {
            EngineStatus = e.Message;
        }
        _announcer.Announce(EngineStatus!, AnnouncementKind.Important);
    }
}

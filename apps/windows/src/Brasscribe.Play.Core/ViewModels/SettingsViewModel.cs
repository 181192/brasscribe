using System.Collections.ObjectModel;
using System.Net;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>
/// Language, appearance, keyboard, motion, talking-score and engine settings, persisted through <see cref="ISettingsStore"/>.
/// The engine credential is not a setting: it lives in the vault, keyed by the engine's server id
/// (<see cref="EngineCredentials"/>), and only a 401 asks for pairing again.
/// </summary>
public sealed partial class SettingsViewModel : ObservableObject
{
    /// <summary>Sent with every pairing so the computer's device list says what this is.</summary>
    public const string Platform = "windows";

    /// <summary>How often the approve-on-the-computer request is polled, and how long it waits.</summary>
    public static readonly TimeSpan AskPollInterval = TimeSpan.FromSeconds(2);
    public static readonly TimeSpan AskTimeout = TimeSpan.FromMinutes(2);

    private readonly ISettingsStore _store;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly IEngineDiscovery _discovery;
    private readonly Func<Uri, string?, IEngineClient> _clients;
    private readonly TimeProvider _time;
    private CancellationTokenSource? _ask;

    public SettingsViewModel(ISettingsStore store, IAnnouncer announcer, IStrings strings, IEngineDiscovery? discovery = null,
        ISecretVault? vault = null, Func<Uri, string?, IEngineClient>? clients = null, TimeProvider? time = null)
    {
        _store = store;
        _announcer = announcer;
        _s = strings;
        _discovery = discovery ?? new EngineDiscovery();
        _clients = clients ?? ((uri, token) => new EngineClient(new HttpClient(), uri) { Token = token });
        _time = time ?? TimeProvider.System;
        Language = store.Get(nameof(Language), "system");
        Appearance = AppearanceSetting.Parse(store.Get<string?>(AppearanceSetting.Key, null));
        _pinkUnlock = new PinkUnlock(store.Get(AppearanceSetting.PinkUnlockedKey, false) || Appearance == Appearance.Pink, _time);
        SingleKeyShortcuts = store.Get(nameof(SingleKeyShortcuts), true);
        ReduceMotion = store.Get(nameof(ReduceMotion), false);
        StandKeepControls = store.Get(nameof(StandKeepControls), false);
        StandTurnPages = store.Get(nameof(StandTurnPages), true);
        StandHintSeen = store.Get(nameof(StandHintSeen), false);
        Verbosity = store.Get(nameof(Verbosity), Verbosity.Standard);
        EngineAddress = store.Get(nameof(EngineAddress), EngineClient.DefaultBaseAddress.ToString());
        FirstRunDone = store.Get(nameof(FirstRunDone), false);
        Seat = store.Get<string?>(nameof(Seat), null);
        Reads = store.Get<string?>(nameof(Reads), null);
        Credentials = new EngineCredentials(vault ?? new InMemorySecretVault(), store);
        EngineToken = Credentials.Current?.Token;
        Connection = new ConnectionMonitor(Credentials, _clients, _discovery, () => EngineUri, u => EngineAddress = u.ToString(),
            announcer, strings, _time);
        Connection.CredentialChanged += (_, _) => EngineToken = Credentials.Current?.Token;
    }

    public EngineCredentials Credentials { get; }

    /// <summary>The status row on Home and here: connected, looking, not connected or pair again.</summary>
    public ConnectionMonitor Connection { get; }

    /// <summary>The first-run screen was seen (it shows once).</summary>
    [ObservableProperty] public partial bool FirstRunDone { get; set; }
    partial void OnFirstRunDoneChanged(bool value) => _store.Set(nameof(FirstRunDone), value);

    /// <summary>What the player plays: a core seat id, "none" (I conduct or listen), or null (not set).</summary>
    [ObservableProperty] public partial string? Seat { get; set; }
    partial void OnSeatChanged(string? value)
    {
        _store.Set(nameof(Seat), value);
        if (!_settingChoice) OnPropertyChanged(nameof(SeatChoice));
    }

    /// <summary>The clef the player reads their part in ("treble", "bass"); null for the band's own.</summary>
    [ObservableProperty] public partial string? Reads { get; set; }
    partial void OnReadsChanged(string? value)
    {
        _store.Set(nameof(Reads), value);
        if (!_settingChoice) OnPropertyChanged(nameof(SeatChoice));
    }

    private bool _settingChoice;

    /// <summary>The answer as one value; setting it tells listeners once, with the seat and its reading together.</summary>
    public Seats.SeatChoice SeatChoice
    {
        get => new(Seat, Reads);
        set
        {
            if (value == SeatChoice) return;
            _settingChoice = true;
            try
            {
                Reads = value.Reads;
                Seat = value.Seat;
            }
            finally { _settingChoice = false; }
            OnPropertyChanged(nameof(SeatChoice));
        }
    }

    /// <summary>"system", "en-US" or "nb-NO".</summary>
    [ObservableProperty] public partial string Language { get; set; }
    /// <summary>Match system, Light, Dark or (once unlocked) Pink, for this PC only (design/system.md §10).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(RootTheme), nameof(UsesPink))]
    public partial Appearance Appearance { get; set; }

    /// <summary>A Windows contrast theme is on (set by the app from AccessibilitySettings): it decides the colours.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(RootTheme), nameof(UsesPink))]
    public partial bool HighContrast { get; set; }

    /// <summary>What every window root asks for: the choice, or Default while a contrast theme is on.</summary>
    public RootTheme RootTheme => AppearanceSetting.Resolve(Appearance, HighContrast);

    /// <summary>The Pink palette is on the chrome now (chosen, and no contrast theme).</summary>
    public bool UsesPink => AppearanceSetting.UsesPink(Appearance, HighContrast);

    private readonly PinkUnlock _pinkUnlock;

    /// <summary>Pink is in the Appearance list: unlocked on this PC, or chosen.</summary>
    public bool PinkUnlocked => _pinkUnlock.IsUnlocked;

    /// <summary>The Appearance box's choices, in order (Pink last once unlocked).</summary>
    public IReadOnlyList<Appearance> AppearanceChoices => AppearanceSetting.Choices(PinkUnlocked);

    /// <summary>Raised once, when the version in About unlocks Pink.</summary>
    public event EventHandler? PinkUnlockedNow;

    /// <summary>
    /// The version in About was activated (a click, Space or Enter, Narrator): the fifth in a row unlocks Pink, keeps it
    /// on this PC, and says so once. Nothing switches by itself.
    /// </summary>
    public void ActivateVersion()
    {
        if (!_pinkUnlock.Tap()) return;
        _store.Set(AppearanceSetting.PinkUnlockedKey, true);
        OnPropertyChanged(nameof(PinkUnlocked));
        OnPropertyChanged(nameof(AppearanceChoices));
        _announcer.Announce(_s["Pink_Unlocked"], AnnouncementKind.Important);
        PinkUnlockedNow?.Invoke(this, EventArgs.Empty);
    }

    [ObservableProperty] public partial bool SingleKeyShortcuts { get; set; }
    [ObservableProperty] public partial bool ReduceMotion { get; set; }
    /// <summary>Music stand: Keep the stand controls visible (off by default).</summary>
    [ObservableProperty] public partial bool StandKeepControls { get; set; }
    /// <summary>Music stand: Turn the pages while playing (on by default; design/music-stand.md §12.2).</summary>
    [ObservableProperty] public partial bool StandTurnPages { get; set; }
    /// <summary>The stand's "Tap the music to show the controls." hint was dismissed; it does not come back.</summary>
    [ObservableProperty] public partial bool StandHintSeen { get; set; }
    [ObservableProperty] public partial Verbosity Verbosity { get; set; }
    [ObservableProperty] public partial string EngineAddress { get; set; }

    /// <summary>The token of the engine in use, from the vault (never written to settings).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsPaired))]
    public partial string? EngineToken { get; set; }

    /// <summary>This PC holds a credential for the engine in use (Unpair is offered).</summary>
    public bool IsPaired => EngineToken is not null;
    [ObservableProperty] public partial string PairingCode { get; set; } = "";
    [ObservableProperty] public partial string? EngineStatus { get; set; }

    /// <summary>While waiting for the owner to allow this PC on the computer: the match code both screens show.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsAsking))]
    public partial string? MatchCode { get; set; }

    public bool IsAsking => MatchCode is not null;

    /// <summary>The match code for screen readers, digit by digit ("4 8 2 1").</summary>
    public string MatchCodeSpoken => MatchCode is null ? "" : string.Join(' ', MatchCode.ToCharArray());

    partial void OnMatchCodeChanged(string? value) => OnPropertyChanged(nameof(MatchCodeSpoken));

    partial void OnLanguageChanged(string value) => _store.Set(nameof(Language), value);
    partial void OnAppearanceChanged(Appearance value) => _store.Set(AppearanceSetting.Key, AppearanceSetting.Serialise(value));
    partial void OnSingleKeyShortcutsChanged(bool value) => _store.Set(nameof(SingleKeyShortcuts), value);
    partial void OnReduceMotionChanged(bool value) => _store.Set(nameof(ReduceMotion), value);
    partial void OnStandKeepControlsChanged(bool value) => _store.Set(nameof(StandKeepControls), value);
    partial void OnStandTurnPagesChanged(bool value) => _store.Set(nameof(StandTurnPages), value);
    partial void OnStandHintSeenChanged(bool value) => _store.Set(nameof(StandHintSeen), value);
    partial void OnVerbosityChanged(Verbosity value) => _store.Set(nameof(Verbosity), value);

    partial void OnEngineAddressChanged(string value)
    {
        _store.Set(nameof(EngineAddress), value);
        Connection?.Refresh();
    }

    public Uri EngineUri => Uri.TryCreate(EngineAddress, UriKind.Absolute, out var u) ? u : EngineClient.DefaultBaseAddress;

    /// <summary>Engines advertising themselves on the local network, from the last search.</summary>
    public ObservableCollection<DiscoveredEngine> DiscoveredEngines { get; } = [];

    [RelayCommand]
    private async Task FindEnginesAsync()
    {
        EngineStatus = _s["Settings_Engine_Searching"];
        var found = await _discovery.BrowseAsync(TimeSpan.FromSeconds(3));
        DiscoveredEngines.Clear();
        foreach (var e in found) DiscoveredEngines.Add(e);
        EngineStatus = found.Count switch
        {
            0 => _s["Settings_Engine_NoneFound"],
            1 => _s.Format("Settings_Engine_FoundOne", found[0].ComputerName),
            _ => _s.Format("Settings_Engine_FoundMany", found.Count),
        };
        _announcer.Announce(EngineStatus, AnnouncementKind.Important);
    }

    /// <summary>
    /// Points the app at a discovered engine. A credential belongs to a server id, not an address: an engine
    /// already paired is used with its own token wherever it now is, and choosing another engine keeps the
    /// first one's record for later.
    /// </summary>
    [RelayCommand]
    private void UseEngine(DiscoveredEngine? engine)
    {
        if (engine is null) return;
        EngineAddress = engine.BaseAddress.ToString();
        if (engine.ServerId is { } id && !string.Equals(id, Credentials.CurrentServerId, StringComparison.OrdinalIgnoreCase)
            && Credentials.CurrentServerId != EngineCredentials.LegacyKey)
            Credentials.CurrentServerId = id;
        EngineToken = Credentials.Current?.Token;
        EngineStatus = Credentials.Current is not null
            ? _s.Format("Settings_Engine_ChosenPaired", engine.ComputerName)
            : _s.Format("Settings_Engine_Chosen", engine.ComputerName);
        _announcer.Announce(EngineStatus, AnnouncementKind.Important);
        Connection.Kick();
    }

    /// <summary>
    /// Checks the engine. A stored token is checked with /v1/devices/me first: when it still works the
    /// typed code is not needed; after a 401 it is dropped and the typed code (if any) pairs again.
    /// </summary>
    [RelayCommand]
    private async Task ConnectAsync(IEngineClient? engine)
    {
        engine ??= _clients(EngineUri, EngineToken);
        try
        {
            var health = await engine.GetHealthAsync();
            if (!health.AuthRequired)
            {
                Connected(health);
                return;
            }

            var stored = health.ServerId is { } id ? Credentials.Get(id) : null;
            stored ??= Credentials.Current is { } current && (current.ServerId == EngineCredentials.LegacyKey || health.ServerId is null) ? current : null;
            // Another engine than the one in use: the first one's record stays for later, this one is now current.
            if (stored is null && health.ServerId is { } other) Credentials.CurrentServerId = other;
            if (stored is not null)
            {
                engine.Token = stored.Token;
                try
                {
                    var me = await engine.GetThisDeviceAsync();
                    Remember(stored, health, me.ServerId);
                    Connected(health);
                    return;
                }
                catch (EngineException e) when (e.Status == HttpStatusCode.NotFound)
                {
                    Connected(health); // a static token: not a paired device, but it works
                    return;
                }
                catch (EngineException e) when (e.Status == HttpStatusCode.Unauthorized)
                {
                    Credentials.Remove(stored.ServerId);
                    EngineToken = null;
                    engine.Token = null;
                }
            }

            if (string.IsNullOrWhiteSpace(PairingCode))
            {
                Say(_s[stored is null ? "Settings_Engine_NeedsCode" : "Settings_Engine_Forgotten"]);
                return;
            }
            var paired = await engine.PairDeviceAsync(PairingCode.Trim(), Environment.MachineName, Platform);
            SavePairing(paired.Token, paired.DeviceId, paired.ServerId ?? health.ServerId, paired.ServerName ?? health.ServerName, engine.BaseAddress);
            engine.Token = paired.Token;
            PairingCode = "";
            Connected(health);
        }
        catch (EngineException e)
        {
            Say(Explain(e));
        }
    }

    /// <summary>What went wrong in plain words (the engine's own text is for logs, not for the screen).</summary>
    private string Explain(EngineException e) => _s[e.Status switch
    {
        HttpStatusCode.Forbidden => "Settings_Engine_CodeWrong",
        HttpStatusCode.TooManyRequests => "Settings_Engine_Locked",
        HttpStatusCode.Unauthorized => "Settings_Engine_Forgotten",
        null => "Settings_Engine_Unreachable",
        _ => "Settings_Engine_Failed",
    }];

    /// <summary>
    /// "Allow it on the computer": no code to read or type (WCAG 3.3.8). The computer shows this PC's name
    /// and a match code; this screen shows the same code and waits, up to 2 minutes, for Allow.
    /// </summary>
    [RelayCommand]
    private async Task AskComputerAsync(IEngineClient? engine)
    {
        engine ??= _clients(EngineUri, null);
        CancelAsk();
        var cts = _ask = new CancellationTokenSource();
        try
        {
            var health = await engine.GetHealthAsync(cts.Token);
            var request = await engine.RequestPairingAsync(Environment.MachineName, Platform, cts.Token);
            MatchCode = request.MatchCode;
            Say(_s.Format("Settings_Engine_AskWaiting", request.MatchCode));
            var deadline = _time.GetUtcNow() + AskTimeout;
            while (_time.GetUtcNow() < deadline)
            {
                await Task.Delay(AskPollInterval, _time, cts.Token);
                var r = await engine.PollPairingRequestAsync(request.RequestId, cts.Token);
                if (r.Status == PairRequestStatus.Approved && r.Token is { } token)
                {
                    SavePairing(token, r.DeviceId, r.ServerId ?? health.ServerId, r.ServerName ?? health.ServerName, engine.BaseAddress);
                    engine.Token = token;
                    MatchCode = null;
                    Connected(health);
                    return;
                }
                if (r.Status == PairRequestStatus.Denied)
                {
                    MatchCode = null;
                    Say(_s["Settings_Engine_AskDenied"]);
                    return;
                }
            }
            MatchCode = null;
            Say(_s["Settings_Engine_AskExpired"]);
        }
        catch (OperationCanceledException) when (cts.IsCancellationRequested)
        {
            MatchCode = null;
        }
        catch (EngineException e)
        {
            MatchCode = null;
            Say(e.Status switch
            {
                HttpStatusCode.TooManyRequests => _s["Settings_Engine_AskBusy"],
                HttpStatusCode.NotFound => _s["Settings_Engine_AskExpired"],
                _ => Explain(e),
            });
        }
        finally
        {
            if (ReferenceEquals(_ask, cts)) _ask = null;
            cts.Dispose();
        }
    }

    /// <summary>Stops waiting for the computer (the dialog closed, or Cancel).</summary>
    [RelayCommand]
    public void CancelAsk()
    {
        try { _ask?.Cancel(); }
        catch (ObjectDisposedException) { }
        MatchCode = null;
    }

    /// <summary>
    /// A brasscribe://pair link (the QR code, or the link opened on this PC): the first listed address that
    /// answers with the link's server id, else that id on the network; then the code in the link, or, when
    /// there is none, the approve-on-the-computer path.
    /// </summary>
    public async Task<bool> PairFromLinkAsync(string text)
    {
        var problem = PairingLink.TryParse(text, out var link);
        if (problem != PairingLinkProblem.None || link is null)
        {
            Say(_s[problem switch
            {
                PairingLinkProblem.NewerVersion => "Settings_Link_Newer",
                PairingLinkProblem.NeedsPinning => "Settings_Link_Newer",
                _ => "Settings_Link_Invalid",
            }]);
            return false;
        }
        string computer = ServerNames.ComputerName(link.ServerName);
        Say(_s.Format("Settings_Link_Looking", computer));
        var candidates = new List<Uri>(link.Hosts);
        Uri? found = null;
        foreach (var host in candidates)
            if (await ServerIdAtAsync(host) is { } id && string.Equals(id, link.ServerId, StringComparison.OrdinalIgnoreCase)) { found = host; break; }
        if (found is null)
        {
            IReadOnlyList<DiscoveredEngine> seen;
            try { seen = await _discovery.BrowseAsync(ConnectionMonitor.BrowseTime); }
            catch (Exception e) when (e is System.Net.Sockets.SocketException or InvalidOperationException) { seen = []; }
            found = seen.FirstOrDefault(e => string.Equals(e.ServerId, link.ServerId, StringComparison.OrdinalIgnoreCase))?.BaseAddress;
        }
        if (found is null)
        {
            Say(_s.Format("Settings_Link_NotFound", computer));
            return false;
        }

        EngineAddress = found.ToString();
        Credentials.CurrentServerId = link.ServerId;
        EngineToken = Credentials.Current?.Token;
        var engine = _clients(found, null);
        if (link.Code is { } code)
        {
            PairingCode = code;
            await ConnectAsync(engine);
        }
        else await AskComputerAsync(engine);
        return Credentials.Current is not null;
    }

    /// <summary>"Unpair": the engine forgets this PC, and this PC forgets the engine.</summary>
    [RelayCommand]
    private async Task UnpairAsync()
    {
        if (Credentials.Current is not { } current) return;
        try { await _clients(EngineUri, current.Token).UnpairAsync(); }
        catch (Exception e) when (e is EngineException or HttpRequestException or NotSupportedException or TaskCanceledException) { }
        Credentials.Remove(current.ServerId);
        EngineToken = null;
        Say(_s.Format("Settings_Engine_Unpaired", ServerNames.ComputerName(current.ServerName ?? "")));
        Connection.Kick();
    }

    private async Task<string?> ServerIdAtAsync(Uri address)
    {
        using var timeout = new CancellationTokenSource(ConnectionMonitor.ProbeTimeout);
        try { return (await _clients(address, null).GetHealthAsync(timeout.Token)).ServerId; }
        catch (Exception e) when (e is EngineException or HttpRequestException or OperationCanceledException or System.Text.Json.JsonException) { return null; }
    }

    private void SavePairing(string token, string? deviceId, string? serverId, string? serverName, Uri address)
    {
        // Engines from before pairing-once have no server id: the address stands in for it.
        var id = serverId is { Length: > 0 } ? serverId : "address:" + address;
        Credentials.Save(new EngineCredential(id, token, serverName, deviceId, address.ToString(), _time.GetUtcNow()));
        if (Credentials.Get(EngineCredentials.LegacyKey) is not null && id != EngineCredentials.LegacyKey) Credentials.Remove(EngineCredentials.LegacyKey);
        EngineToken = token;
    }

    private void Remember(EngineCredential stored, Health health, string? serverId)
    {
        var record = stored with { LastAddress = EngineUri.ToString(), LastOk = _time.GetUtcNow(), ServerName = health.ServerName ?? stored.ServerName };
        if (stored.ServerId == EngineCredentials.LegacyKey && (serverId ?? health.ServerId) is { Length: > 0 } id)
            record = Credentials.Adopt(record, id, health.ServerName);
        else Credentials.Save(record);
        EngineToken = record.Token;
    }

    private void Connected(Health health)
    {
        string name = ServerNames.ComputerName(health.ServerName) is { Length: > 0 } n ? n : _s["Connection_YourComputer"];
        Say(_s.Format("Settings_Engine_Connected", name, health.Version, health.Device.ToUpperInvariant()));
        Connection.Kick();
        Connection.Start();
    }

    private void Say(string text)
    {
        EngineStatus = text;
        _announcer.Announce(text, AnnouncementKind.Important);
    }
}

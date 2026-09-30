using System.Collections.ObjectModel;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.ViewModels;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Bandroom.Core.Pairing;

/// <summary>
/// The Pair a phone window (§3.4): three ways, easiest first. While it is open the engine's pairing
/// window is open with no expiry (ttl_s null); it closes when the window closes. The code is single-use,
/// so "Pair another phone" asks for a fresh one. A new device in /v1/devices means a phone just paired.
/// </summary>
public sealed partial class PairViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly Func<IEngineApi?> _api;
    private readonly IAnnouncer _announcer;
    private readonly TimeProvider _time;
    private HashSet<string>? _knownDevices;
    private DateTimeOffset? _expiresAt;

    public PairViewModel(IStrings strings, Func<IEngineApi?> api, IAnnouncer? announcer = null, TimeProvider? time = null)
    {
        _s = strings;
        _api = api;
        _announcer = announcer ?? new NullAnnouncer();
        _time = time ?? TimeProvider.System;
    }

    public IStrings Strings => _s;
    public string Title => _s["Pair_Title"];
    public string Lead => _s["Pair_Lead"];
    public string Way2 => _s["Pair_Way2"];
    public string Way3 => _s["Pair_Way3"];
    public string QrCaption => _s["Pair_Qr_Caption"];
    public string Limit => _s["Pair_Limit"];
    public string HelpSummary => _s["Pair_Help_Summary"];
    public string HelpWifi => _s["Pair_Help_Wifi"];
    public string AnotherLabel => _s["Pair_Another"];
    public string DoneLabel => _s["Pair_Close"];
    public string AllowLabel => _s["Allow_Ok"];
    public string DenyLabel => _s["Allow_No"];
    public string AllowBody => _s["Allow_Body"];
    public string AllowMatchLabel => _s["Allow_Match"];
    public string CloseLabel => _s["Close"];
    public string LockoutText => _s["Pair_Lockout"];

    [ObservableProperty] public partial string Way1Before { get; set; } = "";
    [ObservableProperty] public partial string Way1Name { get; set; } = "";
    [ObservableProperty] public partial string Way1After { get; set; } = "";
    [ObservableProperty] public partial string Code { get; set; } = "";
    [ObservableProperty] public partial string CodeDisplay { get; set; } = "";
    [ObservableProperty] public partial string CodeSpoken { get; set; } = "";
    [ObservableProperty] public partial string QrPayload { get; set; } = "";
    [ObservableProperty] public partial string QrSpoken { get; set; } = "";
    [ObservableProperty] public partial string HelpAddress { get; set; } = "";
    [ObservableProperty] public partial string HelpAddressSpoken { get; set; } = "";
    [ObservableProperty] public partial string WaitingText { get; set; } = "";
    [ObservableProperty] public partial bool IsWaiting { get; set; }
    [ObservableProperty] public partial string PairedText { get; set; } = "";
    [ObservableProperty] public partial bool HasPaired { get; set; }
    [ObservableProperty] public partial bool IsOpen { get; set; }
    [ObservableProperty] public partial string ErrorText { get; set; } = "";
    [ObservableProperty] public partial bool HasError { get; set; }
    /// <summary>Too many wrong codes: code entry is locked for a while; allowing on the computer still works.</summary>
    [ObservableProperty] public partial bool IsLockedOut { get; set; }

    /// <summary>Phones waiting to be allowed, newest last; the window shows the first.</summary>
    public ObservableCollection<AllowRequestViewModel> Requests { get; } = [];

    /// <summary>"Phone paired" moves focus to that line (§3.4, after pairing).</summary>
    public event Action? PairedFocusRequested;

    /// <summary>Opens (or re-opens, for another phone) the engine's pairing window with no expiry.</summary>
    [RelayCommand]
    public async Task OpenAsync()
    {
        var api = _api();
        if (api is null) { ShowError(); return; }
        try
        {
            if (_knownDevices is null) await SnapshotDevicesAsync(api);
            var state = await api.OpenPairingAsync(new PairingOpenRequest(TtlS: null, SingleUse: true, Extend: false));
            Show(state);
            HasPaired = false;
            PairedText = "";
            HasError = false;
            _announcer.Announce(_s["Pair_Waiting_A11y"]);
        }
        catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException or System.Text.Json.JsonException)
        {
            ShowError();
        }
    }

    private void ShowError()
    {
        HasError = true;
        IsOpen = false;
        ErrorText = _s["Pair_Unavailable"];
    }

    private async Task SnapshotDevicesAsync(IEngineApi api) =>
        _knownDevices = (await api.GetDevicesAsync()).Select(d => d.DeviceId).ToHashSet();

    public void Show(PairingState state)
    {
        IsOpen = state.Open && state.Code is not null;
        Code = state.Code ?? "";
        CodeDisplay = CodeText.Display(Code);
        CodeSpoken = CodeText.Spoken(_s, Code);
        QrPayload = state.Uri;
        QrSpoken = _s.Format("Pair_Qr_A11y", HostName(state.ServerName), CodeDisplay);
        _expiresAt = DateTimeOffset.TryParse(state.ExpiresAt, out var t) ? t : null;
        ShowLockout(state);
        var host = HostName(state.ServerName);
        // The deck's way 1 with the computer's name in bold: split around it.
        string full = _s.Format("Pair_Way1", "\u0001");
        int at = full.IndexOf('\u0001', StringComparison.Ordinal);
        Way1Before = at >= 0 ? full[..at] : full;
        Way1After = at >= 0 ? full[(at + 1)..] : "";
        Way1Name = _s.Format("Header", host);
        if (state.Hosts.FirstOrDefault() is { } first && first.LastIndexOf(':') is var colon and > 0)
        {
            string ip = first[..colon], port = first[(colon + 1)..];
            HelpAddress = _s.Format("Pair_Help_Address", ip, port);
            HelpAddressSpoken = _s.Format("Pair_Help_Address", CodeText.SpokenAddress(_s, ip), port);
        }
        else
        {
            HelpAddress = HelpAddressSpoken = "";
        }
        IsWaiting = IsOpen;
        WaitingText = _s["Pair_Waiting"];
    }

    /// <summary>Shows the lockout while now &lt; locked_until, announced once when it starts.</summary>
    private void ShowLockout(PairingState state)
    {
        bool locked = state.LockedUntilTime is { } until && _time.GetUtcNow() < until;
        if (locked && !IsLockedOut) _announcer.Announce(LockoutText);
        IsLockedOut = locked;
    }

    /// <summary>The name part of "Brasscribe on &lt;name&gt;", so Norwegian can say "Brasscribe på &lt;name&gt;".</summary>
    public static string HostName(string serverName) =>
        serverName.StartsWith("Brasscribe on ", StringComparison.Ordinal) ? serverName["Brasscribe on ".Length..] : serverName;

    /// <summary>
    /// One poll while the window is open: a device that wasn't there before means a phone just paired;
    /// a code with an expiry (an engine that ignores ttl_s null) is extended well before it runs out.
    /// </summary>
    public async Task TickAsync(CancellationToken ct = default)
    {
        var api = _api();
        if (api is null || !IsOpen && !HasPaired) return;
        try
        {
            var devices = await api.GetDevicesAsync(ct);
            if (_knownDevices is not null)
            {
                var added = devices.Where(d => !_knownDevices.Contains(d.DeviceId)).ToList();
                foreach (var d in added)
                {
                    PairedText = _s.Format("Pair_Done", d.Name);
                    HasPaired = true;
                    IsWaiting = false;
                    _announcer.Announce(PairedText);
                    PairedFocusRequested?.Invoke();
                }
            }
            // The spent single-use code (the engine closes it) and the wrong-code lockout.
            var current = await api.GetPairingAsync(ct);
            if (HasPaired) IsOpen = current.Open && current.Code is not null;
            ShowLockout(current);
            _knownDevices = devices.Select(d => d.DeviceId).ToHashSet();

            if (IsOpen && _expiresAt is { } exp && exp - _time.GetUtcNow() < TimeSpan.FromMinutes(2))
            {
                var state = await api.OpenPairingAsync(new PairingOpenRequest(TtlS: 600, SingleUse: true, Extend: true), ct);
                _expiresAt = DateTimeOffset.TryParse(state.ExpiresAt, out var t) ? t : null;
            }
        }
        catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException or System.Text.Json.JsonException) { }
    }

    /// <summary>Done: closes the engine's pairing window, so the code stops working.</summary>
    [RelayCommand]
    public async Task CloseAsync()
    {
        IsOpen = false;
        if (_api() is not { } api) return;
        try { await api.ClosePairingAsync(); }
        catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException or System.Text.Json.JsonException) { }
    }

    /// <summary>A phone chose this computer (from the request watcher).</summary>
    public AllowRequestViewModel AddRequest(PairRequestInfo r, Func<string, bool, Task<PairDecision>> decide)
    {
        var vm = new AllowRequestViewModel(_s, r, decide, _announcer);
        vm.Finished += () => Requests.Remove(vm);
        Requests.Add(vm);
        return vm;
    }

    public void RequestGone(string requestId)
    {
        foreach (var r in Requests.Where(r => r.RequestId == requestId && !r.IsExpired && !r.IsDecided).ToList())
            r.MarkExpired();
    }
}

/// <summary>"Allow Kari's iPhone?" with the four-digit match number both screens show.</summary>
public sealed partial class AllowRequestViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly Func<string, bool, Task<PairDecision>> _decide;
    private readonly IAnnouncer _announcer;

    public AllowRequestViewModel(IStrings s, PairRequestInfo r, Func<string, bool, Task<PairDecision>> decide, IAnnouncer announcer)
    {
        _s = s;
        _decide = decide;
        _announcer = announcer;
        RequestId = r.RequestId;
        DeviceName = r.Name;
        MatchCode = r.MatchCode;
        Title = s.Format("Allow_Title", r.Name);
        MatchSpoken = s.Format("Allow_Match_A11y", string.Join(' ', r.MatchCode.ToCharArray()));
    }

    public string RequestId { get; }
    public string DeviceName { get; }
    public string MatchCode { get; }
    public string Title { get; }
    public string Body => _s["Allow_Body"];
    public string MatchLabel => _s["Allow_Match"];
    public string MatchSpoken { get; }
    public string AllowLabel => _s["Allow_Ok"];
    public string DenyLabel => _s["Allow_No"];
    public string ExpiredText => _s["Allow_Expired"];
    public string FailedText => _s["Allow_Failed"];
    public string CloseLabel => _s["Close"];

    [ObservableProperty] public partial bool IsExpired { get; set; }
    /// <summary>The last answer didn't get through: Allow and Don't allow stay, to try again.</summary>
    [ObservableProperty] public partial bool HasFailed { get; set; }
    [ObservableProperty] public partial bool IsDecided { get; set; }
    public bool IsActive => !IsExpired && !IsDecided;

    partial void OnIsExpiredChanged(bool value) => OnPropertyChanged(nameof(IsActive));
    partial void OnIsDecidedChanged(bool value) => OnPropertyChanged(nameof(IsActive));

    public event Action? Finished;

    public void MarkExpired()
    {
        IsExpired = true;
        _announcer.Announce(ExpiredText);
    }

    [RelayCommand]
    private async Task AllowAsync()
    {
        switch (await DecideAsync(true))
        {
            case PairDecision.Lapsed: MarkExpired(); break;
            case PairDecision.Done: Finish(); break;
        }
    }

    [RelayCommand]
    private async Task DenyAsync()
    {
        if (await DecideAsync(false) != PairDecision.Failed) Finish();
    }

    /// <summary>An answer that doesn't get through is shown on the card, never thrown on the UI thread.</summary>
    private async Task<PairDecision> DecideAsync(bool approve)
    {
        PairDecision result;
        try { result = await _decide(RequestId, approve); }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or EngineHttpException or System.Text.Json.JsonException)
        {
            result = PairDecision.Failed;
        }
        HasFailed = result == PairDecision.Failed;
        if (HasFailed) _announcer.Announce(FailedText);
        return result;
    }

    private void Finish()
    {
        IsDecided = true;
        Finished?.Invoke();
    }

    [RelayCommand]
    private void Dismiss() => Finished?.Invoke();
}

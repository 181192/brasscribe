using System.Globalization;
using System.Net;
using Kalli.Scribe.Services;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Kalli.Scribe.Engine;

/// <summary>The connection states the Play apps show (the same on every platform).</summary>
public enum ConnectionState
{
    /// <summary>No engine paired, or it could not be found for 2 minutes.</summary>
    Offline,
    /// <summary>The last check failed; looking again at the last address, then by server id on the network.</summary>
    Reconnecting,
    /// <summary>The last check succeeded.</summary>
    Connected,
    /// <summary>The engine answered 401: it forgot this device (revoked, reset or unused for long).</summary>
    NeedsPairing,
    /// <summary>The engine's interface version is higher than this app's: only its heartbeat is asked until the app is updated.</summary>
    UpdateApp,
    /// <summary>The engine's interface version is lower or has none: only its heartbeat is asked until the computer's side is updated.</summary>
    UpdateBandroom,
}

/// <summary>
/// Keeps track of the paired engine while the app is in front: a heartbeat every 20 s, which is one request,
/// GET /v1/devices/me (it names the engine and its interface version). GET /v1/health is asked instead while nothing
/// is paired, and after a 401 or 404 there, to learn whose answer that was. When the heartbeat fails: the last
/// address and then the network (mDNS, matched by server id) with backoff 2, 4, 8, 16, 30 s; after 2 minutes it gives
/// up until <see cref="Kick"/> (Connect, network change, the app coming back). Only a 401 from our own engine asks
/// for pairing again; an address change never drops the credential. Due tokens are rotated, the new one stored
/// before it is used. Another engine at the address is not ours, whatever its version: ours is looked for. Our own
/// engine with another interface version (<see cref="InterfaceMatch"/>) is asked for nothing but that heartbeat:
/// the row says which of the two to update and where to get it, the credential stays, and the heartbeat goes on,
/// so it connects again once that is done.
/// </summary>
public sealed partial class ConnectionMonitor : ObservableObject
{
    public static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(20);
    public static readonly TimeSpan GiveUpAfter = TimeSpan.FromMinutes(2);
    public static readonly TimeSpan ProbeTimeout = TimeSpan.FromSeconds(4);
    public static readonly TimeSpan BrowseTime = TimeSpan.FromSeconds(3);
    /// <summary>With nothing paired, a local engine (no pairing needed) is looked for this often.</summary>
    public static readonly TimeSpan UnpairedInterval = TimeSpan.FromSeconds(30);
    /// <summary>Failed checks in a row before a connected row says "Looking for…".</summary>
    public const int FailuresBeforeLooking = 2;

    private static readonly TimeSpan[] Backoff = [TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(16), TimeSpan.FromSeconds(30)];

    private readonly EngineCredentials _credentials;
    private readonly Func<Uri, string?, IEngineClient> _clients;
    private readonly IEngineDiscovery _discovery;
    private readonly Func<Uri> _address;
    private readonly Action<Uri> _setAddress;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly TimeProvider _time;
    private readonly SemaphoreSlim _checking = new(1, 1);

    private DateTimeOffset? _failingSince;
    private int _failures;
    private bool _checkedOnce;
    private CancellationTokenSource? _run;
    private TaskCompletionSource _kick = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public ConnectionMonitor(EngineCredentials credentials, Func<Uri, string?, IEngineClient> clients, IEngineDiscovery discovery,
        Func<Uri> address, Action<Uri> setAddress, IAnnouncer announcer, IStrings strings, TimeProvider? time = null)
    {
        _credentials = credentials;
        _clients = clients;
        _discovery = discovery;
        _address = address;
        _setAddress = setAddress;
        _announcer = announcer;
        _s = strings;
        _time = time ?? TimeProvider.System;
        ServerName = credentials.Current?.ServerName;
        // Until the first check, the row shows the last known state (no "Looking for…" flash at launch).
        if (credentials.Current is { LastOk: not null }) State = ConnectionState.Connected;
        UpdateTexts();
    }

    [ObservableProperty] public partial ConnectionState State { get; private set; } = ConnectionState.Offline;

    /// <summary>"Brasscribe on studio-mac", as the engine names itself.</summary>
    [ObservableProperty] public partial string? ServerName { get; private set; }

    /// <summary>The status row's words ("Connected to Brasscribe on studio-mac").</summary>
    [ObservableProperty] public partial string StatusText { get; private set; } = "";

    /// <summary>Where the newest Brasscribe Play and Bandroom are: the row's action while one of the two must be updated.</summary>
    public static readonly Uri LatestRelease = new("https://github.com/181192/brasscribe/releases/latest");

    /// <summary>The label of the row's action: "Connect" when offline, "Pair again" after a 401, "Get the update" for another interface version, else empty.</summary>
    [ObservableProperty] public partial string ActionText { get; private set; } = "";

    /// <summary>What the action does, for screen readers.</summary>
    [ObservableProperty] public partial string ActionHelp { get; private set; } = "";

    /// <summary>The page the action opens; null when the action is Connect or Pair again.</summary>
    public Uri? ActionUri => NeedsUpdate ? LatestRelease : null;

    /// <summary>For the band's tech person: address, server id and when the engine last answered.</summary>
    [ObservableProperty] public partial string DetailsText { get; private set; } = "";

    [ObservableProperty] public partial DateTimeOffset? LastOk { get; private set; }

    public bool HasAction => State is ConnectionState.Offline or ConnectionState.NeedsPairing || NeedsUpdate;
    public bool IsConnected => State == ConnectionState.Connected;

    /// <summary>The last check found that the app and the engine have different interface versions.</summary>
    public bool NeedsUpdate => State is ConnectionState.UpdateApp or ConnectionState.UpdateBandroom;

    /// <summary>The stored credential changed (paired, rotated, moved to its server id, dropped after a 401).</summary>
    public event EventHandler? CredentialChanged;

    /// <summary>After a 401, the engine forgot this device and this is the only reason to ask for a code.</summary>
    public event EventHandler? PairingNeeded;

    /// <summary>The wait before the next check in the current state; null means wait for <see cref="Kick"/>.</summary>
    public TimeSpan? NextDelay => State switch
    {
        ConnectionState.Connected when _failures > 0 => Backoff[0],
        ConnectionState.Connected or ConnectionState.UpdateApp or ConnectionState.UpdateBandroom => HeartbeatInterval,
        ConnectionState.Reconnecting => Backoff[Math.Clamp(_failures - 1, 0, Backoff.Length - 1)],
        ConnectionState.Offline when _credentials.Current is null => UnpairedInterval,
        _ => null, // gave up, or needs pairing: until Connect, a network change or the app coming back
    };

    /// <summary>Starts the heartbeat (the app is in front). Calling it again while running just checks now.</summary>
    public void Start()
    {
        if (_run is not null) { Kick(); return; }
        _run = new CancellationTokenSource();
        _ = RunAsync(_run.Token);
    }

    /// <summary>Stops the heartbeat (the app is minimised or closing).</summary>
    public void Stop()
    {
        _run?.Cancel();
        _run?.Dispose();
        _run = null;
    }

    public bool IsRunning => _run is not null;

    /// <summary>The row shows a state given with <see cref="Show"/> (sample content): no computer stands behind it, and none is asked.</summary>
    public bool IsPreview { get; private set; }

    /// <summary>Check now, and start over after giving up (Connect, network change).</summary>
    public void Kick()
    {
        _failingSince = null;
        _failures = 0;
        _kick.TrySetResult();
    }

    /// <summary>
    /// Shows a fixed state without checking (screenshots and previews). The row is about the computer named, wherever
    /// the address setting points.
    /// </summary>
    public void Show(ConnectionState state, string? serverName)
    {
        IsPreview = true;
        ServerName = serverName;
        State = state;
        _checkedOnce = true;
        UpdateTexts();
    }

    private async Task RunAsync(CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                // A check that fails in an unexpected way must not end the heartbeat: the next one tries again.
                try { await CheckAsync(ct); }
                catch (Exception e) when (e is not OperationCanceledException)
                {
                    System.Diagnostics.Trace.TraceWarning($"Connection check failed: {e}");
                }
                var kick = _kick.Task;
                using (var wait = CancellationTokenSource.CreateLinkedTokenSource(ct))
                {
                    await Task.WhenAny(kick, Task.Delay(NextDelay ?? Timeout.InfiniteTimeSpan, _time, wait.Token));
                    wait.Cancel();
                }
                if (kick.IsCompleted) _kick = new(TaskCreationOptions.RunContinuationsAsynchronously);
            }
        }
        catch (OperationCanceledException) { }
    }

    /// <summary>One check and the state it leads to.</summary>
    public async Task<ConnectionState> CheckAsync(CancellationToken ct = default)
    {
        await _checking.WaitAsync(ct);
        try
        {
            var next = await DecideAsync(ct);
            Set(next);
            return next;
        }
        finally { _checking.Release(); }
    }

    private async Task<ConnectionState> DecideAsync(CancellationToken ct)
    {
        var address = _address();
        var credential = _credentials.Current;
        if (credential is null)
        {
            // Nothing paired: a local engine that needs no pairing still counts.
            var health = await HealthAsync(address, ct);
            if (health is not null && UpdateFor(health.InterfaceVersion) is { } update) return Answered(update, health.ServerName);
            if (health is { AuthRequired: false })
            {
                Succeeded(address, health.ServerName);
                return ConnectionState.Connected;
            }
            // After a 401 the row keeps saying "Pair again" until the device is paired.
            return State == ConnectionState.NeedsPairing ? ConnectionState.NeedsPairing : ConnectionState.Offline;
        }

        var probe = await ProbeAsync(address, credential, ct);
        if (probe == Probe.Ok) return ConnectionState.Connected;
        if (probe == Probe.Unauthorized) return Forget(credential);
        if (UpdateFor(probe) is { } needed) return Answered(needed, credential.ServerName);

        // Unreachable, or another engine at that address: the last known address, then the network by id.
        foreach (var other in await CandidatesAsync(address, credential, ct))
        {
            var p = await ProbeAsync(other, credential, ct);
            if (p == Probe.Ok)
            {
                _setAddress(other);
                return ConnectionState.Connected;
            }
            if (p == Probe.Unauthorized) return Forget(credential);
            if (UpdateFor(p) is { } moved)
            {
                _setAddress(other);
                return Answered(moved, credential.ServerName);
            }
        }

        var now = _time.GetUtcNow();
        _failingSince ??= now;
        _failures++;
        if (now - _failingSince.Value >= GiveUpAfter) return ConnectionState.Offline;
        // One missed heartbeat is not news: the row keeps its last state until the second one in a row.
        return _failures < FailuresBeforeLooking && State == ConnectionState.Connected ? ConnectionState.Connected : ConnectionState.Reconnecting;
    }

    private async Task<IReadOnlyList<Uri>> CandidatesAsync(Uri tried, EngineCredential credential, CancellationToken ct)
    {
        var list = new List<Uri>();
        if (credential.LastAddress is { } last && Uri.TryCreate(last, UriKind.Absolute, out var lastUri) && lastUri != tried) list.Add(lastUri);
        IReadOnlyList<DiscoveredEngine> found;
        try { found = await _discovery.BrowseAsync(BrowseTime, ct); }
        catch (Exception e) when (e is not OperationCanceledException || !ct.IsCancellationRequested) { found = []; }
        foreach (var e in found)
            if (string.Equals(e.ServerId, credential.ServerId, StringComparison.OrdinalIgnoreCase) && e.BaseAddress != tried && !list.Contains(e.BaseAddress))
                list.Add(e.BaseAddress);
        return list;
    }

    private enum Probe { Ok, Unauthorized, Failed, UpdateApp, UpdateBandroom }

    /// <summary>
    /// One request: GET /v1/devices/me with the stored token. Its answer names the engine and its interface version,
    /// and they are looked at in that order: another engine at this address is not ours (it is not there: ours is
    /// looked for), and ours with another interface version is asked nothing more. A 401 or a 404 (loopback, or a
    /// static token) names no engine, so health is asked to learn whose answer it was.
    /// </summary>
    private async Task<Probe> ProbeAsync(Uri address, EngineCredential credential, CancellationToken ct)
    {
        var client = _clients(address, credential.Token);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(ProbeTimeout);
        DeviceSelf me;
        try
        {
            me = await client.GetThisDeviceAsync(timeout.Token);
        }
        catch (EngineException e) when (e.Status is HttpStatusCode.Unauthorized or HttpStatusCode.NotFound)
        {
            // Health needs no token, and is asked without one: an engine that forgot this device must still answer it.
            var health = await HealthAsync(address, ct);
            if (health is null || !SameEngine(credential, health.ServerId)) return Probe.Failed;
            if (UpdateFor(health.InterfaceVersion) is { } update) return ProbeFor(update);
            if (e.Status == HttpStatusCode.Unauthorized) return Probe.Unauthorized;
            Succeeded(address, health.ServerName, credential);
            return Probe.Ok;
        }
        catch (Exception e) when (IsUnreachable(e, ct))
        {
            return Probe.Failed;
        }

        if (!SameEngine(credential, me.ServerId)) return Probe.Failed; // another engine now answers at this address
        if (UpdateFor(me.InterfaceVersion) is { } needed) return ProbeFor(needed);
        var record = Succeeded(address, credential.ServerName, credential, ParseTime(me.RotateAfter));
        if (record is not null) await RotateIfDueAsync(client, record, ct);
        return Probe.Ok;
    }

    /// <summary>The state for an engine whose interface version is not this app's; null when it is the same.</summary>
    private static ConnectionState? UpdateFor(int? engineVersion) => InterfaceMatch.Of(engineVersion) switch
    {
        InterfaceAnswer.UpdateApp => ConnectionState.UpdateApp,
        InterfaceAnswer.UpdateBandroom => ConnectionState.UpdateBandroom,
        _ => null,
    };

    private static ConnectionState? UpdateFor(Probe probe) => probe switch
    {
        Probe.UpdateApp => ConnectionState.UpdateApp,
        Probe.UpdateBandroom => ConnectionState.UpdateBandroom,
        _ => null,
    };

    private static Probe ProbeFor(ConnectionState update) => update == ConnectionState.UpdateApp ? Probe.UpdateApp : Probe.UpdateBandroom;

    /// <summary>
    /// The engine answered, with another interface version: it is not being looked for, and "Last answered" says now.
    /// Its credential stays as it was (the stored last good check too: the next launch starts from that).
    /// </summary>
    private ConnectionState Answered(ConnectionState update, string? serverName)
    {
        _failingSince = null;
        _failures = 0;
        LastOk = _time.GetUtcNow();
        if (serverName is { Length: > 0 }) ServerName = serverName;
        return update;
    }

    private static bool SameEngine(EngineCredential credential, string? serverId) =>
        string.Equals(credential.ServerId, serverId, StringComparison.OrdinalIgnoreCase);

    private async Task<Health?> HealthAsync(Uri address, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(ProbeTimeout);
        try { return await _clients(address, null).GetHealthAsync(timeout.Token); }
        catch (Exception e) when (IsUnreachable(e, ct)) { return null; }
    }

    private static bool IsUnreachable(Exception e, CancellationToken ct) =>
        e is EngineException or HttpRequestException or System.Text.Json.JsonException or NotSupportedException
        || e is OperationCanceledException && !ct.IsCancellationRequested;

    /// <summary>Records a good check: the address, the time, the name.</summary>
    private EngineCredential? Succeeded(Uri address, string? serverName, EngineCredential? credential = null, DateTimeOffset? rotateAfter = null)
    {
        _failingSince = null;
        _failures = 0;
        var now = _time.GetUtcNow();
        LastOk = now;
        if (serverName is { Length: > 0 }) ServerName = serverName;
        if (credential is null) return null;
        var record = credential with
        {
            LastAddress = address.ToString(),
            LastOk = now,
            ServerName = ServerName ?? credential.ServerName,
            RotateAfter = rotateAfter ?? credential.RotateAfter,
        };
        try { _credentials.Save(record); }
        catch (Exception e) when (e is not OutOfMemoryException) { }
        return record;
    }

    /// <summary>Monthly rotation: the new token goes into the vault before it is used.</summary>
    private async Task RotateIfDueAsync(IEngineClient client, EngineCredential record, CancellationToken ct)
    {
        if (record.RotateAfter is not { } due || _time.GetUtcNow() < due) return;
        try
        {
            var rotated = await client.RotateTokenAsync(ct);
            _credentials.Save(record with { Token = rotated.Token, DeviceId = rotated.DeviceId, RotateAfter = null });
            CredentialChanged?.Invoke(this, EventArgs.Empty);
        }
        catch (Exception e) when (IsUnreachable(e, ct) || e is IOException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
        {
            // The old token keeps working; the next good check tries again.
        }
    }

    private ConnectionState Forget(EngineCredential credential)
    {
        _credentials.Remove(credential.ServerId);
        ServerName ??= credential.ServerName;
        CredentialChanged?.Invoke(this, EventArgs.Empty);
        PairingNeeded?.Invoke(this, EventArgs.Empty);
        return ConnectionState.NeedsPairing;
    }

    /// <summary>A change is announced politely; the first check after launch and repeated heartbeats are not.</summary>
    private void Set(ConnectionState next)
    {
        bool announce = _checkedOnce && next != State;
        State = next;
        _checkedOnce = true;
        UpdateTexts();
        if (announce) _announcer.Announce(StatusText);
    }

    partial void OnStateChanged(ConnectionState value)
    {
        OnPropertyChanged(nameof(HasAction));
        OnPropertyChanged(nameof(IsConnected));
        OnPropertyChanged(nameof(NeedsUpdate));
        OnPropertyChanged(nameof(ActionUri));
    }

    /// <summary>The computer part of the name in the app's own sentence ("Brasscribe på studio-mac" in Norwegian).</summary>
    public string ComputerName => ServerName is { Length: > 0 } n ? ServerNames.ComputerName(n) : _s["Connection_YourComputer"];

    private void UpdateTexts()
    {
        StatusText = State switch
        {
            ConnectionState.Connected => _s.Format("Connection_Connected", ComputerName),
            ConnectionState.Reconnecting => _s.Format("Connection_Reconnecting", ComputerName),
            ConnectionState.NeedsPairing => _s.Format("Connection_NeedsPairing", ComputerName),
            ConnectionState.UpdateApp => UpdateText(InterfaceAnswer.UpdateApp),
            ConnectionState.UpdateBandroom => UpdateText(InterfaceAnswer.UpdateBandroom),
            _ => _s["Connection_Offline"],
        };
        ActionText = State switch
        {
            ConnectionState.Offline => _s["Connection_Connect"],
            ConnectionState.NeedsPairing => _s["Connection_PairAgain"],
            ConnectionState.UpdateApp or ConnectionState.UpdateBandroom => _s["Connection_GetUpdate"],
            _ => "",
        };
        ActionHelp = State switch
        {
            ConnectionState.Offline or ConnectionState.NeedsPairing => _s["Connection_ConnectHelp"],
            ConnectionState.UpdateApp or ConnectionState.UpdateBandroom => _s["Connection_GetUpdateHelp"],
            _ => "",
        };
        var current = _credentials.Current;
        var parts = new List<string> { _s.Format("Connection_DetailsAddress", _address()) };
        if (current?.ServerId is { } id) parts.Add(_s.Format("Connection_DetailsServerId", id));
        if ((LastOk ?? current?.LastOk) is { } seen)
            parts.Add(_s.Format("Connection_DetailsLastSeen", seen.ToLocalTime().ToString("g", CultureInfo.CurrentCulture)));
        DetailsText = string.Join(Environment.NewLine, parts);
    }

    /// <summary>"Update Brasscribe on Studio PC. …" or "Update Brasscribe Play. …" for the engine this row is about.</summary>
    public string UpdateText(InterfaceAnswer answer) => UpdateText(_s, answer, onThisPc: !IsPreview && _address().IsLoopback, ServerName);

    /// <summary>
    /// The sentence that says which of the two to update, naming the computer as the other rows do: its own name, "this
    /// PC" for an engine on this PC, "your computer" when it has given no name.
    /// </summary>
    public static string UpdateText(IStrings s, InterfaceAnswer answer, bool onThisPc, string? serverName)
    {
        if (onThisPc && answer == InterfaceAnswer.UpdateBandroom) return s["Connection_UpdateBandroomHere"];
        string computer = onThisPc ? s["Connection_ThisPc"]
            : ServerNames.ComputerName(serverName) is { Length: > 0 } name ? name : s["Connection_YourComputer"];
        return s.Format(answer == InterfaceAnswer.UpdateApp ? "Connection_UpdateApp" : "Connection_UpdateBandroom", computer);
    }

    /// <summary>Refreshes the words after the address or the pairing changed elsewhere.</summary>
    public void Refresh()
    {
        if (ServerName is null && _credentials.Current?.ServerName is { } n) ServerName = n;
        UpdateTexts();
    }

    private static DateTimeOffset? ParseTime(string? iso) =>
        DateTimeOffset.TryParse(iso, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var t) ? t : null;
}

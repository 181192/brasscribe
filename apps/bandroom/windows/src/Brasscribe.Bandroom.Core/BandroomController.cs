using System.Net;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Downloads;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core;

/// <summary>What the controller needs to know about this computer, fixed for the session.</summary>
public sealed record MachineInfo(string ComputerName, string SpeedKey, string RunsOn, IReadOnlyList<string> Addresses);

/// <summary>
/// Gathers the supervisor state, /v1/status, the running job, the device list and host health into
/// snapshots for the flyout and the tray icon. Polls the engine every 5 s while the flyout is open and
/// every 30 s otherwise (the contract's cadence); pair requests every 5 s always; host health every tick.
/// </summary>
public sealed class BandroomController
{
    public static readonly TimeSpan Tick = TimeSpan.FromSeconds(5);
    public static readonly TimeSpan IdlePoll = TimeSpan.FromSeconds(30);

    private readonly EngineSupervisor _sup;
    private readonly Func<int, IEngineApi> _apiFor;
    private readonly IHostMetrics _metrics;
    private readonly IStrings _s;
    private readonly BandroomPaths _paths;
    private readonly TimeProvider _time;
    private readonly LoadAverager _load;
    private (int Port, IEngineApi Api)? _api;
    private DateTimeOffset _lastEnginePoll = DateTimeOffset.MinValue;
    private StatusInfo? _status;
    private JobView? _job;
    private HealthSnapshot? _health;
    private ModelCheckResult _models = ModelCheckResult.Ready;
    private bool _flyoutOpen;

    public BandroomController(EngineSupervisor supervisor, Func<int, IEngineApi> apiFor, IHostMetrics metrics, IStrings strings,
        BandroomPaths paths, MachineInfo machine, TimeProvider? time = null)
    {
        _sup = supervisor;
        _apiFor = apiFor;
        _metrics = metrics;
        _s = strings;
        _paths = paths;
        Machine = machine;
        _time = time ?? TimeProvider.System;
        _load = new LoadAverager(_time);
        _sup.Changed += () => Publish();
    }

    public PairRequestWatcher Requests { get; } = new();

    /// <summary>Setup: whether every environment is installed, and how far it is (0..1).</summary>
    public bool SetupComplete { get; set; } = true;
    public double SetupFraction { get; set; }
    /// <summary>Which of the downloads a full-band score needs are missing (<see cref="ModelCheck"/>); checked every tick.</summary>
    public Func<ModelCheckResult> CheckModels { get; set; } = () => ModelCheckResult.Ready;
    /// <summary>The model download, when one has been started: its progress replaces the missing-download problem.</summary>
    public ModelDownloader? Downloads { get; set; }
    /// <summary>The computer's name and hardware; the name changes when one is set in Settings.</summary>
    public MachineInfo Machine { get; set; }
    public bool Updating { get; set; }

    public event Action<BandroomSnapshot>? SnapshotReady;
    public event Action<IReadOnlyList<DeviceInfo>>? DevicesChanged;

    public IEngineApi? Api
    {
        get
        {
            if (_sup.State != EngineState.Running || _sup.Port is not { } port) return null;
            if (_api is not { } a || a.Port != port) _api = (port, _apiFor(port));
            return _api.Value.Api;
        }
    }

    /// <summary>Opening the flyout refreshes at once and switches to the 5 s cadence.</summary>
    public bool FlyoutOpen
    {
        get => _flyoutOpen;
        set
        {
            _flyoutOpen = value;
            if (value) _lastEnginePoll = DateTimeOffset.MinValue;
        }
    }

    public async Task RunAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await TickAsync(ct).ConfigureAwait(false);
            try { await Task.Delay(Tick, _time, ct).ConfigureAwait(false); }
            catch (OperationCanceledException) { return; }
        }
    }

    public async Task TickAsync(CancellationToken ct = default)
    {
        SampleHost();
        var api = Api;
        if (api is not null)
        {
            try { await Requests.PollAsync(api, ct).ConfigureAwait(false); }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException) { }

            var now = _time.GetUtcNow();
            if (now - _lastEnginePoll >= (FlyoutOpen ? Tick : IdlePoll))
            {
                _lastEnginePoll = now;
                await PollEngineAsync(api, ct).ConfigureAwait(false);
            }
        }
        else
        {
            _status = null;
            _job = null;
        }
        Publish();
    }

    private async Task PollEngineAsync(IEngineApi api, CancellationToken ct)
    {
        try
        {
            _status = await api.GetStatusAsync(ct).ConfigureAwait(false);
            _job = _status.JobsRunning > 0 ? JobView.From(await api.GetJobsAsync(ct).ConfigureAwait(false), _time.GetUtcNow()) : null;
            if (FlyoutOpen)
                DevicesChanged?.Invoke(await api.GetDevicesAsync(ct).ConfigureAwait(false));
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or System.Text.Json.JsonException)
        {
            // The supervisor notices a dead engine; a slow answer just keeps the last reading.
        }
        catch (EngineHttpException e) when (e.StatusCode is HttpStatusCode.Forbidden or HttpStatusCode.Unauthorized)
        {
            _status = null; // an engine that doesn't know our admin credential
        }
    }

    /// <summary>Refreshes the devices now (opening Phones and tablets, after a removal).</summary>
    public async Task RefreshDevicesAsync()
    {
        if (Api is not { } api) { DevicesChanged?.Invoke([]); return; }
        try { DevicesChanged?.Invoke(await api.GetDevicesAsync().ConfigureAwait(false)); }
        catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException) { }
    }

    private void SampleHost()
    {
        try
        {
            double cpu = _load.Add(_metrics.SampleCpuPercent());
            var (total, avail) = _metrics.Memory();
            long free = _metrics.FreeBytes(_paths.DataDir);
            _models = CheckModels();
            _health = new HealthSnapshot(cpu, total == 0 ? 1 : (double)avail / total, free, _models.Missing);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException) { }
    }

    public BandroomSnapshot Build()
    {
        var problems = new List<Problem>();
        if (_sup.Problem == EngineProblem.NoFreePort) problems.Add(Problems.NoFreePort(_s));
        if (_health is { LowDisk: true } h) problems.Add(Problems.LowDisk(_s, h.FreeBytes, _paths.DataDir));
        string? downloading = null;
        if (SetupComplete && _health is { ModelsReady: false })
        {
            if (Downloads is { Phase: DownloadPhase.Checking or DownloadPhase.Downloading or DownloadPhase.Paused } d)
                downloading = DownloadText.Progress(_s, d.BytesDone, d.BytesTotal, d.MinutesLeft, d.Phase == DownloadPhase.Paused);
            else if (Downloads is { Phase: DownloadPhase.Failed, Error: { } error })
                problems.Add(Problems.DownloadStopped(_s, error));
            else
                problems.Add(Problems.MissingDownload(_s, _models.Missing, _models.MissingFiles));
        }

        var inputs = new StateInputs(_sup.State, SetupComplete, SetupFraction, Updating, problems,
            _job?.Fraction, _status?.OnlineDevices ?? 0);
        string header = _status?.ServerName ?? _sup.Health?.ServerName ?? _s.Format("Header", Machine.ComputerName);
        if (_s.Language == "nb") header = _s.Format("Header", PairViewModel.HostName(header));
        var tech = new TechDetails(
            Machine.Addresses.Select(a => _sup.Port is { } p ? $"{a}:{p}" : a).ToList(),
            _sup.Port,
            _status?.Version ?? _sup.Health?.Version ?? "–",
            Machine.RunsOn,
            _status?.ServerId ?? _sup.Health?.ServerId,
            _paths.DataDir);
        return new BandroomSnapshot(inputs, header, _status, _job, _health, Machine.SpeedKey, tech, downloading);
    }

    public void Publish() => SnapshotReady?.Invoke(Build());
}

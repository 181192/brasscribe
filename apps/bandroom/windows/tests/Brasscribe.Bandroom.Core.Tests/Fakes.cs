using System.Net;
using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

internal static class Strings
{
    private static string Resw(string lang) => Path.Combine(AppContext.BaseDirectory, "Strings", lang, "Resources.resw");
    public static readonly ReswStrings En = new(Resw("en-US"), "en");
    public static readonly ReswStrings Nb = new(Resw("nb-NO"), "nb");
}

/// <summary>A process that exits when told to (or when killed).</summary>
internal sealed class FakeProcess(int id) : IEngineProcess
{
    private readonly TaskCompletionSource<int> _exit = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public int Id { get; } = id;
    public bool Killed { get; private set; }
    public Task<int> WaitForExitAsync() => _exit.Task;
    public void Exit(int code) => _exit.TrySetResult(code);
    public void Kill() { Killed = true; _exit.TrySetResult(-1); }
    public void Dispose() { }
}

internal sealed class FakeLauncher : IProcessLauncher
{
    public List<(ProcessSpec Spec, FakeProcess Process)> Started { get; } = [];
    public Func<ProcessSpec, int>? ExitImmediately { get; set; }

    public IEngineProcess Start(ProcessSpec spec, Action<string> output)
    {
        var p = new FakeProcess(1000 + Started.Count);
        Started.Add((spec, p));
        if (ExitImmediately?.Invoke(spec) is int code) p.Exit(code);
        return p;
    }

    public FakeProcess Last => Started[^1].Process;
}

internal sealed class FakePorts : IPortProbe
{
    public HashSet<int> Taken { get; } = [];
    public bool IsFree(int port) => !Taken.Contains(port);
}

internal sealed class FakeActions : IBandroomActions
{
    public List<string> Calls { get; } = [];
    public Task StartAsync() { Calls.Add("start"); return Task.CompletedTask; }
    public Task StopAsync() { Calls.Add("stop"); return Task.CompletedTask; }
    public Task RestartAsync() { Calls.Add("restart"); return Task.CompletedTask; }
    public void OpenPairWindow() => Calls.Add("pair");
    public void OpenStudio() => Calls.Add("studio");
    public void ShowLogs() => Calls.Add("logs");
    public void CopyText(string text) => Calls.Add("copy:" + text);
    public void FinishSetup() => Calls.Add("setup");
    public void Fix(ProblemKind problem) => Calls.Add("fix:" + problem);
    /// <summary>What removing a device answers: true (removed) unless a test says otherwise.</summary>
    public bool RemoveSucceeds { get; set; } = true;
    public Task<bool> RemoveDeviceAsync(string deviceId) { Calls.Add("remove:" + deviceId); return Task.FromResult(RemoveSucceeds); }
}

internal sealed class RecordingAnnouncer : IAnnouncer
{
    public List<string> Said { get; } = [];
    public void Announce(string text) => Said.Add(text);
}

/// <summary>An in-memory engine for the pairing and devices view models.</summary>
internal sealed class FakeEngine : IEngineApi
{
    public List<DeviceInfo> Devices { get; } = [];
    public List<PairRequestInfo> Requests { get; } = [];
    public List<string> Log { get; } = [];
    public List<PairingOpenRequest> Opens { get; } = [];
    public int CodeCounter { get; set; } = 482913;
    public bool PairingOpen { get; set; }
    public string? ExpiresAt { get; set; }
    public string? LockedUntil { get; set; }

    private PairingState State() => new(PairingOpen, PairingOpen ? CodeCounter.ToString() : null, ExpiresAt, true, "3f9c2a7e11", "Brasscribe on Kalli's PC",
        ["192.168.1.20:8765"], null, $"brasscribe://pair?v=1&id=3f9c2a7e11&h=192.168.1.20:8765&code={CodeCounter}", LockedUntil);

    public Task<HealthInfo> GetHealthAsync(CancellationToken ct = default) =>
        Task.FromResult(new HealthInfo("ok", "0.9.4", "cuda", false, "3f9c2a7e11", "Brasscribe on Kalli's PC"));
    public Task<StatusInfo> GetStatusAsync(CancellationToken ct = default) =>
        Task.FromResult(new StatusInfo("3f9c2a7e11", "Brasscribe on Kalli's PC", "0.9.4", Devices.Count(d => d.Online == true), Devices.Count, PairingOpen, 0, 0));
    public Task<IReadOnlyList<DeviceInfo>> GetDevicesAsync(CancellationToken ct = default) { Log.Add("devices"); return Task.FromResult<IReadOnlyList<DeviceInfo>>(Devices.ToList()); }
    public Task RemoveDeviceAsync(string deviceId, CancellationToken ct = default) { Devices.RemoveAll(d => d.DeviceId == deviceId); return Task.CompletedTask; }
    public Task<PairingState> GetPairingAsync(CancellationToken ct = default) => Task.FromResult(State());
    public Task<PairingState> OpenPairingAsync(PairingOpenRequest request, CancellationToken ct = default)
    {
        Opens.Add(request);
        if (!request.Extend) CodeCounter++;
        PairingOpen = true;
        return Task.FromResult(State());
    }
    public Task<PairingState> ClosePairingAsync(CancellationToken ct = default) { Log.Add("close"); PairingOpen = false; return Task.FromResult(State()); }
    public Task<IReadOnlyList<PairRequestInfo>> GetPairRequestsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<PairRequestInfo>>(Requests.ToList());
    public Task<PairRequestInfo> DecidePairRequestAsync(string requestId, bool approve, CancellationToken ct = default)
    {
        var r = Requests.FirstOrDefault(r => r.RequestId == requestId) ?? throw new EngineHttpException(HttpStatusCode.NotFound, "unknown, expired or already decided");
        Requests.Remove(r);
        return Task.FromResult(r with { Status = approve ? "approved" : "denied" });
    }
    public Task<IReadOnlyList<JobInfo>> GetJobsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<JobInfo>>([]);
}

/// <summary>Records requests and answers from a table of (method path) → (status, json).</summary>
internal sealed class StubHandler : HttpMessageHandler
{
    public List<(HttpRequestMessage Request, string? Body)> Seen { get; } = [];
    public Dictionary<string, (HttpStatusCode Status, string Json)> Routes { get; } = [];

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        string? body = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
        Seen.Add((request, body));
        string key = request.Method.Method + " " + request.RequestUri!.AbsolutePath;
        var (status, json) = Routes.TryGetValue(key, out var r) ? r : (HttpStatusCode.NotFound, "{\"detail\":\"Not Found\"}");
        return new HttpResponseMessage(status) { Content = new StringContent(json, System.Text.Encoding.UTF8, "application/json") };
    }
}

/// <summary>
/// <see cref="FakeEngine"/> with hooks: a hook that throws makes that call fail the way a real engine can (a 500, a
/// timeout, a body that isn't JSON); one that awaits holds the call until the test lets it go.
/// </summary>
internal sealed class FlakyEngine(FakeEngine inner) : IEngineApi
{
    public FakeEngine Inner { get; } = inner;
    public Func<Task>? OnStatus { get; set; }
    public Func<Task>? OnPairRequests { get; set; }
    public Func<Task>? OnDecide { get; set; }
    public int StatusCalls;
    public int PairRequestCalls;

    private static Task Run(Func<Task>? hook) => hook?.Invoke() ?? Task.CompletedTask;

    public Task<HealthInfo> GetHealthAsync(CancellationToken ct = default) => Inner.GetHealthAsync(ct);
    public async Task<StatusInfo> GetStatusAsync(CancellationToken ct = default)
    {
        Interlocked.Increment(ref StatusCalls);
        await Run(OnStatus);
        return await Inner.GetStatusAsync(ct);
    }
    public Task<IReadOnlyList<DeviceInfo>> GetDevicesAsync(CancellationToken ct = default) => Inner.GetDevicesAsync(ct);
    public Task RemoveDeviceAsync(string deviceId, CancellationToken ct = default) => Inner.RemoveDeviceAsync(deviceId, ct);
    public Task<PairingState> GetPairingAsync(CancellationToken ct = default) => Inner.GetPairingAsync(ct);
    public Task<PairingState> OpenPairingAsync(PairingOpenRequest request, CancellationToken ct = default) => Inner.OpenPairingAsync(request, ct);
    public Task<PairingState> ClosePairingAsync(CancellationToken ct = default) => Inner.ClosePairingAsync(ct);
    public async Task<IReadOnlyList<PairRequestInfo>> GetPairRequestsAsync(CancellationToken ct = default)
    {
        Interlocked.Increment(ref PairRequestCalls);
        await Run(OnPairRequests);
        return await Inner.GetPairRequestsAsync(ct);
    }
    public async Task<PairRequestInfo> DecidePairRequestAsync(string requestId, bool approve, CancellationToken ct = default)
    {
        await Run(OnDecide);
        return await Inner.DecidePairRequestAsync(requestId, approve, ct);
    }
    public Task<IReadOnlyList<JobInfo>> GetJobsAsync(CancellationToken ct = default) => Inner.GetJobsAsync(ct);
}

using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Downloads;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom;

/// <summary>
/// Sample content for screenshots and the accessibility scan (--demo): the mockup's computer, phones and
/// job, with no engine running. Everything else goes through the real view models.
/// </summary>
internal sealed class DemoEngine : IEngineApi
{
    private int _code = 482913;
    private bool _open;
    private readonly DateTimeOffset _now = DateTimeOffset.Now;

    public List<DeviceInfo> Devices { get; }
    public List<PairRequestInfo> Requests { get; } = [];

    public DemoEngine()
    {
        Devices =
        [
            new("d-kari", "Kari's iPhone", "ios", "2026-09-01T10:00:00Z", _now.AddSeconds(-10).ToString("O"), null, true),
            new("d-ola", "Ola's Pixel 8", "android", "2026-09-02T10:00:00Z", _now.AddSeconds(-20).ToString("O"), null, true),
            new("d-ipad", "Band iPad", "ios", "2026-09-03T10:00:00Z", _now.AddDays(-3).ToString("O"), null, false),
        ];
    }

    private PairingState State() => new(_open, _open ? _code.ToString() : null, null, true, "3f9c2a7e5d1b", "Brasscribe on Kari's PC",
        ["192.0.2.20:8765"], null,
        $"brasscribe://pair?v=1&id=3f9c2a7e5d1b&name=Brasscribe%20on%20Kari%27s%20PC&h=192.0.2.20:8765&code={_code}");

    public Task<HealthInfo> GetHealthAsync(CancellationToken ct = default) =>
        Task.FromResult(new HealthInfo("ok", "0.9.4", "cuda", false, "3f9c2a7e5d1b", "Brasscribe on Kari's PC"));
    public Task<StatusInfo> GetStatusAsync(CancellationToken ct = default) =>
        Task.FromResult(new StatusInfo("3f9c2a7e5d1b", "Brasscribe on Kari's PC", "0.9.4", 2, Devices.Count, _open, 0, 0));
    public Task<IReadOnlyList<DeviceInfo>> GetDevicesAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<DeviceInfo>>(Devices.ToList());
    public Task RemoveDeviceAsync(string deviceId, CancellationToken ct = default) { Devices.RemoveAll(d => d.DeviceId == deviceId); return Task.CompletedTask; }
    public Task<PairingState> GetPairingAsync(CancellationToken ct = default) => Task.FromResult(State());
    public Task<PairingState> OpenPairingAsync(PairingOpenRequest request, CancellationToken ct = default)
    {
        if (_open && !request.Extend) _code = (_code * 7 + 13) % 900000 + 100000;
        _open = true;
        return Task.FromResult(State());
    }
    public Task<PairingState> ClosePairingAsync(CancellationToken ct = default) { _open = false; return Task.FromResult(State()); }
    public Task<IReadOnlyList<PairRequestInfo>> GetPairRequestsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<PairRequestInfo>>(Requests.ToList());
    public Task<PairRequestInfo> DecidePairRequestAsync(string requestId, bool approve, CancellationToken ct = default)
    {
        var r = Requests.First(r => r.RequestId == requestId);
        Requests.Remove(r);
        return Task.FromResult(r with { Status = approve ? "approved" : "denied" });
    }
    public Task<IReadOnlyList<JobInfo>> GetJobsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<JobInfo>>([]);

    public PairRequestInfo AddRequest()
    {
        var r = new PairRequestInfo("r-kari", "Kari's iPhone", "ios", "4719", DateTimeOffset.UtcNow.ToString("O"), "pending");
        Requests.Add(r);
        return r;
    }

    /// <summary>The flyout in a given state (--state running|busy|attention|stopped|error|setup|starting).</summary>
    public static BandroomSnapshot Snapshot(string state, IStrings s)
    {
        var problems = new List<Problem>();
        var engine = EngineState.Running;
        JobView? job = null;
        bool setup = true;
        switch (state)
        {
            case "busy": job = new JobView("Old Hundredth", "Step_Notes", 0.62, 3); break;
            case "attention": problems.Add(Problems.LowDisk(s, 2_100_000_000, @"C:\Users\Kari\AppData\Local\Brasscribe")); break;
            case "stopped": engine = EngineState.Stopped; break;
            case "error": engine = EngineState.Error; break;
            case "starting": engine = EngineState.Starting; break;
            case "setup": engine = EngineState.Stopped; setup = false; break;
        }
        var running = engine == EngineState.Running;
        return new BandroomSnapshot(
            new StateInputs(engine, setup, 0.32, false, problems, job?.Fraction, running ? 2 : 0),
            s.Format("Header", "Kari's PC"),
            running ? new StatusInfo("3f9c2a7e5d1b", "Brasscribe on Kari's PC", "0.9.4", 2, 3, false, job is null ? 0 : 1, job is null ? 0 : 1) : null,
            job,
            new HealthSnapshot(job is null ? 18 : 91, 0.2, state == "attention" ? 2_100_000_000 : 86_400_000_000, setup ? [] : [ModelComponent.BandWriter]),
            "Health_Speed_Nvidia",
            new TechDetails(running ? ["192.0.2.20:8765", "198.51.100.4:8765"] : [], running ? 8765 : null, "0.9.4",
                "CUDA 12 · NVIDIA GeForce RTX 4070", "3f9c2a7e5d1b", @"C:\Users\Kari\AppData\Local\Brasscribe"));
    }
}

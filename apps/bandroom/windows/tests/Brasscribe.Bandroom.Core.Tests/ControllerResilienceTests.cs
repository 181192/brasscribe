using System.Net;
using System.Text.Json;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.Supervisor;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>The polling loop keeps going whatever the engine answers, and never runs two checks at once.</summary>
public sealed class ControllerResilienceTests : IAsyncLifetime
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-poll").FullName;
    private readonly FlakyEngine _engine = new(new FakeEngine());
    private readonly List<string> _log = [];
    private EngineSupervisor _sup = null!;

    private sealed class Metrics : IHostMetrics
    {
        public Func<double> Cpu = () => 20;
        public double SampleCpuPercent() => Cpu();
        public (ulong Total, ulong Available) Memory() => (16UL << 30, 8UL << 30);
        public long FreeBytes(string path) => 212_000_000_000;
    }

    public async Task InitializeAsync()
    {
        _sup = new EngineSupervisor(new FakeLauncher(), new FakePorts(),
            (_, _) => Task.FromResult<HealthInfo?>(new HealthInfo("ok", "0.9.4", "cpu", false, "3f9c2a7e11", "Brasscribe on Kari's PC")),
            _ => new ProcessSpec("pixi", [], _dir, new Dictionary<string, string>()), new EngineLog(null));
        await _sup.StartAsync();
        for (int i = 0; i < 400 && _sup.State != EngineState.Running; i++) await Task.Delay(5);
        Assert.Equal(EngineState.Running, _sup.State);
    }

    public async Task DisposeAsync()
    {
        await _sup.DisposeAsync();
        Directory.Delete(_dir, recursive: true);
    }

    private BandroomController Make(IHostMetrics? metrics = null, TimeProvider? time = null) =>
        new(_sup, _ => _engine, metrics ?? new Metrics(), Strings.En, new BandroomPaths(_dir),
            new MachineInfo("Kari's PC", "Health_Speed_Cpu", "CPU", []), time)
        {
            Log = line => { lock (_log) _log.Add(line); },
        };

    public static TheoryData<string> Failures => ["500", "401", "timeout", "json", "bug"];

    private static Func<Task> Throw(string kind) => kind switch
    {
        "500" => () => throw new EngineHttpException(HttpStatusCode.InternalServerError, "busy"),
        "401" => () => throw new EngineHttpException(HttpStatusCode.Unauthorized, "who are you"),
        "timeout" => () => throw new TaskCanceledException("The request was canceled due to the configured HttpClient.Timeout"),
        "json" => () => throw new JsonException("'<' is an invalid start of a value"),
        _ => () => throw new InvalidOperationException("something unexpected"),
    };

    [Theory]
    [MemberData(nameof(Failures))]
    public async Task A_failing_check_is_a_missed_reading_and_the_next_one_runs(string kind)
    {
        var ctl = Make();
        ctl.FlyoutOpen = true;
        int snapshots = 0;
        ctl.SnapshotReady += _ => snapshots++;
        _engine.OnStatus = Throw(kind);
        _engine.OnPairRequests = Throw(kind);

        await ctl.TickAsync();
        await ctl.TickAsync();
        Assert.Equal(2, _engine.PairRequestCalls);

        // The engine is well again: the next check reads it.
        _engine.OnStatus = _engine.OnPairRequests = null;
        ctl.FlyoutOpen = true;
        await ctl.TickAsync();
        Assert.Equal(3, _engine.PairRequestCalls);
        Assert.True(snapshots >= 1);
        Assert.NotNull(ctl.Build().Status);
    }

    [Fact]
    public async Task The_loop_survives_a_check_that_throws_and_ends_when_cancelled()
    {
        var time = new FakeTimeProvider(DateTimeOffset.Parse("2026-09-27T12:00:00Z"));
        var metrics = new Metrics { Cpu = () => throw new InvalidOperationException("Queue empty.") };
        var ctl = Make(metrics, time);
        _engine.OnPairRequests = Throw("500");
        using var cts = new CancellationTokenSource();
        var loop = ctl.RunAsync(cts.Token);

        for (int i = 0; i < 400 && _engine.PairRequestCalls < 3; i++)
        {
            time.Advance(BandroomController.Tick);
            await Task.Delay(5);
        }
        Assert.True(_engine.PairRequestCalls >= 3, "the loop stopped after a failing check");
        Assert.False(loop.IsCompleted);
        lock (_log) Assert.Contains(_log, l => l.Contains("Queue empty.", StringComparison.Ordinal));

        cts.Cancel();
        await loop.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task A_check_asked_for_while_one_runs_waits_its_turn()
    {
        var ctl = Make();
        var hold = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        _engine.OnPairRequests = () => hold.Task;

        var first = ctl.TickAsync();
        for (int i = 0; i < 400 && _engine.PairRequestCalls == 0; i++) await Task.Delay(5);
        Assert.Equal(1, _engine.PairRequestCalls);

        // Opening the flyout while the first check is out: returns at once, no second call in parallel.
        ctl.FlyoutOpen = true;
        var second = ctl.TickAsync();
        Assert.True(second.IsCompleted);
        Assert.Equal(1, _engine.PairRequestCalls);

        // The running check goes once more when it is done, so the flyout still gets a fresh reading.
        _engine.OnPairRequests = null;
        hold.SetResult();
        await first;
        Assert.Equal(2, _engine.PairRequestCalls);
        Assert.Equal(1, _engine.StatusCalls);
    }

    [Fact]
    public void Overlapping_polls_raise_arrived_once_per_request()
    {
        var watcher = new PairRequestWatcher();
        int arrived = 0;
        watcher.Arrived += _ => Interlocked.Increment(ref arrived);
        var list = new List<PairRequestInfo> { new("r1", "Kari's iPhone", "ios", "4719", DateTimeOffset.UtcNow.ToString("O"), "pending") };
        Parallel.For(0, 64, _ => watcher.Update(list));
        Assert.Equal(1, arrived);
        Assert.Single(watcher.Pending);
    }

    [Fact]
    public void The_load_average_takes_samples_from_several_threads()
    {
        var load = new LoadAverager(window: TimeSpan.FromMilliseconds(1));
        Parallel.For(0, 10_000, i => load.Add(i % 100));
        Assert.InRange(load.Average, 0, 100);
    }
}

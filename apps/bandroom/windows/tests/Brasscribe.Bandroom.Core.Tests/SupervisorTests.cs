using System.Text.Json;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Supervisor;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class SupervisorTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-sup").FullName;
    private readonly FakeTimeProvider _time = new(DateTimeOffset.Parse("2026-09-27T12:00:00Z"));
    private readonly FakeLauncher _launcher = new();
    private readonly FakePorts _ports = new();
    private bool _healthy = true;

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private EngineSupervisor Make(EngineLaunchConfig? config = null) => new(
        _launcher, _ports,
        (port, _) => Task.FromResult(_healthy && _launcher.Started.Count > 0 && !_launcher.Last.WaitForExitAsync().IsCompleted
            ? new HealthInfo("ok", "0.9.4", "cuda", false, "3f9c2a7e11", "Brasscribe on Kalli's PC")
            : null),
        port => (config ?? Config()).Build(port),
        new EngineLog(Path.Combine(_dir, "logs"), _time),
        _time,
        new SupervisorOptions { StatusFilePath = Path.Combine(_dir, "engine.json") });

    private EngineLaunchConfig Config(bool cuda = true) =>
        new(new BandroomPaths(_dir), @"C:\Program Files\Brasscribe Bandroom\pixi\pixi.exe", "Kalli's PC", "secret-admin-token-0123456789abcdef", cuda);

    /// <summary>Waits for a condition, moving fake time on so back-off delays can run.</summary>
    private async Task Until(Func<bool> condition, bool advance = false, double stepSeconds = 0.5)
    {
        for (int i = 0; i < 400 && !condition(); i++)
        {
            if (advance) _time.Advance(TimeSpan.FromSeconds(stepSeconds));
            await Task.Delay(5);
        }
        Assert.True(condition(), "condition not reached");
    }

    [Fact]
    public async Task Start_reaches_running_on_the_first_port_and_writes_engine_json_without_the_token()
    {
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        Assert.Equal(8765, sup.Port);
        var json = File.ReadAllText(Path.Combine(_dir, "engine.json"));
        using var doc = JsonDocument.Parse(json);
        Assert.Equal(8765, doc.RootElement.GetProperty("port").GetInt32());
        Assert.Equal(_launcher.Last.Id, doc.RootElement.GetProperty("pid").GetInt32());
        Assert.Equal("3f9c2a7e11", doc.RootElement.GetProperty("server_id").GetString());
        Assert.Equal("0.9.4", doc.RootElement.GetProperty("version").GetString());
        Assert.DoesNotContain("secret-admin-token", json);
    }

    [Fact]
    public async Task A_taken_port_moves_to_the_next()
    {
        _ports.Taken.Add(8765);
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        Assert.Equal(8766, sup.Port);
        Assert.Contains("8766", _launcher.Started[0].Spec.Arguments);
    }

    [Fact]
    public async Task No_free_port_is_a_problem_not_a_crash_loop()
    {
        for (int p = 8765; p <= 8775; p++) _ports.Taken.Add(p);
        await using var sup = Make();
        await sup.StartAsync();
        Assert.Equal(EngineState.Stopped, sup.State);
        Assert.Equal(EngineProblem.NoFreePort, sup.Problem);
        Assert.Empty(_launcher.Started);
    }

    [Fact]
    public async Task A_crash_restarts_after_a_backoff()
    {
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        _launcher.Last.Exit(1);
        await Until(() => sup.State == EngineState.Starting);
        Assert.Single(_launcher.Started); // waiting for the back-off
        await Until(() => _launcher.Started.Count == 2 && sup.State == EngineState.Running, advance: true);
        Assert.Equal(1, sup.RecentFailures);
        Assert.Equal(1, sup.LastExitCode);
    }

    [Fact]
    public async Task Three_failures_in_five_minutes_is_an_error_and_try_again_starts_fresh()
    {
        await using var sup = Make();
        await sup.StartAsync();
        for (int i = 1; i <= 3; i++)
        {
            await Until(() => _launcher.Started.Count == i && sup.State == EngineState.Running, advance: true);
            _launcher.Last.Exit(1);
        }
        await Until(() => sup.State == EngineState.Error);
        _time.Advance(TimeSpan.FromMinutes(1));
        await Task.Delay(50);
        Assert.Equal(3, _launcher.Started.Count);
        Assert.False(File.Exists(Path.Combine(_dir, "engine.json")));

        await sup.StartAsync(); // Try again
        await Until(() => sup.State == EngineState.Running);
        Assert.Equal(0, sup.RecentFailures);
    }

    [Fact]
    public async Task Failures_older_than_the_window_are_forgotten()
    {
        await using var sup = Make();
        await sup.StartAsync();
        for (int i = 1; i <= 4; i++)
        {
            await Until(() => _launcher.Started.Count == i && sup.State == EngineState.Running, advance: true);
            _time.Advance(TimeSpan.FromMinutes(3));
            _launcher.Last.Exit(1);
        }
        await Until(() => _launcher.Started.Count == 5 && sup.State == EngineState.Running, advance: true);
        Assert.True(sup.RecentFailures < 3);
    }

    [Fact]
    public async Task An_exit_while_starting_because_the_port_was_taken_is_not_a_failure()
    {
        _healthy = false;
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Starting && _launcher.Started.Count == 1);
        _ports.Taken.Add(8765); // someone else bound it first
        _healthy = true;
        _launcher.Last.Exit(1);
        await Until(() => sup.State == EngineState.Running && sup.Port == 8766);
        Assert.Equal(0, sup.RecentFailures);
    }

    [Fact]
    public async Task Stop_kills_the_engine_and_nothing_restarts_it()
    {
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        var first = _launcher.Last;
        await sup.StopAsync();
        Assert.True(first.Killed);
        Assert.Equal(EngineState.Stopped, sup.State);
        Assert.False(File.Exists(Path.Combine(_dir, "engine.json")));
        _time.Advance(TimeSpan.FromMinutes(2));
        await Task.Delay(50);
        Assert.Single(_launcher.Started);
    }

    [Fact]
    public async Task Restart_starts_a_new_process()
    {
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        await sup.RestartAsync();
        await Until(() => sup.State == EngineState.Running && _launcher.Started.Count == 2);
        Assert.True(_launcher.Started[0].Process.Killed);
        Assert.Equal(0, sup.RecentFailures);
    }

    [Fact]
    public void Backoff_doubles_up_to_thirty_seconds()
    {
        var sup = Make();
        Assert.Equal([2, 4, 8, 16, 30, 30], Enumerable.Range(1, 6).Select(n => (int)sup.Backoff(n).TotalSeconds));
    }

    [Fact]
    public async Task A_start_that_never_answers_times_out_and_counts_as_a_failure()
    {
        _healthy = false;
        await using var sup = Make();
        await sup.StartAsync();
        await Until(() => _launcher.Started.Count == 1);
        await Until(() => _launcher.Started[0].Process.Killed, advance: true, stepSeconds: 10);
        await Until(() => sup.RecentFailures == 1);
    }

    [Fact]
    public void The_engine_command_sets_the_environment_config_py_reads_and_the_admin_credential()
    {
        var spec = Config(cuda: true).Build(8767);
        Assert.EndsWith("pixi.exe", spec.FileName);
        Assert.Equal(["run", "--manifest-path", Path.Combine(_dir, "envs", "pixi.toml"), "--frozen", "-e", "default",
                      "brasscribe", "serve", "--lan", "--port", "8767"], spec.Arguments);
        Assert.Equal(_dir, spec.Environment["BRASSCRIBE_DATA"]);
        Assert.Equal(Path.Combine(_dir, "models"), spec.Environment["BRASSCRIBE_MODELS"]);
        Assert.Equal(Path.Combine(_dir, "envs", "ml", "adapters"), spec.Environment["BRASSCRIBE_ADAPTERS"]);
        Assert.Equal("Kalli's PC", spec.Environment["BRASSCRIBE_COMPUTER_NAME"]);
        Assert.Equal("secret-admin-token-0123456789abcdef", spec.Environment["BRASSCRIBE_ADMIN_TOKEN"]);
        Assert.Equal("pixi", spec.Environment["BRASSCRIBE_ADAPTER_RUNNER"]);
        Assert.Equal("1", spec.Environment["BRASSCRIBE_CUDA"]);
        Assert.Equal(Path.Combine(_dir, "cache", "pixi"), spec.Environment["PIXI_CACHE_DIR"]);
        Assert.DoesNotContain("BRASSCRIBE_TOKEN", spec.Environment.Keys);
        Assert.False(Config(cuda: false).Build(8765).Environment.ContainsKey("BRASSCRIBE_CUDA"));
    }

    [Fact]
    public void The_log_rolls_over_and_keeps_a_tail()
    {
        var log = new EngineLog(Path.Combine(_dir, "roll"), _time, maxBytes: 200, tailLines: 5);
        for (int i = 0; i < 30; i++) log.Write($"line {i} " + new string('x', 20));
        Assert.True(File.Exists(Path.Combine(_dir, "roll", "engine.1.log")));
        Assert.Equal(5, log.Tail(10).Count);
        Assert.EndsWith(new string('x', 20), log.Tail(1)[0]);
        Assert.Contains("line 29", log.Tail(1)[0]);
    }
}

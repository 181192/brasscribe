using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>Setup and updates run one at a time, and a setup that stops says so.</summary>
public sealed class SetupTests
{
    [Fact]
    public async Task Asking_again_while_setup_runs_joins_it()
    {
        var flight = new SingleFlight();
        var hold = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int runs = 0;
        Task Work() { runs++; return hold.Task; }

        var first = flight.RunAsync(Work);
        var second = flight.RunAsync(Work);
        var third = flight.RunAsync(Work);
        Assert.True(flight.IsRunning);
        Assert.Equal(1, runs);
        Assert.False(second.IsCompleted);

        hold.SetResult();
        await Task.WhenAll(first, second, third);
        Assert.False(flight.IsRunning);

        // Done: the next ask starts a new run.
        await flight.RunAsync(() => { runs++; return Task.CompletedTask; });
        Assert.Equal(2, runs);
    }

    [Fact]
    public async Task A_run_that_fails_lets_the_next_one_start()
    {
        var flight = new SingleFlight();
        await Assert.ThrowsAsync<IOException>(() => flight.RunAsync(() => Task.FromException(new IOException("disk"))));
        Assert.False(flight.IsRunning);
        bool ran = false;
        await flight.RunAsync(() => { ran = true; return Task.CompletedTask; });
        Assert.True(ran);
    }

    private sealed class Metrics : IHostMetrics
    {
        public double SampleCpuPercent() => 5;
        public (ulong Total, ulong Available) Memory() => (16UL << 30, 8UL << 30);
        public long FreeBytes(string path) => 212_000_000_000;
    }

    [Fact]
    public async Task Setup_that_stopped_needs_attention_with_finish_setting_up()
    {
        var dir = Directory.CreateTempSubdirectory("bandroom-setup").FullName;
        try
        {
            var sup = new EngineSupervisor(new FakeLauncher(), new FakePorts(), (_, _) => Task.FromResult<HealthInfo?>(null),
                _ => new ProcessSpec("pixi", [], dir, new Dictionary<string, string>()), new EngineLog(null));
            var ctl = new BandroomController(sup, _ => new FakeEngine(), new Metrics(), Strings.En, new BandroomPaths(dir),
                new MachineInfo("Kalli's PC", "Health_Speed_Cpu", "CPU", []))
            {
                SetupComplete = false,
            };
            BandroomSnapshot? last = null;
            ctl.SnapshotReady += s => last = s;
            await ctl.TickAsync();
            Assert.Equal(DisplayState.SettingUp, StateRules.Resolve(last!.Inputs));

            ctl.SetupFailure = "Access to the path 'pixi.toml' is denied.";
            ctl.Publish();
            var info = StateRules.Describe(last.Inputs, Strings.En);
            Assert.Equal(DisplayState.NeedsAttention, info.State);
            Assert.Equal("Brasscribe's own tools aren't installed yet.", info.StatusSub);
            Assert.Equal(PrimaryAction.Fix, info.Primary);
            Assert.Equal("Finish setting up", info.PrimaryLabel);
            Assert.Equal(ProblemKind.MissingDownload, info.Problem!.Kind);
            Assert.Contains("pixi.toml", info.Problem.Details);
        }
        finally { Directory.Delete(dir, true); }
    }
}

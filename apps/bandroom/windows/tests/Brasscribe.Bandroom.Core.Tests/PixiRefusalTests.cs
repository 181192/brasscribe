using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class PixiRefusalTests : IDisposable
{
    /// <summary>What pixi writes when it is older than requires-pixi (0.79.0 against ">=0.80").</summary>
    private static readonly string[] Refused =
    [
        "Error:   × this project requires pixi '>=0.80', but you have pixi 0.79.0",
        @"    ╭─[envs\pixi.toml:14:18]",
        "14 │ requires-pixi = \">=0.80\"",
        "   ·                     ╰── this version requirement is not satisfied",
    ];

    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-pixi").FullName;
    private readonly FakeTimeProvider _time = new(DateTimeOffset.Parse("2026-09-27T12:00:00Z"));

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    [Fact]
    public void Reads_the_requirement_and_the_version_whatever_comes_before()
    {
        var r = PixiRefusal.Find(Refused)!;
        Assert.Equal(">=0.80", r.Required);
        Assert.Equal("0.79.0", r.Found);
        Assert.Equal(Refused[0], r.Message);
        // The cross as a console with another code page shows it.
        Assert.Equal("0.79.0", PixiRefusal.Parse("Error:   Ã— this project requires pixi '>=0.80', but you have pixi 0.79.0")?.Found);
        Assert.Null(PixiRefusal.Find(["Error: × failed to solve the environment", "Traceback (most recent call last):"]));
    }

    private EngineSupervisor Supervisor(FakeLauncher launcher) => new(
        launcher, new FakePorts(), (_, _) => Task.FromResult<HealthInfo?>(null),
        _ => new ProcessSpec("pixi", [], _dir, new Dictionary<string, string>()), new EngineLog(null, _time), _time);

    private async Task Until(Func<bool> condition, bool advance = false)
    {
        for (int i = 0; i < 400 && !condition(); i++)
        {
            if (advance) _time.Advance(TimeSpan.FromSeconds(0.5));
            await Task.Delay(5);
        }
        Assert.True(condition(), "condition not reached");
    }

    [Fact]
    public async Task A_refused_start_stops_at_once_and_says_why()
    {
        var launcher = new FakeLauncher { Output = Refused, ExitImmediately = _ => 1 };
        await using var sup = Supervisor(launcher);
        await sup.StartAsync();
        await Until(() => sup.Problem == EngineProblem.PixiTooOld);
        Assert.Equal(EngineState.Stopped, sup.State);
        Assert.Equal("0.79.0", sup.Refusal?.Found);
        for (int i = 0; i < 20; i++) { _time.Advance(TimeSpan.FromSeconds(30)); await Task.Delay(2); }
        Assert.Single(launcher.Started);

        // Start again: the refusal is forgotten while it tries.
        launcher.Output = [];
        launcher.ExitImmediately = null;
        await sup.StartAsync();
        Assert.Equal(EngineProblem.None, sup.Problem);
        Assert.Null(sup.Refusal);
    }

    [Fact]
    public async Task An_ordinary_crash_still_restarts()
    {
        var launcher = new FakeLauncher { Output = ["Traceback (most recent call last):"], ExitImmediately = _ => 1 };
        await using var sup = Supervisor(launcher);
        await sup.StartAsync();
        await Until(() => launcher.Started.Count >= 2, advance: true);
        Assert.Equal(EngineProblem.None, sup.Problem);
    }

    [Fact]
    public async Task A_refused_install_carries_the_reason()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Path.Combine(_dir, "bundle");
        Directory.CreateDirectory(bundle);
        File.WriteAllText(Path.Combine(bundle, "pixi.toml"), "[workspace]\nrequires-pixi = \">=0.80\"\n");
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), "version: 6\n");
        var launcher = new FakeLauncher { Output = Refused, ExitImmediately = _ => 1 };
        var boot = new Bootstrapper(paths, bundle, "pixi", launcher, new EngineLog(null));
        var ex = await Assert.ThrowsAsync<BootstrapException>(() => boot.RunAsync(false, null, CancellationToken.None));
        Assert.Equal(">=0.80", ex.Refusal?.Required);

        launcher.Output = ["Error: × failed to download"];
        ex = await Assert.ThrowsAsync<BootstrapException>(() => boot.RunAsync(false, null, CancellationToken.None));
        Assert.Null(ex.Refusal);
    }

    private sealed class Metrics : IHostMetrics
    {
        public double SampleCpuPercent() => 5;
        public (ulong Total, ulong Available) Memory() => (16UL << 30, 8UL << 30);
        public long FreeBytes(string path) => 212_000_000_000;
    }

    private BandroomController Controller(EngineSupervisor sup, IStrings s) =>
        new(sup, _ => new FakeEngine(), new Metrics(), s, new BandroomPaths(_dir), new MachineInfo("Kari's PC", "Health_Speed_Cpu", "CPU", []))
        {
            SetupComplete = false,
            // Setup stopped too ("Finish setting up"); the refusal is what's shown, since setting up again can't help.
            SetupFailure = "pixi install -e default exited with 1",
        };

    [Theory]
    [InlineData("en", "Brasscribe can't start", "Get the latest Bandroom")]
    [InlineData("nb", "Brasscribe kan ikke starte", "Last ned den nyeste Bandroom")]
    public async Task A_refused_start_needs_attention_with_the_way_forward_and_pixis_words_for_the_tech_person(
        string language, string title, string fix)
    {
        var s = language == "nb" ? Strings.Nb : Strings.En;
        var launcher = new FakeLauncher { Output = Refused, ExitImmediately = _ => 1 };
        await using var sup = Supervisor(launcher);
        var ctl = Controller(sup, s);
        await sup.StartAsync();
        await Until(() => sup.Problem == EngineProblem.PixiTooOld);
        var snap = ctl.Build();

        var info = StateRules.Describe(snap.Inputs, s);
        Assert.Equal(DisplayState.NeedsAttention, info.State);
        Assert.Equal(ProblemKind.PixiTooOld, info.Problem!.Kind);
        Assert.Equal(title, info.Problem.Title);
        Assert.Equal(s["Pixi_Why"], info.StatusSub);
        Assert.Equal(PrimaryAction.Fix, info.Primary);
        Assert.Equal(fix, info.PrimaryLabel);
        Assert.Contains(Refused[0], info.Problem.Details);

        var actions = new FakeActions();
        var vm = new FlyoutViewModel(s, actions, new RecordingAnnouncer(), _time);
        vm.Apply(snap);
        vm.CopyDiagnosticsCommand.Execute(null);
        Assert.Contains(actions.Calls, c => c.StartsWith("copy:", StringComparison.Ordinal) && c.Contains(Refused[0], StringComparison.Ordinal));
        await vm.PrimaryCommand.ExecuteAsync(null);
        Assert.Contains("fix:PixiTooOld", actions.Calls);
    }

    [Fact]
    public async Task A_refused_setup_or_update_needs_attention_too()
    {
        await using var sup = Supervisor(new FakeLauncher());
        var ctl = Controller(sup, Strings.En);
        ctl.SetupRefusal = PixiRefusal.Find(Refused);
        var info = StateRules.Describe(ctl.Build().Inputs, Strings.En);
        Assert.Equal(DisplayState.NeedsAttention, info.State);
        Assert.Equal(ProblemKind.PixiTooOld, info.Problem!.Kind);
    }

    /// <summary>A supervisor whose engine answers while its process is there.</summary>
    private EngineSupervisor RunningSupervisor(FakeLauncher launcher) => new(
        launcher, new FakePorts(),
        (_, _) => Task.FromResult<HealthInfo?>(launcher.Started.Count > 0 && !launcher.Last.WaitForExitAsync().IsCompleted
            ? new HealthInfo("ok", "0.9.4", "cpu", false, "3f9c2a7e11", "Brasscribe on Kari's PC")
            : null),
        _ => new ProcessSpec("pixi", [], _dir, new Dictionary<string, string>()), new EngineLog(null, _time), _time);

    [Theory]
    [InlineData("en", "Brasscribe couldn't finish updating", "Get the latest Bandroom")]
    [InlineData("nb", "Brasscribe fikk ikke fullført oppdateringen", "Last ned den nyeste Bandroom")]
    public async Task A_refused_update_with_the_previous_engine_running_is_not_cant_start(string language, string title, string fix)
    {
        var s = language == "nb" ? Strings.Nb : Strings.En;
        var launcher = new FakeLauncher();
        await using var sup = RunningSupervisor(launcher);
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        var ctl = new BandroomController(sup, _ => new FakeEngine(), new Metrics(), s, new BandroomPaths(_dir),
            new MachineInfo("Kari's PC", "Health_Speed_Cpu", "CPU", []))
        {
            UpdateFailure = "pixi install -e default exited with 1",
            UpdateRefusal = PixiRefusal.Find(Refused),
        };
        var snap = ctl.Build();
        var info = StateRules.Describe(snap.Inputs, s);
        Assert.Equal(DisplayState.NeedsAttention, info.State);
        Assert.Equal(ProblemKind.UpdateRefused, info.Problem!.Kind);
        Assert.Equal(title, info.Problem.Title);
        Assert.Equal(s["Update_Refused_Why"], info.StatusSub);
        Assert.Equal(fix, info.PrimaryLabel);
        Assert.DoesNotContain(snap.Inputs.Problems, p => p.Kind == ProblemKind.PixiTooOld);

        // The fix opens the latest release; the expander shows the problem and pixi's words.
        var actions = new FakeActions();
        var vm = new FlyoutViewModel(s, actions, new RecordingAnnouncer(), _time);
        vm.Apply(snap);
        Assert.StartsWith(title + Environment.NewLine, vm.TechText, StringComparison.Ordinal);
        Assert.Contains(Refused[0], vm.TechText, StringComparison.Ordinal);
        await vm.PrimaryCommand.ExecuteAsync(null);
        Assert.Contains("fix:UpdateRefused", actions.Calls);

        // Without pixi's words it stays the plain update failure, with Try again.
        ctl.UpdateRefusal = null;
        Assert.Equal(ProblemKind.UpdateFailed, StateRules.Describe(ctl.Build().Inputs, s).Problem!.Kind);
    }

    [Fact]
    public async Task A_setup_refusal_is_not_shown_once_an_engine_runs()
    {
        var launcher = new FakeLauncher();
        await using var sup = RunningSupervisor(launcher);
        var ctl = Controller(sup, Strings.En);
        ctl.SetupRefusal = PixiRefusal.Find(Refused);
        Assert.Equal(ProblemKind.PixiTooOld, StateRules.Describe(ctl.Build().Inputs, Strings.En).Problem!.Kind);
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running);
        Assert.DoesNotContain(ctl.Build().Inputs.Problems, p => p.Kind == ProblemKind.PixiTooOld);
    }

    [Fact]
    public void The_tech_details_lead_with_the_problem_shown()
    {
        var vm = new FlyoutViewModel(Strings.En, new FakeActions(), new RecordingAnnouncer(), _time);
        var tech = new TechDetails(["192.0.2.20"], null, "–", "CPU", null, @"C:\data");
        Assert.DoesNotContain("can't start", vm.FormatTech(tech), StringComparison.Ordinal);
        var shown = vm.FormatTech(tech, Problems.PixiTooOld(Strings.En, PixiRefusal.Find(Refused)!));
        Assert.StartsWith("Brasscribe can't start" + Environment.NewLine, shown, StringComparison.Ordinal);
        Assert.Contains(Refused[0], shown, StringComparison.Ordinal);
    }
}

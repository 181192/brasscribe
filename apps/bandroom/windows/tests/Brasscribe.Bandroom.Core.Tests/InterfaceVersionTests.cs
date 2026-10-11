using System.Net;
using System.Text.RegularExpressions;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>
/// Bandroom and the engine it starts must have the same interface version. When they differ Bandroom says which of
/// the two to update, with a fix that does something, and asks that engine nothing: no status, jobs, devices or pair
/// requests, and no pairing is opened. The one thing every engine is told, once when it first runs, is to close the
/// pairing code it opened as it started.
/// </summary>
public sealed class InterfaceVersionTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-interface").FullName;
    private readonly FlakyEngine _engine = new(new FakeEngine());

    /// <summary>What the engine's health says its interface version is; a test changes it for the next start.</summary>
    private int? _engineVersion = Wire.InterfaceVersion;

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private sealed class Metrics : IHostMetrics
    {
        public double SampleCpuPercent() => 20;
        public (ulong Total, ulong Available) Memory() => (16UL << 30, 8UL << 30);
        public long FreeBytes(string path) => 212_000_000_000;
    }

    [Theory]
    [InlineData(Wire.InterfaceVersion, InterfaceAnswer.Same)]
    [InlineData(Wire.InterfaceVersion + 1, InterfaceAnswer.UpdateBandroom)]
    [InlineData(Wire.InterfaceVersion - 1, InterfaceAnswer.UpdateEngine)]
    [InlineData(null, InterfaceAnswer.UpdateEngine)]
    public void The_engines_number_is_the_same_newer_older_or_missing(int? engine, InterfaceAnswer expected) =>
        Assert.Equal(expected, InterfaceMatch.Of(engine));

    /// <summary>Bandroom's number is the engine's own (engine/src/scribe_engine/wire.py).</summary>
    [SkippableFact]
    public void Bandrooms_number_is_the_engines()
    {
        const string relative = "engine/src/scribe_engine/wire.py";
        string? wire;
        try { wire = Path.Combine(TestPaths.RepoRoot, "engine", "src", "scribe_engine", "wire.py"); }
        catch (DirectoryNotFoundException) { wire = null; }
        Skip.If(wire is null, $"{relative} not found: the tests run outside a checkout");
        var number = Regex.Match(File.ReadAllText(wire!), @"^INTERFACE_VERSION\s*=\s*(\d+)\s*$", RegexOptions.Multiline);
        Assert.True(number.Success, $"{relative} has no INTERFACE_VERSION");
        Assert.Equal(number.Groups[1].Value, Wire.InterfaceVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static EngineApi ApiAnswering(string health)
    {
        var handler = new StubHandler();
        handler.Routes["GET /v1/health"] = (HttpStatusCode.OK, health);
        return new EngineApi(new HttpClient(handler), new Uri("http://127.0.0.1:8765/"), "admin-token");
    }

    [Fact]
    public async Task Health_carries_the_number_and_without_one_it_is_null()
    {
        var health = await ApiAnswering(
            """{"status":"ok","version":"0.9.4","interface_version":1,"device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kari's PC"}""").GetHealthAsync();
        Assert.Equal(1, health.InterfaceVersion);
        Assert.Equal("cpu", health.Device);
        var before = await ApiAnswering(
            """{"status":"ok","version":"0.9.3","device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kari's PC"}""").GetHealthAsync();
        Assert.Null(before.InterfaceVersion);
        // What it is, is still known: it counts as running, and is named in the flyout.
        Assert.Equal("0.9.3", before.Version);
        Assert.Equal("Brasscribe on Kari's PC", before.ServerName);
    }

    [Theory]
    [InlineData("1.5")]
    [InlineData("1.0")]
    [InlineData("\"1\"")]
    [InlineData("true")]
    [InlineData("null")]
    [InlineData("99999999999")]
    public async Task A_number_that_is_not_a_whole_number_is_an_engine_to_update_not_one_that_does_not_answer(string number)
    {
        var health = await ApiAnswering(
            $$"""{"status":"ok","version":"0.9.4","interface_version":{{number}},"device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kari's PC"}""").GetHealthAsync();
        Assert.Null(health.InterfaceVersion);
        Assert.Equal(InterfaceAnswer.UpdateEngine, InterfaceMatch.Of(health.InterfaceVersion));
        Assert.Equal("abc", health.ServerId);
    }

    [Fact]
    public async Task The_number_is_read_even_when_the_rest_of_health_cannot_be()
    {
        var health = await ApiAnswering($$"""{"interface_version":{{Wire.InterfaceVersion + 1}},"version":7,"device":null,"auth_required":"yes"}""").GetHealthAsync();
        Assert.Equal(Wire.InterfaceVersion + 1, health.InterfaceVersion);
        Assert.Equal(InterfaceAnswer.UpdateBandroom, InterfaceMatch.Of(health.InterfaceVersion));
    }

    /// <summary>A controller on a supervisor whose engine answers health with <see cref="_engineVersion"/>, wired before it starts.</summary>
    private (EngineSupervisor Supervisor, BandroomController Controller) Make(IStrings? strings = null)
    {
        var sup = new EngineSupervisor(new FakeLauncher(), new FakePorts(),
            (_, _) => Task.FromResult<HealthInfo?>(new HealthInfo("ok", "0.9.4", "cpu", false, "3f9c2a7e11", "Brasscribe on Kari's PC",
                InterfaceVersion: _engineVersion)),
            _ => new ProcessSpec("pixi", [], _dir, new Dictionary<string, string>()), new EngineLog(null),
            options: new SupervisorOptions { StopTimeout = TimeSpan.FromMilliseconds(50) });
        var ctl = new BandroomController(sup, _ => _engine, new Metrics(), strings ?? Strings.En, new BandroomPaths(_dir),
            new MachineInfo("Kari's PC", "Health_Speed_Cpu", "CPU", ["192.0.2.20"]));
        return (sup, ctl);
    }

    private static async Task Until(Func<bool> condition, string what)
    {
        for (int i = 0; i < 600 && !condition(); i++) await Task.Delay(5);
        Assert.True(condition(), what);
    }

    /// <summary>The engine runs, and what Bandroom does when one first runs has been done.</summary>
    private async Task<(EngineSupervisor Supervisor, BandroomController Controller)> RunningAsync(int? engineVersion, IStrings? strings = null,
        Action<BandroomController>? before = null)
    {
        _engineVersion = engineVersion;
        var (sup, ctl) = Make(strings);
        before?.Invoke(ctl);
        bool published = false;
        ctl.SnapshotReady += s => published |= s.Inputs.Engine == EngineState.Running;
        await sup.StartAsync();
        await Until(() => sup.State == EngineState.Running && published, "the engine did not reach Running");
        return (sup, ctl);
    }

    [Theory]
    [InlineData(Wire.InterfaceVersion)]
    [InlineData(Wire.InterfaceVersion + 1)]
    [InlineData(Wire.InterfaceVersion - 1)]
    [InlineData(null)]
    public async Task The_pairing_code_an_engine_opened_at_start_is_closed_when_it_first_runs_whatever_its_version(int? engineVersion)
    {
        _engine.Inner.PairingOpen = true; // as `scribe serve --lan` leaves it
        var (sup, ctl) = await RunningAsync(engineVersion);
        await using var _ = sup;

        Assert.Equal(["close"], _engine.Inner.Log);
        Assert.False(_engine.Inner.PairingOpen);
        Assert.Empty(_engine.Inner.Opens);

        // Once: checks and snapshots while it runs do not close a code the Pair window opens later.
        await ctl.TickAsync();
        ctl.Publish();
        Assert.Single(_engine.Inner.Log, "close");

        // The next start is another engine process with a code of its own.
        _engine.Inner.PairingOpen = true;
        await sup.RestartAsync();
        await Until(() => _engine.Inner.Log.Count(l => l == "close") == 2, "the restarted engine's start-up code was not closed");
        Assert.False(_engine.Inner.PairingOpen);
    }

    [Fact]
    public async Task An_engine_that_starts_while_the_Pair_window_is_open_keeps_its_code()
    {
        _engine.Inner.PairingOpen = true;
        var (sup, _) = await RunningAsync(Wire.InterfaceVersion, before: ctl => ctl.PairWindowOpen = () => true);
        await using var __ = sup;
        Assert.DoesNotContain("close", _engine.Inner.Log);
        Assert.True(_engine.Inner.PairingOpen);
    }

    [Fact]
    public async Task An_engine_with_the_same_number_is_asked_and_paired_on_as_before()
    {
        var (sup, ctl) = await RunningAsync(Wire.InterfaceVersion);
        await using var _ = sup;
        ctl.FlyoutOpen = true;
        await ctl.TickAsync();

        Assert.Equal(InterfaceAnswer.Same, ctl.Interface);
        Assert.NotNull(ctl.Api);
        Assert.Equal(1, _engine.StatusCalls);
        Assert.Equal(1, _engine.PairRequestCalls);
        Assert.Empty(ctl.Build().Inputs.Problems);
        Assert.Equal(PrimaryAction.PairPhone, StateRules.Describe(ctl.Build().Inputs, Strings.En).Primary);
    }

    [Theory]
    [InlineData(0, InterfaceAnswer.UpdateEngine, ProblemKind.EngineBehind)]
    [InlineData(null, InterfaceAnswer.UpdateEngine, ProblemKind.EngineBehind)]
    [InlineData(2, InterfaceAnswer.UpdateBandroom, ProblemKind.UpdateBandroom)]
    public async Task An_engine_with_another_number_is_asked_nothing_and_no_pairing_is_opened(int? engineVersion, InterfaceAnswer answer, ProblemKind kind)
    {
        var (sup, ctl) = await RunningAsync(engineVersion);
        await using var _ = sup;
        BandroomSnapshot? last = null;
        IReadOnlyList<DeviceInfo>? devices = null;
        ctl.SnapshotReady += s => last = s;
        ctl.DevicesChanged += d => devices = d;

        // The flyout open, so everything that is polled would be.
        ctl.FlyoutOpen = true;
        await ctl.TickAsync();
        await ctl.TickAsync();
        await ctl.RefreshDevicesAsync();

        Assert.Equal(answer, ctl.Interface);
        Assert.Null(ctl.Api);
        Assert.Equal(0, _engine.StatusCalls);
        Assert.Equal(0, _engine.PairRequestCalls);
        // Its health (the supervisor's), and the closing of the code it opened at start: nothing else.
        Assert.Equal(["close"], _engine.Inner.Log);
        Assert.Empty(devices!);
        Assert.Null(last!.Status);
        Assert.Null(last.Job);

        // The engine still runs (it is not restarted), and the state is Needs attention with the fix as the one button.
        Assert.Equal(EngineState.Running, sup.State);
        var info = StateRules.Describe(last.Inputs, Strings.En);
        Assert.Equal(DisplayState.NeedsAttention, info.State);
        Assert.Equal(kind, info.Problem!.Kind);
        Assert.Equal(PrimaryAction.Fix, info.Primary);

        // Pair a phone: nothing is opened on the engine, and no code or QR code is shown.
        var pair = new PairViewModel(Strings.En, () => ctl.Api, new RecordingAnnouncer());
        await pair.OpenAsync();
        Assert.Empty(_engine.Inner.Opens);
        Assert.False(_engine.Inner.PairingOpen);
        Assert.False(pair.IsOpen);
        Assert.Equal("", pair.Code);
        Assert.Equal("", pair.QrPayload);
    }

    // ---- the fix always does something ----

    [Theory]
    // A newer engine: only a newer Bandroom helps.
    [InlineData(InterfaceAnswer.UpdateBandroom, false, true, false, InterfaceFix.LatestBandroom)]
    [InlineData(InterfaceAnswer.UpdateBandroom, false, false, false, InterfaceFix.LatestBandroom)]
    // An older engine while this app bundles another one than is installed: the update from here.
    [InlineData(InterfaceAnswer.UpdateEngine, false, true, false, InterfaceFix.UpdateEngine)]
    // The installed one is already this app's: updating would do nothing.
    [InlineData(InterfaceAnswer.UpdateEngine, false, false, false, InterfaceFix.LatestBandroom)]
    // The update was run and the engine is still older: not the same button again.
    [InlineData(InterfaceAnswer.UpdateEngine, false, true, true, InterfaceFix.LatestBandroom)]
    [InlineData(InterfaceAnswer.UpdateEngine, false, false, true, InterfaceFix.LatestBandroom)]
    // A developer's own folder: nothing from here, either way.
    [InlineData(InterfaceAnswer.UpdateEngine, true, true, false, InterfaceFix.None)]
    [InlineData(InterfaceAnswer.UpdateBandroom, true, false, false, InterfaceFix.None)]
    public void The_fix_offered_is_one_that_does_something(InterfaceAnswer match, bool development, bool pending, bool tried, InterfaceFix expected) =>
        Assert.Equal(expected, InterfaceMatch.FixFor(match, development, pending, tried));

    public static TheoryData<string, int, bool, bool, ProblemKind, string, string, string> Words() => new()
    {
        { "en", 2, false, false, ProblemKind.UpdateBandroom, "Update Bandroom",
            "Brasscribe on this PC is newer than this copy of Bandroom, and they only work together when both are up to date.", "Get the latest Bandroom" },
        { "nb", 2, false, false, ProblemKind.UpdateBandroom, "Oppdater Bandroom",
            "Brasscribe på denne PC-en er nyere enn denne utgaven av Bandroom, og de virker bare sammen når begge er oppdatert.", "Last ned den nyeste Bandroom" },
        { "en", 0, true, false, ProblemKind.UpdateEngine, "Brasscribe needs to be updated",
            "Brasscribe on this PC is older than this copy of Bandroom, and they only work together when both are up to date.", "Update Brasscribe" },
        { "nb", 0, true, false, ProblemKind.UpdateEngine, "Brasscribe må oppdateres",
            "Brasscribe på denne PC-en er eldre enn denne utgaven av Bandroom, og de virker bare sammen når begge er oppdatert.", "Oppdater Brasscribe" },
        { "en", 0, false, false, ProblemKind.EngineBehind, "Brasscribe needs to be updated",
            "Brasscribe on this PC is older than this copy of Bandroom, and this copy can't update it. The latest Bandroom brings both up to date.", "Get the latest Bandroom" },
        { "nb", 0, false, false, ProblemKind.EngineBehind, "Brasscribe må oppdateres",
            "Brasscribe på denne PC-en er eldre enn denne utgaven av Bandroom, og denne utgaven kan ikke oppdatere den. Den nyeste Bandroom oppdaterer begge.", "Last ned den nyeste Bandroom" },
        { "en", 0, true, true, ProblemKind.DevelopmentEngine, "Brasscribe and Bandroom don't match",
            "Brasscribe runs from a development folder here, and it and this copy of Bandroom only work together when both are up to date. Update the folder, or build Bandroom from it.", "" },
        { "nb", 2, false, true, ProblemKind.DevelopmentEngine, "Brasscribe og Bandroom passer ikke sammen",
            "Brasscribe kjører fra en utviklingsmappe her, og den og denne utgaven av Bandroom virker bare sammen når begge er oppdatert. Oppdater mappen, eller bygg Bandroom fra den.", "" },
    };

    [Theory]
    [MemberData(nameof(Words))]
    public async Task The_flyout_says_which_of_the_two_to_update_and_its_button_does_something(
        string language, int engineVersion, bool pending, bool development, ProblemKind kind, string title, string why, string fix)
    {
        var s = language == "nb" ? Strings.Nb : Strings.En;
        var (sup, ctl) = await RunningAsync(engineVersion, s, c =>
        {
            c.EngineUpdatePending = pending;
            c.DevelopmentEngine = development;
        });
        await using var _ = sup;
        var snap = ctl.Build();
        var info = StateRules.Describe(snap.Inputs, s);
        Assert.Equal(kind, info.Problem!.Kind);
        Assert.Equal(title, info.Problem.Title);
        Assert.Equal(why, info.StatusSub);
        Assert.Equal(fix, info.PrimaryLabel);
        // The numbers are for the tech person's details, never the message.
        Assert.DoesNotContain(title + why + fix, char.IsDigit);
        Assert.Contains($"interface version is {engineVersion}; this Bandroom is built for {Wire.InterfaceVersion}", info.Problem.Details, StringComparison.Ordinal);

        var actions = new FakeActions();
        var vm = new FlyoutViewModel(s, actions, new RecordingAnnouncer());
        vm.Apply(snap);
        Assert.False(vm.PrimaryIsPair);
        // A button exactly when there is something for it to do.
        Assert.Equal(fix.Length > 0, vm.HasPrimary);
        Assert.Equal(fix.Length > 0 ? PrimaryAction.Fix : PrimaryAction.None, info.Primary);
        await vm.PrimaryCommand.ExecuteAsync(null);
        Assert.Equal(fix.Length > 0 ? ["fix:" + kind] : [], actions.Calls);
    }

    [Fact]
    public async Task After_one_update_that_left_the_engine_older_the_fix_is_the_latest_Bandroom_and_a_matching_engine_clears_it_all()
    {
        var (sup, ctl) = await RunningAsync(0, before: c => c.EngineUpdatePending = true);
        await using var _ = sup;
        Assert.Equal(ProblemKind.UpdateEngine, Assert.Single(ctl.Build().Inputs.Problems).Kind);

        // Update Brasscribe was chosen: the workspace is this app's now, and the engine restarted from it is still older.
        ctl.EngineUpdateTried = true;
        ctl.EngineUpdatePending = false;
        await sup.RestartAsync();
        await Until(() => sup.State == EngineState.Running, "the engine did not come back");
        var behind = Assert.Single(ctl.Build().Inputs.Problems);
        Assert.Equal(ProblemKind.EngineBehind, behind.Kind);
        Assert.Equal("Get the latest Bandroom", behind.FixLabel);

        // The latest Bandroom was installed, or the engine put right: it starts with this Bandroom's number.
        _engineVersion = Wire.InterfaceVersion;
        BandroomSnapshot? last = null;
        ctl.SnapshotReady += s => last = s;
        await sup.RestartAsync();
        await Until(() => sup.State == EngineState.Running && last is { Inputs.Engine: EngineState.Running }, "the engine did not come back");
        Assert.Equal(InterfaceAnswer.Same, ctl.Interface);
        Assert.Empty(last!.Inputs.Problems);
        Assert.NotNull(ctl.Api);
        Assert.Equal(PrimaryAction.PairPhone, StateRules.Describe(last.Inputs, Strings.En).Primary);
        // And should it fall behind again one day, the update from this app is offered afresh.
        Assert.False(ctl.EngineUpdateTried);
    }

    [Fact]
    public async Task After_a_failed_update_that_problem_comes_first_and_the_previous_engine_is_still_asked_nothing()
    {
        var (sup, ctl) = await RunningAsync(0, before: c => c.EngineUpdatePending = true);
        await using var _ = sup;
        ctl.UpdateFailure = "pixi install -e default exited with 1";
        var problems = ctl.Build().Inputs.Problems;
        Assert.Equal([ProblemKind.UpdateFailed, ProblemKind.UpdateEngine], problems.Select(p => p.Kind));
        Assert.Null(ctl.Api);
    }

    [Fact]
    public async Task No_engine_running_is_not_a_mismatch()
    {
        var (sup, ctl) = await RunningAsync(0);
        await sup.StopAsync();
        Assert.Equal(InterfaceAnswer.Same, ctl.Interface);
        Assert.DoesNotContain(ctl.Build().Inputs.Problems, p => p.IsInterface);
        await sup.DisposeAsync();
    }

    // ---- Phones and tablets ----

    private static DeviceInfo Phone(string id, string name) =>
        new(id, name, "ios", "2026-09-01T10:00:00Z", DateTimeOffset.UtcNow.AddSeconds(-5).ToString("O"), null, true);

    [Theory]
    [InlineData("en", "Brasscribe on this PC is older than this copy of Bandroom, and this copy can't update it. The latest Bandroom brings both up to date.")]
    [InlineData("nb", "Brasscribe på denne PC-en er eldre enn denne utgaven av Bandroom, og denne utgaven kan ikke oppdatere den. Den nyeste Bandroom oppdaterer begge.")]
    public async Task Phones_and_tablets_on_a_mismatch_says_why_instead_of_no_phones_yet_and_offers_no_pairing(string language, string why)
    {
        var s = language == "nb" ? Strings.Nb : Strings.En;
        var actions = new FakeActions();
        var said = new RecordingAnnouncer();
        var vm = new FlyoutViewModel(s, actions, said);
        var focus = new List<string>();
        vm.FocusRequested += focus.Add;

        // While the engine matched, its phones were listed.
        var (matching, ok) = await RunningAsync(Wire.InterfaceVersion, s);
        vm.Apply(ok.Build());
        vm.ApplyDevices([Phone("d-kari", "Kari's iPhone")], DateTimeOffset.UtcNow);
        Assert.True(vm.CanPair);
        Assert.Equal(s["Devices_Empty"], vm.EmptyDevicesText);
        await matching.DisposeAsync();

        var (sup, ctl) = await RunningAsync(0, s);
        await using var _ = sup;
        ctl.DevicesChanged += list => vm.ApplyDevices(list, DateTimeOffset.UtcNow);
        vm.Apply(ctl.Build());
        vm.ShowDevicesCommand.Execute(null);
        await ctl.RefreshDevicesAsync();

        // No rows from before (nothing could be done with them), the reason in place of "No phones yet", no Pair.
        Assert.Empty(vm.Devices);
        Assert.True(vm.HasNoDevices);
        Assert.Equal(why, vm.EmptyDevicesText);
        Assert.NotEqual(s["Devices_Empty"], vm.EmptyDevicesText);
        Assert.False(vm.CanPair);
        // A list that arrives late (read before the mismatch was known) is not shown either.
        vm.ApplyDevices([Phone("d-kari", "Kari's iPhone")], DateTimeOffset.UtcNow);
        Assert.Empty(vm.Devices);

        // Pair, should it be reached all the same, is never a click that does nothing: back to the problem, said aloud.
        said.Said.Clear();
        focus.Clear();
        vm.PairCommand.Execute(null);
        Assert.DoesNotContain("pair", actions.Calls);
        Assert.Equal(FlyoutView.Main, vm.View);
        Assert.Equal(["Primary"], focus);
        Assert.Equal([vm.ProblemTitle + ". " + why], said.Said);
    }

    [Fact]
    public async Task The_mismatch_need_not_be_the_first_problem_for_Phones_and_tablets_to_say_so()
    {
        var (sup, ctl) = await RunningAsync(0, before: c => c.EngineUpdatePending = true);
        await using var _ = sup;
        ctl.UpdateFailure = "pixi install -e default exited with 1";
        var vm = new FlyoutViewModel(Strings.En, new FakeActions(), new RecordingAnnouncer());
        vm.Apply(ctl.Build());
        Assert.Equal("Brasscribe couldn't finish updating", vm.ProblemTitle);
        Assert.False(vm.CanPair);
        Assert.StartsWith("Brasscribe on this PC is older than this copy of Bandroom", vm.EmptyDevicesText);
    }
}

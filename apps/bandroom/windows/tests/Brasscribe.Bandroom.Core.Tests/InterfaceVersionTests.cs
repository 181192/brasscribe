using System.Net;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>
/// Bandroom and the engine it starts must have the same interface version. When they differ Bandroom says which of
/// the two to update and asks that engine nothing: no status, jobs, devices or pair requests, and no pairing is opened.
/// </summary>
public sealed class InterfaceVersionTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-interface").FullName;
    private readonly FlakyEngine _engine = new(new FakeEngine());

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

    [Fact]
    public async Task Health_carries_the_number_and_an_engine_from_before_it_has_none()
    {
        var handler = new StubHandler();
        var api = new EngineApi(new HttpClient(handler), new Uri("http://127.0.0.1:8765/"), "admin-token");
        handler.Routes["GET /v1/health"] = (HttpStatusCode.OK,
            """{"status":"ok","version":"0.9.4","interface_version":1,"device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kari's PC"}""");
        Assert.Equal(1, (await api.GetHealthAsync()).InterfaceVersion);
        handler.Routes["GET /v1/health"] = (HttpStatusCode.OK,
            """{"status":"ok","version":"0.9.3","device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kari's PC"}""");
        Assert.Null((await api.GetHealthAsync()).InterfaceVersion);
    }

    /// <summary>A supervisor whose engine answers health with this interface version, and a controller on it.</summary>
    private async Task<(EngineSupervisor Supervisor, BandroomController Controller)> RunningAsync(int? engineVersion, IStrings? strings = null)
    {
        var sup = new EngineSupervisor(new FakeLauncher(), new FakePorts(),
            (_, _) => Task.FromResult<HealthInfo?>(new HealthInfo("ok", "0.9.4", "cpu", false, "3f9c2a7e11", "Brasscribe on Kari's PC",
                InterfaceVersion: engineVersion)),
            _ => new ProcessSpec("pixi", [], _dir, new Dictionary<string, string>()), new EngineLog(null));
        await sup.StartAsync();
        for (int i = 0; i < 400 && sup.State != EngineState.Running; i++) await Task.Delay(5);
        Assert.Equal(EngineState.Running, sup.State);
        var ctl = new BandroomController(sup, _ => _engine, new Metrics(), strings ?? Strings.En, new BandroomPaths(_dir),
            new MachineInfo("Kari's PC", "Health_Speed_Cpu", "CPU", ["192.0.2.20"]));
        return (sup, ctl);
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
    [InlineData(0, InterfaceAnswer.UpdateEngine, ProblemKind.UpdateEngine)]
    [InlineData(null, InterfaceAnswer.UpdateEngine, ProblemKind.UpdateEngine)]
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
        Assert.Empty(_engine.Inner.Log);
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

    [Theory]
    [InlineData("en", 2, "Update Bandroom",
        "Brasscribe on this PC is newer than this copy of Bandroom, and they only work together when both are up to date.", "Get the latest Bandroom")]
    [InlineData("nb", 2, "Oppdater Bandroom",
        "Brasscribe på denne PC-en er nyere enn denne utgaven av Bandroom, og de virker bare sammen når begge er oppdatert.", "Last ned den nyeste Bandroom")]
    [InlineData("en", 0, "Brasscribe needs to be updated",
        "Brasscribe on this PC is older than this copy of Bandroom, and they only work together when both are up to date.", "Update Brasscribe")]
    [InlineData("nb", 0, "Brasscribe må oppdateres",
        "Brasscribe på denne PC-en er eldre enn denne utgaven av Bandroom, og de virker bare sammen når begge er oppdatert.", "Oppdater Brasscribe")]
    public async Task The_flyout_says_which_of_the_two_to_update(string language, int engineVersion, string title, string why, string fix)
    {
        var s = language == "nb" ? Strings.Nb : Strings.En;
        var (sup, ctl) = await RunningAsync(engineVersion, s);
        await using var _ = sup;
        var snap = ctl.Build();
        var info = StateRules.Describe(snap.Inputs, s);
        Assert.Equal(title, info.Problem!.Title);
        Assert.Equal(why, info.StatusSub);
        Assert.Equal(fix, info.PrimaryLabel);
        // The numbers are for the tech person's details, never the message.
        Assert.DoesNotContain(title + why + fix, char.IsDigit);
        Assert.Contains($"interface version is {engineVersion}; this Bandroom is built for {Wire.InterfaceVersion}", info.Problem.Details, StringComparison.Ordinal);

        var actions = new FakeActions();
        var vm = new FlyoutViewModel(s, actions, new RecordingAnnouncer());
        vm.Apply(snap);
        Assert.False(vm.PrimaryIsPair);
        await vm.PrimaryCommand.ExecuteAsync(null);
        Assert.Contains("fix:" + info.Problem.Kind, actions.Calls);
        Assert.DoesNotContain("pair", actions.Calls);
    }

    [Fact]
    public async Task After_a_failed_update_that_problem_comes_first_and_the_previous_engine_is_still_asked_nothing()
    {
        var (sup, ctl) = await RunningAsync(0);
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
        Assert.DoesNotContain(ctl.Build().Inputs.Problems, p => p.Kind is ProblemKind.UpdateEngine or ProblemKind.UpdateBandroom);
        await sup.DisposeAsync();
    }
}

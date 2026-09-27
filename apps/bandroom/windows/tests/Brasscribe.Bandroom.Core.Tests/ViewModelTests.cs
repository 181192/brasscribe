using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class FlyoutViewModelTests
{
    private readonly FakeActions _actions = new();
    private readonly RecordingAnnouncer _said = new();
    private readonly FakeTimeProvider _time = new(DateTimeOffset.Parse("2026-09-27T12:05:00Z"));

    private FlyoutViewModel Make(IStrings? s = null) => new(s ?? Strings.En, _actions, _said, _time);

    private static BandroomSnapshot Snap(EngineState e = EngineState.Running, JobView? job = null, int online = 2, int paired = 3,
        IReadOnlyList<Problem>? problems = null, int queued = 0) =>
        new(new StateInputs(e, true, 1, false, problems ?? [], job?.Fraction, online),
            "Brasscribe on Kalli's PC",
            new StatusInfo("3f9c2a7e11", "Brasscribe on Kalli's PC", "0.9.4", online, paired, false, job is null ? 0 : 1, queued),
            job,
            new HealthSnapshot(12, 0.2, 86_400_000_000, true),
            "Health_Speed_Nvidia",
            new TechDetails(["192.168.1.20:8765"], 8765, "0.9.4", "CUDA · NVIDIA GeForce RTX 4070", "3f9c2a7e11deadbeef", @"C:\Users\kalli\AppData\Local\Brasscribe"));

    [Fact]
    public void Idle_flyout_matches_the_mockup()
    {
        var vm = Make();
        vm.Apply(Snap());
        Assert.Equal("Brasscribe on Kalli's PC", vm.Header);
        Assert.Equal("Running", vm.StatusWord);
        Assert.Equal("Ready. Phones and tablets can send recordings.", vm.StatusSub);
        Assert.Equal("Pair a phone", vm.PrimaryLabel);
        Assert.True(vm.PrimaryIsPair);
        Assert.Equal("2 connected now · 3 paired", vm.DevicesSummary);
        Assert.Equal("Calm", vm.LoadWord);
        Assert.Equal(1, vm.LoadLevel);
        Assert.Equal("Getting full", vm.MemoryWord);
        Assert.Equal(2, vm.MemoryLevel);
        Assert.Equal("86 GB free", vm.DiskText);
        Assert.Equal("Ready", vm.ReadyWord);
        Assert.Equal("Uses the graphics card (NVIDIA)", vm.SpeedCaption);
        Assert.Contains("192.168.1.20:8765", vm.TechText);
        Assert.Contains("3f9c2a7e…", vm.TechText);
        Assert.False(vm.IsBusy);
        Assert.Equal(TrayBadge.None, vm.Badge);
    }

    [Fact]
    public void Busy_shows_the_job_and_announces_the_state_once()
    {
        var vm = Make();
        vm.Apply(Snap());
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Notes", 0.62, 3), queued: 1));
        Assert.True(vm.IsBusy);
        Assert.Equal("Running · Making a score", vm.StatusWord);
        Assert.Equal("Writing down the notes", vm.JobStep);
        Assert.Equal("“Mikkel”", vm.JobSource);
        Assert.Equal("62% · about 3 min left", vm.JobProgressText);
        Assert.Equal("1 more waiting", vm.QueueText);
        Assert.Equal(TrayBadge.Pie, vm.Badge);
        Assert.Equal(4, vm.PieEighths);
        Assert.Equal(["Running · Making a score"], _said.Said);
        // The same reading again: nothing new to say.
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Notes", 0.63, 3)));
        Assert.Single(_said.Said);
        // 10 points later: progress is announced.
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Notes", 0.73, 2)));
        Assert.Equal("Writing down the notes, 73% · about 2 min left", _said.Said[^1]);
    }

    [Fact]
    public async Task Stop_while_busy_confirms_and_keep_going_does_nothing()
    {
        var vm = Make();
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Notes", 0.62, 3)));
        string? focus = null;
        vm.FocusRequested += f => focus = f;
        await vm.StopCommand.ExecuteAsync(null);
        Assert.Equal(FlyoutView.Confirm, vm.View);
        Assert.Equal("Stop while “Mikkel” is being made?", vm.ConfirmTitle);
        Assert.Equal("Stop now", vm.ConfirmPrimaryLabel);
        Assert.Equal("Keep going", vm.ConfirmSecondaryLabel);
        Assert.Equal("ConfirmTitle", focus);
        vm.ConfirmCancelCommand.Execute(null);
        Assert.Equal(FlyoutView.Main, vm.View);
        Assert.Empty(_actions.Calls);

        await vm.StopCommand.ExecuteAsync(null);
        await vm.ConfirmPrimaryCommand.ExecuteAsync(null);
        Assert.Equal(["stop"], _actions.Calls);
    }

    [Fact]
    public async Task Stop_names_the_phone_that_sent_the_recording_when_the_engine_says()
    {
        var vm = Make();
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Layers", 0.3, 5, "Kari's iPhone")));
        Assert.Equal("“Mikkel” from Kari's iPhone", vm.JobSource);
        Assert.Equal("Separating the soloist from the band", vm.JobStep);
        await vm.StopCommand.ExecuteAsync(null);
        Assert.Equal("Kari's iPhone keeps the recording and can send it again.", vm.ConfirmBody);
        vm.ConfirmCancelCommand.Execute(null);
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Separate", 0.3, 5)));
        Assert.Equal("Separating the instruments", vm.JobStep);
        await vm.StopCommand.ExecuteAsync(null);
        Assert.Equal("The phone keeps the recording and can send it again.", vm.ConfirmBody);
    }

    [Fact]
    public async Task Stop_when_idle_needs_no_confirmation()
    {
        var vm = Make();
        vm.Apply(Snap());
        await vm.StopCommand.ExecuteAsync(null);
        Assert.Equal(["stop"], _actions.Calls);
        Assert.Equal(FlyoutView.Main, vm.View);
    }

    [Fact]
    public async Task Restart_when_done_waits_for_the_job()
    {
        var vm = Make();
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Notes", 0.62, 3)));
        await vm.RestartCommand.ExecuteAsync(null);
        Assert.Equal("Restart when “Mikkel” is done?", vm.ConfirmTitle);
        Assert.Equal("Restart when done", vm.ConfirmPrimaryLabel);
        Assert.Equal("Restart now", vm.ConfirmTertiaryLabel);
        await vm.ConfirmPrimaryCommand.ExecuteAsync(null);
        Assert.True(vm.RestartPending);
        Assert.Empty(_actions.Calls);
        vm.Apply(Snap(job: new JobView("Mikkel", "Step_Layout", 0.95, 1)));
        Assert.Empty(_actions.Calls);
        vm.Apply(Snap());
        Assert.Equal(["restart"], _actions.Calls);
    }

    [Fact]
    public async Task Removing_a_device_confirms_then_focuses_the_next_row_or_the_heading()
    {
        var vm = Make();
        vm.Apply(Snap());
        var now = _time.GetUtcNow();
        vm.ApplyDevices([
            new DeviceInfo("d1", "Kari's iPhone", "ios", "2026-09-01T10:00:00Z", now.AddSeconds(-5).ToString("O"), null, true),
            new DeviceInfo("d2", "Band iPad", "ios", "2026-09-01T10:00:00Z", now.AddDays(-3).ToString("O"), null, false),
        ], now);
        var foci = new List<string>();
        vm.FocusRequested += foci.Add;
        vm.ShowDevicesCommand.Execute(null);
        Assert.Equal("Back", foci[^1]);
        Assert.Equal("Connected now", vm.Devices[0].Subtitle);
        Assert.Equal("Last used 3 days ago", vm.Devices[1].Subtitle);
        Assert.Equal("Remove Kari's iPhone", vm.Devices[0].RemoveName);

        vm.RemoveDeviceCommand.Execute(vm.Devices[0]);
        Assert.Equal("Remove Kari's iPhone?", vm.ConfirmTitle);
        await vm.ConfirmPrimaryCommand.ExecuteAsync(null);
        Assert.Equal(["remove:d1"], _actions.Calls);
        Assert.Equal(FlyoutView.Devices, vm.View);
        Assert.Equal("Row:0", foci[^1]);
        Assert.Contains("Kari's iPhone is removed.", _said.Said);

        vm.RemoveDeviceCommand.Execute(vm.Devices[0]);
        await vm.ConfirmPrimaryCommand.ExecuteAsync(null);
        Assert.False(vm.HasDevices);
        Assert.Equal("DevicesHeading", foci[^1]);
    }

    [Fact]
    public void Escape_leaves_a_sub_view_first()
    {
        var vm = Make();
        vm.Apply(Snap());
        vm.ShowDevicesCommand.Execute(null);
        Assert.False(vm.Escape());
        Assert.Equal(FlyoutView.Main, vm.View);
        Assert.True(vm.Escape());
    }

    [Fact]
    public async Task The_primary_follows_the_state()
    {
        var vm = Make();
        vm.Apply(Snap(EngineState.Stopped));
        Assert.Equal("Start Brasscribe", vm.PrimaryLabel);
        await vm.PrimaryCommand.ExecuteAsync(null);
        vm.Apply(Snap(EngineState.Error));
        Assert.Equal("Try again", vm.PrimaryLabel);
        await vm.PrimaryCommand.ExecuteAsync(null);
        vm.Apply(Snap(EngineState.Stopped, problems: [Problems.NoFreePort(Strings.En)]));
        Assert.Equal("Needs attention", vm.StatusWord);
        await vm.PrimaryCommand.ExecuteAsync(null);
        vm.Apply(Snap(problems: [Problems.LowDisk(Strings.En, 2_100_000_000, "C:\\data")]));
        Assert.Equal("2.1 GB free. Brasscribe needs 3 GB to make a score.", vm.StatusSub);
        Assert.Equal("Space is running low", vm.ProblemTitle);
        Assert.Equal("2.1 GB free", Strings.En.Format("Health_Disk_Value", HealthWords.GigabytesText(2_150_000_000, Strings.En.Culture)));
        await vm.PrimaryCommand.ExecuteAsync(null);
        vm.Apply(Snap());
        await vm.PrimaryCommand.ExecuteAsync(null);
        Assert.Equal(["start", "start", "restart", "fix:LowDisk", "pair"], _actions.Calls);
    }

    [Fact]
    public void Norwegian_dates_and_summary()
    {
        var now = DateTimeOffset.Parse("2026-10-10T12:00:00+02:00");
        var d = new DeviceInfo("d", "Ola's Pixel 8", "android", "2026-09-01T10:00:00Z", "2026-09-26T10:00:00+02:00", null, false);
        Assert.Equal("Sist brukt 26. september", DeviceText.Subtitle(d, now, Strings.Nb));
        Assert.Equal("Last used 26 September", DeviceText.Subtitle(d, now, Strings.En));
        Assert.Equal("Ingen tilkoblet nå · 3 sammenkoblet", DeviceText.Summary(0, 3, Strings.Nb));
        Assert.Equal("2,1 GB ledig. Brasscribe trenger 3 GB for å lage et partitur.", Problems.LowDisk(Strings.Nb, 2_150_000_000, "C:\\d").Why);
        var vm = Make(Strings.Nb);
        vm.Apply(Snap());
        Assert.Equal("Kjører", vm.StatusWord);
        Assert.Equal("Koble til en telefon", vm.PrimaryLabel);
    }

    [Fact]
    public void Connected_devices_come_first_then_by_last_use()
    {
        var now = DateTimeOffset.Parse("2026-09-27T12:00:00Z");
        var rows = DeviceText.Rows([
            new("a", "Old", "ios", "x", "2026-09-01T10:00:00Z"),
            new("b", "Recent", "android", "x", "2026-09-26T10:00:00Z"),
            new("c", "Online", "ios", "x", "2026-09-20T10:00:00Z", null, true),
            new("d", "Band iPad", "ios", "x", "2026-09-27T11:59:40Z"), // no "online" field: seen within a minute
        ], now, Strings.En);
        Assert.Equal(["d", "c", "b", "a"], rows.Select(r => r.Id));
        Assert.True(rows[0].IsTablet);
    }
}

public sealed class PairViewModelTests
{
    private readonly FakeEngine _engine = new();
    private readonly RecordingAnnouncer _said = new();
    private readonly FakeTimeProvider _time = new(DateTimeOffset.Parse("2026-09-27T12:00:00Z"));

    private PairViewModel Make(IStrings? s = null) => new(s ?? Strings.En, () => _engine, _said, _time);

    [Fact]
    public async Task Opening_asks_for_a_window_without_expiry_and_shows_three_ways()
    {
        var vm = Make();
        await vm.OpenAsync();
        Assert.Equal(new PairingOpenRequest(null, true, false), _engine.Opens.Single());
        Assert.Equal("482 914", vm.CodeDisplay);
        Assert.Equal("Code: 4 8 2, 9 1 4", vm.CodeSpoken);
        Assert.StartsWith("brasscribe://pair?v=1", vm.QrPayload);
        Assert.Equal("QR code for pairing with Brasscribe on Kalli's PC. It holds the same code: 482 914.", vm.QrSpoken);
        Assert.Equal("On the phone, open Brasscribe › Settings › Your computer and choose ", vm.Way1Before);
        Assert.Equal("Brasscribe on Kalli's PC", vm.Way1Name);
        Assert.Equal(". Then allow it here.", vm.Way1After);
        Assert.Equal("Or type this address in Brasscribe on the phone: 192.168.1.20, port 8765", vm.HelpAddress);
        Assert.Contains("192 dot 168 dot 1 dot 20", vm.HelpAddressSpoken);
        Assert.True(vm.IsWaiting);
        Assert.Equal(["Waiting for a phone."], _said.Said);
    }

    [Fact]
    public async Task Norwegian_way_one_names_the_computer_in_its_own_sentence()
    {
        var vm = Make(Strings.Nb);
        await vm.OpenAsync();
        Assert.Equal("Brasscribe på Kalli's PC", vm.Way1Name);
        Assert.StartsWith("Åpne Brasscribe på telefonen", vm.Way1Before);
    }

    [Fact]
    public async Task A_new_device_means_paired_and_pair_another_gets_a_fresh_code()
    {
        _engine.Devices.Add(new("old", "Band iPad", "ios", "x", "2026-09-26T10:00:00Z"));
        var vm = Make();
        int focus = 0;
        vm.PairedFocusRequested += () => focus++;
        await vm.OpenAsync();
        string first = vm.Code;
        await vm.TickAsync();
        Assert.False(vm.HasPaired);

        _engine.Devices.Add(new("new", "Kari's iPhone", "ios", "x", "2026-09-27T12:00:00Z"));
        _engine.PairingOpen = false; // the single-use code is spent
        await vm.TickAsync();
        Assert.True(vm.HasPaired);
        Assert.Equal("Kari's iPhone is paired.", vm.PairedText);
        Assert.Equal(1, focus);
        Assert.Contains("Kari's iPhone is paired.", _said.Said);
        Assert.False(vm.IsOpen);

        await vm.OpenAsync(); // Pair another phone
        Assert.NotEqual(first, vm.Code);
        Assert.True(vm.IsOpen);
        Assert.False(vm.HasPaired);
    }

    [Fact]
    public async Task A_code_with_an_expiry_is_extended_in_the_background()
    {
        _engine.ExpiresAt = _time.GetUtcNow().AddMinutes(10).ToString("O");
        var vm = Make();
        await vm.OpenAsync();
        await vm.TickAsync();
        Assert.Single(_engine.Opens);
        _time.Advance(TimeSpan.FromMinutes(9));
        await vm.TickAsync();
        Assert.Equal(new PairingOpenRequest(600, true, true), _engine.Opens[^1]);
    }

    [Fact]
    public async Task Too_many_wrong_codes_shows_the_lockout_until_it_passes_and_says_it_once()
    {
        var vm = Make();
        await vm.OpenAsync();
        Assert.False(vm.IsLockedOut);
        _engine.LockedUntil = _time.GetUtcNow().AddSeconds(30).ToString("O");
        await vm.TickAsync();
        Assert.True(vm.IsLockedOut);
        Assert.Equal("Too many wrong codes. Wait a moment, or allow the phone here.", vm.LockoutText);
        await vm.TickAsync();
        Assert.Single(_said.Said, "Too many wrong codes. Wait a moment, or allow the phone here.");
        Assert.True(vm.IsOpen); // the code itself stays the same
        _time.Advance(TimeSpan.FromSeconds(31));
        await vm.TickAsync();
        Assert.False(vm.IsLockedOut);
        _engine.LockedUntil = null;
        await vm.TickAsync();
        Assert.False(vm.IsLockedOut);
    }

    [Fact]
    public void Locked_until_is_read_from_the_pairing_state()
    {
        var s = System.Text.Json.JsonSerializer.Deserialize<PairingState>("""
            {"open":true,"code":"482913","expires_at":null,"single_use":true,"server_id":"x","server_name":"Brasscribe on PC",
             "hosts":[],"fingerprint":null,"uri":"brasscribe://pair?v=1","locked_until":"2026-09-27T12:00:30+00:00"}
            """, EngineJson.Options)!;
        Assert.Equal(DateTimeOffset.Parse("2026-09-27T12:00:30Z"), s.LockedUntilTime);
        var old = System.Text.Json.JsonSerializer.Deserialize<PairingState>("""
            {"open":true,"code":"1","expires_at":null,"single_use":true,"server_id":"x","server_name":"n","hosts":[],"fingerprint":null,"uri":"u"}
            """, EngineJson.Options)!;
        Assert.Null(old.LockedUntilTime);
    }

    [Fact]
    public async Task Done_closes_the_pairing_window()
    {
        var vm = Make();
        await vm.OpenAsync();
        await vm.CloseAsync();
        Assert.Contains("close", _engine.Log);
        Assert.False(_engine.PairingOpen);
    }

    [Fact]
    public async Task Without_an_engine_the_window_says_so()
    {
        var vm = new PairViewModel(Strings.En, () => null, _said, _time);
        await vm.OpenAsync();
        Assert.True(vm.HasError);
        Assert.False(vm.IsOpen);
    }

    [Fact]
    public async Task Allow_with_the_match_number_and_an_expired_request()
    {
        var watcher = new PairRequestWatcher(_time);
        var vm = Make();
        watcher.Arrived += r => vm.AddRequest(r, (id, ok) => watcher.DecideAsync(_engine, id, ok));
        watcher.Gone += vm.RequestGone;

        _engine.Requests.Add(new("r1", "Kari's iPhone", "ios", "4719", _time.GetUtcNow().ToString("O"), "pending"));
        await watcher.PollAsync(_engine);
        var req = Assert.Single(vm.Requests);
        Assert.Equal("Allow Kari's iPhone?", req.Title);
        Assert.Equal("4719", req.MatchCode);
        Assert.Equal("The phone shows the number: 4 7 1 9", req.MatchSpoken);
        await req.AllowCommand.ExecuteAsync(null);
        Assert.Empty(vm.Requests);
        Assert.Empty(_engine.Requests);

        _engine.Requests.Add(new("r2", "Ola's Pixel 8", "android", "1234", _time.GetUtcNow().ToString("O"), "pending"));
        await watcher.PollAsync(_engine);
        _time.Advance(TimeSpan.FromMinutes(2));
        await watcher.PollAsync(_engine); // lapsed after two minutes
        var expired = Assert.Single(vm.Requests);
        Assert.True(expired.IsExpired);
        Assert.False(expired.IsActive);
        Assert.Contains("This request has expired. Choose this computer on the phone again.", _said.Said);
    }

    [Fact]
    public async Task Allowing_a_request_the_engine_already_forgot_shows_expired()
    {
        var watcher = new PairRequestWatcher(_time);
        var vm = Make();
        var req = vm.AddRequest(new("gone", "Kari's iPhone", "ios", "4719", _time.GetUtcNow().ToString("O"), "pending"),
            (id, ok) => watcher.DecideAsync(_engine, id, ok));
        await req.AllowCommand.ExecuteAsync(null);
        Assert.True(req.IsExpired);
    }
}

public sealed class ControllerTests
{
    private sealed class Metrics : IHostMetrics
    {
        public double Cpu = 20;
        public long Free = 212_000_000_000;
        public double SampleCpuPercent() => Cpu;
        public (ulong Total, ulong Available) Memory() => (16UL << 30, 8UL << 30);
        public long FreeBytes(string path) => Free;
    }

    [Fact]
    public async Task Snapshots_combine_supervisor_status_and_host_health()
    {
        var dir = Directory.CreateTempSubdirectory("bandroom-ctl").FullName;
        try
        {
            var engine = new FakeEngine();
            engine.Devices.Add(new("d1", "Kari's iPhone", "ios", "x", DateTimeOffset.UtcNow.ToString("O"), null, true));
            var launcher = new FakeLauncher();
            var sup = new EngineSupervisor(launcher, new FakePorts(),
                (_, _) => Task.FromResult<HealthInfo?>(new HealthInfo("ok", "0.9.4", "cuda", false, "3f9c2a7e11", "Brasscribe on Kalli's PC")),
                p => new ProcessSpec("pixi", [], dir, new Dictionary<string, string>()), new EngineLog(null));
            var metrics = new Metrics();
            var ctl = new BandroomController(sup, _ => engine, metrics, Strings.En, new BandroomPaths(dir),
                new MachineInfo("Kalli's PC", "Health_Speed_Nvidia", "CUDA · RTX 4070", ["192.168.1.20"]));
            BandroomSnapshot? last = null;
            IReadOnlyList<DeviceInfo>? devices = null;
            ctl.SnapshotReady += s => last = s;
            ctl.DevicesChanged += d => devices = d;

            await ctl.TickAsync();
            Assert.Equal(EngineState.Stopped, last!.Inputs.Engine);
            Assert.Equal("Brasscribe on Kalli's PC", last.Header);

            await sup.StartAsync();
            for (int i = 0; i < 200 && sup.State != EngineState.Running; i++) await Task.Delay(5);
            ctl.FlyoutOpen = true;
            await ctl.TickAsync();
            Assert.Equal(1, last.Status!.OnlineDevices);
            Assert.Single(devices!);
            Assert.Equal(["192.168.1.20:8765"], last.Tech.Addresses);
            Assert.Equal(Level.Low, last.Health!.Load);
            Assert.Empty(last.Inputs.Problems);

            metrics.Free = 2_100_000_000;
            await ctl.TickAsync();
            Assert.Equal(ProblemKind.LowDisk, Assert.Single(last.Inputs.Problems).Kind);
            await sup.StopAsync();
        }
        finally { Directory.Delete(dir, true); }
    }
}

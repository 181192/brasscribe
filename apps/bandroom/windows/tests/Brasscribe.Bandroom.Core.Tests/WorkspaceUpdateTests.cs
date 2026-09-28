using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>
/// The app's workspace and the copy in the data folder after an app update: stamp compare, the all-or-nothing swap,
/// what it keeps, lockfile changed or not, and rollback when the engine environment won't install.
/// </summary>
public sealed class WorkspaceUpdateTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-update").FullName;
    private readonly BandroomPaths _paths;

    public WorkspaceUpdateTests()
    {
        _paths = new BandroomPaths(Path.Combine(_dir, "data"));
        WorkspaceSwap.RetryDelay = _ => TimeSpan.Zero;
    }

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private static void Write(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    private static string? Read(string path) => File.Exists(path) ? File.ReadAllText(path) : null;

    private string Studio => Path.Combine(_paths.Workspace, "engine", "src", "brasscribe_engine", "static", "assets", "studio.js");

    /// <summary>An app workspace; <paramref name="studio"/> is the file that changes between builds.</summary>
    private string Bundle(string name, string studio, string lockText = "version: 6\n")
    {
        var b = Path.Combine(_dir, name);
        Write(Path.Combine(b, "pixi.toml"), "[workspace]\nname = \"brasscribe\"\n");
        Write(Path.Combine(b, "pixi.lock"), lockText);
        Write(Path.Combine(b, "engine", "src", "brasscribe_engine", "static", "assets", "studio.js"), studio);
        Write(Path.Combine(b, "music", "src", "music.py"), "# music\n");
        Write(Path.Combine(b, "ml", "adapters", "run_adapter.py"), "# adapters\n");
        Write(Path.Combine(b, WorkspaceStamp.FileName), "{\"commit\": \"c3dc2ad\", \"version\": \"0.1.0\"}");
        return b;
    }

    private static Bootstrapper Boot(BandroomPaths paths, string bundle, FakeLauncher launcher) =>
        new(paths, bundle, "pixi", launcher, new EngineLog(null));

    /// <summary>The first run, with every environment installed, plus things of the user's own.</summary>
    private async Task Installed(string bundle)
    {
        await Boot(_paths, bundle, new FakeLauncher { ExitImmediately = _ => 0 }).RunAsync(false, null, CancellationToken.None);
        Write(Path.Combine(_paths.Workspace, ".pixi", "envs", "default", "Scripts", "brasscribe.exe"), "engine env");
        Write(Path.Combine(_paths.Workspace, "notes.txt"), "keep me");
        Write(Path.Combine(_paths.DataDir, "companion", "devices.json"), "{\"devices\": []}");
        Write(Path.Combine(_paths.Models, "mega53", "model.ckpt"), "weights");
        Write(Path.Combine(_paths.DataDir, "runs", "job-1", "score.musicxml"), "<score/>");
    }

    private void UserDataIsIntact()
    {
        Assert.Equal("engine env", Read(Path.Combine(_paths.Workspace, ".pixi", "envs", "default", "Scripts", "brasscribe.exe")));
        Assert.Equal("keep me", Read(Path.Combine(_paths.Workspace, "notes.txt")));
        Assert.Equal("{\"devices\": []}", Read(Path.Combine(_paths.DataDir, "companion", "devices.json")));
        Assert.Equal("weights", Read(Path.Combine(_paths.Models, "mega53", "model.ckpt")));
        Assert.Equal("<score/>", Read(Path.Combine(_paths.DataDir, "runs", "job-1", "score.musicxml")));
    }

    // ----- stamp compare -----

    [Fact]
    public void The_stamp_is_the_macOS_builds_recipe_over_content_not_dates()
    {
        // `find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256` over these two files.
        var d = Path.Combine(_dir, "tiny");
        Write(Path.Combine(d, "pixi.lock"), "version: 6\n");
        Write(Path.Combine(d, "engine", "a.py"), "x\n");
        Write(Path.Combine(d, WorkspaceStamp.FileName), "{}");
        const string expected = "582940b0d7182786d0ed162dff6eae3fce22840025b40328a3afe01aeb85e51c";
        Assert.Equal(expected, WorkspaceStamp.Compute(d).Stamp);
        File.SetLastWriteTimeUtc(Path.Combine(d, "engine", "a.py"), new DateTime(2001, 1, 1, 0, 0, 0, DateTimeKind.Utc));
        Assert.Equal(expected, WorkspaceStamp.Compute(d).Stamp);
        Write(Path.Combine(d, "engine", "a.py"), "y\n");
        Assert.NotEqual(expected, WorkspaceStamp.Compute(d).Stamp);
    }

    [Fact]
    public async Task A_new_build_of_the_workspace_is_pending_and_the_same_build_is_not()
    {
        var v1 = Bundle("v1", "old studio");
        await Installed(v1);
        var same = Boot(_paths, v1, new FakeLauncher());
        Assert.True(same.WorkspaceCurrent);
        Assert.Empty(same.Pending(false));
        Assert.Equal("c3dc2ad", WorkspaceStamp.Read(_paths.Workspace)?.Commit);

        var boot = Boot(_paths, Bundle("v2", "fixed studio"), new FakeLauncher());
        Assert.False(boot.WorkspaceCurrent);
        Assert.True(boot.IsUpdate);
        Assert.Equal(["workspace"], boot.Pending(false));
    }

    [Fact]
    public void The_short_stamp_names_the_commit()
    {
        Assert.Equal("0cf2582 · 5faffacca071", new WorkspaceStamp("5faffacca071b90cf438", Commit: "0cf2582").Short);
        Assert.Equal("5faffacca071", new WorkspaceStamp("5faffacca071b90cf438").Short);
    }

    // ----- the update -----

    [Fact]
    public async Task An_unchanged_lockfile_replaces_the_code_and_reuses_the_environments()
    {
        await Installed(Bundle("v1", "old studio"));
        Write(Path.Combine(_paths.Workspace, "engine", "src", "brasscribe_engine", "removed.py"), "gone in v2");
        var launcher = new FakeLauncher { ExitImmediately = _ => 0 };
        var boot = Boot(_paths, Bundle("v2", "fixed studio"), launcher);

        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.Empty(launcher.Started);
        Assert.Equal("fixed studio", Read(Studio));
        Assert.False(File.Exists(Path.Combine(_paths.Workspace, "engine", "src", "brasscribe_engine", "removed.py")));
        Assert.True(boot.IsComplete(false));
        Assert.True(boot.EngineReady);
        Assert.False(Directory.Exists(Path.Combine(_paths.Workspace, WorkspaceSwap.WorkDir)));
        UserDataIsIntact();
    }

    [Fact]
    public async Task A_new_lockfile_installs_every_environment_again()
    {
        await Installed(Bundle("v1", "old studio"));
        var launcher = new FakeLauncher { ExitImmediately = _ => 0 };
        var boot = Boot(_paths, Bundle("v2", "fixed studio", "version: 6\n# numpy 2.6\n"), launcher);
        Assert.Equal("workspace", boot.Pending(false)[0]);
        Assert.Contains("default", boot.Pending(false));

        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.Equal(EnvironmentPlan.Environments(false), launcher.Started.Select(s => s.Spec.Arguments[^1]));
        Assert.Equal("version: 6\n# numpy 2.6\n", Read(Path.Combine(_paths.Workspace, "pixi.lock")));
        Assert.True(boot.IsComplete(false));
        UserDataIsIntact();
    }

    [Fact]
    public async Task A_failed_engine_install_puts_the_old_copy_back_and_its_engine_can_still_start()
    {
        var v1 = Bundle("v1", "old studio");
        await Installed(v1);
        var before = WorkspaceStamp.Read(_paths.Workspace);
        var launcher = new FakeLauncher { ExitImmediately = spec => spec.Arguments[^1] == "default" ? 1 : 0 };
        var boot = Boot(_paths, Bundle("v2", "fixed studio", "version: 6\n# numpy 2.6\n"), launcher);

        var ex = await Assert.ThrowsAsync<BootstrapException>(() => boot.RunAsync(false, null, CancellationToken.None));
        Assert.Equal("default", ex.Environment);
        Assert.Equal("old studio", Read(Studio));
        Assert.Equal("version: 6\n", Read(Path.Combine(_paths.Workspace, "pixi.lock")));
        Assert.Equal(before, WorkspaceStamp.Read(_paths.Workspace));
        Assert.True(boot.EngineReady); // the previous engine starts meanwhile
        Assert.Equal(["workspace", "default"], boot.Pending(false).Take(2)); // Try again does it all again
        UserDataIsIntact();
    }

    [Fact]
    public async Task Quitting_during_the_engine_install_puts_the_old_copy_back()
    {
        await Installed(Bundle("v1", "old studio"));
        var launcher = new FakeLauncher();
        var boot = Boot(_paths, Bundle("v2", "fixed studio", "version: 6\n# new\n"), launcher);
        using var cts = new CancellationTokenSource();
        var run = boot.RunAsync(false, null, cts.Token);
        for (int i = 0; i < 200 && launcher.Started.Count == 0; i++) await Task.Delay(5);
        Assert.Equal("fixed studio", Read(Studio)); // swapped in while pixi installs
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal("old studio", Read(Studio));
        Assert.True(boot.EngineReady);
        UserDataIsIntact();
    }

    [Fact]
    public async Task A_failed_adapter_install_after_the_engine_keeps_the_new_copy()
    {
        await Installed(Bundle("v1", "old studio"));
        var launcher = new FakeLauncher { ExitImmediately = spec => spec.Arguments[^1] == "beat-this" ? 1 : 0 };
        var boot = Boot(_paths, Bundle("v2", "fixed studio", "version: 6\n# new\n"), launcher);
        await Assert.ThrowsAsync<BootstrapException>(() => boot.RunAsync(false, null, CancellationToken.None));
        Assert.Equal("fixed studio", Read(Studio));
        Assert.True(boot.EngineReady);
        Assert.Equal(["beat-this", "separator", "muscriptor", "mega53", "panns"], boot.Pending(false));
    }

    // ----- the swap -----

    [Fact]
    public async Task A_failure_part_way_through_the_swap_puts_the_old_copy_back()
    {
        var v1 = Bundle("v1", "old studio");
        await Installed(v1);
        var before = WorkspaceStamp.Read(_paths.Workspace);
        var v2 = Bundle("v2", "fixed studio");
        // engine\ is already in place when music\ fails.
        Assert.Throws<IOException>(() => WorkspaceSwap.Install(v2, _paths.Workspace, WorkspaceStamp.Compute(v2),
            name => { if (name == "music") throw new IOException("disk full"); }));
        Assert.Equal("old studio", Read(Studio));
        Assert.Equal(before, WorkspaceStamp.Read(_paths.Workspace));
        Assert.True(File.Exists(Path.Combine(_paths.Workspace, "music", "src", "music.py")));
        Assert.False(Directory.Exists(Path.Combine(_paths.Workspace, WorkspaceSwap.WorkDir)));
        UserDataIsIntact();
    }

    [Fact]
    public async Task An_update_cut_short_is_undone_at_the_next_start()
    {
        await Installed(Bundle("v1", "old studio"));
        var before = WorkspaceStamp.Read(_paths.Workspace);
        var v2 = Bundle("v2", "fixed studio");
        Write(Path.Combine(v2, "kvartett", "k.py"), "# new in v2\n");
        _ = WorkspaceSwap.Install(v2, _paths.Workspace, WorkspaceStamp.Compute(v2)); // never committed: the app quit
        Assert.Equal("fixed studio", Read(Studio));

        Boot(_paths, v2, new FakeLauncher()).RecoverInterruptedUpdate();
        Assert.Equal("old studio", Read(Studio));
        Assert.Equal(before, WorkspaceStamp.Read(_paths.Workspace));
        Assert.False(Directory.Exists(Path.Combine(_paths.Workspace, "kvartett")));
        Assert.False(Directory.Exists(Path.Combine(_paths.Workspace, WorkspaceSwap.WorkDir)));
        UserDataIsIntact();
    }

    // ----- what the flyout says -----

    [Fact]
    public void Updating_shows_its_progress_and_a_failed_update_needs_attention_with_try_again()
    {
        var updating = new StateInputs(EngineState.Stopped, true, 0.3, true, [], null, 0);
        var info = StateRules.Describe(updating, Strings.En);
        Assert.Equal(DisplayState.Updating, info.State);
        Assert.Equal("Updating Brasscribe… 30%. Back in about a minute. Phones reconnect by themselves.", info.StatusSub);
        Assert.StartsWith("Oppdaterer Brasscribe … 30 %.", StateRules.Describe(updating, Strings.Nb).StatusSub);

        var failed = new StateInputs(EngineState.Running, true, 1, false, [Problems.UpdateFailed(Strings.En, "pixi install -e default exited with 1")], null, 0);
        info = StateRules.Describe(failed, Strings.En);
        Assert.Equal(DisplayState.NeedsAttention, info.State);
        Assert.Equal(ProblemKind.UpdateFailed, info.Problem?.Kind);
        Assert.Equal("Brasscribe couldn't finish updating", info.Problem?.Title);
        Assert.Equal("Try again", info.PrimaryLabel);
    }

    [Fact]
    public void The_tech_details_show_the_engines_build_and_the_apps_workspace()
    {
        var vm = new FlyoutViewModel(Strings.En, new FakeActions(), new RecordingAnnouncer(), TimeProvider.System);
        var tech = new TechDetails([], 8765, "0.1.0", "CPU", "3f9c2a7e11", @"C:\Users\kalli\AppData\Local\Brasscribe",
            Build: "c3dc2ad 5faffacca071", Workspace: "0cf2582 · 68fe81c4cca4");
        string text = vm.FormatTech(tech);
        Assert.Contains("Engine build c3dc2ad 5faffacca071", text);
        Assert.Contains("Workspace    0cf2582 · 68fe81c4cca4", text);
        Assert.Contains("–", new FlyoutViewModel(Strings.Nb, new FakeActions(), new RecordingAnnouncer(), TimeProvider.System)
            .FormatTech(tech with { Build = null }));
    }

    [Fact]
    public void Health_from_an_engine_without_a_build_still_reads()
    {
        var old = System.Text.Json.JsonSerializer.Deserialize<HealthInfo>(
            """{"status":"ok","version":"0.1.0","device":"cpu","auth_required":false,"server_id":"a","server_name":"b"}""", EngineJson.Options);
        Assert.Null(old!.Build);
        var now = System.Text.Json.JsonSerializer.Deserialize<HealthInfo>(
            """{"status":"ok","version":"0.1.0","build":"c3dc2ad 5faffacca071","device":"cpu","auth_required":false,"server_id":"a","server_name":"b"}""",
            EngineJson.Options);
        Assert.Equal("c3dc2ad 5faffacca071", now!.Build);
    }

    [Fact]
    public void A_missing_app_workspace_changes_nothing()
    {
        Write(Path.Combine(_paths.Workspace, "pixi.toml"), "old");
        Assert.Throws<DirectoryNotFoundException>(() =>
            WorkspaceSwap.Install(Path.Combine(_dir, "missing"), _paths.Workspace, new WorkspaceStamp("x")));
        Assert.Equal("old", Read(Path.Combine(_paths.Workspace, "pixi.toml")));
    }
}

using System.Text.RegularExpressions;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>
/// The reader of printed music (homr, AGPL-3.0) is fetched on this computer only when it is asked for in Settings:
/// never by setup, and with what it is, its licence and its source shown before the button.
/// </summary>
public sealed class SheetReaderTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-reader").FullName;
    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private string Bundle()
    {
        var b = Path.Combine(_dir, "bundle");
        Directory.CreateDirectory(Path.Combine(b, "ml", "adapters"));
        File.WriteAllText(Path.Combine(b, "pixi.toml"), "[workspace]\nname = \"scribe\"\n");
        File.WriteAllText(Path.Combine(b, "pixi.lock"), "version: 6\n");
        File.WriteAllText(Path.Combine(b, "ml", "adapters", "run_adapter.py"), "# adapters\n");
        return b;
    }

    /// <summary>A launcher whose <c>pixi install -e homr</c> makes the environment's folder, as pixi does.</summary>
    private static FakeLauncher Pixi(BandroomPaths paths, Func<ProcessSpec, int>? exit = null) => new()
    {
        ExitImmediately = spec =>
        {
            int code = exit?.Invoke(spec) ?? 0;
            if (code == 0 && spec.Arguments[0] == "install" && spec.Arguments[^1] == SheetReader.Environment)
                Directory.CreateDirectory(paths.ReaderEnvironment);
            return code;
        },
    };

    private async Task<(Bootstrapper Boot, FakeLauncher Launcher, BandroomPaths Paths)> SetUpAsync(Func<ProcessSpec, int>? exit = null)
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var launcher = Pixi(paths, exit);
        var boot = new Bootstrapper(paths, Bundle(), Path.Combine("app", "pixi", "pixi.exe"), launcher, new EngineLog(null));
        await new Bootstrapper(paths, Bundle(), "pixi", new FakeLauncher { ExitImmediately = _ => 0 }, new EngineLog(null))
            .RunAsync(false, null, CancellationToken.None);
        return (boot, launcher, paths);
    }

    [Fact]
    public async Task Setup_never_installs_the_reader()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var launcher = new FakeLauncher { ExitImmediately = _ => 0 };
        var boot = new Bootstrapper(paths, Bundle(), "pixi", launcher, new EngineLog(null));
        Assert.DoesNotContain(SheetReader.Environment, EnvironmentPlan.Environments(cuda: false).Concat(EnvironmentPlan.Environments(cuda: true)));
        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.True(boot.IsComplete(cuda: false));
        Assert.DoesNotContain(launcher.Started, s => s.Spec.Arguments.Contains(SheetReader.Environment));
        Assert.False(boot.ReaderInstalled);
    }

    [Fact]
    public async Task Asked_for_it_installs_the_environment_and_then_the_weights_with_the_engines_own_runner()
    {
        var (boot, launcher, paths) = await SetUpAsync();
        await boot.InstallReaderAsync(CancellationToken.None);

        Assert.Equal(2, launcher.Started.Count);
        var install = launcher.Started[0].Spec;
        Assert.Equal(["install", "--manifest-path", paths.Manifest, "--frozen", "-e", "homr"], install.Arguments);
        Assert.Equal(paths.PixiCache, install.Environment["PIXI_CACHE_DIR"]);

        var weights = launcher.Started[1].Spec;
        Assert.Equal(["run", "--manifest-path", paths.Manifest, "--frozen", "-e", "default",
            "python", Path.Combine(paths.Adapters, "run_adapter.py"), "--setup", "homr"], weights.Arguments);
        // As the engine runs it: the weights go to the models folder it reads, and the runner uses pixi, found on the PATH.
        Assert.Equal(paths.Models, weights.Environment["SCRIBE_MODELS"]);
        Assert.Equal("pixi", weights.Environment["SCRIBE_ADAPTER_RUNNER"]);
        Assert.StartsWith(Path.Combine("app", "pixi") + Path.PathSeparator, weights.Environment["PATH"]);

        Assert.True(boot.ReaderInstalled);
        Assert.Empty(boot.Pending(cuda: false));
    }

    [Fact]
    public async Task The_environment_is_where_the_engine_looks_for_it()
    {
        var (boot, _, paths) = await SetUpAsync();
        // adapters.py, environment_installed, with the pixi runner: .pixi/envs/<name> beside pixi.toml, two folders up
        // from the adapters folder the engine is given.
        string engine = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "engine", "src", "scribe_engine", "adapters.py"));
        Assert.Contains("adapters_dir.parents[1] / \".pixi\" / \"envs\" / name", engine);
        Assert.Equal(Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(paths.Adapters))!, ".pixi", "envs", "homr"), paths.ReaderEnvironment);
        Assert.Equal(Path.GetDirectoryName(paths.Manifest), Path.GetDirectoryName(Path.GetDirectoryName(paths.Adapters)));
        Assert.False(boot.ReaderInstalled);
    }

    [Fact]
    public void The_runner_and_the_workspace_have_what_the_install_asks_for()
    {
        string toml = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "pixi.toml"));
        Assert.Matches(@"(?m)^homr = \{", toml);
        string runner = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "ml", "adapters", "run_adapter.py"));
        Assert.Contains("argv == [\"--setup\", \"homr\"]", runner);
        // The line a failed fetch ends on: the runner's prefix and its name for the case.
        Assert.Contains("REFUSAL = \"scribe-refusal: \"", runner);
        Assert.Contains("{REFUSAL}weights_missing", runner);
        Assert.Equal("scribe-refusal: weights_missing", SheetReader.WeightsNotFetched);
        // The weights are pinned in the runner alone: Bandroom names no archive, size or checksum of its own.
        var pinned = Regex.Matches(runner, @"""((?:segnet|encoder|decoder)[\w-]+\.zip)""").Select(m => m.Groups[1].Value).ToList();
        Assert.Equal(3, pinned.Count);
        foreach (var file in Directory.EnumerateFiles(Path.Combine(TestPaths.RepoRoot, "apps", "bandroom"), "*.*", SearchOption.AllDirectories)
                     .Where(f => (f.EndsWith(".cs", StringComparison.Ordinal) || f.EndsWith(".swift", StringComparison.Ordinal))
                                 && !f.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar)
                                 && !f.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar)
                                 && !f.Contains(Path.DirectorySeparatorChar + "build" + Path.DirectorySeparatorChar)
                                 && !f.Contains(Path.DirectorySeparatorChar + ".build" + Path.DirectorySeparatorChar)))
        {
            string text = File.ReadAllText(file);
            Assert.DoesNotContain(pinned, text.Contains);
        }
    }

    [Theory]
    [InlineData("install", null, SheetReaderFailure.Environment)]
    [InlineData("run", "scribe-refusal: weights_missing", SheetReaderFailure.Network)]
    [InlineData("run", "segnet.zip: SHA-256 abc, expected def; not kept", SheetReaderFailure.Weights)]
    public async Task A_step_that_fails_says_which_and_leaves_the_reader_uninstalled(string step, string? output, SheetReaderFailure expected)
    {
        var (boot, launcher, _) = await SetUpAsync(spec => spec.Arguments[0] == step ? 4 : 0);
        if (output is not null) launcher.Output = ["urlopen error: no route to the host", output];
        var e = await Assert.ThrowsAsync<SheetReaderException>(() => boot.InstallReaderAsync(CancellationToken.None));
        Assert.Equal(expected, e.Failure);
        Assert.Equal(4, e.ExitCode);
        Assert.False(boot.ReaderInstalled);
        Assert.Empty(boot.Pending(cuda: false)); // not something setup now has to finish

        // Trying again runs both steps again; each picks up what it already has.
        launcher.ExitImmediately = Pixi(new BandroomPaths(Path.Combine(_dir, "data"))).ExitImmediately;
        launcher.Output = [];
        await boot.InstallReaderAsync(CancellationToken.None);
        Assert.True(boot.ReaderInstalled);
    }

    [Fact]
    public async Task Without_an_installed_engine_nothing_is_run()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var launcher = new FakeLauncher { ExitImmediately = _ => 0 };
        var boot = new Bootstrapper(paths, Bundle(), "pixi", launcher, new EngineLog(null));
        var e = await Assert.ThrowsAsync<SheetReaderException>(() => boot.InstallReaderAsync(CancellationToken.None));
        Assert.Equal(SheetReaderFailure.NotSetUp, e.Failure);
        Assert.Empty(launcher.Started);
    }

    [Fact]
    public async Task Cancelling_kills_the_install_and_leaves_it_uninstalled()
    {
        var (boot, _, paths) = await SetUpAsync();
        var launcher = new FakeLauncher();
        boot = new Bootstrapper(paths, Bundle(), "pixi", launcher, new EngineLog(null));
        using var cts = new CancellationTokenSource();
        var run = boot.InstallReaderAsync(cts.Token);
        for (int i = 0; i < 100 && launcher.Started.Count == 0; i++) await Task.Delay(5);
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.True(launcher.Last.Killed);
        Assert.False(boot.ReaderInstalled);
    }

    [Fact]
    public async Task An_installed_reader_is_kept_up_with_a_new_lockfile_and_one_never_asked_for_is_not_installed_by_it()
    {
        var (boot, launcher, paths) = await SetUpAsync();
        string bundle = Path.Combine(_dir, "bundle");
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), "version: 6\n# changed\n");
        Assert.DoesNotContain("homr", boot.Pending(cuda: false));
        await boot.RunAsync(false, null, CancellationToken.None);

        await boot.InstallReaderAsync(CancellationToken.None);
        Assert.Empty(boot.Pending(cuda: false));
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), "version: 6\n# changed again\n");
        Assert.Equal("homr", boot.Pending(cuda: false)[^1]);
        launcher.Started.Clear();
        var progress = new List<BootstrapProgress>();
        await boot.RunAsync(false, new Sync(progress), CancellationToken.None);
        Assert.Equal(["install", "--manifest-path", paths.Manifest, "--frozen", "-e", "homr"], launcher.Started[^1].Spec.Arguments);
        Assert.Contains(progress, p => p.Environment == "homr" && p.ItemKey == "Setup_Item_SheetReader");
        Assert.True(boot.ReaderInstalled);
        Assert.Empty(boot.Pending(cuda: false));
        Assert.Equal("Noteleser (homr)", Strings.Nb["Setup_Item_SheetReader"]);
    }

    private sealed class Sync(List<BootstrapProgress> list) : IProgress<BootstrapProgress>
    {
        public void Report(BootstrapProgress value) => list.Add(value);
    }

    // ----- the card in Settings -----

    private sealed class Host : ISheetReaderHost
    {
        public bool CanInstall { get; set; } = true;
        public bool Installed { get; set; }
        public long FreeBytes { get; set; } = 212_000_000_000;
        public int Installs { get; private set; }
        public Func<Task> Install { get; set; } = () => Task.CompletedTask;
        public async Task InstallAsync()
        {
            Installs++;
            await Install();
        }
    }

    [Fact]
    public void Before_anything_is_fetched_the_card_says_what_it_is_its_licence_and_where_it_comes_from()
    {
        var en = new SheetReaderViewModel(Strings.En, new Host());
        Assert.Equal("Sheet music from pictures", en.Header);
        Assert.Contains("homr", en.Body);
        Assert.Contains("not part of Brasscribe", en.Body);
        Assert.Contains("AGPL-3.0", en.Body);
        Assert.Contains("PyPI", en.Source);
        Assert.Contains("homr's releases on GitHub", en.Source);
        Assert.Contains("about 0.6 GB", en.Source);
        Assert.Contains("this PC downloads it", en.Source);
        Assert.Contains("separate program", en.Source);
        Assert.Equal("Read about homr and its licence", en.ReadMore);
        Assert.Equal("Install the reader", en.Button);
        Assert.Equal(SheetReaderState.NotInstalled, en.State);
        Assert.True(en.ShowsButton && en.CanInstall);
        Assert.Equal("", en.Status);
        Assert.Equal("https://github.com/liebharc/homr", SheetReader.Page.AbsoluteUri);

        var nb = new SheetReaderViewModel(Strings.Nb, new Host());
        Assert.Equal("Noter fra bilder", nb.Header);
        Assert.Contains("noteleser, homr, som ikke er en del av Brasscribe", nb.Body);
        Assert.Contains("lisensen AGPL-3.0", nb.Body);
        Assert.Contains("omtrent 0,6 GB", nb.Source);
        Assert.Contains("eget program", nb.Source);
        Assert.Equal("Installer noteleseren", nb.Button);
    }

    /// <summary>
    /// The copy deck (design/shared/server-app.md §10, settings.reader.*) and the two apps say the same: the deck's
    /// rows are this app's strings, and the Mac's (its bokmål is in make-strings.py, keyed by the English).
    /// </summary>
    [Fact]
    public void The_copy_deck_and_both_apps_have_the_same_words()
    {
        var deck = File.ReadLines(Path.Combine(TestPaths.RepoRoot, "design", "shared", "server-app.md"))
            .Where(l => l.StartsWith("| settings.reader", StringComparison.Ordinal))
            .Select(l => l.Trim('|').Split(" | ").Select(c => c.Trim()).ToArray())
            .ToDictionary(c => c[0], c => (En: c[1], Nb: c[2]));
        string mac = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "apps", "bandroom", "macos", "scripts", "make-strings.py"));
        var keys = Strings.En.All.Keys.Where(k => k.StartsWith("Settings_Reader", StringComparison.Ordinal)).ToList();
        Assert.Equal(11, keys.Count);
        Assert.Equal(keys.Count + 1, deck.Count); // the source line is there once per platform
        foreach (var key in keys)
        {
            string name = key.ToLowerInvariant().Replace('_', '.');
            var win = deck[deck.ContainsKey(name) ? name : name + ".win"];
            static string Placeholders(string s) => s.Replace("{n}", "{0}").Replace("{m}", "{1}");
            Assert.Equal(Strings.En[key], Placeholders(win.En));
            Assert.Equal(Strings.Nb[key], Placeholders(win.Nb));

            var forMac = deck[deck.ContainsKey(name) ? name : name + ".mac"];
            static string Swift(string s) => s.Replace("{n}", "%@").Replace("{m}", "%@");
            Assert.Contains($"\"{Swift(forMac.En)}\":", mac);
            Assert.Contains($"\"{Swift(forMac.Nb)}\"", mac);
        }
    }

    [Fact]
    public void The_catalogues_sample_states_show_the_card_without_installing_anything()
    {
        var host = new Host();
        var vm = new SheetReaderViewModel(Strings.En, host);
        Assert.Null(SheetReaderViewModel.SampleState("running"));
        Assert.Null(SheetReaderViewModel.SampleState(null));

        vm.ShowSample(SheetReaderViewModel.SampleState("reader-installing")!.Value);
        Assert.True(vm.IsInstalling && vm.IsSample);
        Assert.False(vm.ShowsProgress); // a bar that moves would never give a picture that keeps still
        Assert.Equal("Installing the reader… This takes a few minutes.", vm.Status);
        vm.Refresh();
        Assert.Equal(SheetReaderState.Installing, vm.State);

        vm.ShowSample(SheetReaderViewModel.SampleState("reader-failed")!.Value);
        Assert.Equal("The reader's files couldn't be downloaded. Check the internet connection, then try again.", vm.Status);
        Assert.Equal("Try again", vm.Button);
        vm.Refresh();
        Assert.Equal(SheetReaderState.Failed, vm.State);

        host.Installed = true; // as the app's sample host says once that state is asked for
        vm.ShowSample(SheetReaderViewModel.SampleState("reader-installed")!.Value);
        vm.Refresh();
        Assert.Equal(SheetReaderState.Installed, vm.State);
        Assert.False(vm.ShowsButton);
        Assert.Equal(0, host.Installs);

        // The catalogue asks for exactly the states the app knows.
        string views = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "apps", "windows", "tools", "ScreenCheck", "BandroomCatalogue.cs"));
        foreach (var state in (string[])["reader-installing", "reader-installed", "reader-failed"])
        {
            Assert.Contains($"settings:{state}", views);
            Assert.NotNull(SheetReaderViewModel.SampleState(state));
        }
    }

    [Fact]
    public async Task Installing_shows_progress_then_installed_and_says_so()
    {
        var gate = new TaskCompletionSource();
        var host = new Host();
        host.Install = async () => { await gate.Task; host.Installed = true; };
        var said = new RecordingAnnouncer();
        var vm = new SheetReaderViewModel(Strings.En, host, said);
        var changed = new List<string?>();
        vm.PropertyChanged += (_, e) => changed.Add(e.PropertyName);

        var run = vm.InstallAsync();
        Assert.Equal(SheetReaderState.Installing, vm.State);
        Assert.True(vm.IsInstalling && vm.ShowsProgress);
        Assert.False(vm.ShowsButton);
        Assert.Equal("Installing the reader… This takes a few minutes.", vm.Status);
        Assert.Contains(nameof(SheetReaderViewModel.Status), changed);
        await vm.InstallAsync(); // a second press while it runs starts nothing
        Assert.Equal(1, host.Installs);

        gate.SetResult();
        await run;
        Assert.Equal(SheetReaderState.Installed, vm.State);
        Assert.False(vm.ShowsButton || vm.IsInstalling);
        Assert.Equal("The reader is installed. Phones can send pictures of sheet music now.", vm.Status);
        Assert.Equal([vm.Status], said.Said);
    }

    [Theory]
    [InlineData(SheetReaderFailure.Network, "The reader's files couldn't be downloaded. Check the internet connection, then try again.")]
    [InlineData(SheetReaderFailure.Environment, "The reader wasn't installed. Try again; the log has the details.")]
    [InlineData(SheetReaderFailure.Weights, "The reader wasn't installed. Try again; the log has the details.")]
    public async Task A_failure_is_said_on_the_card_with_try_again(SheetReaderFailure failure, string words)
    {
        var host = new Host { Install = () => throw new SheetReaderException(failure, 4) };
        var said = new RecordingAnnouncer();
        var vm = new SheetReaderViewModel(Strings.En, host, said);
        await vm.InstallAsync();
        Assert.Equal(SheetReaderState.Failed, vm.State);
        Assert.Equal(words, vm.Status);
        Assert.Equal("Try again", vm.Button);
        Assert.True(vm.ShowsButton && vm.CanInstall);
        Assert.Equal([words], said.Said);

        host.Install = () => { host.Installed = true; return Task.CompletedTask; };
        await vm.InstallAsync();
        Assert.Equal(SheetReaderState.Installed, vm.State);
        Assert.Equal(2, host.Installs);
    }

    [Fact]
    public async Task Anything_else_that_goes_wrong_is_a_failure_too_and_never_leaves_the_card_installing()
    {
        var vm = new SheetReaderViewModel(Strings.En, new Host { Install = () => throw new InvalidOperationException("pixi.exe is gone") });
        await vm.InstallAsync();
        Assert.Equal(SheetReaderState.Failed, vm.State);
        Assert.Equal("Try again", vm.Button);
    }

    [Fact]
    public async Task Too_little_space_is_said_before_anything_is_fetched()
    {
        var host = new Host { FreeBytes = 1_200_000_000 };
        var vm = new SheetReaderViewModel(Strings.Nb, host);
        await vm.InstallAsync();
        Assert.Equal(SheetReaderState.Failed, vm.State);
        Assert.Equal("Ikke nok plass: noteleseren trenger omtrent 2,0 GB, og 1,2 GB er ledig.", vm.Status);
        Assert.Equal(0, host.Installs);
        Assert.True(SheetReader.NeededFreeBytes > SheetReader.DownloadBytes);
    }

    [Fact]
    public async Task While_brasscribe_is_being_set_up_the_button_waits()
    {
        var host = new Host { CanInstall = false };
        var vm = new SheetReaderViewModel(Strings.En, host);
        Assert.True(vm.ShowsButton);
        Assert.False(vm.CanInstall);
        Assert.Equal("Brasscribe is still being set up. The reader can be installed once that is done.", vm.Status);
        await vm.InstallAsync();
        Assert.Equal(0, host.Installs);

        var changed = new List<string?>();
        vm.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        host.CanInstall = true;
        vm.Refresh();
        Assert.True(vm.CanInstall);
        Assert.Equal("", vm.Status);
        Assert.Contains(nameof(SheetReaderViewModel.CanInstall), changed);
    }

    [Fact]
    public void A_reader_that_is_already_there_is_shown_as_installed_and_one_that_went_away_is_offered_again()
    {
        var host = new Host { Installed = true };
        var vm = new SheetReaderViewModel(Strings.En, host);
        Assert.Equal(SheetReaderState.Installed, vm.State);
        Assert.False(vm.ShowsButton);
        host.Installed = false;
        vm.Refresh();
        Assert.Equal(SheetReaderState.NotInstalled, vm.State);
        Assert.True(vm.ShowsButton);
    }

    [Fact]
    public async Task Quitting_in_the_middle_is_not_a_failure()
    {
        var vm = new SheetReaderViewModel(Strings.En, new Host { Install = () => throw new OperationCanceledException() });
        await vm.InstallAsync();
        Assert.Equal(SheetReaderState.NotInstalled, vm.State);
    }
}

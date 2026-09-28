using System.Security.Cryptography;
using System.Text;
using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class BootstrapTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-boot").FullName;
    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private string Bundle()
    {
        var b = Path.Combine(_dir, "bundle");
        Directory.CreateDirectory(Path.Combine(b, "engine", "src"));
        Directory.CreateDirectory(Path.Combine(b, "ml", "adapters"));
        File.WriteAllText(Path.Combine(b, "pixi.toml"), "[workspace]\nname = \"brasscribe\"\n");
        File.WriteAllText(Path.Combine(b, "pixi.lock"), "version: 6\n");
        File.WriteAllText(Path.Combine(b, "engine", "src", "api.py"), "# engine\n");
        File.WriteAllText(Path.Combine(b, "ml", "adapters", "run_adapter.py"), "# adapters\n");
        return b;
    }

    [Theory]
    [InlineData(31, 0, 15, 5222, 552.22)]
    [InlineData(32, 0, 15, 6094, 560.94)]
    [InlineData(27, 21, 14, 5241, 452.41)]
    public void Nvidia_driver_number_comes_from_the_windows_driver_version(int a, int b, int c, int d, double expected)
    {
        var gpu = new GpuAdapter("NVIDIA GeForce RTX 4070", GpuAdapter.Nvidia, new Version(a, b, c, d));
        Assert.Equal(expected, gpu.NvidiaDriver!.Value, 2);
    }

    [Fact]
    public void Cuda_needs_an_nvidia_card_with_driver_525_or_newer()
    {
        var rtx = new GpuAdapter("NVIDIA GeForce RTX 4070", GpuAdapter.Nvidia, new Version(31, 0, 15, 5222));
        var oldNvidia = new GpuAdapter("NVIDIA GeForce GTX 1060", GpuAdapter.Nvidia, new Version(27, 21, 14, 5241));
        var intel = new GpuAdapter("Intel(R) UHD Graphics", 0x8086, new Version(31, 0, 101, 4502));
        var amd = new GpuAdapter("AMD Radeon RX 7800", 0x1002, new Version(31, 0, 24027, 1012));
        Assert.True(EnvironmentPlan.UseCuda([intel, rtx]));
        Assert.False(EnvironmentPlan.UseCuda([oldNvidia]));
        Assert.False(EnvironmentPlan.UseCuda([intel, amd]));
        Assert.False(EnvironmentPlan.UseCuda([]));
    }

    [Fact]
    public void The_engine_env_is_always_default_and_only_torch_adapters_get_cuda_builds()
    {
        Assert.Equal(["default", "swift-f0", "basic-pitch", "beat-this-cuda", "separator-cuda", "muscriptor-cuda", "mega53-cuda", "panns-cuda"],
            EnvironmentPlan.Environments(cuda: true));
        Assert.Equal(["default", "swift-f0", "basic-pitch", "beat-this", "separator", "muscriptor", "mega53", "panns"],
            EnvironmentPlan.Environments(cuda: false));
    }

    [Fact]
    public void Every_planned_environment_exists_in_pixi_toml()
    {
        var toml = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "pixi.toml"));
        foreach (var env in EnvironmentPlan.Environments(true).Concat(EnvironmentPlan.Environments(false)).Distinct())
            Assert.Matches($@"(?m)^{System.Text.RegularExpressions.Regex.Escape(env)} = \{{", toml);
    }

    [Fact]
    public void Setup_items_use_the_plain_words_of_the_copy_deck()
    {
        Assert.Equal("Setup_Item_BandWriter", EnvironmentPlan.ItemKey("muscriptor-cuda"));
        Assert.Equal("Setup_Item_Separator", EnvironmentPlan.ItemKey("mega53"));
        Assert.Equal("Setup_Item_BeatFinder", EnvironmentPlan.ItemKey("beat-this-cuda"));
        Assert.Equal("Setup_Item_Listening", EnvironmentPlan.ItemKey("default"));
    }

    [Fact]
    public async Task Bootstrap_copies_the_workspace_installs_each_env_and_resumes_after_a_failure()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var launcher = new FakeLauncher();
        int calls = 0;
        // The fourth install (beat-this) fails once.
        launcher.ExitImmediately = spec => ++calls == 4 ? 1 : 0;
        var boot = new Bootstrapper(paths, Bundle(), @"C:\app\pixi\pixi.exe", launcher, new EngineLog(null));
        Assert.False(boot.IsComplete(cuda: false));
        Assert.False(boot.EngineReady);

        var progress = new List<BootstrapProgress>();
        var ex = await Assert.ThrowsAsync<BootstrapException>(() => boot.RunAsync(false, new SyncProgress(progress), CancellationToken.None));
        Assert.Equal("beat-this", ex.Environment);
        Assert.True(File.Exists(Path.Combine(paths.Workspace, "ml", "adapters", "run_adapter.py")));
        Assert.True(boot.EngineReady);
        Assert.Equal(["beat-this", "separator", "muscriptor", "mega53", "panns"], boot.Pending(false));

        var first = launcher.Started[0].Spec;
        Assert.Equal(["install", "--manifest-path", paths.Manifest, "--frozen", "-e", "default"], first.Arguments);
        Assert.Equal(paths.PixiCache, first.Environment["PIXI_CACHE_DIR"]);

        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.True(boot.IsComplete(cuda: false));
        Assert.Equal(4 + 5, launcher.Started.Count); // resumed: only the remaining five ran again
        Assert.Equal("beat-this", launcher.Started[4].Spec.Arguments[^1]);

        // Switching to CUDA installs only the torch adapters' CUDA builds.
        Assert.Equal(["beat-this-cuda", "separator-cuda", "muscriptor-cuda", "mega53-cuda", "panns-cuda"], boot.Pending(true));
    }

    [Fact]
    public async Task A_new_lockfile_reinstalls()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Bundle();
        var boot = new Bootstrapper(paths, bundle, "pixi", new FakeLauncher { ExitImmediately = _ => 0 }, new EngineLog(null));
        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.True(boot.IsComplete(false));
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), "version: 6\n# changed\n");
        Assert.Contains("workspace", boot.Pending(false));
        Assert.Contains("default", boot.Pending(false));
    }

    [Fact]
    public async Task A_new_app_version_with_other_sources_copies_the_workspace_again_but_keeps_the_environments()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Bundle();
        var boot = new Bootstrapper(paths, bundle, "pixi", new FakeLauncher { ExitImmediately = _ => 0 }, new EngineLog(null));
        await boot.RunAsync(false, null, CancellationToken.None);
        Directory.CreateDirectory(Path.Combine(bundle, "music"));
        File.WriteAllText(Path.Combine(bundle, "music", "pyproject.toml"), "[project]\nname = \"brasscribe-music\"\n");
        Assert.Equal(["workspace"], boot.Pending(false));
        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.True(File.Exists(Path.Combine(paths.Workspace, "music", "pyproject.toml")));
    }

    [Fact]
    public async Task Cancelling_kills_the_install()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var launcher = new FakeLauncher();
        var boot = new Bootstrapper(paths, Bundle(), "pixi", launcher, new EngineLog(null));
        using var cts = new CancellationTokenSource();
        var run = boot.RunAsync(false, null, cts.Token);
        for (int i = 0; i < 100 && launcher.Started.Count == 0; i++) await Task.Delay(5);
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.True(launcher.Last.Killed);
        Assert.Contains("default", boot.Pending(false));
    }

    /// <summary>
    /// An install from before stamps: env markers hold SHA256.HashData(File.ReadAllBytes(pixi.lock)) and the copy has
    /// no stamp. The streamed hash must match the markers (or an update reinstalls everything), the engine it has can
    /// start, and only the workspace is replaced.
    /// </summary>
    [Fact]
    public async Task An_install_from_before_stamps_keeps_its_environments_and_replaces_only_the_workspace()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Bundle();
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), string.Concat(Enumerable.Repeat("package: x\n", 200_000))); // 2.2 MB, several buffers
        string lockHash = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(bundle, "pixi.lock"))));
        foreach (var f in Directory.EnumerateFiles(bundle, "*", SearchOption.AllDirectories))
        {
            var dst = Path.Combine(paths.Workspace, Path.GetRelativePath(bundle, f));
            Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
            File.Copy(f, dst);
        }
        Directory.CreateDirectory(paths.SetupMarkers);
        File.WriteAllText(Path.Combine(paths.SetupMarkers, "workspace"), "path-and-size hash");
        foreach (var env in EnvironmentPlan.Environments(cuda: false))
            File.WriteAllText(Path.Combine(paths.SetupMarkers, "env-" + env), lockHash);

        var launcher = new FakeLauncher();
        var boot = new Bootstrapper(paths, bundle, "pixi", launcher, new EngineLog(null));
        Assert.Equal(lockHash, boot.LockHash);
        Assert.Equal(["workspace"], boot.Pending(false));
        Assert.True(boot.EngineReady);
        Assert.True(boot.IsUpdate);

        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.Empty(launcher.Started);
        Assert.True(await boot.IsCompleteAsync(cuda: false));
        Assert.Equal(boot.BundleStamp, WorkspaceStamp.Read(paths.Workspace));
        Assert.False(boot.IsComplete(cuda: true));
    }

    /// <summary>
    /// The app asks at start-up, again when setup is finished and on every setup progress report. Once
    /// the answer is yes, asking again reads nothing: here pixi.lock is locked and still the answer comes.
    /// </summary>
    [Fact]
    public async Task Once_complete_asking_again_does_not_read_the_lockfile()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Bundle();
        var boot = new Bootstrapper(paths, bundle, "pixi", new FakeLauncher { ExitImmediately = _ => 0 }, new EngineLog(null));
        Assert.False(await boot.IsCompleteAsync(cuda: false));
        await boot.RunAsync(false, null, CancellationToken.None);
        Assert.True(boot.IsComplete(cuda: false));
        Assert.True(boot.EngineReady);

        var lockFile = Path.Combine(bundle, "pixi.lock");
        using (new FileStream(lockFile, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            Assert.Throws<IOException>(() => File.ReadAllBytes(lockFile));
            Assert.True(boot.IsComplete(cuda: false));
            Assert.True(await boot.IsCompleteAsync(cuda: false));
            Assert.True(boot.EngineReady);
            // Pending is exact, but the lockfile's hash is kept while its size and time are unchanged.
            Assert.Empty(boot.Pending(cuda: false));
        }
    }

    private sealed class SyncProgress(List<BootstrapProgress> list) : IProgress<BootstrapProgress>
    {
        public void Report(BootstrapProgress value) => list.Add(value);
    }
}

internal static class TestPaths
{
    public static string RepoRoot
    {
        get
        {
            var d = new DirectoryInfo(AppContext.BaseDirectory);
            while (d is not null && !File.Exists(Path.Combine(d.FullName, "pixi.toml"))) d = d.Parent;
            return d?.FullName ?? throw new DirectoryNotFoundException("repository root");
        }
    }
}

using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>
/// An install and a stage never run on one environment at once: Bandroom holds the environment's lock file with no
/// sharing while it installs it (the engine's envlock.py holds the same file while a stage uses it), waits for a stage
/// that has it, and skips an environment a stage installed meanwhile.
/// </summary>
public sealed class EnvironmentLockTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-envlock").FullName;

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    [Fact]
    public async Task An_install_waits_for_a_stage_that_has_the_environment()
    {
        var path = Path.Combine(_dir, "locks", "separator.lock");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var stage = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);  // a stage using it
        var install = EnvironmentLock.HoldAsync(path, CancellationToken.None, TimeSpan.FromMilliseconds(20));
        await Task.Delay(300);
        Assert.False(install.IsCompleted);
        stage.Dispose();
        await using var held = await install.WaitAsync(TimeSpan.FromSeconds(10));
        // While Bandroom holds it, nobody else can have it.
        Assert.ThrowsAny<IOException>(() => new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite));
    }

    [Fact]
    public async Task Cancelling_ends_the_wait()
    {
        var path = Path.Combine(_dir, "locks", "beat-this.lock");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var stage = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(200));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => EnvironmentLock.HoldAsync(path, cts.Token, TimeSpan.FromMilliseconds(20)));
    }

    [Fact]
    public async Task An_environment_a_stage_installed_meanwhile_is_not_installed_again()
    {
        var paths = new BandroomPaths(Path.Combine(_dir, "data"));
        var bundle = Path.Combine(_dir, "bundle");
        Directory.CreateDirectory(Path.Combine(bundle, "ml", "adapters"));
        File.WriteAllText(Path.Combine(bundle, "pixi.toml"), "[workspace]\nname = \"scribe\"\n");
        File.WriteAllText(Path.Combine(bundle, "pixi.lock"), "version: 6\n");
        File.WriteAllText(Path.Combine(bundle, WorkspaceStamp.FileName), "{\"commit\": \"c3dc2ad\", \"version\": \"0.1.0\"}");
        var launcher = new FakeLauncher();
        var boot = new Bootstrapper(paths, bundle, "pixi", launcher, new EngineLog(null));
        // Every environment except the first adapter's installs at once; that one is "installed by a stage" while
        // Bandroom waits for its lock.
        var first = boot.Pending(false).First(p => p is not ("workspace" or "default"));
        launcher.ExitImmediately = _ => 0;
        var lockPath = Path.Combine(paths.EnvironmentLocks, first + ".lock");
        Directory.CreateDirectory(paths.EnvironmentLocks);
        var stage = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        var run = boot.RunAsync(false, null, CancellationToken.None);
        await Task.Delay(500);
        Assert.DoesNotContain(launcher.Started, s => s.Spec.Arguments[^1] == first);
        Directory.CreateDirectory(paths.SetupMarkers);
        File.WriteAllText(Path.Combine(paths.SetupMarkers, "env-" + first), WorkspaceStamp.FileHash(Path.Combine(bundle, "pixi.lock")));
        stage.Dispose();
        await run.WaitAsync(TimeSpan.FromSeconds(30));
        Assert.DoesNotContain(launcher.Started, s => s.Spec.Arguments[^1] == first);
        Assert.Contains(launcher.Started, s => s.Spec.Arguments[^1] == "default");
    }
}

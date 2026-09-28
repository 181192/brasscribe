using System.Globalization;
using System.Security.Cryptography;

namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>A display adapter as DXGI reports it: PCI vendor id and the user-mode driver version (a.b.c.d).</summary>
public sealed record GpuAdapter(string Description, uint VendorId, Version? DriverVersion)
{
    public const uint Nvidia = 0x10DE;

    /// <summary>
    /// NVIDIA's own driver number from the Windows driver version: 31.0.15.5222 is 552.22
    /// (the last digit of the third part and the whole fourth part).
    /// </summary>
    public double? NvidiaDriver =>
        VendorId == Nvidia && DriverVersion is { Build: >= 0, Revision: >= 0 } v
            ? ((v.Build % 10) * 10000 + v.Revision) / 100.0
            : null;
}

/// <summary>
/// Which pixi environments this computer gets (spec §5.3, Windows GPU): the CUDA builds of the torch
/// adapters with an NVIDIA card and a CUDA 12 driver (525 or newer), the CPU builds otherwise. AMD and
/// Intel GPUs use the CPU; the engine has no DirectML path. The engine environment is always "default".
/// </summary>
public static class EnvironmentPlan
{
    public const double MinCudaDriver = 525.0;
    public static readonly string[] TorchAdapters = ["beat-this", "separator", "muscriptor", "mega53", "panns"];
    public static readonly string[] PlainAdapters = ["swift-f0", "basic-pitch"];

    public static GpuAdapter? CudaAdapter(IEnumerable<GpuAdapter> adapters) =>
        adapters.FirstOrDefault(a => a.NvidiaDriver >= MinCudaDriver);

    public static bool UseCuda(IEnumerable<GpuAdapter> adapters) => CudaAdapter(adapters) is not null;

    /// <summary>The environments to install, in order: the engine first, so Bandroom can start as early as possible.</summary>
    public static IReadOnlyList<string> Environments(bool cuda) =>
        ["default", .. PlainAdapters, .. TorchAdapters.Select(a => cuda ? a + "-cuda" : a)];

    /// <summary>What the setup window calls each environment (copy deck setup.3.items).</summary>
    public static string ItemKey(string environment) => environment.Replace("-cuda", "", StringComparison.Ordinal) switch
    {
        "muscriptor" => "Setup_Item_BandWriter",
        "separator" or "mega53" => "Setup_Item_Separator",
        "beat-this" => "Setup_Item_BeatFinder",
        _ => "Setup_Item_Listening",
    };
}

public sealed record BootstrapProgress(int Step, int Steps, string Environment, string ItemKey)
{
    public double Fraction => Steps == 0 ? 1 : (double)Step / Steps;
}

/// <summary>
/// First run (spec §5.1 option A): copy the pixi workspace that ships with the app (pixi.toml, pixi.lock,
/// the engine and adapter sources) into the data folder, then <c>pixi install --frozen -e &lt;env&gt;</c>
/// for each environment. A marker per environment holds the lockfile's hash, so a run that was stopped
/// resumes where it was (pixi keeps what it already downloaded in its cache), and an update installs
/// only when the lockfile changed.
/// After an app update the copy's stamp differs from the app's: the copy is replaced all or nothing
/// (<see cref="WorkspaceSwap"/>), and kept only once the engine environment installs from it; a failure
/// puts the old copy back, and the engine it had still starts.
/// </summary>
public sealed class Bootstrapper
{
    private readonly BandroomPaths _paths;
    private readonly string _bundledWorkspace;
    private readonly string _pixiExe;
    private readonly IProcessLauncher _launcher;
    private readonly EngineLog _log;

    public Bootstrapper(BandroomPaths paths, string bundledWorkspace, string pixiExe, IProcessLauncher launcher, EngineLog log)
    {
        _paths = paths;
        _bundledWorkspace = bundledWorkspace;
        _pixiExe = pixiExe;
        _launcher = launcher;
        _log = log;
    }

    private readonly object _gate = new();
    private readonly Dictionary<string, (long Length, DateTime Written, string Hash)> _hashes = [];
    private (string Fingerprint, WorkspaceStamp Stamp)? _stamp;
    // Setup only ever adds markers, so once complete stays complete for the life of the process.
    private readonly bool[] _complete = new bool[2];

    /// <summary>SHA-256 of the app's pixi.lock, streamed; computed again only when the file's size or time changes.</summary>
    public string LockHash => CachedHash(Path.Combine(_bundledWorkspace, "pixi.lock"));

    /// <summary>SHA-256 of the installed copy's pixi.lock: the one its environments were installed from.</summary>
    public string InstalledLockHash => CachedHash(Path.Combine(_paths.Workspace, "pixi.lock"));

    private string CachedHash(string path)
    {
        var file = new FileInfo(path);
        if (!file.Exists) return "";
        lock (_gate)
            if (_hashes.TryGetValue(path, out var c) && c.Length == file.Length && c.Written == file.LastWriteTimeUtc) return c.Hash;
        string hash = WorkspaceStamp.FileHash(path);
        lock (_gate) _hashes[path] = (file.Length, file.LastWriteTimeUtc, hash);
        return hash;
    }

    /// <summary>
    /// The app workspace's stamp: its files' contents hashed, with the commit the build wrote. Hashed again only
    /// when a file's path, size or time changes.
    /// </summary>
    public WorkspaceStamp BundleStamp
    {
        get
        {
            if (!Directory.Exists(_bundledWorkspace)) return new WorkspaceStamp(null);
            string fingerprint = BundleHash;
            lock (_gate)
                if (_stamp is { } s && s.Fingerprint == fingerprint) return s.Stamp;
            var stamp = WorkspaceStamp.Compute(_bundledWorkspace);
            lock (_gate) _stamp = (fingerprint, stamp);
            return stamp;
        }
    }

    /// <summary>The copy in the data folder is this app's workspace.</summary>
    public bool WorkspaceCurrent =>
        File.Exists(_paths.Manifest) && WorkspaceStamp.Read(_paths.Workspace)?.Stamp is { } have && have == BundleStamp.Stamp;

    /// <summary>
    /// An engine is installed that can run: a copy of the workspace and the engine environment installed from its
    /// lockfile. True during an update until the swap, and again after a failed update is rolled back.
    /// </summary>
    public bool HasInstalledEngine => File.Exists(_paths.Manifest) && MarkerMatches("env-default", InstalledLockHash);

    /// <summary>What's pending replaces an engine that already ran (Updating), rather than making the first one.</summary>
    public bool IsUpdate => HasInstalledEngine;

    /// <summary>Undoes an update the app didn't finish (it quit, or the power went): the old copy is back.</summary>
    public void RecoverInterruptedUpdate()
    {
        try { WorkspaceSwap.Recover(_paths.Workspace); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _log.Write("bandroom: undoing an unfinished update: " + e.Message); }
    }

    /// <summary>The lockfile plus every bundled file's path and size: tells cheaply whether the stamp needs hashing again.</summary>
    public string BundleHash => BundleHashWith(LockHash);

    private string BundleHashWith(string lockHash)
    {
        if (!Directory.Exists(_bundledWorkspace)) return "";
        var sb = new System.Text.StringBuilder(lockHash);
        foreach (var f in Directory.EnumerateFiles(_bundledWorkspace, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal))
        {
            var info = new FileInfo(f);
            sb.Append('\n').Append(Path.GetRelativePath(_bundledWorkspace, f).Replace('\\', '/')).Append(' ').Append(info.Length)
              .Append(' ').Append(info.LastWriteTimeUtc.Ticks);
        }
        return Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(sb.ToString())));
    }

    private string Marker(string name) => Path.Combine(_paths.SetupMarkers, name);

    private bool MarkerMatches(string name, string hash) =>
        File.Exists(Marker(name)) && File.ReadAllText(Marker(name)).Trim() == hash;

    private void WriteMarker(string name, string hash)
    {
        Directory.CreateDirectory(_paths.SetupMarkers);
        File.WriteAllText(Marker(name), hash);
    }

    /// <summary>The steps still to do: "workspace" and then environment names.</summary>
    public IReadOnlyList<string> Pending(bool cuda)
    {
        string hash = LockHash;
        var steps = new List<string>();
        if (!WorkspaceCurrent) steps.Add("workspace");
        steps.AddRange(EnvironmentPlan.Environments(cuda).Where(e => !MarkerMatches("env-" + e, hash)));
        return steps;
    }

    /// <summary>
    /// Every step done. Hashes the lockfile and walks the bundled workspace until the answer is yes, and
    /// remembers the yes; <see cref="IsCompleteAsync"/> does the first look off the calling thread.
    /// </summary>
    public bool IsComplete(bool cuda)
    {
        int i = cuda ? 1 : 0;
        if (Volatile.Read(ref _complete[i])) return true;
        bool complete = Pending(cuda).Count == 0;
        if (complete) Volatile.Write(ref _complete[i], true);
        return complete;
    }

    public Task<bool> IsCompleteAsync(bool cuda, CancellationToken ct = default) => Task.Run(() => IsComplete(cuda), ct);

    /// <summary>The engine environment is installed, so the engine can start while adapters still download.</summary>
    public bool EngineReady => HasInstalledEngine;

    public ProcessSpec InstallSpec(string environment) => new(
        _pixiExe,
        ["install", "--manifest-path", _paths.Manifest, "--frozen", "-e", environment],
        _paths.Workspace,
        new Dictionary<string, string> { ["PIXI_CACHE_DIR"] = _paths.PixiCache, ["PYTHONUTF8"] = "1" });

    /// <summary>
    /// Runs the pending steps. A new copy of the workspace is kept once the engine environment is installed from
    /// it (at once when its lockfile's environment is already there); until then any failure, or cancelling,
    /// puts the old copy back. Adapter environments after that resume as before.
    /// </summary>
    public async Task RunAsync(bool cuda, IProgress<BootstrapProgress>? progress, CancellationToken ct)
    {
        string hash = LockHash;
        var pending = Pending(cuda);
        int step = 0;
        WorkspaceSwap? swap = null;
        try
        {
            foreach (var item in pending)
            {
                ct.ThrowIfCancellationRequested();
                progress?.Report(new BootstrapProgress(step, pending.Count, item, EnvironmentPlan.ItemKey(item)));
                if (item == "workspace")
                {
                    var stamp = BundleStamp;
                    _log.Write($"bandroom: workspace {WorkspaceStamp.Read(_paths.Workspace)?.Short ?? "(none)"} -> {stamp.Short}");
                    swap = WorkspaceSwap.Install(_bundledWorkspace, _paths.Workspace, stamp);
                    _log.Write("bandroom: workspace copied to " + _paths.Workspace);
                    if (!pending.Contains("default")) { swap.Commit(); swap = null; }
                }
                else
                {
                    var spec = InstallSpec(item);
                    _log.Write($"bandroom: setting up {item}: {spec.FileName} {string.Join(' ', spec.Arguments)}");
                    using var p = _launcher.Start(spec, _log.Write);
                    using var reg = ct.Register(p.Kill);
                    int code = await p.WaitForExitAsync().ConfigureAwait(false);
                    ct.ThrowIfCancellationRequested();
                    if (code != 0) throw new BootstrapException(item, code, _log.Tail(20));
                    WriteMarker("env-" + item, hash);
                    if (item == "default" && swap is not null) { swap.Commit(); swap = null; }
                }
                step++;
            }
        }
        catch
        {
            if (swap is not null)
            {
                _log.Write("bandroom: the update stopped; putting the previous workspace back");
                try { swap.Rollback(); }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _log.Write("bandroom: rollback: " + e.Message); }
            }
            throw;
        }
        progress?.Report(new BootstrapProgress(pending.Count, pending.Count, "", ""));
    }
}

public sealed class BootstrapException(string environment, int exitCode, IReadOnlyList<string> tail)
    : Exception(string.Create(CultureInfo.InvariantCulture, $"pixi install -e {environment} exited with {exitCode}"))
{
    public string Environment { get; } = environment;
    public int ExitCode { get; } = exitCode;
    public IReadOnlyList<string> Tail { get; } = tail;
}

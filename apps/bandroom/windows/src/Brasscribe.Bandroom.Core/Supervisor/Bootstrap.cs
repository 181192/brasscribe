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
        SheetReader.Environment => "Setup_Item_SheetReader",
        "muscriptor" => "Setup_Item_BandWriter",
        "separator" or "mega53" => "Setup_Item_Separator",
        "beat-this" => "Setup_Item_BeatFinder",
        _ => "Setup_Item_Listening",
    };
}

/// <summary>
/// The reader of printed music (homr, AGPL-3.0): what turns a picture or a PDF of sheet music into notes for the
/// engine's <c>sheet</c> and <c>sheet-tab</c> profiles. It is no part of setup and no part of the app: this computer
/// fetches it, from where its makers publish it, only when the person asks for it in Settings. The engine offers
/// the two profiles where its environment is (<c>environment_installed</c> in the engine's adapters.py), looked for
/// again at every request, so nothing restarts when it arrives.
/// </summary>
public static class SheetReader
{
    /// <summary>Its pixi environment, and the folder of its weights under the models folder.</summary>
    public const string Environment = "homr";
    public const string Licence = "AGPL-3.0";
    /// <summary>Its makers' page: what it is, its source and its licence.</summary>
    public static readonly Uri Page = new("https://github.com/liebharc/homr");
    /// <summary>What is fetched, about: the environment from PyPI and conda-forge, and the weights from homr's release.</summary>
    public const long DownloadBytes = 475_000_000 + 139_000_000;
    /// <summary>The free space an install asks for: the download, pixi's cache of it, and room to spare.</summary>
    public const long NeededFreeBytes = 2_000_000_000;
    /// <summary>The line the adapter runner ends on when the weights could not be fetched (run_adapter.py, REFUSAL).</summary>
    public const string WeightsNotFetched = "scribe-refusal: weights_missing";
    /// <summary>The line it ends on when the disk filled up while the weights were written.</summary>
    public const string DiskFull = "scribe-refusal: no_space";

    /// <summary>
    /// What an installer (pixi, uv) says when it cannot reach where the packages are: the words of the HTTP and
    /// socket layers under it, which stay the same from one version to the next where its own wording does not.
    /// </summary>
    private static readonly string[] NoConnection =
    [
        "error sending request", "dns error", "failed to lookup address", "tcp connect error", "Connection refused",
        "Network is unreachable", "No route to host", "operation timed out", "No such host is known",
    ];

    /// <summary>What it, or the system under it, says when the disk is full.</summary>
    private static readonly string[] NoSpace = ["No space left on device", "not enough space on the disk", "os error 28", "os error 112"];

    /// <summary>
    /// What a line of a failed step's output says about why it failed, if it says: the runner's own names for the
    /// two cases, else the installer's words for no connection or a full disk.
    /// </summary>
    public static SheetReaderFailure? Reason(string line)
    {
        string said = line.Trim();
        if (said == DiskFull) return SheetReaderFailure.DiskFull;
        if (said == WeightsNotFetched) return SheetReaderFailure.Network;
        if (NoSpace.Any(w => said.Contains(w, StringComparison.OrdinalIgnoreCase))) return SheetReaderFailure.DiskFull;
        if (NoConnection.Any(w => said.Contains(w, StringComparison.OrdinalIgnoreCase))) return SheetReaderFailure.Network;
        return null;
    }
}

/// <summary>Why the reader was not installed.</summary>
public enum SheetReaderFailure
{
    /// <summary>There is no engine workspace to install it into yet.</summary>
    NotSetUp,
    /// <summary>pixi could not install its environment.</summary>
    Environment,
    /// <summary>The environment or the weights could not be fetched: no network, or one that stalled.</summary>
    Network,
    /// <summary>The disk filled up during the install.</summary>
    DiskFull,
    /// <summary>The weights step stopped on something else (a checksum that does not match, the disk).</summary>
    Weights,
}

public sealed class SheetReaderException(SheetReaderFailure failure, int exitCode = 0)
    : Exception(string.Create(CultureInfo.InvariantCulture, $"the reader of printed music was not installed: {failure} (exit code {exitCode})"))
{
    public SheetReaderFailure Failure { get; } = failure;
    public int ExitCode { get; } = exitCode;
}

/// <summary>
/// One step of setup. <c>EngineCurrent</c>: the app's own workspace is in place and its engine environment installed,
/// so the engine can start while the adapters still install. Worked out as setup goes, so the progress handler (on the
/// UI thread) never hashes.
/// </summary>
public sealed record BootstrapProgress(int Step, int Steps, string Environment, string ItemKey, bool EngineCurrent = false)
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

    /// <summary>
    /// What's pending replaces an engine that already ran with another build of the workspace (Updating), rather
    /// than making the first one or resuming its adapters.
    /// </summary>
    public bool IsUpdate => HasInstalledEngine && !WorkspaceCurrent;

    /// <summary>Undoes an update the app didn't finish (it quit, or the power went): the old copy is back.</summary>
    public void RecoverInterruptedUpdate()
    {
        try { WorkspaceSwap.Recover(_paths.Workspace, _log.Write); }
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
        // The reader only where it was asked for, and then kept up with the lockfile like the others.
        if (File.Exists(Marker(ReaderMarker)) && !MarkerMatches(ReaderMarker, hash)) steps.Add(SheetReader.Environment);
        return steps;
    }

    private const string ReaderMarker = "env-" + SheetReader.Environment;

    /// <summary>
    /// The reader of printed music is on this computer: its environment is where the engine looks for it, and an
    /// install here ran to its end (the environment, then the weights).
    /// </summary>
    public bool ReaderInstalled => File.Exists(Marker(ReaderMarker)) && Directory.Exists(_paths.ReaderEnvironment);

    /// <summary>
    /// The reader's weights, fetched and checked by the adapter runner itself (<c>run_adapter.py --setup homr</c>, with
    /// the engine's Python): the archives, their sizes and their SHA-256s are pinned there and nowhere else. The
    /// runner gets what the engine gives it: the models folder, pixi as its runner, and pixi on the PATH.
    /// </summary>
    public ProcessSpec ReaderWeightsSpec(string? path = null)
    {
        path ??= Environment.GetEnvironmentVariable("PATH") ?? "";
        return new ProcessSpec(
            _pixiExe,
            ["run", "--manifest-path", _paths.Manifest, "--frozen", "-e", "default",
             "python", Path.Combine(_paths.Adapters, "run_adapter.py"), "--setup", SheetReader.Environment],
            _paths.Workspace,
            new Dictionary<string, string>
            {
                ["SCRIBE_MODELS"] = _paths.Models,
                ["SCRIBE_ADAPTER_RUNNER"] = "pixi",
                ["PIXI_CACHE_DIR"] = _paths.PixiCache,
                ["PYTHONUTF8"] = "1",
                ["PATH"] = Path.GetDirectoryName(_pixiExe) is { Length: > 0 } dir ? dir + Path.PathSeparator + path : path,
            });
    }

    /// <summary>
    /// Installs the reader, when the person asked for it: <c>pixi install --frozen -e homr</c> in the installed
    /// workspace, then its weights. Both steps pick up where a stopped run left off (pixi keeps what it downloaded,
    /// the runner the archives it has whole), so trying again is cheap. Throws <see cref="SheetReaderException"/>.
    /// </summary>
    public async Task InstallReaderAsync(CancellationToken ct)
    {
        if (!HasInstalledEngine) throw new SheetReaderException(SheetReaderFailure.NotSetUp);
        string hash = InstalledLockHash;
        var install = InstallSpec(SheetReader.Environment);
        _log.Write($"bandroom: installing the reader of printed music: {install.FileName} {string.Join(' ', install.Arguments)}");
        // Why a step failed is the last thing its output says about it: a full disk, no connection, or neither.
        SheetReaderFailure? why = null;
        void Listen(string line) => why = SheetReader.Reason(line) ?? why;
        int code = await RunAsync(install, Listen, ct).ConfigureAwait(false);
        if (code != 0) throw new SheetReaderException(why ?? SheetReaderFailure.Environment, code);
        var weights = ReaderWeightsSpec();
        _log.Write($"bandroom: fetching the reader's weights: {weights.FileName} {string.Join(' ', weights.Arguments)}");
        why = null;
        code = await RunAsync(weights, Listen, ct).ConfigureAwait(false);
        if (code != 0) throw new SheetReaderException(why ?? SheetReaderFailure.Weights, code);
        WriteMarker(ReaderMarker, hash);
        _log.Write("bandroom: the reader of printed music is installed");
    }

    private async Task<int> RunAsync(ProcessSpec spec, Action<string> line, CancellationToken ct)
    {
        using var p = _launcher.Start(spec, l => { _log.Write(l); line(l); });
        using var reg = ct.Register(p.Kill);
        int code = await p.WaitForExitAsync().ConfigureAwait(false);
        ct.ThrowIfCancellationRequested();
        return code;
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

    /// <summary>
    /// Whether the engine may be started once an update stopped with the previous workspace put back
    /// (<paramref name="failed"/>). That engine is ready by its marker, but it is started only when its environment
    /// holds the command this app runs. Otherwise nothing is started: a start could only fail, and its error would
    /// hide the update's own problem, whose fix runs the update again.
    /// </summary>
    public bool StartsAfterUpdate(bool failed) => EngineReady && (!failed || File.Exists(_paths.EngineCommand));

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
                bool engineCurrent = !pending.Skip(step).Any(p => p is "workspace" or "default");
                progress?.Report(new BootstrapProgress(step, pending.Count, item, EnvironmentPlan.ItemKey(item), engineCurrent));
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
                    PixiRefusal? refusal = null;
                    using var p = _launcher.Start(spec, line =>
                    {
                        _log.Write(line);
                        refusal ??= PixiRefusal.Parse(line);
                    });
                    using var reg = ct.Register(p.Kill);
                    int code = await p.WaitForExitAsync().ConfigureAwait(false);
                    ct.ThrowIfCancellationRequested();
                    if (code != 0) throw new BootstrapException(item, code, _log.Tail(20)) { Refusal = refusal };
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
        progress?.Report(new BootstrapProgress(pending.Count, pending.Count, "", "", EngineCurrent: true));
    }
}

public sealed class BootstrapException(string environment, int exitCode, IReadOnlyList<string> tail)
    : Exception(string.Create(CultureInfo.InvariantCulture, $"pixi install -e {environment} exited with {exitCode}"))
{
    public string Environment { get; } = environment;
    public int ExitCode { get; } = exitCode;
    public IReadOnlyList<string> Tail { get; } = tail;
    /// <summary>Set when pixi refused the workspace (too old for it): installing again can't help.</summary>
    public PixiRefusal? Refusal { get; init; }
}

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

    public string LockHash => Hash(Path.Combine(_bundledWorkspace, "pixi.lock"));

    /// <summary>The lockfile plus every bundled file's path and size: a new app version with other sources copies again.</summary>
    public string BundleHash
    {
        get
        {
            if (!Directory.Exists(_bundledWorkspace)) return "";
            var sb = new System.Text.StringBuilder(LockHash);
            foreach (var f in Directory.EnumerateFiles(_bundledWorkspace, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal))
                sb.Append('\n').Append(Path.GetRelativePath(_bundledWorkspace, f).Replace('\\', '/')).Append(' ').Append(new FileInfo(f).Length);
            return Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(sb.ToString())));
        }
    }

    private static string Hash(string file) =>
        File.Exists(file) ? Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(file))) : "";

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
        if (!MarkerMatches("workspace", BundleHash)) steps.Add("workspace");
        steps.AddRange(EnvironmentPlan.Environments(cuda).Where(e => !MarkerMatches("env-" + e, hash)));
        return steps;
    }

    public bool IsComplete(bool cuda) => Pending(cuda).Count == 0;

    /// <summary>The engine environment is installed, so the engine can start while adapters still download.</summary>
    public bool EngineReady => MarkerMatches("env-default", LockHash) && MarkerMatches("workspace", BundleHash);

    public ProcessSpec InstallSpec(string environment) => new(
        _pixiExe,
        ["install", "--manifest-path", _paths.Manifest, "--frozen", "-e", environment],
        _paths.Workspace,
        new Dictionary<string, string> { ["PIXI_CACHE_DIR"] = _paths.PixiCache, ["PYTHONUTF8"] = "1" });

    public async Task RunAsync(bool cuda, IProgress<BootstrapProgress>? progress, CancellationToken ct)
    {
        string hash = LockHash;
        var pending = Pending(cuda);
        int step = 0;
        foreach (var item in pending)
        {
            ct.ThrowIfCancellationRequested();
            progress?.Report(new BootstrapProgress(step, pending.Count, item, EnvironmentPlan.ItemKey(item)));
            if (item == "workspace")
            {
                CopyWorkspace();
                WriteMarker("workspace", BundleHash);
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
            }
            step++;
        }
        progress?.Report(new BootstrapProgress(pending.Count, pending.Count, "", ""));
    }

    /// <summary>Copies the bundled workspace; files already there with the same size and time are kept.</summary>
    private void CopyWorkspace()
    {
        if (!Directory.Exists(_bundledWorkspace))
            throw new DirectoryNotFoundException("the app's workspace is missing: " + _bundledWorkspace);
        foreach (var src in Directory.EnumerateFiles(_bundledWorkspace, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(_bundledWorkspace, src);
            var dst = Path.Combine(_paths.Workspace, rel);
            var s = new FileInfo(src);
            var d = new FileInfo(dst);
            if (d.Exists && d.Length == s.Length && d.LastWriteTimeUtc == s.LastWriteTimeUtc) continue;
            Directory.CreateDirectory(d.DirectoryName!);
            File.Copy(src, dst, overwrite: true);
            File.SetLastWriteTimeUtc(dst, s.LastWriteTimeUtc);
        }
        _log.Write("bandroom: workspace copied to " + _paths.Workspace);
    }
}

public sealed class BootstrapException(string environment, int exitCode, IReadOnlyList<string> tail)
    : Exception(string.Create(CultureInfo.InvariantCulture, $"pixi install -e {environment} exited with {exitCode}"))
{
    public string Environment { get; } = environment;
    public int ExitCode { get; } = exitCode;
    public IReadOnlyList<string> Tail { get; } = tail;
}

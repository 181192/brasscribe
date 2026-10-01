namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// Where things live on this computer (spec §5.2), all under the per-user data folder
/// (%LOCALAPPDATA%\Brasscribe on Windows):
/// <c>envs</c> the pixi workspace copied from the app, <c>cache\pixi</c>, <c>models</c>, <c>logs</c>,
/// <c>bandroom</c> (Bandroom's own state: the admin credential, setup markers), and engine.json.
/// </summary>
public sealed record BandroomPaths(string DataDir)
{
    public string Workspace => Path.Combine(DataDir, "envs");
    public string Manifest => Path.Combine(Workspace, "pixi.toml");
    public string Adapters => Path.Combine(Workspace, "ml", "adapters");
    public string PixiCache => Path.Combine(DataDir, "cache", "pixi");
    public string Models => Path.Combine(DataDir, "models");
    public string Logs => Path.Combine(DataDir, "logs");
    public string State => Path.Combine(DataDir, "bandroom");
    public string AdminTokenFile => Path.Combine(State, "admin-token");
    public string SetupMarkers => Path.Combine(State, "setup");
    /// <summary>The Appearance choice: this PC only, never roamed (design/system.md §10).</summary>
    public string AppearanceFile => Path.Combine(State, "appearance");
    /// <summary>The name shown to phones, when one is set in Settings.</summary>
    public string ComputerNameFile => Path.Combine(State, "computer-name");
    public string StatusFile => Path.Combine(DataDir, "engine.json");

    public static BandroomPaths ForCurrentUser() =>
        new(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe"));
}

/// <summary>
/// What the engine process needs: the pinned pixi, the data folder, the computer's name, the admin credential,
/// the band sounds the app bundles (<c>band\</c> next to the exe; null when this build has none) and the Rust
/// core's command line (<c>core\brasscribe-core.exe</c> next to the exe; null when this build has none).
/// </summary>
public sealed record EngineLaunchConfig(
    BandroomPaths Paths,
    string PixiExe,
    string ComputerName,
    string AdminToken,
    bool UseCuda,
    string? BandSoundsDir = null,
    string? CoreCli = null)
{
    /// <summary>The user's Hugging Face key (HF_TOKEN), read at each start so a key saved in Settings reaches the next one.</summary>
    public Func<string?>? HuggingFaceToken { get; init; }

    /// <summary>This process's environment variables (PATH, HF_HOME, HF_HUB_CACHE, HF_TOKEN), read at each start.</summary>
    public Func<string, string?> Variable { get; init; } = Environment.GetEnvironmentVariable;

    /// <summary>The bundled band sounds folder under <paramref name="appDir"/>, if the SoundFont and its part map are there.</summary>
    public static string? FindBandSounds(string appDir)
    {
        string dir = Path.Combine(appDir, "band");
        return File.Exists(Path.Combine(dir, "brasscribe-band.sf2")) && File.Exists(Path.Combine(dir, "mapping.json")) ? dir : null;
    }

    /// <summary>The bundled core command line under <paramref name="appDir"/> (the bass-tab profile runs it), if it is there.</summary>
    public static string? FindCoreCli(string appDir)
    {
        string exe = Path.Combine(appDir, "core", "brasscribe-core.exe");
        return File.Exists(exe) ? exe : null;
    }

    /// <summary>
    /// <c>pixi run --manifest-path &lt;envs&gt;\pixi.toml --frozen -e default brasscribe serve --lan --port N</c>
    /// with the environment variables config.py reads (spec §5.2) and the admin credential.
    /// </summary>
    public ProcessSpec Build(int port)
    {
        var env = new Dictionary<string, string>
        {
            ["BRASSCRIBE_DATA"] = Paths.DataDir,
            ["BRASSCRIBE_MODELS"] = Paths.Models,
            ["BRASSCRIBE_ADAPTERS"] = Paths.Adapters,
            ["BRASSCRIBE_COMPUTER_NAME"] = ComputerName,
            ["BRASSCRIBE_ADMIN_TOKEN"] = AdminToken,
            // Adapters run in the pixi environments bootstrap installed; torch ones use <name>-cuda on an NVIDIA PC.
            ["BRASSCRIBE_ADAPTER_RUNNER"] = "pixi",
            ["PIXI_CACHE_DIR"] = Paths.PixiCache,
            ["PYTHONUTF8"] = "1",
            // run_adapter.py calls "pixi" by name.
            ["PATH"] = Path.GetDirectoryName(PixiExe) is { Length: > 0 } dir
                ? dir + Path.PathSeparator + (Variable("PATH") ?? "")
                : Variable("PATH") ?? "",
        };
        if (UseCuda) env["BRASSCRIBE_CUDA"] = "1";
        // The muscriptor adapter finds the band writer in the hub cache Bandroom downloaded it to, with the same key.
        foreach (var name in (string[])["HF_HOME", "HF_HUB_CACHE"])
            if (Variable(name) is { Length: > 0 } value) env[name] = value;
        if ((Variable("HF_TOKEN") is { Length: > 0 } t ? t : HuggingFaceToken?.Invoke()) is { Length: > 0 } token) env["HF_TOKEN"] = token;
        // Studio (served by the engine) plays the band SoundFont from here.
        if (BandSoundsDir is { Length: > 0 }) env["BRASSCRIBE_BAND_SOUNDS_DIR"] = BandSoundsDir;
        // The installed workspace has no core to build: the bass-tab profile runs the bundled command line.
        if (CoreCli is { Length: > 0 }) env["BRASSCRIBE_CORE_CLI"] = CoreCli;
        return new ProcessSpec(
            PixiExe,
            ["run", "--manifest-path", Paths.Manifest, "--frozen", "-e", "default",
             "brasscribe", "serve", "--lan", "--port", port.ToString(System.Globalization.CultureInfo.InvariantCulture)],
            Paths.Workspace,
            env);
    }
}

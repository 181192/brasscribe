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
    public string StatusFile => Path.Combine(DataDir, "engine.json");

    public static BandroomPaths ForCurrentUser() =>
        new(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe"));
}

/// <summary>What the engine process needs: the pinned pixi, the data folder, the computer's name and the admin credential.</summary>
public sealed record EngineLaunchConfig(
    BandroomPaths Paths,
    string PixiExe,
    string ComputerName,
    string AdminToken,
    bool UseCuda)
{
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
                ? dir + Path.PathSeparator + (Environment.GetEnvironmentVariable("PATH") ?? "")
                : Environment.GetEnvironmentVariable("PATH") ?? "",
        };
        if (UseCuda) env["BRASSCRIBE_CUDA"] = "1";
        return new ProcessSpec(
            PixiExe,
            ["run", "--manifest-path", Paths.Manifest, "--frozen", "-e", "default",
             "brasscribe", "serve", "--lan", "--port", port.ToString(System.Globalization.CultureInfo.InvariantCulture)],
            Paths.Workspace,
            env);
    }
}

namespace Brasscribe.Bandroom.Core.Downloads;

/// <summary>
/// The three downloads a full-band score needs (docs/plan/apps-plan.md §7). None of them ship with the app:
/// each comes from where its makers publish it, and this computer fetches it. Listed in catalogue order.
/// </summary>
public enum ModelComponent
{
    /// <summary>BS-RoFormer SW: lifts the soloist out of the band (the <c>separator</c> adapter). No stated licence.</summary>
    SoloistSeparator,
    /// <summary>Mega-53: splits the band into its instruments (the <c>mega53</c> adapter). No stated licence.</summary>
    InstrumentSeparator,
    /// <summary>MuScriptor medium: writes down the notes. CC BY-NC 4.0, gated on Hugging Face.</summary>
    BandWriter,
}

/// <summary>Where a component's files go.</summary>
public abstract record ModelHome
{
    private ModelHome() { }

    /// <summary><c>&lt;models&gt;\&lt;folder&gt;</c>, the folder the engine reads through BRASSCRIBE_MODELS.</summary>
    public sealed record Models(string Folder) : ModelHome;

    /// <summary>
    /// The Hugging Face hub cache, laid out as <c>huggingface_hub</c> lays it out, so the adapter's
    /// <c>hf_hub_download</c> finds it without fetching again.
    /// </summary>
    public sealed record Hub(string Repo, string Revision) : ModelHome;
}

/// <summary>One file of a component, from its original release URL. Never re-hosted by us.</summary>
/// <param name="Name">File name in the component's folder (or snapshot).</param>
/// <param name="Url">The upstream release URL.</param>
/// <param name="Size">Bytes upstream publishes; 0 when upstream changes the file (then no size or checksum check).</param>
/// <param name="Sha256">SHA-256 upstream publishes (GitHub release asset digest, Hugging Face X-Linked-Etag), lower-case hex.</param>
/// <param name="GitBlob">Git blob id of a small (non-LFS) Hugging Face file: its name in the hub cache's blobs folder.</param>
public sealed record ModelFile(string Name, Uri Url, long Size, string? Sha256 = null, string? GitBlob = null)
{
    /// <summary>Name under <c>blobs\</c> in the hub cache: the SHA-256 for LFS files, the git blob id otherwise.</summary>
    public string BlobName => Sha256 ?? GitBlob ?? Name;
}

/// <summary>
/// Upstream release URLs, sizes and checksums, as the adapters in ml/adapters expect them: run_adapter.py's
/// <c>separator</c> (audio-separator, <c>--model_file_dir &lt;models&gt;\separator</c>, BS-Roformer-SW.ckpt),
/// <c>mega53</c> (<c>&lt;models&gt;\mega53</c>, MSST v1.0.21 assets) and <c>muscriptor</c>
/// (<c>hf://MuScriptor/muscriptor-medium</c>). The same values as Bandroom for macOS (ModelCatalog.swift).
/// </summary>
public static class ModelCatalog
{
    public const string MuscriptorRepo = "MuScriptor/muscriptor-medium";
    /// <summary>The revision the checksums below belong to.</summary>
    public const string MuscriptorRevision = "f32236969308476e01fd3aae67357de5feb05a2d";
    public const string HuggingFaceHost = "huggingface.co";

    private const string SeparatorRelease = "https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs";
    private const string Mega53Release = "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21";
    private const string HfResolve = "https://huggingface.co/" + MuscriptorRepo + "/resolve/" + MuscriptorRevision;

    public static IReadOnlyList<ModelComponent> All { get; } = Enum.GetValues<ModelComponent>();

    public static IReadOnlyList<ModelFile> Files(ModelComponent component) => component switch
    {
        ModelComponent.SoloistSeparator =>
        [
            new("BS-Roformer-SW.ckpt", new Uri($"{SeparatorRelease}/BS-Roformer-SW.ckpt"),
                699_412_152, Sha256: "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e"),
            new("BS-Roformer-SW.yaml", new Uri($"{SeparatorRelease}/BS-Roformer-SW.yaml"),
                4_653, Sha256: "b558996f1e25eb48798bd6502505a5de94c4f966d6edfb1a0420f06cc40b501a"),
            // audio-separator reads its model list from here before every run; with it in place it needs no
            // network. Upstream edits it, so no size or checksum.
            new("download_checks.json",
                new Uri("https://raw.githubusercontent.com/TRvlvr/application_data/main/filelists/download_checks.json"), 0),
        ],
        ModelComponent.InstrumentSeparator =>
        [
            new("mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", new Uri($"{Mega53Release}/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"),
                1_368_919_887, Sha256: "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"),
            new("mvsep_mega_model_bs_roformer_53_stems.yaml", new Uri($"{Mega53Release}/mvsep_mega_model_bs_roformer_53_stems.yaml"),
                4_184, Sha256: "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"),
        ],
        _ =>
        [
            new("model.safetensors", new Uri($"{HfResolve}/model.safetensors"),
                1_228_144_472, Sha256: "ac80adbdf85d87231735fd948af7013441c0afced316c4e9067fd5d8a7fb97ec"),
            new("config.json", new Uri($"{HfResolve}/config.json"),
                126, GitBlob: "3862558703a8c30630ff1149b58e2f070179c774"),
        ],
    };

    public static ModelHome Home(this ModelComponent component) => component switch
    {
        ModelComponent.SoloistSeparator => new ModelHome.Models("separator"),
        ModelComponent.InstrumentSeparator => new ModelHome.Models("mega53"),
        _ => new ModelHome.Hub(MuscriptorRepo, MuscriptorRevision),
    };

    /// <summary>Needs the user's own Hugging Face key, and the licence accepted on the model page.</summary>
    public static bool NeedsHuggingFaceKey(this ModelComponent component) => component == ModelComponent.BandWriter;

    /// <summary>The page people read before they download: the licence (or its absence) is stated there.</summary>
    public static Uri Page(this ModelComponent component) => component switch
    {
        ModelComponent.SoloistSeparator => new Uri("https://github.com/nomadkaraoke/python-audio-separator"),
        ModelComponent.InstrumentSeparator => new Uri("https://github.com/ZFTurbo/Music-Source-Separation-Training"),
        _ => new Uri("https://huggingface.co/" + MuscriptorRepo),
    };

    public static long TotalBytes(ModelComponent component) => Files(component).Sum(f => f.Size);

    /// <summary>
    /// The hub cache: HF_HUB_CACHE, else HF_HOME\hub, else %USERPROFILE%\.cache\huggingface\hub (as huggingface_hub
    /// and the engine's adapters.py resolve it).
    /// </summary>
    public static string HubCache(IReadOnlyDictionary<string, string?> environment, string home)
    {
        if (environment.TryGetValue("HF_HUB_CACHE", out var cache) && !string.IsNullOrEmpty(cache)) return cache;
        if (environment.TryGetValue("HF_HOME", out var hf) && !string.IsNullOrEmpty(hf)) return Path.Combine(hf, "hub");
        return Path.Combine(home, ".cache", "huggingface", "hub");
    }

    /// <summary>The hub cache of this process's environment and user profile.</summary>
    public static string HubCache() => HubCache(
        new Dictionary<string, string?>
        {
            ["HF_HUB_CACHE"] = Environment.GetEnvironmentVariable("HF_HUB_CACHE"),
            ["HF_HOME"] = Environment.GetEnvironmentVariable("HF_HOME"),
        },
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));

    /// <summary><c>models--MuScriptor--muscriptor-medium</c> in the hub cache.</summary>
    public static string HubRepoFolder(string repo, string hub) => Path.Combine(hub, "models--" + repo.Replace("/", "--", StringComparison.Ordinal));
}

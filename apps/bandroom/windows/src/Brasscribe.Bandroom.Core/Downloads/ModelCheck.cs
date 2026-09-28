namespace Brasscribe.Bandroom.Core.Downloads;

/// <summary>What is missing, in catalogue order, and which files (for the tech person).</summary>
public sealed record ModelCheckResult(IReadOnlyList<ModelComponent> Missing, IReadOnlyList<string> MissingFiles)
{
    public static ModelCheckResult Ready { get; } = new([], []);
    public bool IsReady => Missing.Count == 0;
}

/// <summary>
/// Whether the downloads a full-band score needs are there (§7 "Ready to make scores"). Runs every few
/// seconds, so it looks at names and sizes only; checksums are checked once, when a download finishes.
/// </summary>
public static class ModelCheck
{
    /// <param name="models">The folder the engine gets as BRASSCRIBE_MODELS.</param>
    /// <param name="hub">The Hugging Face hub cache (<see cref="ModelCatalog.HubCache()"/>), where the band writer lives.</param>
    /// <param name="catalog">The files of each component; the real catalogue unless a test says otherwise.</param>
    public static ModelCheckResult Check(string models, string hub, Func<ModelComponent, IReadOnlyList<ModelFile>>? catalog = null)
    {
        catalog ??= ModelCatalog.Files;
        var missing = new List<ModelComponent>();
        var files = new List<string>();
        foreach (var c in ModelCatalog.All)
        {
            var absent = MissingFiles(c, models, hub, catalog(c));
            if (absent.Count == 0) continue;
            missing.Add(c);
            files.AddRange(absent);
        }
        return new ModelCheckResult(missing, files);
    }

    public static bool IsPresent(ModelComponent c, string models, string hub, IReadOnlyList<ModelFile> files) =>
        MissingFiles(c, models, hub, files).Count == 0;

    private static List<string> MissingFiles(ModelComponent c, string models, string hub, IReadOnlyList<ModelFile> files)
    {
        switch (c.Home())
        {
            case ModelHome.Models m:
                string dir = Path.Combine(models, m.Folder);
                return files.Where(f => !FileMatches(Path.Combine(dir, f.Name), f.Size)).Select(f => Path.Combine(dir, f.Name)).ToList();
            case ModelHome.Hub h:
                // As hf_hub_download resolves "main": refs\main names the snapshot the adapter reads.
                string folder = ModelCatalog.HubRepoFolder(h.Repo, hub);
                string? rev = ReadRef(folder);
                if (rev is null) return files.Select(f => Path.Combine(folder, "snapshots", h.Revision, f.Name)).ToList();
                string snapshot = Path.Combine(folder, "snapshots", rev);
                // A newer upstream revision has other sizes; then the files being there is enough.
                return files.Where(f => !FileMatches(Path.Combine(snapshot, f.Name), rev == h.Revision ? f.Size : 0))
                    .Select(f => Path.Combine(snapshot, f.Name)).ToList();
            default:
                return [];
        }
    }

    /// <summary>The revision in <c>refs\main</c>, or null when there is none.</summary>
    internal static string? ReadRef(string repoFolder)
    {
        try
        {
            string path = Path.Combine(repoFolder, "refs", "main");
            if (!File.Exists(path)) return null;
            string rev = File.ReadAllText(path).Trim();
            return rev.Length > 0 ? rev : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }

    /// <summary>A regular file (through symbolic links) and, when <paramref name="size"/> &gt; 0, exactly that many bytes.</summary>
    public static bool FileMatches(string path, long size)
    {
        try
        {
            var info = new FileInfo(path);
            if (info.LinkTarget is not null && info.ResolveLinkTarget(returnFinalTarget: true) is FileInfo target) info = target;
            if (!info.Exists) return false;
            return size <= 0 || info.Length == size;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }
}

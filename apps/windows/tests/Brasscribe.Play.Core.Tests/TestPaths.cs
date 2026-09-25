namespace Brasscribe.Play.Core.Tests;

/// <summary>Locates fixtures and the repo-level data/models folders (absent in CI, so tests skip).</summary>
internal static class TestPaths
{
    public static string Fixture(string name) => Path.Combine(AppContext.BaseDirectory, "Fixtures", name);

    public static string Output(string relative) => Path.Combine(AppContext.BaseDirectory, relative);

    /// <summary>The repository root: the nearest ancestor holding apps/windows.</summary>
    public static string? RepoRoot
    {
        get
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                if (Directory.Exists(Path.Combine(dir.FullName, "apps", "windows"))) return dir.FullName;
                dir = dir.Parent;
            }
            return null;
        }
    }

    /// <summary>A file under data/ or models/ in the repo, or null when it is not there.</summary>
    public static string? RepoFile(string relative)
    {
        var env = Environment.GetEnvironmentVariable("BRASSCRIBE_REPO");
        foreach (var root in new[] { env, RepoRoot }.Where(r => r is not null))
        {
            var p = Path.Combine(root!, relative);
            if (File.Exists(p)) return p;
        }
        return null;
    }

    public static string GoldenMusicXml => "data/golden/mikkel-arranged-band/brass-band.musicxml";
    public static string GoldenComposition => "data/golden/mikkel-arranged-band/composition.json";
    public static string SwiftF0Stream => "models/converted/swift-f0/swift-f0-stream.onnx";
}

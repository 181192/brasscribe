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

    /// <summary>The skip reason for a test that needs <paramref name="relative"/> (as passed to <see cref="RepoFile"/>).</summary>
    public static string Missing(string relative) =>
        relative.StartsWith("data/sounds/", StringComparison.Ordinal)
            ? $"{relative} not found: SoundFonts are downloads or build outputs (`pixi run fetch-sounds` fetches the band SoundFonts; scripts/worktree-setup.sh links data/ into a worktree, or set BRASSCRIBE_REPO)"
            : relative.StartsWith("data/", StringComparison.Ordinal) || relative.StartsWith("models/", StringComparison.Ordinal)
                ? $"{relative} not found: data/ and models/ are not in git (scripts/worktree-setup.sh links them into a worktree, or set BRASSCRIBE_REPO to a checkout that has them)"
                : $"{relative} not found: run the tests from a checkout, or set BRASSCRIBE_REPO";

    /// <summary>The skip reason for a test that runs the Rust core through brasscribe_ffi.</summary>
    public const string NoNativeCore =
        "BRASSCRIBE_FFI_PATH is not set: `scripts/core-artifacts.sh ensure host` puts the native core at core/target/release/libbrasscribe_ffi.dylib (.so, .dll); point BRASSCRIBE_FFI_PATH at it";

    public static string GoldenMusicXml =>"data/golden/mikkel-arranged-band/brass-band.musicxml";
    public static string GoldenComposition => "data/golden/mikkel-arranged-band/composition.json";
    public static string SwiftF0Stream => "models/converted/swift-f0/swift-f0-stream.onnx";
}

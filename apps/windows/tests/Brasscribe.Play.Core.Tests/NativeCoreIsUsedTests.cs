using Brasscribe.Play.Core.Bridge;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The tests that run the Rust core skip themselves when SCRIBE_FFI_PATH is not set, so that the suite runs
/// without a core. That must not hide a core that is there: these fail when the variable names a library
/// that is missing, and when the checkout has a built core that the variable does not point at (an
/// environment file from before a change of names, for one).
/// </summary>
public class NativeCoreIsUsedTests
{
    private static string? Named => Environment.GetEnvironmentVariable("SCRIBE_FFI_PATH") is { Length: > 0 } p ? p : null;

    /// <summary>A host build of the core in this checkout, under whatever name: any *_ffi library.</summary>
    private static string? Built()
    {
        var root = Environment.GetEnvironmentVariable("BRASSCRIBE_REPO") is { Length: > 0 } repo ? repo : TestPaths.RepoRoot;
        var dir = root is null ? null : Path.Combine(root, "core", "target", "release");
        if (dir is null || !Directory.Exists(dir)) return null;
        return Directory.EnumerateFiles(dir)
            .FirstOrDefault(f => Path.GetFileNameWithoutExtension(f).EndsWith("_ffi", StringComparison.Ordinal)
                                 && Path.GetExtension(f) is ".dylib" or ".so" or ".dll");
    }

    [Fact]
    public void The_library_SCRIBE_FFI_PATH_names_is_there_and_loads()
    {
        if (Named is not { } path) return;
        Assert.True(File.Exists(path), $"SCRIBE_FFI_PATH names {path}, which is not there: run scripts/worktree-setup.sh, or build the core");
        Assert.True(NativeCoreBridge.TryCreate() is not null, $"SCRIBE_FFI_PATH names {path}, but scribe_ffi did not load from it");
    }

    [Fact]
    public void A_built_core_is_not_left_out_of_the_tests()
    {
        if (Named is not null || Built() is not { } built) return;
        Assert.Fail($"a core is built at {built}, but SCRIBE_FFI_PATH is not set, so every test of the native core would skip: "
                    + "run scripts/worktree-setup.sh and load .scribe-env, or set SCRIBE_FFI_PATH to libscribe_ffi "
                    + "(a library under another name is from before the core was renamed: build the core again)");
    }
}

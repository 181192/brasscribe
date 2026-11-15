using Kalli.Scribe.OnDevice;

namespace Kalli.Scribe.Tests;

/// <summary>
/// ONNX Runtime's telemetry events are switched off before every session: sessions are made only by
/// <see cref="OnnxSessions.Create"/>, which switches them off first. The runtime has no way to ask whether they are
/// on, so this checks the code that makes sessions.
/// </summary>
public class OnnxTelemetryTests
{
    private static string WindowsApps => Path.Combine(TestPaths.RepoRoot ?? throw new InvalidOperationException("no repository"), "apps", "windows");

    private static IEnumerable<string> AppSources() =>
        Directory.EnumerateFiles(WindowsApps, "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Split(Path.DirectorySeparatorChar).Any(p => p is "bin" or "obj" or "tests"));

    [Fact]
    public void Sessions_are_made_only_where_telemetry_is_switched_off_first()
    {
        var makers = AppSources().Where(f => File.ReadAllText(f).Contains("new InferenceSession(")).Select(Path.GetFileName).ToList();
        Assert.Equal(["OnnxSessions.cs"], makers);

        var code = File.ReadAllText(AppSources().Single(f => Path.GetFileName(f) == "OnnxSessions.cs"));
        var create = code.IndexOf("Create(string modelPath", StringComparison.Ordinal);
        Assert.True(create > 0);
        var off = code.IndexOf("TelemetryOff();", create, StringComparison.Ordinal);
        var first = code.IndexOf("new InferenceSession(", create, StringComparison.Ordinal);
        Assert.True(off > 0 && off < first, "OnnxSessions.Create switches telemetry off before it makes a session");
    }

    [Fact]
    public void No_one_switches_telemetry_back_on()
    {
        Assert.DoesNotContain(AppSources(), f => File.ReadAllText(f).Contains("EnableTelemetryEvents"));
    }

    [Fact]
    public void Switching_off_works_on_the_runtime_the_app_ships()
    {
        OnnxSessions.TelemetryOff();
        OnnxSessions.TelemetryOff();
    }
}

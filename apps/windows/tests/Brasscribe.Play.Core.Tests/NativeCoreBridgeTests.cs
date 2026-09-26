using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The Rust core through its C ABI. Runs when BRASSCRIBE_FFI_PATH points at a built
/// brasscribe_ffi (libbrasscribe_ffi.dylib, .so or brasscribe_ffi.dll); skipped otherwise.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class NativeCoreBridgeTests(ITestOutputHelper log)
{
    private static NativeCoreBridge? Bridge() =>
        Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is { Length: > 0 } ? NativeCoreBridge.TryCreate() : null;

    [Fact]
    public void Normalizes_and_arranges_the_golden_composition()
    {
        var bridge = Bridge();
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (bridge is null || json is null || golden is null) return;

        log.WriteLine($"native core {bridge.Version}");
        Assert.True(bridge.IsNative);
        var composition = bridge.ParseComposition(File.ReadAllText(json));
        Assert.Equal(5, composition.Voices.Count);

        var xml = bridge.ArrangeMusicXml(composition, "layers")!;
        var mine = MusicXmlTalkingScoreBuilder.Build(xml);
        var reference = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(golden));
        Assert.Equal(reference.Parts.Select(p => p.Name), mine.Parts.Select(p => p.Name));
        for (int p = 0; p < reference.Parts.Count; p++)
        {
            int a = Notes(reference.Parts[p]), b = Notes(mine.Parts[p]);
            log.WriteLine($"{reference.Parts[p].Name}: reference {a} notes, core {b}");
        }
        Assert.Equal(reference.Parts.Sum(Notes), mine.Parts.Sum(Notes));
    }

    [Fact]
    public void Invalid_json_raises_a_core_error()
    {
        var bridge = Bridge();
        if (bridge is null) return;
        var e = Assert.Throws<CoreBridgeException>(() => bridge.ParseComposition("{\"title\": 3}"));
        Assert.NotEqual(0, e.Status);
    }

    private static int Notes(TsPart part) =>
        part.Bars.Sum(b => b.Events.Count(e => e.Kind is EventKind.Note or EventKind.Chord or EventKind.Unpitched));
}

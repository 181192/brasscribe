using Brasscribe.Core;
using Xunit;

public class BrasscribeCoreTests
{
    private const string Composition = """
        {"title": "Test", "voices": [
          {"id": "melody", "role": "melody", "notes": [
            {"pitch": 72, "start": 0, "dur": 24}, {"pitch": 74, "start": 24, "dur": 24}]},
          {"id": "bass", "role": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 48}]}],
         "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}]}
        """;

    [Fact]
    public void ReportsVersion() => Assert.False(string.IsNullOrEmpty(BrasscribeCore.Version));

    [Fact]
    public void ArrangesToTransposedMusicXml()
    {
        var xml = BrasscribeCore.ArrangeMusicXml(Composition);
        Assert.Contains("<part-name>Solo Cornet</part-name>", xml);
        Assert.Contains("<step>D</step>", xml); // concert C5 on a B-flat cornet is written D5
    }

    [Fact]
    public void NormalizesComposition()
    {
        var json = BrasscribeCore.NormalizeComposition(Composition);
        Assert.StartsWith("{\n \"title\": \"Test\"", json);
        Assert.Contains("\"performed_dur\": null", json);
    }

    [Fact]
    public void InvalidJsonThrows()
    {
        var e = Assert.Throws<BrasscribeException>(() => BrasscribeCore.NormalizeComposition("{"));
        Assert.Equal(1, e.Code);
    }

    [Fact]
    public void ArrangesMikkelLayersWhenDataIsPresent()
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "../../../../../../data/mikkel/repro");
        if (!Directory.Exists(dir)) return; // data/ is not in the repository
        byte[] F(string n) => File.ReadAllBytes(Path.Combine(dir, "layers", n));
        var layers = new LayerMidi(F("solo-sw.mid"), F("solo-mus.mid"), F("solo-bp.mid"), F("bass-mus.mid"), F("orchestra-mus.mid"), F("drums-mus.mid"));
        var (comp, xml) = BrasscribeCore.ArrangeLayersSong(layers, File.ReadAllText(Path.Combine(dir, "mix.beats")), "Mikkel");
        Assert.Contains("\"free_regions\": [", comp);
        Assert.Equal(18, xml.Split("<score-part ").Length - 1);
        Assert.Contains("<words>ad lib.</words>", xml);
    }

    [Fact]
    public void SpellsPitches()
    {
        var s = BrasscribeCore.SpellPitches([0, 1, 2], [66, 69, 74]);
        Assert.Equal(["F", "A", "D"], s.Select(p => p.Step));
        Assert.Equal(1, s[0].Alter);
    }
}

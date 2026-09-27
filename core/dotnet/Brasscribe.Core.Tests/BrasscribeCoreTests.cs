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
    public void ArrangesForTheQuartet()
    {
        var xml = BrasscribeCore.ArrangeMusicXmlWith(Composition, lineup: "quartet");
        foreach (var part in new[] { "1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium" })
        {
            Assert.Contains($"<part-name>{part}</part-name>", xml);
        }
        Assert.DoesNotContain("<part-name>Solo Cornet</part-name>", xml);
        var e = Assert.Throws<BrasscribeException>(() => BrasscribeCore.ArrangeMusicXmlWith(Composition, lineup: "nonet"));
        Assert.Equal(1, e.Code);
    }

    [Fact]
    public void SeatsAndTheirParts()
    {
        var seats = BrasscribeCore.Seats();
        Assert.Equal(18, seats.Count);
        var euph = seats.Single(s => s.Id == "euphonium");
        Assert.Equal("Euphonium", euph.Name);
        Assert.Equal("Eufonium", euph.NbName);
        Assert.Equal(new[] { "treble", "bass" }, euph.Reads);
        Assert.Equal("Solo althorn", seats.Single(s => s.Id == "solo-horn").NbName);
        // Three spot checks of the seat -> part table.
        Assert.Equal(new SeatPart("Euphonium", false, true), BrasscribeCore.SeatPart("minimal", "1st-baritone"));
        Assert.Equal(new SeatPart("Euphonium", false, false), BrasscribeCore.SeatPart("quartet", "eb-bass"));
        Assert.Equal(new SeatPart(null, false, false), BrasscribeCore.SeatPart("quartet", "percussion"));
        Assert.Throws<BrasscribeException>(() => BrasscribeCore.SeatPart("band", "tuba"));
    }

    [Fact]
    public void PartSourcesAndBassClefReading()
    {
        var sources = BrasscribeCore.PartSources(Composition);
        Assert.Equal(new PartSource("Solo Cornet", "recording"), sources[0]);
        Assert.Contains(new PartSource("Flugelhorn", "arranged"), sources);
        var xml = BrasscribeCore.ArrangeMusicXmlWith(Composition, lineup: "minimal", seat: "euphonium", reads: "bass");
        Assert.Contains("<part-name>Euphonium</part-name>", xml);
        Assert.Throws<BrasscribeException>(() => BrasscribeCore.ArrangeMusicXmlWith(Composition, seat: "solo-cornet", reads: "bass"));
        Assert.Throws<BrasscribeException>(() => BrasscribeCore.ArrangeMusicXmlWith(Composition, lineup: "quartet", seat: "euphonium", lead: "seat"));
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
    public void HumanizesWithTheComposition()
    {
        var notes = new[] { new ScoreNote(24, 24, 0.5, 1.0, 74, 80), new ScoreNote(0, 24, 0.0, 0.5, 72, 80) };
        var h = BrasscribeCore.Humanize(notes, "Solo Cornet", 0, compositionJson: Composition);
        Assert.Equal([72, 74], h.Notes.Select(n => n.Pitch));
        Assert.Contains("\"voice\": \"melody\"", h.StatsJson);
    }

    /// <summary>Every talking-score conformance vector, both languages, through the C ABI.</summary>
    [Fact]
    public void PassesEveryTalkingScoreVector()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "../../../../../../docs/accessibility/talking-score-vectors.json");
        if (!File.Exists(path)) return;
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(path));
        int n = 0;
        foreach (var c in doc.RootElement.GetProperty("cases").EnumerateArray())
        {
            foreach (var lang in new[] { "en", "nb" })
            {
                var request = VectorRequest(c, lang);
                Assert.Equal(c.GetProperty("expected").GetProperty(lang).GetString(), BrasscribeCore.TalkingAnnounceJson(request));
                n++;
            }
        }
        Assert.True(n >= 50);
    }

    /// <summary>A vector read as every app reads it: B-flat cornet, written key 2 sharps and 128 bars unless stated.</summary>
    private static string VectorRequest(System.Text.Json.JsonElement c, string lang)
    {
        var s = c.GetProperty("settings");
        var cx = c.GetProperty("context");
        string? Str(System.Text.Json.JsonElement e, string k) => e.TryGetProperty(k, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.String ? v.GetString() : null;
        long? Int(System.Text.Json.JsonElement e, string k) => e.TryGetProperty(k, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.Number ? v.GetInt64() : null;
        var hasPart = c.TryGetProperty("part", out var pn);
        var b = c.TryGetProperty("bar", out var bv) ? bv : default;
        var hasBar = b.ValueKind == System.Text.Json.JsonValueKind.Object;
        object? region = null;
        bool entering = false;
        if (hasBar && b.TryGetProperty("free_region", out var fr))
        {
            region = new { start_bar = fr.GetProperty("start_bar").GetInt64(), end_bar = fr.GetProperty("end_bar").GetInt64(),
                start_s = fr.GetProperty("start_s").GetDouble(), end_s = fr.GetProperty("end_s").GetDouble() };
            entering = fr.TryGetProperty("entering", out var en) && en.GetBoolean();
        }
        var request = new
        {
            part = new
            {
                name = (hasPart ? Str(pn, "name") : null) ?? Str(cx, "part") ?? "Solo Cornet",
                name_nb = hasPart ? Str(pn, "name_nb") : null,
                instrument = (hasPart ? Str(pn, "instrument") : null) ?? "Cornet in B♭",
                instrument_nb = hasPart ? Str(pn, "instrument_nb") : "kornett i B",
                transpose = new { chromatic = -2, diatonic = -1 },
            },
            bar = new
            {
                number = (hasBar ? Int(b, "number") : null) ?? Int(cx, "bar") ?? 1,
                key_fifths = (hasBar ? Int(b, "key_fifths") : null) ?? 2,
                tempo_bpm = hasBar && b.TryGetProperty("tempo_bpm", out var t) ? t.GetDouble() : (double?)null,
                free_region = region,
                entering_region = entering,
                a_tempo = hasBar && b.TryGetProperty("a_tempo", out var at) && at.GetBoolean(),
                total_bars = 128,
            },
            @event = c.GetProperty("event"),
            context = new { part = Str(cx, "part"), bar = Int(cx, "bar"), pitch_mode = Str(cx, "pitch_mode") },
            settings = new { lang, pitch_mode = Str(s, "pitch_mode") ?? "written", verbosity = Str(s, "verbosity") ?? "standard" },
        };
        return System.Text.Json.JsonSerializer.Serialize(request);
    }

    [Fact]
    public void TalkingScoreNavigatesAnArrangedScore()
    {
        var xml = BrasscribeCore.ArrangeMusicXml(Composition);
        using var ts = new TalkingScore(xml, Composition);
        Assert.Contains("\"total_bars\"", ts.Json);
        var start = new TalkingCursor(0, 0, 0);
        var (text, ctx) = ts.Announce(start);
        Assert.StartsWith("bar 1", text);
        Assert.Equal(1, ctx.Bar);
        Assert.NotNull(ts.Navigate(start, "part"));
        Assert.Contains("Solo Cornet", ts.Export("text"));
    }

    [Fact]
    public void SpellsPitches()
    {
        var s = BrasscribeCore.SpellPitches([0, 1, 2], [66, 69, 74]);
        Assert.Equal(["F", "A", "D"], s.Select(p => p.Step));
        Assert.Equal(1, s[0].Alter);
    }
}

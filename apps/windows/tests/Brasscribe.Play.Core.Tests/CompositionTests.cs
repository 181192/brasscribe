using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Tests;

public class CompositionTests
{
    private const string Sample = """
    {"title":"t","voices":[{"id":"solo","role":"melody","instrument_hint":"cornet","layer":"solo","future_field":7,
      "notes":[{"pitch":72,"start":84,"dur":12,"confidence":0.55,"sources":["swiftf0"],"onset_s":0.03,"offset_s":0.15,
                "performed_dur":6,"articulations":["staccato"]},
               {"pitch":42,"start":96,"dur":12,"onset_s":null,"offset_s":null}]}],
     "meters":[{"tick":0,"beats":4,"beat_unit":4}],"keys":[{"tick":0,"fifths":-1,"mode":"major"}],
     "beat_times":[0.0,0.5,1.0,1.5,2.0],"first_downbeat":1,"ticks_per_beat":24,
     "free_regions":[{"start":0,"end":96,"start_s":0.0,"end_s":31.5,"tempo_bpm":60,"notation":"proportional","label":"ad lib."}]}
    """;

    [Fact]
    public void Parses_new_fields_and_keeps_unknown_ones()
    {
        var c = CompositionJson.Parse(Sample);
        var n = c.Voices[0].Notes[0];
        Assert.Equal(VoiceRole.Melody, c.Voices[0].Role);
        Assert.Equal(6, n.PerformedDur);
        Assert.Equal(["staccato"], n.Articulations);
        Assert.Equal(Certainty.Uncertain, n.Certainty);
        Assert.Null(c.Voices[0].Notes[1].OnsetS);
        Assert.Equal(1.0, c.Voices[0].Notes[1].Confidence);
        Assert.Single(c.FreeRegions);
        Assert.Equal(31.5, c.FreeRegions[0].EndS);
        Assert.True(c.Voices[0].Extra!.ContainsKey("future_field"));

        var again = CompositionJson.Parse(CompositionJson.Serialize(c));
        Assert.True(again.Voices[0].Extra!.ContainsKey("future_field"));
        Assert.Equal(c.EndTick, again.EndTick);
    }

    [Fact]
    public void Files_without_free_time_fields_load()
    {
        var c = CompositionJson.Parse("""{"title":"x","voices":[],"meters":[{"tick":0,"beats":3}],"keys":[{"tick":0,"fifths":0}]}""");
        Assert.Empty(c.FreeRegions);
        Assert.Equal(24, c.TicksPerBeat);
        Assert.Equal(4, c.Meters[0].BeatUnit);
        Assert.Equal(120.0, c.Bpm);
    }

    [Fact]
    public void Tick_and_seconds_map_through_the_beat_times()
    {
        var c = CompositionJson.Parse(Sample);
        Assert.Equal(0.5, c.SecondsAt(0), 6);     // tick 0 is beat 1
        Assert.Equal(1.0, c.SecondsAt(24), 6);
        Assert.Equal(24, c.TickAt(1.0), 6);
        Assert.Equal(120.0, c.Bpm, 6);
    }

    [Theory]
    [InlineData(0.95, Certainty.Confident)]
    [InlineData(0.7, Certainty.Confident)]
    [InlineData(0.69, Certainty.Uncertain)]
    [InlineData(0.4, Certainty.Uncertain)]
    [InlineData(0.39, Certainty.VeryUncertain)]
    public void Certainty_thresholds(double confidence, Certainty expected) =>
        Assert.Equal(expected, Note.CertaintyOf(confidence));

    [Fact]
    public void Golden_composition_loads()
    {
        var path = TestPaths.RepoFile(TestPaths.GoldenComposition);
        if (path is null) return; // data/ is not present in CI
        var c = CompositionJson.Parse(File.ReadAllText(path));
        // The golden output is re-saved when the engine improves, so check its shape, not exact counts.
        Assert.Equal(["solo", "bass", "strings", "brass", "drums"], c.Voices.Select(v => v.Id));
        Assert.True(c.Voices.Single(v => v.Id == "solo").Notes.Count > 300);
        Assert.Contains(c.Voices.SelectMany(v => v.Notes), n => n.OnsetS is null); // drums carry no performed time
        Assert.All(c.FreeRegions, r => Assert.True(r.End > r.Start && r.EndS > r.StartS && r.TempoBpm > 0));
    }
}

using System.Text.Json;
using System.Text.Json.Nodes;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Runs every case of docs/accessibility/talking-score-vectors.json (copied into Fixtures) in both
/// languages. Per the vectors' header: B-flat cornet (chromatic -2) and written key 2 sharps unless stated.
/// </summary>
public class TalkingScoreVectorTests
{
    private static readonly JsonSerializerOptions Snake = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    private static JsonArray Cases() =>
        JsonNode.Parse(File.ReadAllText(TestPaths.Fixture("talking-score-vectors.json")))!["cases"]!.AsArray();

    public static TheoryData<string, string> All()
    {
        var data = new TheoryData<string, string>();
        foreach (var c in Cases())
            foreach (var lang in new[] { "en", "nb" })
                data.Add(c!["id"]!.GetValue<string>(), lang);
        return data;
    }

    [Fact]
    public void Vector_file_has_the_expected_cases() => Assert.Equal(24, Cases().Count);

    [Theory]
    [MemberData(nameof(All))]
    public void Matches_vector(string id, string lang)
    {
        var v = Vector(id, lang);
        Assert.Equal(v.Expected, Announcer.Announce(v.Part, v.Bar, v.Event, v.Context, v.Settings));
    }

    /// <summary>The same vectors through the Rust core, when BRASSCRIBE_FFI_PATH points at a built brasscribe_ffi.</summary>
    [SkippableTheory]
    [MemberData(nameof(All))]
    public void Native_core_matches_vector(string id, string lang)
    {
        Skip.If(Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is not { Length: > 0 }, TestPaths.NoNativeCore);
        var core = Bridge.NativeCoreBridge.TryCreate();
        Assert.NotNull(core);
        var v = Vector(id, lang);
        Assert.Equal(v.Expected, core.Announce(v.Part, v.Bar, v.Event, v.Context, v.Settings));
    }

    internal sealed record VectorCase(AnnouncePart Part, AnnounceBar Bar, TsEvent Event, AnnounceContext Context, TalkingScoreSettings Settings, string Expected);

    internal static VectorCase Vector(string id, string lang)
    {
        var c = Cases().Single(x => x!["id"]!.GetValue<string>() == id)!;
        var settingsNode = c["settings"]!;
        var settings = new TalkingScoreSettings(
            Lang: lang,
            PitchMode: settingsNode["pitch_mode"]?.GetValue<string>() == "concert" ? PitchMode.Concert : PitchMode.Written,
            Verbosity: settingsNode["verbosity"]?.GetValue<string>() switch { "brief" => Verbosity.Brief, "full" => Verbosity.Full, _ => Verbosity.Standard });

        var ctxNode = c["context"]!;
        var ctx = new AnnounceContext(
            ctxNode["part"]?.GetValue<string>(),
            ctxNode["bar"]?.GetValue<int?>(),
            ctxNode["pitch_mode"]?.GetValue<string>() switch { "concert" => PitchMode.Concert, "written" => PitchMode.Written, _ => null });

        var partNode = c["part"];
        var part = new AnnouncePart(
            partNode?["name"]?.GetValue<string>() ?? ctx.Part ?? "Solo Cornet",
            partNode?["name_nb"]?.GetValue<string>(),
            partNode?["instrument"]?.GetValue<string>() ?? "Cornet in B♭",
            partNode?["instrument_nb"]?.GetValue<string>() ?? (partNode is null ? "kornett i B" : null),
            new TsTranspose(-2, -1));

        var barNode = c["bar"];
        TsFreeRegion? region = null;
        bool entering = false;
        if (barNode?["free_region"] is { } fr)
        {
            region = new TsFreeRegion
            {
                StartBar = fr["start_bar"]!.GetValue<int>(),
                EndBar = fr["end_bar"]!.GetValue<int>(),
                StartS = fr["start_s"]!.GetValue<double>(),
                EndS = fr["end_s"]!.GetValue<double>(),
            };
            entering = fr["entering"]?.GetValue<bool>() ?? false;
        }
        int? keyChange = barNode?["key_fifths"]?.GetValue<int>();
        var bar = new AnnounceBar(
            Number: barNode?["number"]?.GetValue<int>() ?? ctx.Bar ?? 1,
            KeyFifths: keyChange ?? 2,
            KeyChanged: keyChange is not null,
            TempoMarked: barNode?["tempo_bpm"]?.GetValue<double>(),
            FreeRegion: region,
            EnteringRegion: entering,
            ATempo: barNode?["a_tempo"]?.GetValue<bool>() ?? false,
            TotalBars: 128);

        var ev = c["event"].Deserialize<TsEvent>(Snake)!;
        return new VectorCase(part, bar, ev, ctx, settings, c["expected"]![lang]!.GetValue<string>());
    }

    [Theory]
    [InlineData(2, -2, 0)]    // B-flat instrument, written D major sounds C major
    [InlineData(0, 3, -3)]    // E-flat soprano cornet, written C sounds E-flat major
    [InlineData(3, -9, 0)]    // E-flat horn (down a major sixth), written A sounds C
    [InlineData(0, 0, 0)]
    public void Concert_key_follows_the_transposition(int written, int chromatic, int concert) =>
        Assert.Equal(concert, Announcer.ConcertKey(written, new TsTranspose(chromatic)));

    [Theory]
    [InlineData("en", 65.4, "at 1 minute 5 seconds")]
    [InlineData("nb", 125, "ved 2 minutter 5 sekunder")]
    [InlineData("en", 0.4, "at 0 seconds")]
    public void Free_time_positions_use_minutes_past_a_minute(string lang, double seconds, string expected)
    {
        var ev = new TsEvent { Kind = EventKind.Note, Type = "quarter", TimeS = seconds, Written = new("C", 0, 5) };
        var bar = new AnnounceBar(3, 0, FreeRegion: new TsFreeRegion { StartBar = 1, EndBar = 4 });
        var text = Announcer.Announce(new AnnouncePart("Solo Cornet"), bar, ev, new AnnounceContext("Solo Cornet", 3),
            new TalkingScoreSettings(lang));
        Assert.StartsWith(expected + ":", text);
    }

    [Fact]
    public void Chord_is_read_low_to_high()
    {
        var ev = new TsEvent
        {
            Kind = EventKind.Chord, Type = "quarter", Pos = new TsPos(1),
            Pitches = [new(new("G", 0, 5), new("F", 0, 5)), new(new("C", 0, 5), new("B", -1, 4)), new(new("E", 0, 5), new("D", 0, 5))],
        };
        var text = Announcer.Announce(new AnnouncePart("Solo Cornet"), new AnnounceBar(4, 0), ev, new AnnounceContext("Solo Cornet", 4),
            new TalkingScoreSettings());
        Assert.Equal("beat 1: chord, 3 notes: C 5, E 5, G 5, quarter note", text);
    }

    [Fact]
    public void Checked_note_no_longer_announces_uncertainty()
    {
        var ev = new TsEvent { Type = "quarter", Pos = new TsPos(1), Written = new("D", 0, 5), Confidence = 0.3, Checked = true };
        var text = Announcer.Announce(new AnnouncePart("Solo Cornet"), new AnnounceBar(4, 0), ev, new AnnounceContext("Solo Cornet", 4),
            new TalkingScoreSettings());
        Assert.Equal("beat 1: D 5, quarter note", text);
    }
}

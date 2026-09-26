using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Brasscribe.Play.Core.TalkingScore;

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    PropertyNameCaseInsensitive = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    NumberHandling = JsonNumberHandling.AllowReadingFromString)]
[JsonSerializable(typeof(TalkingScoreDocument))]
[JsonSerializable(typeof(TsEvent))]
internal sealed partial class TalkingScoreJsonContext : JsonSerializerContext;

/// <summary>
/// The talking-score document and the announcer inputs in their JSON form
/// (docs/accessibility/talking-score-spec.md §6, snake_case keys), as the Rust core reads and writes them.
/// </summary>
public static class TalkingScoreJson
{
    public static TalkingScoreDocument Parse(string json) =>
        JsonSerializer.Deserialize(json, TalkingScoreJsonContext.Default.TalkingScoreDocument)
        ?? throw new JsonException("Talking score JSON is null");

    public static JsonNode? Event(TsEvent ev) =>
        JsonSerializer.SerializeToNode(ev, TalkingScoreJsonContext.Default.TsEvent);

    public static JsonObject Part(AnnouncePart part) => Compact(new JsonObject
    {
        ["name"] = part.Name,
        ["name_nb"] = part.NameNb,
        ["instrument"] = part.Instrument,
        ["instrument_nb"] = part.InstrumentNb,
        ["transpose"] = part.Transpose is { } t ? Transpose(t) : null,
    });

    public static JsonObject Bar(AnnounceBar bar) => Compact(new JsonObject
    {
        ["number"] = bar.Number,
        ["key_fifths"] = bar.KeyFifths,
        ["key_changed"] = bar.KeyChanged,
        ["time_changed"] = bar.TimeChanged is { } tc ? new JsonObject { ["beats"] = tc.Beats, ["beat_type"] = tc.BeatType } : null,
        ["tempo_bpm"] = bar.TempoMarked,
        ["rehearsal"] = bar.Rehearsal,
        ["free_region"] = bar.FreeRegion is { } r ? FreeRegion(r) : null,
        ["entering_region"] = bar.EnteringRegion,
        ["a_tempo"] = bar.ATempo,
        ["total_bars"] = bar.TotalBars,
    });

    public static JsonObject Context(AnnounceContext ctx) => Compact(new JsonObject
    {
        ["part"] = ctx.Part,
        ["bar"] = ctx.Bar,
        ["pitch_mode"] = ctx.PitchMode is { } m ? Name(m) : null,
    });

    public static JsonObject Settings(TalkingScoreSettings s) => new()
    {
        ["lang"] = s.Lang,
        ["pitch_mode"] = Name(s.PitchMode),
        ["verbosity"] = s.Verbosity switch { Verbosity.Brief => "brief", Verbosity.Full => "full", _ => "standard" },
        ["octave_style"] = s.OctaveStyle == OctaveStyle.Helmholtz ? "helmholtz" : "scientific",
        ["announce_confident"] = s.AnnounceConfident,
    };

    /// <summary>The request of one out-of-document announcement (the conformance-vector form).</summary>
    public static string AnnounceRequest(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context,
        TalkingScoreSettings settings, bool byBar) => new JsonObject
    {
        ["part"] = Part(part),
        ["bar"] = Bar(bar),
        ["event"] = Event(ev),
        ["context"] = Context(context),
        ["settings"] = Settings(settings),
        ["by_bar"] = byBar,
    }.ToJsonString();

    public static string Name(PitchMode m) => m == PitchMode.Concert ? "concert" : "written";

    private static JsonObject Transpose(TsTranspose t) =>
        new() { ["chromatic"] = t.Chromatic, ["diatonic"] = t.Diatonic, ["octave"] = t.Octave };

    private static JsonObject FreeRegion(TsFreeRegion r) => new()
    {
        ["start_bar"] = r.StartBar,
        ["end_bar"] = r.EndBar,
        ["start_s"] = r.StartS,
        ["end_s"] = r.EndS,
        ["tempo_bpm"] = r.TempoBpm,
        ["notation"] = r.Notation,
        ["label"] = r.Label,
    };

    private static JsonObject Compact(JsonObject o)
    {
        foreach (var key in o.Where(kv => kv.Value is null).Select(kv => kv.Key).ToList()) o.Remove(key);
        return o;
    }
}

using System.Reflection;
using System.Text.Json;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Checks the hand-written DTOs against a snapshot of engine/openapi.json, so a change in the
/// engine contract shows up as a failing test here. Refresh Fixtures/openapi.json when the engine changes
/// (copy engine/openapi.json; an engine test fails while it differs).
/// </summary>
public class OpenApiContractTests
{
    /// <summary>The tab profile's result. The engine's <c>Tab</c> is <see cref="TabResult"/> here (Kalli.Scribe.Tab is a namespace).</summary>
    private static readonly Dictionary<string, Type> TabDtos = new()
    {
        ["Tab"] = typeof(TabResult),
        ["TabNote"] = typeof(TabNote),
        ["TabPosition"] = typeof(TabPosition),
        ["TabString"] = typeof(TabString),
        ["TabTuning"] = typeof(TabTuning),
        ["TabInstrument"] = typeof(TabInstrument),
        ["TabViolation"] = typeof(TabViolation),
        ["TuningFit"] = typeof(TuningFit),
        ["TabKey"] = typeof(TabKey),
        ["TabMeter"] = typeof(TabMeter),
        ["ReferencePitch"] = typeof(ReferencePitch),
    };

    private static readonly Dictionary<string, Type> Dtos = new Dictionary<string, Type>
    {
        ["Health"] = typeof(Health),
        ["AudioRef"] = typeof(AudioRef),
        ["JobCreate"] = typeof(JobCreate),
        ["Job"] = typeof(Job),
        ["StageState"] = typeof(StageState),
        ["Artifact"] = typeof(Artifact),
        ["StageArtifacts"] = typeof(StageArtifacts),
        ["FileRef"] = typeof(FileRef),
        ["ProfileInfo"] = typeof(ProfileInfo),
        ["PairRequest"] = typeof(PairRequest),
        ["PairResponse"] = typeof(PairResponse),
        ["Composition"] = typeof(Composition),
        ["Voice"] = typeof(Voice),
        ["Note"] = typeof(Note),
        ["Meter"] = typeof(Meter),
        ["KeySig"] = typeof(KeySig),
        ["Evidence"] = typeof(Evidence),
        ["NoteEvidence"] = typeof(NoteEvidence),
        ["ModelHeard"] = typeof(ModelHeard),
        ["ModelInfo"] = typeof(ModelInfo),
        ["RunUpdate"] = typeof(RunUpdate),
        ["DeviceSelf"] = typeof(DeviceSelf),
        ["RotateResponse"] = typeof(RotateResponse),
        ["PairRequestCreate"] = typeof(PairRequestCreate),
        ["PairRequestInfo"] = typeof(PairRequestInfo),
        ["PairRequestResult"] = typeof(PairRequestResult),
    }.Concat(TabDtos).ToDictionary();


    private static JsonElement Spec() => JsonDocument.Parse(File.ReadAllText(TestPaths.Fixture("openapi.json"))).RootElement;

    private static HashSet<string> SnakeProperties(Type t) =>
        t.GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.GetCustomAttribute<System.Text.Json.Serialization.JsonIgnoreAttribute>() is null
                        && p.GetCustomAttribute<System.Text.Json.Serialization.JsonExtensionDataAttribute>() is null)
            .Select(p => JsonNamingPolicy.SnakeCaseLower.ConvertName(p.Name))
            .ToHashSet();

    public static TheoryData<string> SchemaNames() => new(Dtos.Keys);

    [Theory]
    [MemberData(nameof(SchemaNames))]
    public void Every_schema_property_maps_to_a_dto_property(string schema)
    {
        var props = Spec().GetProperty("components").GetProperty("schemas").GetProperty(schema).GetProperty("properties");
        var mine = SnakeProperties(Dtos[schema]);
        var missing = props.EnumerateObject().Select(p => p.Name).Where(n => !mine.Contains(n)).ToList();
        Assert.True(missing.Count == 0, $"{schema} lacks: {string.Join(", ", missing)}");
    }

    [Fact]
    public void Job_event_fields_are_covered()
    {
        var schema = Spec().GetProperty("paths").GetProperty("/v1/jobs/{job_id}/events").GetProperty("get")
            .GetProperty("responses").GetProperty("200").GetProperty("content").GetProperty("text/event-stream")
            .GetProperty("schema").GetProperty("properties");
        var mine = SnakeProperties(typeof(JobEvent));
        Assert.All(schema.EnumerateObject(), p => Assert.Contains(p.Name, mine));
    }

    [Theory]
    [InlineData("/v1/health", "get")]
    [InlineData("/v1/pair", "post")]
    [InlineData("/v1/profiles", "get")]
    [InlineData("/v1/audio", "post")]
    [InlineData("/v1/jobs", "post")]
    [InlineData("/v1/jobs/{job_id}", "get")]
    [InlineData("/v1/jobs/{job_id}", "delete")]
    [InlineData("/v1/jobs/{job_id}/events", "get")]
    [InlineData("/v1/jobs/{job_id}/composition", "get")]
    [InlineData("/v1/jobs/{job_id}/artifacts", "get")]
    [InlineData("/v1/jobs/{job_id}/artifacts/{name}", "get")]
    [InlineData("/v1/jobs/{job_id}/stages", "get")]
    [InlineData("/v1/jobs/{job_id}/stages/{stage}/files/{name}", "get")]
    [InlineData("/v1/jobs/{job_id}/musicxml", "get")]
    [InlineData("/v1/jobs/{job_id}/pdf", "get")]
    [InlineData("/v1/jobs/{job_id}/midi", "get")]
    [InlineData("/v1/jobs/{job_id}/audio", "get")]
    [InlineData("/v1/jobs", "get")]
    [InlineData("/v1/jobs/{job_id}/evidence", "get")]
    [InlineData("/v1/jobs/{job_id}/tab", "get")]
    [InlineData("/v1/jobs/{job_id}/input", "get")]
    [InlineData("/v1/runs/{job_id}", "patch")]
    [InlineData("/v1/runs/{job_id}", "delete")]
    [InlineData("/v1/devices/me", "get")]
    [InlineData("/v1/devices/me", "delete")]
    [InlineData("/v1/devices/me/rotate", "post")]
    [InlineData("/v1/pair/requests", "post")]
    [InlineData("/v1/pair/requests/{request_id}", "get")]
    public void Every_endpoint_the_client_calls_exists(string path, string method) =>
        Assert.True(Spec().GetProperty("paths").GetProperty(path).TryGetProperty(method, out _));

    private static JsonElement Schema(string name) => Spec().GetProperty("components").GetProperty("schemas").GetProperty(name);

    [Fact]
    public void Every_schema_of_the_tab_is_modelled()
    {
        var spec = Spec().GetProperty("components").GetProperty("schemas").EnumerateObject().Select(p => p.Name)
            .Where(n => n.StartsWith("Tab", StringComparison.Ordinal) || n is "TuningFit" or "ReferencePitch").ToHashSet();
        Assert.True(spec.SetEquals(TabDtos.Keys), string.Join(", ", spec.Order()));
    }

    /// <summary>
    /// Each property of a tab schema is a constructor parameter of its record: nullable where the spec allows null,
    /// and with a default exactly where the spec does not require it.
    /// </summary>
    [Fact]
    public void Tab_fields_are_nullable_and_optional_as_in_the_spec()
    {
        var nullability = new NullabilityInfoContext();
        var wrong = new List<string>();
        foreach (var (name, type) in TabDtos)
        {
            var schema = Schema(name);
            var required = schema.TryGetProperty("required", out var r) ? r.EnumerateArray().Select(e => e.GetString()!).ToHashSet() : [];
            var parameters = type.GetConstructors().Single(c => c.GetParameters().Length > 0).GetParameters()
                .ToDictionary(p => JsonNamingPolicy.SnakeCaseLower.ConvertName(p.Name!));
            foreach (var prop in schema.GetProperty("properties").EnumerateObject())
            {
                if (!parameters.TryGetValue(prop.Name, out var p)) { wrong.Add($"{name}.{prop.Name}: no parameter"); continue; }
                bool specNullable = prop.Value.TryGetProperty("anyOf", out var any) &&
                    any.EnumerateArray().Any(a => a.TryGetProperty("type", out var t) && t.GetString() == "null");
                bool mine = Nullable.GetUnderlyingType(p.ParameterType) is not null || nullability.Create(p).ReadState == NullabilityState.Nullable;
                if (mine != specNullable) wrong.Add($"{name}.{prop.Name}: nullable in the spec is {specNullable}");
                if (p.HasDefaultValue == required.Contains(prop.Name)) wrong.Add($"{name}.{prop.Name}: required in the spec is {required.Contains(prop.Name)}");
            }
        }
        Assert.True(wrong.Count == 0, string.Join("; ", wrong));
    }

    private static HashSet<string> SpecEnum(string schema, string prop)
    {
        var p = Schema(schema).GetProperty("properties").GetProperty(prop);
        if (p.TryGetProperty("enum", out var direct)) return direct.EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        return p.GetProperty("anyOf").EnumerateArray().SelectMany(alt =>
            alt.TryGetProperty("enum", out var e) ? e.EnumerateArray().Select(v => v.GetString()!)
            : alt.TryGetProperty("const", out var c) ? [c.GetString()!] : []).ToHashSet();
    }

    private static void AssertEnum<TEnum>(string schema, string prop) where TEnum : struct, Enum
    {
        var spec = SpecEnum(schema, prop);
        var mine = WireEnum<TEnum>.Values.Select(v => WireEnum<TEnum>.IdOf(v)!).ToHashSet();
        Assert.True(spec.SetEquals(mine), $"{schema}.{prop}: the spec has {string.Join(", ", spec)}");
    }

    [Fact]
    public void Tab_enums_match_the_spec()
    {
        AssertEnum<FrettedInstrument>("JobCreate", "instrument");
        AssertEnum<FingeringStyle>("JobCreate", "style");
        AssertEnum<Recording>("JobCreate", "recording");
        AssertEnum<Octave>("JobCreate", "octave");
        AssertEnum<TabLayout>("JobCreate", "layout");
        AssertEnum<TabChords>("JobCreate", "chords");
        AssertEnum<NotationClef>("TabInstrument", "notation");
        AssertEnum<FingeringStyle>("Tab", "style");
        AssertEnum<TabLayout>("Tab", "layout");
        AssertEnum<OctaveSource>("Tab", "octave_source");
        AssertEnum<KeyMode>("TabKey", "mode");
        // The stand-in for a value this client does not know has no id: it is not a value of the API.
        Assert.Null(WireEnum<FrettedInstrument>.IdOf(FrettedInstrument.Unknown));
        Assert.Throws<ArgumentException>(() => WireEnum<Octave>.Wire(Octave.Unknown));
    }

    /// <summary>
    /// The spec names the tunings in the option's description only: "bass-4: standard, eb-standard, ...; bass-5: ...;
    /// ukulele-baritone, mandolin: standard" (instruments that share their tunings are named together).
    /// </summary>
    [Fact]
    public void The_tunings_of_each_instrument_match_the_spec()
    {
        var properties = Schema("JobCreate").GetProperty("properties");
        var described = properties.GetProperty("tuning").GetProperty("description").GetString()!;
        Assert.Contains("its first when left out", described);
        var spec = new Dictionary<string, List<string>>();
        foreach (var clause in described[(described.IndexOf("left out. ", StringComparison.Ordinal) + "left out. ".Length)..].Split("; "))
        {
            var parts = clause.Split(": ");
            Assert.True(parts.Length == 2, clause);
            foreach (var n in parts[0].Split(", ")) spec[n] = [.. parts[1].Split(", ")];
        }
        var kinds = WireEnum<FrettedInstrument>.Values;
        Assert.True(spec.Keys.ToHashSet().SetEquals(kinds.Select(k => k.Id()!)));
        foreach (var kind in kinds) Assert.Equal(spec[kind.Id()!], kind.Tunings());
        foreach (var kind in kinds) Assert.Equal(kind.Tunings()[0], kind.DefaultTuning());
        // What a job that names no recording is taken as: "default: song (instrument for a ukulele or a mandolin)".
        var recording = properties.GetProperty("recording").GetProperty("description").GetString()!;
        Assert.EndsWith("default: song (instrument for a ukulele or a mandolin)", recording);
        Assert.Equal(["ukulele", "ukulele-baritone", "mandolin"], kinds.Where(k => k.AloneByDefault()).Select(k => k.Id()));
        foreach (var kind in kinds) Assert.Equal(kind.AloneByDefault() ? Recording.Instrument : Recording.Song, kind.DefaultRecording());
        // The profile's own default instrument, and the one of its id for older apps.
        var instrument = properties.GetProperty("instrument").GetProperty("description").GetString()!;
        Assert.Contains("Default: guitar-6. The bass-tab profile takes the basses only; default: bass-4", instrument);
        Assert.Equal(["bass-4", "bass-5", "bass-6"], kinds.Where(k => k.IsBass()).Select(k => k.Id()));
        var capo = properties.GetProperty("capo").GetProperty("anyOf")[0];
        Assert.Equal(TabOptions.MaxCapo, capo.GetProperty("maximum").GetDouble());
    }

    [Fact]
    public void A_tab_job_sends_each_option_by_its_id_and_nothing_it_leaves_out()
    {
        var all = new TabOptions(FrettedInstrument.Guitar7, "eb-standard", 2, FingeringStyle.Lead, Recording.Song, Octave.Up, TabLayout.Notation, TabChords.Completed);
        var body = JsonDocument.Parse(JsonSerializer.Serialize(TabJobs.Tab("a", all), EngineJsonContext.Default.JobCreate)).RootElement;
        Assert.Equal("tab", body.GetProperty("profile").GetString());
        Assert.Equal(("guitar-7", "eb-standard", 2, "lead", "song", "+12", "notation", "completed"), (body.GetProperty("instrument").GetString(),
            body.GetProperty("tuning").GetString(), body.GetProperty("capo").GetInt32(), body.GetProperty("style").GetString(), body.GetProperty("recording").GetString(),
            body.GetProperty("octave").GetString(), body.GetProperty("layout").GetString(), body.GetProperty("chords").GetString()));
        var none = JsonDocument.Parse(JsonSerializer.Serialize(TabJobs.Tab("a"), EngineJsonContext.Default.JobCreate)).RootElement;
        foreach (var name in new[] { "instrument", "tuning", "capo", "style", "recording", "octave", "layout", "chords" })
            Assert.False(none.TryGetProperty(name, out _), name);
        Assert.Throws<ArgumentException>(() => TabJobs.Tab("a", new TabOptions(FrettedInstrument.Unknown)));
    }

    [Fact]
    public void A_tab_from_a_newer_engine_reads_with_its_unknown_values_as_unknown()
    {
        var path = TestPaths.RepoFile("apps/fixtures/bass-line/tab.json")!;
        var json = File.ReadAllText(path);
        var tab = TabResult.Parse(json)!;
        Assert.Equal(FingeringStyle.AsPlayed, tab.Style);
        Assert.Equal(FrettedInstruments.OfPreset(tab.Preset), (FrettedInstrument.Bass4, "standard"));
        var node = System.Text.Json.Nodes.JsonNode.Parse(json)!;
        node["style"] = "thumb-slap";
        node["layout"] = "chord-boxes";
        node["octave_source"] = "asked";
        node["key"]!["mode"] = "dorian";
        node["instrument"]!["notation"] = "alto";
        var newer = TabResult.Parse(node.ToJsonString())!;
        Assert.Equal((FingeringStyle.Unknown, TabLayout.Unknown, OctaveSource.Unknown, KeyMode.Unknown, (NotationClef?)NotationClef.Unknown),
            (newer.Style, newer.Layout, newer.OctaveSource, newer.Key.Mode, newer.Instrument.Notation));
        Assert.Equal(tab.Notes.Count, newer.Notes.Count);
        // A clef left out or null is not known; one this client knows reads as itself.
        node["instrument"]!["notation"] = null;
        Assert.Null(TabResult.Parse(node.ToJsonString())!.Instrument.Notation);
        node["instrument"]!.AsObject().Remove("notation");
        Assert.Null(TabResult.Parse(node.ToJsonString())!.Instrument.Notation);
        node["instrument"]!["notation"] = "bass-8vb";
        Assert.Equal(NotationClef.Bass8vb, TabResult.Parse(node.ToJsonString())!.Instrument.Notation);
        // Read back as it was written.
        Assert.Equal(tab.Notes.Select(n => (n.Pitch, n.String, n.Fret)), TabResult.Parse(TabResult.Serialize(tab))!.Notes.Select(n => (n.Pitch, n.String, n.Fret)));
        Assert.Null(TabResult.Parse("not json"));
    }
}

using System.Reflection;
using System.Text.Json;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Checks the hand-written DTOs against a snapshot of engine/openapi.json, so a change in the
/// engine contract shows up as a failing test here. Refresh Fixtures/openapi.json when the engine changes
/// (copy engine/openapi.json; an engine test fails while it differs).
/// </summary>
public class OpenApiContractTests
{
    private static readonly Dictionary<string, Type> Dtos = new()
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
    };

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
    [InlineData("/v1/runs/{job_id}", "patch")]
    [InlineData("/v1/runs/{job_id}", "delete")]
    [InlineData("/v1/devices/me", "get")]
    [InlineData("/v1/devices/me", "delete")]
    [InlineData("/v1/devices/me/rotate", "post")]
    [InlineData("/v1/pair/requests", "post")]
    [InlineData("/v1/pair/requests/{request_id}", "get")]
    public void Every_endpoint_the_client_calls_exists(string path, string method) =>
        Assert.True(Spec().GetProperty("paths").GetProperty(path).TryGetProperty(method, out _));
}

using System.Text.Json;
using System.Text.Json.Serialization;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Engine;

// DTOs for the companion engine API (engine/openapi.json, "brasscribe engine" 0.1.0).
// Property names map to snake_case through EngineJsonContext.

public sealed record Health(string Version, string Device, bool AuthRequired, string Status = "ok");

public sealed record AudioRef(string AudioId, string Sha256, string Filename, long Bytes);

/// <summary>Exactly one of AudioId (an upload), SourceId (a listed source) or Path (a file in the engine's data directory).</summary>
public sealed record JobCreate(
    string? AudioId,
    string Profile = "orchestra-with-soloist",
    bool RenderAudio = true,
    bool AllowHeavy = true,
    string? Title = null,
    string? SourceId = null,
    string? Path = null,
    string Lineup = "full",
    string Difficulty = "faithful",
    string? Key = null,
    int? Transpose = null);

/// <summary>Arrangement choices a job can carry: lineup full|minimal, difficulty faithful|standard|easier, a target key or a transposition.</summary>
public sealed record ArrangementOptions(string Lineup = "full", string Difficulty = "faithful", string? Key = null, int? Transpose = null)
{
    public static readonly ArrangementOptions Default = new();
}

public sealed record StageState(string Name, string Status, string? Device = null, string? Kind = null, double? Seconds = null);

public sealed record Job(
    string Id,
    string Profile,
    string Status,
    double Created,
    IReadOnlyList<StageState> Stages,
    string? AudioId = null,
    string? Title = null,
    string? Error = null,
    double? Started = null,
    double? Finished = null,
    double Progress = 0.0,
    IReadOnlyList<string>? Outputs = null,
    string? PreviousRunId = null)
{
    [JsonIgnore]
    public bool IsTerminal => Status is JobStatus.Succeeded or JobStatus.Failed or JobStatus.Cancelled;
}

public static class JobStatus
{
    public const string Queued = "queued";
    public const string Running = "running";
    public const string Succeeded = "succeeded";
    public const string Failed = "failed";
    public const string Cancelled = "cancelled";
    public const string Unknown = "unknown";
}

public sealed record Artifact(string Name, long Bytes, string MediaType, string Url);

public sealed record ProfileInfo(string Name, string Pipeline, string Description, bool Validated, IReadOnlyList<string> Stages);

public sealed record PairRequest(string Code, string? DeviceName = null);

public sealed record PairResponse(string Token);

/// <summary>One Server-Sent Event payload (the data: line). type is job, stage or log.</summary>
public sealed record JobEvent(
    int Id,
    string Run,
    string Type,
    double Time,
    string? Stage = null,
    string? Status = null,
    string? Kind = null,
    string? Device = null,
    double? Seconds = null,
    double? Fraction = null,
    string? Message = null,
    string? Error = null);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(Health))]
[JsonSerializable(typeof(AudioRef))]
[JsonSerializable(typeof(JobCreate))]
[JsonSerializable(typeof(Job))]
[JsonSerializable(typeof(List<Job>))]
[JsonSerializable(typeof(List<Artifact>))]
[JsonSerializable(typeof(List<ProfileInfo>))]
[JsonSerializable(typeof(PairRequest))]
[JsonSerializable(typeof(PairResponse))]
[JsonSerializable(typeof(JobEvent))]
[JsonSerializable(typeof(Composition))]
internal sealed partial class EngineJsonContext : JsonSerializerContext;

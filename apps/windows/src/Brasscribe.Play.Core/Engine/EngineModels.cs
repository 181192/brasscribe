using System.Text.Json;
using System.Text.Json.Serialization;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Engine;

// DTOs for the companion engine API (engine/openapi.json, "brasscribe engine" 0.1.0).
// Property names map to snake_case through EngineJsonContext.

public sealed record Health(string Version, string Device, bool AuthRequired, string Status = "ok",
    string? ServerId = null, string? ServerName = null);

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
    int? Transpose = null,
    bool Muscriptor = true,
    string? Seat = null,
    string? Reads = null,
    string? Lead = null);

/// <summary>Arrangement choices a job can carry: lineup full|minimal|quartet, difficulty faithful|standard|easier, a target key or a transposition.</summary>
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
    string? PreviousRunId = null,
    string? DeviceName = null)
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

/// <summary>One output file of a stage.</summary>
public sealed record FileRef(string Name, long Bytes, string MediaType, string Url, string? Sha256 = null);

/// <summary>A stage of a run with its output files (stems, layers, MIDI, beats, Composition, MusicXML …).</summary>
public sealed record StageArtifacts(string Stage, string Status, IReadOnlyList<FileRef> Files, string? Kind = null,
    string? Key = null, string? Device = null, double? Seconds = null);

public sealed record ProfileInfo(string Name, string Pipeline, string Description, bool Validated, IReadOnlyList<string> Stages);

public sealed record PairRequest(string Code, string? DeviceName = null, string? Platform = null);

public sealed record PairResponse(string Token, string? DeviceId = null, string? ServerId = null, string? ServerName = null);

public sealed record ModelInfo(string Model, string Name);

/// <summary>What one transcriber heard at a note: its concert pitch (null: no note there) and whether it agrees.</summary>
public sealed record ModelHeard(string Model, string Name, bool Agrees, int? Pitch = null);

/// <summary>An uncertain note: its confidence and what each transcriber heard at its onset.</summary>
public sealed record NoteEvidence(string Voice, int Start, int Pitch, double Confidence, IReadOnlyList<ModelHeard> Models, double? OnsetS = null)
{
    /// <summary>The pitch the disagreeing transcribers heard most often, as a shift from the written note.</summary>
    [JsonIgnore]
    public int? AlternativeShift => Models.Where(m => !m.Agrees && m.Pitch is not null)
        .GroupBy(m => m.Pitch!.Value)
        .OrderByDescending(g => g.Count()).ThenBy(g => Math.Abs(g.Key - Pitch))
        .Select(g => (int?)(g.Key - Pitch)).FirstOrDefault();
}

/// <summary>GET /v1/jobs/{id}/evidence: what each transcriber heard at the notes Brasscribe is unsure about.</summary>
public sealed record Evidence(IReadOnlyList<ModelInfo> Models, IReadOnlyList<NoteEvidence> Notes)
{
    public static readonly Evidence Empty = new([], []);

    /// <summary>The evidence for the note at <paramref name="start"/> in <paramref name="voice"/> with this pitch class.</summary>
    public NoteEvidence? NoteAt(string voice, int start, int pitch) =>
        Notes.FirstOrDefault(n => n.Voice == voice && n.Start == start && ((n.Pitch - pitch) % 12 + 12) % 12 == 0);

    public static string Serialize(Evidence e) => JsonSerializer.Serialize(e, EngineJsonContext.Default.Evidence);

    public static Evidence? Parse(string json)
    {
        try { return JsonSerializer.Deserialize(json, EngineJsonContext.Default.Evidence); }
        catch (JsonException) { return null; }
    }
}

public sealed record RunUpdate(string Title);

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
[JsonSerializable(typeof(List<StageArtifacts>))]
[JsonSerializable(typeof(PairRequest))]
[JsonSerializable(typeof(PairResponse))]
[JsonSerializable(typeof(JobEvent))]
[JsonSerializable(typeof(Composition))]
[JsonSerializable(typeof(Evidence))]
[JsonSerializable(typeof(RunUpdate))]
internal sealed partial class EngineJsonContext : JsonSerializerContext;

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Brasscribe.Bandroom.Core.Engine;

/// <summary>GET /v1/status: what the computer shows at a glance (owner endpoint).</summary>
public sealed record StatusInfo(
    string ServerId,
    string ServerName,
    string Version,
    int OnlineDevices,
    int PairedDevices,
    bool PairingOpen,
    int JobsRunning,
    int JobsQueued);

/// <summary>GET /v1/health.</summary>
public sealed record HealthInfo(string Status, string Version, string Device, bool AuthRequired, string? ServerId, string? ServerName);

/// <summary>GET /v1/devices row. <see cref="Online"/> is null on engines that don't report presence yet.</summary>
public sealed record DeviceInfo(
    string DeviceId,
    string Name,
    string Platform,
    string PairedAt,
    string LastSeen,
    string? RotatedAt = null,
    bool? Online = null)
{
    public DateTimeOffset? LastSeenAt => DateTimeOffset.TryParse(LastSeen, out var t) ? t : null;
}

/// <summary>POST /v1/pairing body. <see cref="TtlS"/> null means "open until closed" and must be sent as null.</summary>
public sealed record PairingOpenRequest(double? TtlS, bool SingleUse = true, bool Extend = false);

/// <summary>GET/POST/DELETE /v1/pairing.</summary>
public sealed record PairingState(
    bool Open,
    string? Code,
    string? ExpiresAt,
    bool SingleUse,
    string ServerId,
    string ServerName,
    IReadOnlyList<string> Hosts,
    string? Fingerprint,
    string Uri);

/// <summary>A phone asking to be allowed (approve on the computer).</summary>
public sealed record PairRequestInfo(string RequestId, string Name, string Platform, string MatchCode, string CreatedAt, string Status)
{
    public DateTimeOffset? CreatedAtTime => DateTimeOffset.TryParse(CreatedAt, out var t) ? t : null;
}

public sealed record StageInfo(string Name, string Status);

/// <summary>GET /v1/jobs row (only the fields Bandroom shows).</summary>
public sealed record JobInfo(
    string Id,
    string Profile,
    string? Title,
    string Status,
    double Created,
    double? Started,
    double? Finished,
    double Progress,
    IReadOnlyList<StageInfo>? Stages);

/// <summary>The engine's JSON conventions: snake_case names; nulls are written (ttl_s: null matters).</summary>
public static class EngineJson
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };
}

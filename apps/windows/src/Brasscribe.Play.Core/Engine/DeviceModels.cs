using System.Text.Json.Serialization;

namespace Brasscribe.Play.Core.Engine;

// DTOs for this device's pairing with the engine (engine/openapi.json, tag "devices" and "pairing").

/// <summary>GET /v1/devices/me: this device as the engine knows it. Times are ISO 8601, UTC.</summary>
public sealed record DeviceSelf(
    string DeviceId,
    string Name,
    string Platform,
    string PairedAt,
    string LastSeen,
    string ServerId,
    string RotateAfter,
    string ExpiresIfIdleAfter,
    string? RotatedAt = null,
    bool? Online = null);

/// <summary>POST /v1/devices/me/rotate: the new token; the old one works until the new one is first used.</summary>
public sealed record RotateResponse(string Token, string DeviceId);

/// <summary>POST /v1/pair/requests: ask the owner to allow this device on the computer.</summary>
public sealed record PairRequestCreate(string? DeviceName = null, string? Platform = null);

/// <summary>The waiting request, with the match code both screens show.</summary>
public sealed record PairRequestInfo(string RequestId, string Name, string Platform, string MatchCode, string CreatedAt, string Status);

/// <summary>GET /v1/pair/requests/{id}: pending, denied, or approved with the token (handed out once).</summary>
public sealed record PairRequestResult(
    string Status,
    string? Token = null,
    string? DeviceId = null,
    string? ServerId = null,
    string? ServerName = null);

public static class PairRequestStatus
{
    public const string Pending = "pending";
    public const string Approved = "approved";
    public const string Denied = "denied";
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(DeviceSelf))]
[JsonSerializable(typeof(RotateResponse))]
[JsonSerializable(typeof(PairRequestCreate))]
[JsonSerializable(typeof(PairRequestInfo))]
[JsonSerializable(typeof(PairRequestResult))]
[JsonSerializable(typeof(PairRequest))]
[JsonSerializable(typeof(PairResponse))]
internal sealed partial class DeviceJsonContext : JsonSerializerContext;

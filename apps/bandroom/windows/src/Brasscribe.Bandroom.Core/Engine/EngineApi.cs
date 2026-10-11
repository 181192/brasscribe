using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;

namespace Brasscribe.Bandroom.Core.Engine;

/// <summary>The engine endpoints Bandroom uses. All owner calls carry the admin bearer.</summary>
public interface IEngineApi
{
    Task<HealthInfo> GetHealthAsync(CancellationToken ct = default);
    Task<StatusInfo> GetStatusAsync(CancellationToken ct = default);
    Task<IReadOnlyList<DeviceInfo>> GetDevicesAsync(CancellationToken ct = default);
    Task RemoveDeviceAsync(string deviceId, CancellationToken ct = default);
    Task<PairingState> GetPairingAsync(CancellationToken ct = default);
    Task<PairingState> OpenPairingAsync(PairingOpenRequest request, CancellationToken ct = default);
    Task<PairingState> ClosePairingAsync(CancellationToken ct = default);
    Task<IReadOnlyList<PairRequestInfo>> GetPairRequestsAsync(CancellationToken ct = default);
    Task<PairRequestInfo> DecidePairRequestAsync(string requestId, bool approve, CancellationToken ct = default);
    Task<IReadOnlyList<JobInfo>> GetJobsAsync(CancellationToken ct = default);
}

/// <summary>HTTP client for the engine on loopback.</summary>
public sealed class EngineApi : IEngineApi
{
    private readonly HttpClient _http;
    private bool _statusMissing;

    /// <param name="http">A client whose lifetime the caller owns.</param>
    /// <param name="baseUri">http://127.0.0.1:&lt;port&gt;/</param>
    /// <param name="adminToken">Sent as the bearer on every call; owner endpoints require it once the engine knows it.</param>
    public EngineApi(HttpClient http, Uri baseUri, string? adminToken)
    {
        _http = http;
        BaseUri = baseUri;
        AdminToken = adminToken;
    }

    public Uri BaseUri { get; }
    public string? AdminToken { get; }

    private HttpRequestMessage Request(HttpMethod method, string path, object? body = null)
    {
        var req = new HttpRequestMessage(method, new Uri(BaseUri, path));
        if (!string.IsNullOrEmpty(AdminToken)) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", AdminToken);
        if (body is not null) req.Content = JsonContent.Create(body, body.GetType(), options: EngineJson.Options);
        return req;
    }

    private async Task<T> SendAsync<T>(HttpMethod method, string path, object? body, CancellationToken ct)
    {
        using var req = Request(method, path, body);
        using var res = await _http.SendAsync(req, ct).ConfigureAwait(false);
        await EnsureAsync(res, ct).ConfigureAwait(false);
        return (await res.Content.ReadFromJsonAsync<T>(EngineJson.Options, ct).ConfigureAwait(false))!;
    }

    private static async Task EnsureAsync(HttpResponseMessage res, CancellationToken ct)
    {
        if (res.IsSuccessStatusCode) return;
        string detail = "";
        try { detail = await res.Content.ReadAsStringAsync(ct).ConfigureAwait(false); }
        catch (HttpRequestException) { }
        throw new EngineHttpException(res.StatusCode, detail);
    }

    /// <summary>
    /// GET /v1/health. The interface version is read by itself first: one that is not a whole number is "none"
    /// (the engine is the one to update), and from an engine with another version the rest of the answer is read only
    /// as far as it can be, so that such an engine still counts as running and is named for what it is.
    /// </summary>
    public async Task<HealthInfo> GetHealthAsync(CancellationToken ct = default)
    {
        using var req = Request(HttpMethod.Get, "v1/health");
        using var res = await _http.SendAsync(req, ct).ConfigureAwait(false);
        await EnsureAsync(res, ct).ConfigureAwait(false);
        string body = await res.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        using var doc = System.Text.Json.JsonDocument.Parse(body);
        var root = doc.RootElement;
        if (root.ValueKind != System.Text.Json.JsonValueKind.Object) throw new System.Text.Json.JsonException("health is not an object");
        int? version = InterfaceMatch.Read(root);
        if (InterfaceMatch.Of(version) == InterfaceAnswer.Same)
            return System.Text.Json.JsonSerializer.Deserialize<HealthInfo>(body, EngineJson.Options)!;
        string? Text(string name) => root.TryGetProperty(name, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.String ? v.GetString() : null;
        return new HealthInfo(Text("status") ?? "ok", Text("version") ?? "–", Text("device") ?? "", false, Text("server_id"), Text("server_name"),
            Text("build"), version);
    }

    /// <summary>GET /v1/status; an engine without it (404) gets the same numbers from health, devices and jobs.</summary>
    public async Task<StatusInfo> GetStatusAsync(CancellationToken ct = default)
    {
        if (!_statusMissing)
        {
            try { return await SendAsync<StatusInfo>(HttpMethod.Get, "v1/status", null, ct).ConfigureAwait(false); }
            catch (EngineHttpException e) when (e.StatusCode == HttpStatusCode.NotFound) { _statusMissing = true; }
        }
        var health = await GetHealthAsync(ct).ConfigureAwait(false);
        var devices = await GetDevicesAsync(ct).ConfigureAwait(false);
        var jobs = await GetJobsAsync(ct).ConfigureAwait(false);
        return new StatusInfo(health.ServerId ?? "", health.ServerName ?? "", health.Version,
            devices.Count(d => d.Online == true), devices.Count, false,
            jobs.Count(j => j.Status == "running"), jobs.Count(j => j.Status == "queued"));
    }

    public async Task<IReadOnlyList<DeviceInfo>> GetDevicesAsync(CancellationToken ct = default) =>
        await SendAsync<List<DeviceInfo>>(HttpMethod.Get, "v1/devices", null, ct).ConfigureAwait(false);

    public async Task RemoveDeviceAsync(string deviceId, CancellationToken ct = default)
    {
        using var req = Request(HttpMethod.Delete, "v1/devices/" + Uri.EscapeDataString(deviceId));
        using var res = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (res.StatusCode == HttpStatusCode.NotFound) return; // already gone
        await EnsureAsync(res, ct).ConfigureAwait(false);
    }

    public Task<PairingState> GetPairingAsync(CancellationToken ct = default) => SendAsync<PairingState>(HttpMethod.Get, "v1/pairing", null, ct);

    public Task<PairingState> OpenPairingAsync(PairingOpenRequest request, CancellationToken ct = default) =>
        SendAsync<PairingState>(HttpMethod.Post, "v1/pairing", request, ct);

    public Task<PairingState> ClosePairingAsync(CancellationToken ct = default) => SendAsync<PairingState>(HttpMethod.Delete, "v1/pairing", null, ct);

    public async Task<IReadOnlyList<PairRequestInfo>> GetPairRequestsAsync(CancellationToken ct = default) =>
        await SendAsync<List<PairRequestInfo>>(HttpMethod.Get, "v1/pairing/requests", null, ct).ConfigureAwait(false);

    public Task<PairRequestInfo> DecidePairRequestAsync(string requestId, bool approve, CancellationToken ct = default) =>
        SendAsync<PairRequestInfo>(HttpMethod.Post, $"v1/pairing/requests/{Uri.EscapeDataString(requestId)}/{(approve ? "approve" : "deny")}", null, ct);

    public async Task<IReadOnlyList<JobInfo>> GetJobsAsync(CancellationToken ct = default) =>
        await SendAsync<List<JobInfo>>(HttpMethod.Get, "v1/jobs", null, ct).ConfigureAwait(false);
}

public sealed class EngineHttpException(HttpStatusCode status, string detail)
    : Exception($"engine answered {(int)status}: {detail}")
{
    public HttpStatusCode StatusCode { get; } = status;
    public string Detail { get; } = detail;
}

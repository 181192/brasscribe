using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Engine;

public sealed class EngineException(string message, HttpStatusCode? status = null, Exception? inner = null, string? code = null)
    : Exception(message, inner)
{
    /// <summary>The job ran and failed (its own error is English and stays in the log).</summary>
    public const string JobFailed = "job_failed";

    /// <summary>The request got no answer in time (not the player's Cancel).</summary>
    public const string Timeout = "timeout";

    public HttpStatusCode? Status { get; } = status;

    /// <summary>
    /// What went wrong, as a machine code: the engine's <c>code</c> on a refused job
    /// (quartet_needs_group, percussion_solo, seat_no_tune, reads_not_offered, invalid_options),
    /// or <see cref="JobFailed"/> / <see cref="Timeout"/>; null when there is none.
    /// </summary>
    public string? Code { get; } = code;

    /// <summary>The <c>code</c> of an engine error body (<c>{"detail": ..., "code": ...}</c>), when it has one.</summary>
    public static string? CodeOf(string body)
    {
        try
        {
            using var doc = System.Text.Json.JsonDocument.Parse(body);
            return doc.RootElement.ValueKind == System.Text.Json.JsonValueKind.Object
                   && doc.RootElement.TryGetProperty("code", out var c) && c.ValueKind == System.Text.Json.JsonValueKind.String
                ? c.GetString()
                : null;
        }
        catch (System.Text.Json.JsonException)
        {
            return null;
        }
    }
}

/// <summary>Score downloads the engine serves per job.</summary>
public enum JobDownload { MusicXml, Pdf, Midi, Audio }

public interface IEngineClient
{
    Uri BaseAddress { get; }
    string? Token { get; set; }
    Task<Health> GetHealthAsync(CancellationToken ct = default);
    Task<string> PairAsync(string code, string? deviceName, CancellationToken ct = default);
    Task<IReadOnlyList<ProfileInfo>> ListProfilesAsync(CancellationToken ct = default);
    Task<AudioRef> UploadAudioAsync(Stream audio, string filename, CancellationToken ct = default);
    Task<Job> CreateJobAsync(JobCreate request, CancellationToken ct = default);
    Task<Job> GetJobAsync(string jobId, CancellationToken ct = default);
    Task<Job> CancelJobAsync(string jobId, CancellationToken ct = default);
    IAsyncEnumerable<JobEvent> StreamEventsAsync(string jobId, int after = -1, CancellationToken ct = default);
    Task<Composition> GetCompositionAsync(string jobId, CancellationToken ct = default);
    Task<IReadOnlyList<Artifact>> ListArtifactsAsync(string jobId, CancellationToken ct = default);
    Task<Stream> DownloadAsync(string jobId, JobDownload what, CancellationToken ct = default);
    Task<Stream> GetArtifactAsync(string jobId, string name, CancellationToken ct = default);

    /// <summary>Every stage of a run with its output files.</summary>
    Task<IReadOnlyList<StageArtifacts>> ListStagesAsync(string jobId, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot list stages.");

    Task<Stream> GetStageFileAsync(string jobId, string stage, string name, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot read stage files.");
    /// <summary>Braille music (BRF) of the score, or of one part (1-based number or name).</summary>
    Task<Stream> DownloadBrailleAsync(string jobId, string? part = null, CancellationToken ct = default);

    /// <summary>The engine's runs, newest first as the engine keeps them.</summary>
    Task<IReadOnlyList<Job>> ListJobsAsync(CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot list runs.");

    /// <summary>Confidence and what each transcriber heard at the uncertain notes.</summary>
    Task<Evidence> GetEvidenceAsync(string jobId, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot read evidence.");

    /// <summary>Retitles a run: its manifest, Composition and MusicXML.</summary>
    Task<Job> RenameRunAsync(string jobId, string title, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot rename runs.");

    Task DeleteRunAsync(string jobId, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot delete runs.");

    /// <summary>Pairs with a code and returns the whole answer (token, device id, server id and name).</summary>
    Task<PairResponse> PairDeviceAsync(string code, string? deviceName, string? platform, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot pair.");

    /// <summary>This device as the engine knows it; 401 once the engine has forgotten it, 404 on loopback.</summary>
    Task<DeviceSelf> GetThisDeviceAsync(CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot check the device.");

    /// <summary>A new token for this device. The caller stores it before using it.</summary>
    Task<RotateResponse> RotateTokenAsync(CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot rotate the token.");

    /// <summary>Forgets this device on the engine.</summary>
    Task UnpairAsync(CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot unpair.");

    /// <summary>Asks the owner to allow this device on the computer; 429 when too many are waiting.</summary>
    Task<PairRequestInfo> RequestPairingAsync(string? deviceName, string? platform, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot ask the computer.");

    Task<PairRequestResult> PollPairingRequestAsync(string requestId, CancellationToken ct = default) =>
        throw new NotSupportedException("This engine client cannot ask the computer.");
}

/// <summary>
/// Client for the companion engine (engine/openapi.json). Loopback clients are trusted; LAN
/// clients call <see cref="PairAsync"/> with the code the engine prints and then send the token
/// as a bearer header on every request.
/// </summary>
public sealed class EngineClient : IEngineClient
{
    public static readonly Uri DefaultBaseAddress = new("http://127.0.0.1:8765/");

    private readonly HttpClient _http;

    public EngineClient(HttpClient http, Uri? baseAddress = null)
    {
        _http = http;
        BaseAddress = baseAddress ?? http.BaseAddress ?? DefaultBaseAddress;
        if (!BaseAddress.AbsoluteUri.EndsWith('/')) BaseAddress = new Uri(BaseAddress.AbsoluteUri + "/");
    }

    public Uri BaseAddress { get; }
    public string? Token { get; set; }

    public Task<Health> GetHealthAsync(CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, "v1/health", null, EngineJsonContext.Default.Health, ct);

    public async Task<string> PairAsync(string code, string? deviceName, CancellationToken ct = default)
    {
        var content = JsonContent.Create(new PairRequest(code, deviceName), EngineJsonContext.Default.PairRequest);
        try
        {
            var r = await SendJsonAsync(HttpMethod.Post, "v1/pair", content, EngineJsonContext.Default.PairResponse, ct).ConfigureAwait(false);
            Token = r.Token;
            return r.Token;
        }
        catch (EngineException e) when (e.Status == HttpStatusCode.Forbidden)
        {
            throw new EngineException("The pairing code was not accepted.", e.Status, e);
        }
    }

    public async Task<PairResponse> PairDeviceAsync(string code, string? deviceName, string? platform, CancellationToken ct = default)
    {
        var content = JsonContent.Create(new PairRequest(code, deviceName, platform), DeviceJsonContext.Default.PairRequest);
        try
        {
            return await SendJsonAsync(HttpMethod.Post, "v1/pair", content, DeviceJsonContext.Default.PairResponse, ct).ConfigureAwait(false);
        }
        catch (EngineException e) when (e.Status == HttpStatusCode.Forbidden)
        {
            throw new EngineException("The pairing code was not accepted.", e.Status, e);
        }
    }

    public Task<DeviceSelf> GetThisDeviceAsync(CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, "v1/devices/me", null, DeviceJsonContext.Default.DeviceSelf, ct);

    public Task<RotateResponse> RotateTokenAsync(CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Post, "v1/devices/me/rotate", null, DeviceJsonContext.Default.RotateResponse, ct);

    public Task UnpairAsync(CancellationToken ct = default) => SendNoContentAsync(HttpMethod.Delete, "v1/devices/me", ct);

    public Task<PairRequestInfo> RequestPairingAsync(string? deviceName, string? platform, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Post, "v1/pair/requests",
            JsonContent.Create(new PairRequestCreate(deviceName, platform), DeviceJsonContext.Default.PairRequestCreate),
            DeviceJsonContext.Default.PairRequestInfo, ct);

    public Task<PairRequestResult> PollPairingRequestAsync(string requestId, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, $"v1/pair/requests/{Uri.EscapeDataString(requestId)}", null, DeviceJsonContext.Default.PairRequestResult, ct);

    public async Task<IReadOnlyList<ProfileInfo>> ListProfilesAsync(CancellationToken ct = default) =>
        await SendJsonAsync(HttpMethod.Get, "v1/profiles", null, EngineJsonContext.Default.ListProfileInfo, ct).ConfigureAwait(false);

    public Task<AudioRef> UploadAudioAsync(Stream audio, string filename, CancellationToken ct = default)
    {
        // The name goes as UTF-8 in a quoted filename, as browsers send it (RFC 7578 §4.2). .NET would
        // otherwise encode a name like "Kjærlighet.wav" as "=?utf-8?B?…?=", which the engine takes
        // literally, and the run's title and the file's extension come from it.
        var form = new MultipartFormDataContent { HeaderEncodingSelector = (_, _) => System.Text.Encoding.UTF8 };
        var file = new StreamContent(audio);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        file.Headers.TryAddWithoutValidation("Content-Disposition", $"form-data; name=\"file\"; filename=\"{QuotedFileName(filename)}\"");
        form.Add(file);
        return SendJsonAsync(HttpMethod.Post, "v1/audio", form, EngineJsonContext.Default.AudioRef, ct);
    }

    /// <summary>A file name that is safe inside a quoted header parameter: no line breaks, quotes or backslashes.</summary>
    internal static string QuotedFileName(string name)
    {
        var b = new System.Text.StringBuilder(name.Length);
        foreach (char c in name) b.Append(c is '"' or '\\' || char.IsControl(c) ? '_' : c);
        return b.Length == 0 ? "audio.wav" : b.ToString();
    }

    public Task<Job> CreateJobAsync(JobCreate request, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Post, "v1/jobs", JsonContent.Create(request, EngineJsonContext.Default.JobCreate),
            EngineJsonContext.Default.Job, ct);

    public Task<Job> GetJobAsync(string jobId, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, $"v1/jobs/{Uri.EscapeDataString(jobId)}", null, EngineJsonContext.Default.Job, ct);

    public Task<Job> CancelJobAsync(string jobId, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Delete, $"v1/jobs/{Uri.EscapeDataString(jobId)}", null, EngineJsonContext.Default.Job, ct);

    public Task<Composition> GetCompositionAsync(string jobId, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, $"v1/jobs/{Uri.EscapeDataString(jobId)}/composition", null, EngineJsonContext.Default.Composition, ct);

    public async Task<IReadOnlyList<Artifact>> ListArtifactsAsync(string jobId, CancellationToken ct = default) =>
        await SendJsonAsync(HttpMethod.Get, $"v1/jobs/{Uri.EscapeDataString(jobId)}/artifacts", null, EngineJsonContext.Default.ListArtifact, ct).ConfigureAwait(false);

    public Task<Stream> DownloadAsync(string jobId, JobDownload what, CancellationToken ct = default)
    {
        string leaf = what switch
        {
            JobDownload.MusicXml => "musicxml",
            JobDownload.Pdf => "pdf",
            JobDownload.Midi => "midi",
            JobDownload.Audio => "audio",
            _ => throw new ArgumentOutOfRangeException(nameof(what)),
        };
        return SendStreamAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/{leaf}", ct);
    }

    public Task<Stream> DownloadBrailleAsync(string jobId, string? part = null, CancellationToken ct = default) =>
        SendStreamAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/braille" + (part is null ? "" : $"?part={Uri.EscapeDataString(part)}"), ct);

    public Task<Stream> GetArtifactAsync(string jobId, string name, CancellationToken ct = default) =>
        SendStreamAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/artifacts/{Uri.EscapeDataString(name)}", ct);

    public async Task<IReadOnlyList<StageArtifacts>> ListStagesAsync(string jobId, CancellationToken ct = default) =>
        await SendJsonAsync(HttpMethod.Get, $"v1/jobs/{Uri.EscapeDataString(jobId)}/stages", null, EngineJsonContext.Default.ListStageArtifacts, ct).ConfigureAwait(false);

    public Task<Stream> GetStageFileAsync(string jobId, string stage, string name, CancellationToken ct = default) =>
        SendStreamAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/stages/{Uri.EscapeDataString(stage)}/files/{Uri.EscapeDataString(name)}", ct);

    public async Task<IReadOnlyList<Job>> ListJobsAsync(CancellationToken ct = default) =>
        await SendJsonAsync(HttpMethod.Get, "v1/jobs", null, EngineJsonContext.Default.ListJob, ct).ConfigureAwait(false);

    public Task<Evidence> GetEvidenceAsync(string jobId, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Get, $"v1/jobs/{Uri.EscapeDataString(jobId)}/evidence", null, EngineJsonContext.Default.Evidence, ct);

    public Task<Job> RenameRunAsync(string jobId, string title, CancellationToken ct = default) =>
        SendJsonAsync(HttpMethod.Patch, $"v1/runs/{Uri.EscapeDataString(jobId)}",
            JsonContent.Create(new RunUpdate(title), EngineJsonContext.Default.RunUpdate), EngineJsonContext.Default.Job, ct);

    public Task DeleteRunAsync(string jobId, CancellationToken ct = default) =>
        SendNoContentAsync(HttpMethod.Delete, $"v1/runs/{Uri.EscapeDataString(jobId)}", ct);

    private async Task SendNoContentAsync(HttpMethod method, string path, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(method, new Uri(BaseAddress, path));
        Authorize(req);
        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (IsTransport(e, ct))
        {
            throw Transport(e);
        }
        using (resp) await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Streams a job's events. When the connection drops before the job ends, it reconnects with
    /// ?after=&lt;last id&gt; so no event is lost or repeated. Ends after the terminal job event.
    /// A stream with nothing on it (not even the engine's keepalive) for <see cref="StreamIdleTimeout"/>
    /// counts as dropped. Failed attempts in a row wait longer each time (<see cref="ReconnectDelay"/>);
    /// after <see cref="MaxReconnects"/> of them the stream ends with an <see cref="EngineException"/>.
    /// </summary>
    public async IAsyncEnumerable<JobEvent> StreamEventsAsync(string jobId, int after = -1,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        int last = after;
        int failures = 0;
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            using var req = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseAddress, $"v1/jobs/{Uri.EscapeDataString(jobId)}/events?after={last}"));
            req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));
            if (last >= 0) req.Headers.TryAddWithoutValidation("Last-Event-ID", last.ToString(System.Globalization.CultureInfo.InvariantCulture));
            Authorize(req);

            HttpResponseMessage? resp = null;
            Stream? body = null;
            Exception? dropped = null;
            try
            {
                resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
                await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
                body = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
            }
            catch (Exception e) when (IsTransport(e, ct))
            {
                resp?.Dispose();
                dropped = e;
            }

            if (body is not null)
            {
                bool terminal = false;
                await using (body)
                using (resp)
                {
                    var events = ServerSentEventParser.ReadAsync(body, ct: ct, idleTimeout: StreamIdleTimeout).GetAsyncEnumerator(ct);
                    while (true)
                    {
                        bool more;
                        try { more = await events.MoveNextAsync().ConfigureAwait(false); }
                        catch (Exception e) when (IsTransport(e, ct)) { more = false; dropped = e; }
                        if (!more) break;

                        var sse = events.Current;
                        JobEvent? ev;
                        try { ev = JsonSerializer.Deserialize(sse.Data, EngineJsonContext.Default.JobEvent); }
                        catch (JsonException) { continue; }
                        if (ev is null || ev.Id <= last) continue;
                        last = ev.Id;
                        failures = 0;
                        yield return ev;
                        if (ev.Type == "job" && ev.Status is JobStatus.Succeeded or JobStatus.Failed or JobStatus.Cancelled)
                        {
                            terminal = true;
                            break;
                        }
                    }
                    try { await events.DisposeAsync().ConfigureAwait(false); }
                    catch (Exception e) when (IsTransport(e, ct)) { }
                }
                if (terminal) yield break;

                // The stream closed without a terminal event: ask for the job state before reconnecting.
                // An engine that cannot be reached right now counts as one more failed attempt.
                Job? job = null;
                try { job = await GetJobAsync(jobId, ct).ConfigureAwait(false); }
                catch (EngineException e) when (e.Status is null) { dropped = e; }
                if (job?.IsTerminal == true) yield break;
            }

            if (++failures > MaxReconnects)
                throw dropped switch
                {
                    EngineException e => e,
                    null => new EngineException("Lost the connection to the engine."),
                    _ => Transport(dropped),
                };
            await Task.Delay(ReconnectDelay(failures), ct).ConfigureAwait(false);
        }
    }

    /// <summary>A job's event stream with nothing on it for this long is reconnected (the engine sends a keepalive every 15 s).</summary>
    public TimeSpan StreamIdleTimeout { get; init; } = TimeSpan.FromSeconds(45);

    /// <summary>Failed attempts in a row before the event stream gives up: about half a minute with the default delays.</summary>
    public int MaxReconnects { get; init; } = 10;

    /// <summary>The wait before reconnect attempt n (from 1): 250 ms, doubling, at most 5 s.</summary>
    public Func<int, TimeSpan> ReconnectDelay { get; init; } =
        n => TimeSpan.FromMilliseconds(Math.Min(5000, 250 << Math.Clamp(n - 1, 0, 5)));

    /// <summary>A failure of the connection or the transfer, as opposed to the engine's answer or the caller's Cancel.</summary>
    private static bool IsTransport(Exception e, CancellationToken ct) =>
        e is HttpRequestException or IOException or TimeoutException
        || (e is OperationCanceledException && !ct.IsCancellationRequested);

    /// <summary>A transport failure as an <see cref="EngineException"/>: a timeout (HttpClient.Timeout, idle stream) or no connection.</summary>
    private EngineException Transport(Exception e) => e is OperationCanceledException or TimeoutException
        ? new EngineException($"The engine at {BaseAddress} did not answer in time.", null, e, EngineException.Timeout)
        : new EngineException($"The engine at {BaseAddress} could not be reached.", null, e);

    private void Authorize(HttpRequestMessage req)
    {
        if (!string.IsNullOrEmpty(Token)) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
    }

    private async Task<T> SendJsonAsync<T>(HttpMethod method, string path, HttpContent? content,
        System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> type, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(method, new Uri(BaseAddress, path)) { Content = content };
        Authorize(req);
        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (IsTransport(e, ct))
        {
            throw Transport(e);
        }
        using (resp)
        {
            await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
            T? value;
            try
            {
                await using var s = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                value = await JsonSerializer.DeserializeAsync(s, type, ct).ConfigureAwait(false);
            }
            catch (Exception e) when (IsTransport(e, ct))
            {
                throw Transport(e);
            }
            catch (JsonException e)
            {
                throw new EngineException($"The engine's answer to {path} could not be read.", resp.StatusCode, e);
            }
            return value ?? throw new EngineException($"Empty response from {path}.", resp.StatusCode);
        }
    }

    private async Task<Stream> SendStreamAsync(string path, CancellationToken ct)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseAddress, path));
        Authorize(req);
        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (IsTransport(e, ct))
        {
            throw Transport(e);
        }
        await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
        try
        {
            return await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        }
        catch (Exception e) when (IsTransport(e, ct))
        {
            resp.Dispose();
            throw Transport(e);
        }
    }

    private static async Task EnsureSuccessAsync(HttpResponseMessage resp, CancellationToken ct)
    {
        if (resp.IsSuccessStatusCode) return;
        string detail = "";
        try { detail = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false); }
        catch (Exception e) when (IsTransport(e, ct)) { }
        resp.Dispose();
        string message = resp.StatusCode switch
        {
            HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden => "The engine needs pairing. Enter the code it shows.",
            HttpStatusCode.NotFound => "The engine does not have that item.",
            _ => $"The engine answered {(int)resp.StatusCode}.",
        };
        throw new EngineException(detail.Length > 0 && detail.Length < 500 ? $"{message} {detail}" : message, resp.StatusCode,
            code: detail.Length > 0 ? EngineException.CodeOf(detail) : null);
    }
}

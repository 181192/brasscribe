using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Engine;

public sealed class EngineException(string message, HttpStatusCode? status = null, Exception? inner = null)
    : Exception(message, inner)
{
    public HttpStatusCode? Status { get; } = status;
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

    public async Task<IReadOnlyList<ProfileInfo>> ListProfilesAsync(CancellationToken ct = default) =>
        await SendJsonAsync(HttpMethod.Get, "v1/profiles", null, EngineJsonContext.Default.ListProfileInfo, ct).ConfigureAwait(false);

    public Task<AudioRef> UploadAudioAsync(Stream audio, string filename, CancellationToken ct = default)
    {
        var form = new MultipartFormDataContent();
        var file = new StreamContent(audio);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(file, "file", filename);
        return SendJsonAsync(HttpMethod.Post, "v1/audio", form, EngineJsonContext.Default.AudioRef, ct);
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

    /// <summary>
    /// Streams a job's events. When the connection drops before the job ends, it reconnects with
    /// ?after=&lt;last id&gt; so no event is lost or repeated. Ends after the terminal job event.
    /// </summary>
    public async IAsyncEnumerable<JobEvent> StreamEventsAsync(string jobId, int after = -1,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        int last = after;
        int failures = 0;
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            var req = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseAddress, $"v1/jobs/{Uri.EscapeDataString(jobId)}/events?after={last}"));
            req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));
            if (last >= 0) req.Headers.TryAddWithoutValidation("Last-Event-ID", last.ToString(System.Globalization.CultureInfo.InvariantCulture));
            Authorize(req);

            HttpResponseMessage? resp = null;
            Stream? body = null;
            try
            {
                resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
                await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
                body = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
            }
            catch (HttpRequestException) when (++failures <= 5)
            {
                resp?.Dispose();
                await Task.Delay(TimeSpan.FromMilliseconds(250 * failures), ct).ConfigureAwait(false);
                continue;
            }

            bool terminal = false;
            await using (body)
            using (resp)
            {
                var events = ServerSentEventParser.ReadAsync(body, ct: ct).GetAsyncEnumerator(ct);
                while (true)
                {
                    bool more;
                    try { more = await events.MoveNextAsync().ConfigureAwait(false); }
                    catch (IOException) when (!ct.IsCancellationRequested) { more = false; }
                    catch (HttpRequestException) when (!ct.IsCancellationRequested) { more = false; }
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
                await events.DisposeAsync().ConfigureAwait(false);
            }
            if (terminal) yield break;

            // The stream closed without a terminal event: ask for the job state before reconnecting.
            var job = await GetJobAsync(jobId, ct).ConfigureAwait(false);
            if (job.IsTerminal) yield break;
            if (++failures > 20) throw new EngineException("Lost the connection to the engine.");
            await Task.Delay(TimeSpan.FromMilliseconds(200), ct).ConfigureAwait(false);
        }
    }

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
        catch (HttpRequestException e)
        {
            throw new EngineException($"The engine at {BaseAddress} could not be reached.", null, e);
        }
        using (resp)
        {
            await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
            await using var s = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
            return await JsonSerializer.DeserializeAsync(s, type, ct).ConfigureAwait(false)
                   ?? throw new EngineException($"Empty response from {path}.");
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
        catch (HttpRequestException e)
        {
            throw new EngineException($"The engine at {BaseAddress} could not be reached.", null, e);
        }
        await EnsureSuccessAsync(resp, ct).ConfigureAwait(false);
        return await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
    }

    private static async Task EnsureSuccessAsync(HttpResponseMessage resp, CancellationToken ct)
    {
        if (resp.IsSuccessStatusCode) return;
        string detail = "";
        try { detail = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false); }
        catch (HttpRequestException) { }
        resp.Dispose();
        string message = resp.StatusCode switch
        {
            HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden => "The engine needs pairing. Enter the code it shows.",
            HttpStatusCode.NotFound => "The engine does not have that item.",
            _ => $"The engine answered {(int)resp.StatusCode}.",
        };
        throw new EngineException(detail.Length > 0 && detail.Length < 500 ? $"{message} {detail}" : message, resp.StatusCode);
    }
}

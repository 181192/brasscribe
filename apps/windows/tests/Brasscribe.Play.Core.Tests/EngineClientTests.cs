using System.Net;
using System.Text;
using System.Text.Json;
using Brasscribe.Play.Core.Engine;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>An HttpMessageHandler that answers from a function and records every request.</summary>
internal sealed class FakeHandler(Func<HttpRequestMessage, int, HttpResponseMessage> respond) : HttpMessageHandler
{
    public List<(HttpRequestMessage Request, string? Body)> Requests { get; } = [];

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        string? body = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
        Requests.Add((request, body));
        return respond(request, Requests.Count - 1);
    }

    public static HttpResponseMessage Json(string json, HttpStatusCode code = HttpStatusCode.OK) =>
        new(code) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    public static HttpResponseMessage Sse(string text) =>
        new(HttpStatusCode.OK) { Content = new StringContent(text, Encoding.UTF8, "text/event-stream") };
}

public class EngineClientTests
{
    private const string JobJson = """{"id":"j1","profile":"solo","status":"running","created":1.0,"stages":[{"name":"f0","status":"started"}],"progress":0.5}""";

    private static (EngineClient Client, FakeHandler Handler) Make(Func<HttpRequestMessage, int, HttpResponseMessage> f)
    {
        var h = new FakeHandler(f);
        return (new EngineClient(new HttpClient(h), new Uri("http://engine.local:8765")), h);
    }

    [Fact]
    public async Task Pairing_stores_the_token_and_sends_it_as_bearer()
    {
        var (c, h) = Make((r, i) => r.RequestUri!.AbsolutePath switch
        {
            "/v1/pair" => FakeHandler.Json("""{"token":"tok-123"}"""),
            _ => FakeHandler.Json("""[{"name":"solo","pipeline":"A-solo","description":"One brass line","validated":false,"stages":["f0"]}]"""),
        });
        await c.PairAsync("4821", "Kalli-PC");
        var profiles = await c.ListProfilesAsync();

        Assert.Equal("tok-123", c.Token);
        Assert.Equal("""{"code":"4821","device_name":"Kalli-PC"}""", h.Requests[0].Body);
        Assert.Null(h.Requests[0].Request.Headers.Authorization);
        Assert.Equal("Bearer", h.Requests[1].Request.Headers.Authorization!.Scheme);
        Assert.Equal("tok-123", h.Requests[1].Request.Headers.Authorization!.Parameter);
        Assert.Equal("solo", profiles.Single().Name);
    }

    [Fact]
    public async Task Lists_runs_reads_evidence_renames_and_deletes()
    {
        var (c, h) = Make((r, _) => (r.Method.Method, r.RequestUri!.AbsolutePath) switch
        {
            ("GET", "/v1/jobs") => FakeHandler.Json($"[{JobJson}]"),
            ("GET", "/v1/jobs/j1/evidence") => FakeHandler.Json("""
                {"models":[{"model":"swift-f0","name":"SwiftF0"},{"model":"basic-pitch","name":"Basic Pitch"}],
                 "notes":[{"voice":"melody","start":24,"pitch":67,"confidence":0.42,"onset_s":1.0,
                   "models":[{"model":"swift-f0","name":"SwiftF0","pitch":67,"agrees":true},{"model":"basic-pitch","name":"Basic Pitch","pitch":69,"agrees":false}]}]}
                """),
            ("PATCH", "/v1/runs/j1") => FakeHandler.Json(JobJson.Replace("\"status\":\"running\"", "\"status\":\"succeeded\",\"title\":\"Old Hundredth\"")),
            ("DELETE", "/v1/runs/j1") => new HttpResponseMessage(HttpStatusCode.NoContent),
            _ => new HttpResponseMessage(HttpStatusCode.NotFound),
        });

        var jobs = await c.ListJobsAsync();
        var evidence = await c.GetEvidenceAsync("j1");
        var renamed = await c.RenameRunAsync("j1", "Old Hundredth");
        await c.DeleteRunAsync("j1");

        Assert.Equal("j1", jobs.Single().Id);
        var note = evidence.NoteAt("melody", 24, 55)!;
        Assert.Equal(0.42, note.Confidence);
        Assert.Equal(2, note.AlternativeShift);
        Assert.Equal([67, 69], note.Models.Select(m => m.Pitch!.Value));
        Assert.Equal("""{"title":"Old Hundredth"}""", h.Requests[2].Body);
        Assert.Equal("Old Hundredth", renamed.Title);
        Assert.Equal(HttpMethod.Delete, h.Requests[3].Request.Method);
        Assert.Equal(evidence.Notes.Single().Pitch, Evidence.Parse(Evidence.Serialize(evidence))!.Notes.Single().Pitch);
    }

    [Fact]
    public async Task Rejected_pairing_code_is_a_plain_message()
    {
        var (c, _) = Make((_, _) => new HttpResponseMessage(HttpStatusCode.Forbidden));
        var e = await Assert.ThrowsAsync<EngineException>(() => c.PairAsync("0000", null));
        Assert.Equal(HttpStatusCode.Forbidden, e.Status);
        Assert.Contains("not accepted", e.Message);
    }

    [Fact]
    public async Task Create_job_posts_snake_case_and_cancel_uses_delete()
    {
        var (c, h) = Make((r, _) => FakeHandler.Json(JobJson, r.Method == HttpMethod.Post ? HttpStatusCode.Accepted : HttpStatusCode.OK));
        var job = await c.CreateJobAsync(new JobCreate("a1", "brass-band", RenderAudio: false));
        await c.CancelJobAsync(job.Id);

        using var doc = JsonDocument.Parse(h.Requests[0].Body!);
        Assert.Equal("a1", doc.RootElement.GetProperty("audio_id").GetString());
        Assert.Equal("brass-band", doc.RootElement.GetProperty("profile").GetString());
        Assert.False(doc.RootElement.GetProperty("render_audio").GetBoolean());
        Assert.Equal(HttpMethod.Delete, h.Requests[1].Request.Method);
        Assert.Equal("/v1/jobs/j1", h.Requests[1].Request.RequestUri!.AbsolutePath);
        Assert.Equal(0.5, job.Progress);
    }

    [Fact]
    public async Task Upload_is_multipart_with_file_field()
    {
        var (c, h) = Make((_, _) => FakeHandler.Json("""{"audio_id":"a1","sha256":"ff","filename":"m.wav","bytes":4}""", HttpStatusCode.Created));
        var r = await c.UploadAudioAsync(new MemoryStream([1, 2, 3, 4]), "m.wav");
        Assert.Equal("a1", r.AudioId);
        Assert.Equal("multipart/form-data", h.Requests[0].Request.Content!.Headers.ContentType!.MediaType);
        Assert.Contains("name=file", h.Requests[0].Body);
        Assert.Contains("filename=m.wav", h.Requests[0].Body);
    }

    [Fact]
    public async Task Events_resume_after_a_dropped_stream_without_repeats()
    {
        // First connection delivers events 0 and 1 then closes; the second is asked for after=1.
        var (c, h) = Make((r, i) =>
        {
            string path = r.RequestUri!.AbsolutePath;
            if (path.EndsWith("/events"))
            {
                return r.RequestUri.Query.Contains("after=-1")
                    ? FakeHandler.Sse(": keepalive\n\nid: 0\nevent: stage\ndata: {\"id\":0,\"run\":\"j1\",\"type\":\"stage\",\"time\":1,\"stage\":\"f0\",\"status\":\"started\",\"fraction\":0.0}\n\n" +
                                      "id: 1\nevent: stage\ndata: {\"id\":1,\"run\":\"j1\",\"type\":\"stage\",\"time\":2,\n" +
                                      "data: \"stage\":\"f0\",\"status\":\"ran\",\"fraction\":0.5}\n\n")
                    : FakeHandler.Sse("id: 1\ndata: {\"id\":1,\"run\":\"j1\",\"type\":\"stage\",\"time\":2}\n\n" +
                                      "id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n");
            }
            return FakeHandler.Json(JobJson);
        });

        var events = new List<JobEvent>();
        await foreach (var e in c.StreamEventsAsync("j1")) events.Add(e);

        Assert.Equal([0, 1, 2], events.Select(e => e.Id));
        Assert.Equal(0.5, events[1].Fraction);
        Assert.Equal("succeeded", events[2].Status);
        var second = h.Requests.Last(r => r.Request.RequestUri!.AbsolutePath.EndsWith("/events")).Request;
        Assert.Contains("after=1", second.RequestUri!.Query);
        Assert.Equal("1", second.Headers.GetValues("Last-Event-ID").Single());
    }

    [Fact]
    public async Task Unreachable_engine_gives_a_plain_message()
    {
        var (c, _) = Make((_, _) => throw new HttpRequestException("refused"));
        var e = await Assert.ThrowsAsync<EngineException>(() => c.GetHealthAsync());
        Assert.Contains("could not be reached", e.Message);
    }

    [Fact]
    public void Eta_is_withheld_early_then_smoothed()
    {
        var clock = new FakeTimeProvider();
        var est = new ProgressEstimator(clock);
        est.Start();
        clock.Advance(TimeSpan.FromSeconds(1));
        Assert.Null(est.Update(0.01));
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Equal(TimeSpan.FromSeconds(30), est.Update(0.25)); // 10 s for a quarter: 30 s left
        clock.Advance(TimeSpan.FromSeconds(10));
        var r = est.Update(0.5)!.Value.TotalSeconds; // raw 20 s, smoothed toward it
        Assert.InRange(r, 20, 30);
        Assert.Equal(TimeSpan.Zero, est.Update(1.0));
    }
}

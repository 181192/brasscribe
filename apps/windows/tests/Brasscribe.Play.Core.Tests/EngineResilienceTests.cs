using System.Net;
using System.Text;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The engine client under a bad network: timeouts, broken answers, dropped and silent event streams.
/// Every failure reaches the caller as an <see cref="EngineException"/>, which the screens already handle.
/// </summary>
public class EngineResilienceTests
{
    private const string JobJson = """{"id":"j1","profile":"solo","status":"running","created":1.0,"stages":[],"progress":0.5}""";
    private const string Terminal = "id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n";
    private const string First = "id: 0\nevent: stage\ndata: {\"id\":0,\"run\":\"j1\",\"type\":\"stage\",\"time\":1,\"stage\":\"f0\",\"status\":\"started\"}\n\n";

    /// <summary>A handler that answers asynchronously from a function (which may wait or throw).</summary>
    private sealed class AsyncHandler(Func<HttpRequestMessage, int, CancellationToken, Task<HttpResponseMessage>> respond) : HttpMessageHandler
    {
        public List<HttpRequestMessage> Requests { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Requests.Add(request);
            return respond(request, Requests.Count - 1, ct);
        }
    }

    /// <summary>A body that sends its text and then nothing more, without closing (a half-open connection).</summary>
    private sealed class HangingStream(string text) : Stream
    {
        private readonly MemoryStream _head = new(Encoding.UTF8.GetBytes(text));

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            int n = _head.Read(buffer.Span);
            if (n > 0) return n;
            await Task.Delay(Timeout.Infinite, ct);
            return 0;
        }

        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct) =>
            ReadAsync(buffer.AsMemory(offset, count), ct).AsTask();

        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    private static EngineClient Client(HttpMessageHandler h, TimeSpan? timeout = null, TimeSpan? idle = null) =>
        new(new HttpClient(h) { Timeout = timeout ?? Timeout.InfiniteTimeSpan }, new Uri("http://engine.local:8765"))
        {
            ReconnectDelay = _ => TimeSpan.Zero,
            StreamIdleTimeout = idle ?? TimeSpan.FromSeconds(45),
        };

    [Fact]
    public async Task A_request_that_times_out_is_an_engine_timeout()
    {
        var c = Client(new AsyncHandler(async (_, _, ct) =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return new HttpResponseMessage();
        }), timeout: TimeSpan.FromMilliseconds(50));

        var e = await Assert.ThrowsAsync<EngineException>(() => c.ListProfilesAsync());
        Assert.Equal(EngineException.Timeout, e.Code);
        Assert.Equal("Error_Timeout", EngineErrors.Key(e));

        var s = await Assert.ThrowsAsync<EngineException>(() => c.DownloadAsync("j1", JobDownload.Pdf));
        Assert.Equal(EngineException.Timeout, s.Code);
    }

    [Fact]
    public async Task The_players_cancel_is_still_a_cancellation()
    {
        var c = Client(new AsyncHandler(async (_, _, ct) =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return new HttpResponseMessage();
        }));
        using var cts = new CancellationTokenSource(50);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => c.GetHealthAsync(cts.Token));
    }

    [Fact]
    public async Task An_answer_that_is_not_json_is_an_engine_error()
    {
        var c = Client(new FakeHandler((_, _) => FakeHandler.Json("<html>proxy error</html>")));
        var e = await Assert.ThrowsAsync<EngineException>(() => c.GetJobAsync("j1"));
        Assert.Equal(HttpStatusCode.OK, e.Status);
        Assert.Equal("Error_Engine", EngineErrors.Key(e));
    }

    [Fact]
    public async Task A_body_cut_off_while_reading_is_unreachable()
    {
        var c = Client(new AsyncHandler((_, _, _) => throw new IOException("connection reset")));
        var e = await Assert.ThrowsAsync<EngineException>(() => c.GetHealthAsync());
        Assert.Null(e.Status);
        Assert.Equal("Error_Unreachable", EngineErrors.Key(e));
    }

    [Fact]
    public async Task An_event_stream_that_cannot_connect_gives_up_with_an_engine_error()
    {
        var h = new FakeHandler((_, _) => throw new HttpRequestException("refused"));
        var c = Client(h);
        await Assert.ThrowsAsync<EngineException>(async () =>
        {
            await foreach (var _ in c.StreamEventsAsync("j1")) { }
        });
        Assert.Equal(c.MaxReconnects + 1, h.Requests.Count);
    }

    [Fact]
    public async Task A_short_outage_after_a_dropped_stream_does_not_end_the_job()
    {
        // The stream drops after event 0; the engine is then away for three tries, and comes back.
        int n = 0;
        var c = Client(new FakeHandler((r, _) =>
        {
            n++;
            if (r.RequestUri!.AbsolutePath.EndsWith("/events"))
                return r.RequestUri.Query.Contains("after=-1") ? FakeHandler.Sse(First) : FakeHandler.Sse(Terminal);
            if (n <= 6) throw new HttpRequestException("network is unreachable");
            return FakeHandler.Json(JobJson);
        }));

        var ids = new List<int>();
        await foreach (var e in c.StreamEventsAsync("j1")) ids.Add(e.Id);
        Assert.Equal([0, 2], ids);
    }

    [Fact]
    public async Task A_silent_event_stream_is_reconnected()
    {
        var h = new AsyncHandler((r, _, _) =>
        {
            if (!r.RequestUri!.AbsolutePath.EndsWith("/events")) return Task.FromResult(FakeHandler.Json(JobJson));
            var body = r.RequestUri.Query.Contains("after=-1") ? new HangingStream(": keepalive\n\n" + First) : new HangingStream(Terminal);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(body) });
        });
        var c = Client(h, idle: TimeSpan.FromMilliseconds(200));

        var ids = new List<int>();
        using var guard = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await foreach (var e in c.StreamEventsAsync("j1", ct: guard.Token)) ids.Add(e.Id);

        Assert.Equal([0, 2], ids);
        Assert.Contains("after=0", h.Requests.Last().RequestUri!.Query);
    }

    // Thirty keepalives 100 ms apart (3 s) outlast a 2 s idle limit only if each one resets it. The stream's wait and
    // the idle limit are two timers on the machine's clock, so the test holds only while no single wait runs past the
    // limit: a wait of 100 ms may take twenty times as long on a busy CI machine before it does. (At 150 ms against
    // 600 ms, four times, a Windows runner now and then did.)
    [Fact]
    public async Task Keepalives_keep_a_quiet_stream_open()
    {
        var events = ServerSentEventParser.ReadAsync(new KeepaliveStream(30, TimeSpan.FromMilliseconds(100)), idleTimeout: TimeSpan.FromSeconds(2));
        var all = new List<ServerSentEvent>();
        await foreach (var e in events) all.Add(e);
        Assert.Single(all);
    }

    /// <summary>Sends a keepalive every <paramref name="every"/>, <paramref name="count"/> times, then one event and the end.</summary>
    private sealed class KeepaliveStream(int count, TimeSpan every) : Stream
    {
        private int _sent;
        private byte[]? _pending;

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            if (_pending is null)
            {
                if (_sent > count) return 0;
                await Task.Delay(every, ct);
                _pending = Encoding.UTF8.GetBytes(_sent++ < count ? ": keepalive\n\n" : "data: done\n\n");
            }
            int n = Math.Min(buffer.Length, _pending.Length);
            _pending.AsSpan(0, n).CopyTo(buffer.Span);
            _pending = n == _pending.Length ? null : _pending[n..];
            return n;
        }

        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct) =>
            ReadAsync(buffer.AsMemory(offset, count), ct).AsTask();

        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    [Fact]
    public async Task An_upload_keeps_a_norwegian_file_name()
    {
        var h = new FakeHandler((_, _) => FakeHandler.Json("""{"audio_id":"a1","sha256":"ff","filename":"x","bytes":4}""", HttpStatusCode.Created));
        var c = Client(h);
        await c.UploadAudioAsync(new MemoryStream([1, 2, 3, 4]), "Kjærlighet \"live\".wav");

        string body = h.Requests[0].Body!;
        Assert.Contains("filename=\"Kjærlighet _live_.wav\"", body);
        Assert.DoesNotContain("=?utf-8?", body, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task The_heartbeat_survives_a_check_that_throws()
    {
        var time = new FakeTimeProvider();
        int asked = 0;
        bool started = false;
        var address = new Uri("http://127.0.0.1:8765/");
        var lan = new FakeLan();
        lan.At[address] = new FakeLan.Engine("0123456789abcdef0123456789abcdef", "PC") { AuthRequired = false };
        var monitor = new ConnectionMonitor(new EngineCredentials(new InMemorySecretVault(), new InMemorySettings()), lan.Client,
            new FakeBrowse(() => []), () => started && ++asked == 1 ? throw new InvalidOperationException("settings not ready") : address,
            _ => { }, new Said(), ConnectionMonitorTests.Strings(), time);

        started = true;
        monitor.Start();
        for (int i = 0; i < 50 && asked < 1; i++) await Task.Delay(10);
        monitor.Kick();
        for (int i = 0; i < 1000 && monitor.State != ConnectionState.Connected; i++) await Task.Delay(10);

        Assert.Equal(ConnectionState.Connected, monitor.State);
        Assert.True(monitor.IsRunning);
        monitor.Stop();
    }
}

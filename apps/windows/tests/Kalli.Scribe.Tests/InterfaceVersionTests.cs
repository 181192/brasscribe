using System.Net;
using System.Text.RegularExpressions;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The app and the engine must have the same interface version. When they differ the app says which of the two to
/// update and asks that engine for nothing but the two answers that carry its number (health, and this device's own
/// answer, which is the paired heartbeat): no pairing, no job, no list, no unpairing; the stored pairing stays.
/// </summary>
public class InterfaceVersionTests
{
    private const string StudioId = "0123456789abcdef0123456789abcdef";
    private const string OtherId = "ffffffffffffffffffffffffffffffff";
    private static readonly Uri Old = new("http://192.0.2.20:8765/");
    private static readonly Uri New = new("http://192.0.2.44:8765/");

    private const string UpdateBandroom = "Update Brasscribe on Studio PC. This app is newer than Brasscribe there, and they only work together when both are up to date.";
    private const string UpdateApp = "Update Brasscribe Play. Brasscribe on Studio PC is newer than this app, and they only work together when both are up to date.";

    [Theory]
    [InlineData(Wire.InterfaceVersion, InterfaceAnswer.Same)]
    [InlineData(Wire.InterfaceVersion + 1, InterfaceAnswer.UpdateApp)]
    [InlineData(Wire.InterfaceVersion - 1, InterfaceAnswer.UpdateBandroom)]
    [InlineData(null, InterfaceAnswer.UpdateBandroom)]
    public void The_engines_number_is_the_same_newer_older_or_missing(int? engine, InterfaceAnswer expected) =>
        Assert.Equal(expected, InterfaceMatch.Of(engine));

    /// <summary>The client's number, scheme and service are the engine's own (engine/src/scribe_engine/wire.py).</summary>
    [SkippableFact]
    public void The_apps_number_scheme_and_service_are_the_engines()
    {
        const string wire = "engine/src/scribe_engine/wire.py";
        // Outside a checkout (the tests copied somewhere to run) there is no engine source to compare with. CI always
        // runs in one: there the comparison is never skipped.
        bool outside = TestPaths.RepoRoot is null && Environment.GetEnvironmentVariable("SCRIBE_REPO") is null;
        if (Environment.GetEnvironmentVariable("CI") is { Length: > 0 }) Assert.False(outside, TestPaths.Missing(wire));
        Skip.If(outside, TestPaths.Missing(wire));
        string python = File.ReadAllText(TestPaths.RepoFile(wire)!);
        string Value(string name) => Regex.Match(python, $@"^{name}\s*=\s*""?([^""\r\n]+?)""?\s*$", RegexOptions.Multiline) is { Success: true } m
            ? m.Groups[1].Value
            : throw new Xunit.Sdk.XunitException($"{wire} has no {name}");
        Assert.Equal(Value("INTERFACE_VERSION"), Wire.InterfaceVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Assert.Equal(Value("PAIRING_SCHEME"), Wire.PairScheme);
        Assert.Equal(Value("SERVICE_TYPE"), Wire.ServiceType);
    }

    [Fact]
    public async Task Health_carries_the_number_and_without_one_it_is_null()
    {
        var lan = new FakeLan();
        var studio = lan.At[Old] = new FakeLan.Engine(StudioId, "Studio PC");
        Assert.Equal(Wire.InterfaceVersion, (await lan.Client(Old, null).GetHealthAsync()).InterfaceVersion);
        studio.InterfaceVersion = null;
        var health = await lan.Client(Old, null).GetHealthAsync();
        Assert.Null(health.InterfaceVersion);
        // Whose answer it was is still known.
        Assert.Equal(StudioId, health.ServerId);
        Assert.Equal("Brasscribe on Studio PC", health.ServerName);
    }

    // ---- the engine client: the one place where the rule is kept ----

    private const string Job = """{"id":"j1","profile":"solo","status":"succeeded","created":1.0,"stages":[],"outputs":["solo.musicxml"]}""";

    private static string HealthWith(string number) =>
        $$"""{"version":"0.4.0","interface_version":{{number}},"device":"cpu","auth_required":false,"server_id":"{{StudioId}}","server_name":"Brasscribe on Studio PC"}""";

    /// <summary>An engine that answers everything; its health says <paramref name="number"/> (raw JSON).</summary>
    private static (EngineClient Client, FakeHandler Handler) Engine(string number)
    {
        var handler = new FakeHandler((r, _) => r.RequestUri!.AbsolutePath switch
        {
            "/v1/health" => FakeHandler.Json(HealthWith(number)),
            "/v1/jobs" when r.Method == HttpMethod.Get => FakeHandler.Json($"[{Job}]"),
            "/v1/profiles" => FakeHandler.Json("[]"),
            _ when r.Method == HttpMethod.Delete && r.RequestUri.AbsolutePath.StartsWith("/v1/runs/", StringComparison.Ordinal) => new HttpResponseMessage(HttpStatusCode.NoContent),
            _ => FakeHandler.Json(Job),
        });
        return (new EngineClient(new HttpClient(handler), Old), handler);
    }

    private static List<string> Paths(FakeHandler handler) => handler.Requests.Select(r => $"{r.Request.Method.Method} {r.Request.RequestUri!.AbsolutePath}").ToList();

    public static TheoryData<string, Func<IEngineClient, Task>> EveryOtherRequest() => new()
    {
        { "list the scores", c => c.ListJobsAsync() },
        { "open a score", c => c.GetJobAsync("j1") },
        { "its notes", c => c.GetCompositionAsync("j1") },
        { "its MusicXML", c => c.DownloadAsync("j1", JobDownload.MusicXml) },
        { "its evidence", c => c.GetEvidenceAsync("j1") },
        { "its layers", c => c.ListStagesAsync("j1") },
        { "a layer file", c => c.GetStageFileAsync("j1", "layers", "beats.json") },
        { "an export", c => c.GetArtifactAsync("j1", "solo.pdf") },
        { "braille", c => c.DownloadBrailleAsync("j1") },
        { "rename", c => c.RenameRunAsync("j1", "Old Hundredth") },
        { "delete", c => c.DeleteRunAsync("j1") },
        { "upload", c => c.UploadAudioAsync(new MemoryStream([1, 2, 3, 4]), "take.wav") },
        { "a job", c => c.CreateJobAsync(new JobCreate("a1")) },
        { "cancel", c => c.CancelJobAsync("j1") },
        { "the event stream", async c => { await foreach (var _ in c.StreamEventsAsync("j1")) { } } },
        { "profiles", c => c.ListProfilesAsync() },
        { "pair", c => c.PairDeviceAsync("482913", "PC", "windows") },
        { "ask the computer", c => c.RequestPairingAsync("PC", "windows") },
        { "poll the request", c => c.PollPairingRequestAsync("req-1") },
        { "rotate", c => c.RotateTokenAsync() },
        { "unpair", c => c.UnpairAsync() },
    };

    [Theory]
    [MemberData(nameof(EveryOtherRequest))]
    public async Task A_request_to_an_engine_with_another_interface_version_is_not_sent(string what, Func<IEngineClient, Task> request)
    {
        foreach (var (number, answer) in new[] { ("0", InterfaceAnswer.UpdateBandroom), ("2", InterfaceAnswer.UpdateApp) })
        {
            var (client, handler) = Engine(number);
            int told = 0;
            client.InterfaceMismatch = () => told++;

            var refused = await Assert.ThrowsAsync<EngineException>(() => request(client));
            Assert.True(refused.Interface == answer, what);
            // The words are the update ones, never "can't reach" or "score failed".
            Assert.Equal(answer == InterfaceAnswer.UpdateApp ? "Error_UpdateApp_Title" : "Error_UpdateBandroom_Title", EngineErrors.Key(refused));
            Assert.Contains($"this app is built for {Wire.InterfaceVersion}", refused.Message);
            Assert.Equal(["GET /v1/health"], Paths(handler));
            Assert.Equal(1, told);

            // And not the next time either: the answer is remembered, health is not asked again.
            await Assert.ThrowsAsync<EngineException>(() => request(client));
            Assert.Equal(["GET /v1/health"], Paths(handler));
        }
    }

    [Fact]
    public async Task The_number_is_not_known_until_the_first_answer_and_then_it_is_not_asked_again()
    {
        var (client, handler) = Engine(Wire.InterfaceVersion.ToString());
        await client.ListJobsAsync();
        await client.GetJobAsync("j1");
        await client.DeleteRunAsync("j1");
        Assert.Equal(["GET /v1/health", "GET /v1/jobs", "GET /v1/jobs/j1", "DELETE /v1/runs/j1"], Paths(handler));
    }

    [Fact]
    public async Task After_a_request_that_got_no_answer_the_engine_is_asked_for_its_number_again()
    {
        string number = Wire.InterfaceVersion.ToString();
        bool down = false;
        var handler = new FakeHandler((r, _) =>
        {
            if (down) throw new HttpRequestException("connection refused");
            return r.RequestUri!.AbsolutePath == "/v1/health" ? FakeHandler.Json(HealthWith(number)) : FakeHandler.Json($"[{Job}]");
        });
        var client = new EngineClient(new HttpClient(handler), Old);
        await client.ListJobsAsync();

        // The computer goes away, and what answers at the address afterwards has another interface version.
        down = true;
        var unreachable = await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Null(unreachable.Interface);
        down = false;
        number = (Wire.InterfaceVersion + 1).ToString();
        handler.Requests.Clear();

        var refused = await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Equal(InterfaceAnswer.UpdateApp, refused.Interface);
        Assert.Equal(["GET /v1/health"], Paths(handler));
    }

    [Fact]
    public async Task A_job_in_flight_stops_with_the_update_words_when_the_engine_is_replaced_under_it()
    {
        string number = Wire.InterfaceVersion.ToString();
        var handler = new FakeHandler((r, _) =>
        {
            string path = r.RequestUri!.AbsolutePath;
            if (path == "/v1/health") return FakeHandler.Json(HealthWith(number));
            if (path.EndsWith("/events", StringComparison.Ordinal))
            {
                // The stream ends without the job's end: the engine was stopped for its update.
                number = "0";
                return FakeHandler.Sse("id: 0\nevent: stage\ndata: {\"id\":0,\"run\":\"j1\",\"type\":\"stage\",\"time\":1,\"stage\":\"f0\",\"status\":\"started\",\"fraction\":0.1}\n\n");
            }
            return FakeHandler.Json(Job.Replace("succeeded", "running"));
        });
        var client = new EngineClient(new HttpClient(handler), Old);

        var seen = new List<int>();
        var refused = await Assert.ThrowsAsync<EngineException>(async () =>
        {
            await foreach (var e in client.StreamEventsAsync("j1")) seen.Add(e.Id);
        });
        Assert.Equal([0], seen);
        Assert.Equal(InterfaceAnswer.UpdateBandroom, refused.Interface);
        // Health, the stream, health again: the job's state is not asked of the other engine.
        Assert.Equal(["GET /v1/health", "GET /v1/jobs/j1/events", "GET /v1/health"], Paths(handler));
    }

    [Theory]
    [InlineData("1.5")]
    [InlineData("1.0")]
    [InlineData("\"1\"")]
    [InlineData("true")]
    [InlineData("null")]
    [InlineData("99999999999")]
    [InlineData("[1]")]
    public async Task A_number_that_is_not_a_whole_number_means_update_the_computer_not_unreachable(string number)
    {
        var (client, handler) = Engine(number);
        var health = await client.GetHealthAsync();
        Assert.Null(health.InterfaceVersion);
        Assert.Equal(StudioId, health.ServerId);
        var refused = await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Equal(InterfaceAnswer.UpdateBandroom, refused.Interface);
        Assert.Equal(["GET /v1/health"], Paths(handler));
    }

    [Fact]
    public async Task The_number_is_read_even_when_the_rest_of_the_answer_cannot_be()
    {
        // A later engine may answer health in another shape: its number still says which of the two to update.
        var handler = new FakeHandler((_, _) => FakeHandler.Json($$"""{"interface_version":{{Wire.InterfaceVersion + 1}},"version":7,"device":null,"auth_required":"yes","server_id":"{{StudioId}}"}"""));
        var client = new EngineClient(new HttpClient(handler), Old);
        var health = await client.GetHealthAsync();
        Assert.Equal(Wire.InterfaceVersion + 1, health.InterfaceVersion);
        Assert.Equal(InterfaceAnswer.UpdateApp, (await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync())).Interface);
    }

    public static TheoryData<string> NotAnEnginesAnswer() => new()
    {
        "{}",
        "<html><body>Sign in to the network</body></html>",
        "[]",
        """{"interface_version":0}""",
        $$"""{"interface_version":{{Wire.InterfaceVersion + 1}}}""",
        """{"interface_version":0,"server_id":7}""",
        """{"status":"ok"}""",
    };

    [Theory]
    [MemberData(nameof(NotAnEnginesAnswer))]
    public async Task An_answer_that_does_not_say_which_engine_it_is_could_not_be_read_and_is_no_reason_to_update(string body)
    {
        var handler = new FakeHandler((_, _) => FakeHandler.Json(body));
        var client = new EngineClient(new HttpClient(handler), Old);
        int told = 0;
        client.InterfaceMismatch = () => told++;

        Assert.Null((await Assert.ThrowsAsync<EngineException>(() => client.GetHealthAsync())).Interface);
        Assert.Null((await Assert.ThrowsAsync<EngineException>(() => client.GetThisDeviceAsync())).Interface);
        var failed = await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Null(failed.Interface);
        Assert.NotEqual("Error_UpdateBandroom_Title", EngineErrors.Key(failed));
        Assert.Equal(0, told);
        // Nothing was learnt: the next request asks again, and nothing else is sent.
        await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Equal(["GET /v1/health", "GET /v1/devices/me", "GET /v1/health", "GET /v1/health"], Paths(handler));
    }

    [Fact]
    public async Task A_request_decides_from_the_health_it_asked_itself_whatever_another_request_does_meanwhile()
    {
        bool down = false;
        var handler = new FakeHandler((r, _) =>
        {
            if (down) throw new HttpRequestException("connection refused");
            return r.RequestUri!.AbsolutePath == "/v1/health" ? FakeHandler.Json(HealthWith("0")) : FakeHandler.Json($"[{Job}]");
        });
        var client = new EngineClient(new HttpClient(handler), Old);
        // While the list's own health answer is being noted, another request on the same client loses its connection.
        client.InterfaceMismatch = () =>
        {
            down = true;
            try { client.GetHealthAsync().GetAwaiter().GetResult(); }
            catch (EngineException) { }
            down = false;
        };

        var refused = await Assert.ThrowsAsync<EngineException>(() => client.ListJobsAsync());
        Assert.Equal(InterfaceAnswer.UpdateBandroom, refused.Interface);
        Assert.DoesNotContain("GET /v1/jobs", Paths(handler));
    }

    // ---- the status row ----

    private sealed class Rig
    {
        public FakeLan Lan { get; } = new();
        public FakeLan.Engine Studio { get; } = new(StudioId, "Studio PC");
        public FakeTimeProvider Time { get; } = new(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero));
        public Said Said { get; } = new();
        public List<DiscoveredEngine> OnNetwork { get; } = [];
        public Uri Address { get; set; } = Old;
        public EngineCredentials Credentials { get; }
        public ConnectionMonitor Monitor { get; }

        public Rig(string lang = "en-US")
        {
            Studio.Tokens.Add("tok-1");
            Lan.At[Old] = Studio;
            Credentials = new EngineCredentials(new InMemorySecretVault(), new InMemorySettings());
            Credentials.Save(new EngineCredential(StudioId, "tok-1", "Brasscribe on Studio PC"));
            Monitor = new ConnectionMonitor(Credentials, Lan.Client, new FakeBrowse(() => OnNetwork), () => Address, u => Address = u,
                Said, ConnectionMonitorTests.Strings(lang), Time);
        }
    }

    [Theory]
    [InlineData(0, ConnectionState.UpdateBandroom, UpdateBandroom)]
    [InlineData(null, ConnectionState.UpdateBandroom, UpdateBandroom)]
    [InlineData(2, ConnectionState.UpdateApp, UpdateApp)]
    public async Task A_heartbeat_against_another_interface_version_says_which_to_update_and_asks_nothing_else(
        int? engine, ConnectionState expected, string sentence)
    {
        var rig = new Rig();
        rig.Studio.InterfaceVersion = engine;
        bool asked = false;
        rig.Monitor.PairingNeeded += (_, _) => asked = true;

        Assert.Equal(expected, await rig.Monitor.CheckAsync());
        Assert.Equal(sentence, rig.Monitor.StatusText);
        Assert.True(rig.Monitor.NeedsUpdate);
        Assert.False(rig.Monitor.IsConnected);
        // Not "pair again" and not "looking for"; the pairing is kept.
        Assert.False(asked);
        Assert.Equal("tok-1", rig.Credentials.Get(StudioId)!.Token);
        // One request: the heartbeat's own answer carried the number.
        Assert.Equal(["GET /v1/devices/me"], rig.Lan.Calls);
        // The numbers are never the message.
        Assert.DoesNotContain(rig.Monitor.StatusText, char.IsDigit);
        // It keeps checking, so the row follows the update without pairing again.
        Assert.Equal(ConnectionMonitor.HeartbeatInterval, rig.Monitor.NextDelay);
    }

    [Fact]
    public async Task The_update_row_has_something_to_do_and_says_when_the_engine_last_answered()
    {
        var rig = new Rig();
        rig.Studio.InterfaceVersion = 2;
        await rig.Monitor.CheckAsync();

        Assert.True(rig.Monitor.HasAction);
        Assert.Equal("Get the update", rig.Monitor.ActionText);
        Assert.StartsWith("Opens the page", rig.Monitor.ActionHelp);
        Assert.Equal("https://github.com/181192/brasscribe/releases/latest", rig.Monitor.ActionUri!.AbsoluteUri);
        Assert.Equal(rig.Time.GetUtcNow(), rig.Monitor.LastOk);
        Assert.Contains("Last answered: ", rig.Monitor.DetailsText);
        // The stored record keeps its last good check: the next launch does not start from "Connected".
        Assert.Null(rig.Credentials.Get(StudioId)!.LastOk);

        // Connect and Pair again are not links.
        rig.Studio.InterfaceVersion = Wire.InterfaceVersion;
        await rig.Monitor.CheckAsync();
        Assert.Null(rig.Monitor.ActionUri);
        Assert.False(rig.Monitor.HasAction);
    }

    [Theory]
    [InlineData("1.5")]
    [InlineData("\"1\"")]
    [InlineData("true")]
    [InlineData("99999999999")]
    public async Task A_malformed_number_is_update_the_computer_for_the_row_too(string number)
    {
        var rig = new Rig();
        rig.Studio.RawInterfaceVersion = number;
        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
        Assert.Equal(UpdateBandroom, rig.Monitor.StatusText);

        // With nothing paired the number comes from health: the same.
        rig.Credentials.Remove(StudioId);
        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
    }

    [Fact]
    public async Task Bandroom_updated_during_a_session_is_noticed_at_the_next_heartbeat_and_connects_again_after_its_update()
    {
        var rig = new Rig();
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());

        rig.Studio.InterfaceVersion = Wire.InterfaceVersion + 1;
        Assert.Equal(ConnectionState.UpdateApp, await rig.Monitor.CheckAsync());
        Assert.Contains(UpdateApp, rig.Said.Items);

        rig.Studio.InterfaceVersion = Wire.InterfaceVersion;
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal("tok-1", rig.Credentials.Get(StudioId)!.Token);
        Assert.Equal(0, rig.Studio.Pairings);
        Assert.All(rig.Lan.Calls, c => Assert.Equal("GET /v1/devices/me", c));
    }

    [Fact]
    public async Task The_sentence_is_in_norwegian_too()
    {
        var rig = new Rig("nb-NO");
        rig.Studio.InterfaceVersion = 0;
        await rig.Monitor.CheckAsync();
        Assert.Equal("Oppdater Brasscribe på Studio PC. Denne appen er nyere enn Brasscribe der, og de virker bare sammen når begge er oppdatert.", rig.Monitor.StatusText);
        Assert.Equal("Hent oppdateringen", rig.Monitor.ActionText);
        rig.Studio.InterfaceVersion = 2;
        await rig.Monitor.CheckAsync();
        Assert.Equal("Oppdater Brasscribe Play. Brasscribe på Studio PC er nyere enn denne appen, og de virker bare sammen når begge er oppdatert.", rig.Monitor.StatusText);
    }

    [Theory]
    [InlineData("http://127.0.0.1:8765/", "en-US", "Update Brasscribe on this PC. It is older than this app, and they only work together when both are up to date.")]
    [InlineData("http://localhost:8765/", "nb-NO", "Oppdater Brasscribe på denne PC-en. Den er eldre enn denne appen, og de virker bare sammen når begge er oppdatert.")]
    public async Task An_engine_on_this_pc_is_named_this_pc(string address, string lang, string sentence)
    {
        var rig = new Rig(lang);
        var here = new Uri(address);
        rig.Lan.At.Clear();
        rig.Lan.At[here] = rig.Studio;
        rig.Address = here;
        rig.Credentials.Remove(StudioId);
        rig.Studio.AuthRequired = false;
        rig.Studio.InterfaceVersion = 0;
        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
        Assert.Equal(sentence, rig.Monitor.StatusText);
    }

    [Fact]
    public void A_computer_that_has_given_no_name_is_your_computer()
    {
        var s = ConnectionMonitorTests.Strings();
        Assert.Equal("Update Brasscribe Play. Brasscribe on your computer is newer than this app, and they only work together when both are up to date.",
            ConnectionMonitor.UpdateText(s, InterfaceAnswer.UpdateApp, onThisPc: false, null));
    }

    [Fact]
    public async Task An_engine_found_at_a_new_address_is_checked_before_anything_else_is_asked_there()
    {
        var rig = new Rig();
        rig.Lan.At.Remove(Old);
        rig.Lan.At[New] = rig.Studio;
        rig.Studio.InterfaceVersion = 0;
        rig.OnNetwork.Add(new DiscoveredEngine("Brasscribe on Studio PC", New, StudioId, "Studio PC"));

        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
        Assert.Equal(New, rig.Address);
        Assert.NotNull(rig.Credentials.Get(StudioId));
        Assert.All(rig.Lan.Calls, c => Assert.Equal("GET /v1/devices/me", c));
    }

    [Theory]
    [InlineData(false)] // it does not know our token: 401, then its health says whose answer that was
    [InlineData(true)]  // it answers our token (a restored backup, a copied data folder): its own answer names it
    public async Task Another_engine_at_the_address_is_not_ours_to_update_it_is_ours_that_is_looked_for(bool knowsOurToken)
    {
        var rig = new Rig();
        var other = rig.Lan.At[Old] = new FakeLan.Engine(OtherId, "Other") { InterfaceVersion = 0 };
        if (knowsOurToken) other.Tokens.Add("tok-1");
        bool asked = false;
        rig.Monitor.PairingNeeded += (_, _) => asked = true;

        await rig.Monitor.CheckAsync();
        var state = await rig.Monitor.CheckAsync();
        Assert.Equal(ConnectionState.Reconnecting, state);
        Assert.False(rig.Monitor.NeedsUpdate);
        Assert.False(asked);
        Assert.NotNull(rig.Credentials.Get(StudioId));
    }

    [Fact]
    public async Task Our_own_engine_with_another_version_that_answers_401_is_update_not_pair_again()
    {
        var rig = new Rig();
        rig.Studio.InterfaceVersion = 2;
        rig.Studio.Tokens.Clear();
        Assert.Equal(ConnectionState.UpdateApp, await rig.Monitor.CheckAsync());
        Assert.NotNull(rig.Credentials.Get(StudioId));
        Assert.Equal(["GET /v1/devices/me", "GET /v1/health"], rig.Lan.Calls);
    }

    [Fact]
    public async Task With_nothing_paired_the_row_still_says_which_to_update()
    {
        var rig = new Rig();
        rig.Credentials.Remove(StudioId);
        rig.Studio.InterfaceVersion = 0;
        rig.Studio.AuthRequired = false;
        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
        Assert.Equal(UpdateBandroom, rig.Monitor.StatusText);
        Assert.Equal(["GET /v1/health"], rig.Lan.Calls);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("<html><body>Sign in to the network</body></html>")]
    public async Task Something_else_answering_at_the_address_is_not_an_engine_to_update(string body)
    {
        // Paired: the engine is looked for, and found where it now is.
        var rig = new Rig();
        rig.Lan.At.Remove(Old);
        rig.Lan.NotAnEngine[Old] = body;
        await rig.Monitor.CheckAsync();
        Assert.Equal(ConnectionState.Reconnecting, await rig.Monitor.CheckAsync());
        Assert.False(rig.Monitor.NeedsUpdate);
        Assert.Null(rig.Monitor.ActionUri);
        rig.Lan.At[New] = rig.Studio;
        rig.OnNetwork.Add(new DiscoveredEngine("Brasscribe on Studio PC", New, StudioId, "Studio PC"));
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal(New, rig.Address);

        // Nothing paired: not connected, and nothing to update.
        var unpaired = new Rig();
        unpaired.Credentials.Remove(StudioId);
        unpaired.Lan.At.Remove(Old);
        unpaired.Lan.NotAnEngine[Old] = body;
        Assert.Equal(ConnectionState.Offline, await unpaired.Monitor.CheckAsync());
        Assert.False(unpaired.Monitor.NeedsUpdate);
    }

    // ---- pairing and unpairing ----

    private static (SettingsViewModel Vm, FakeLan Lan, FakeLan.Engine Studio) Settings(int? engine, string? pairedWith = null)
    {
        var lan = new FakeLan();
        var studio = lan.At[Old] = new FakeLan.Engine(StudioId, "Studio PC") { InterfaceVersion = engine };
        var settings = new InMemorySettings();
        settings.Set("EngineAddress", Old.ToString());
        var vault = new InMemorySecretVault();
        if (pairedWith is not null)
        {
            new EngineCredentials(vault, settings).Save(new EngineCredential(StudioId, pairedWith, "Brasscribe on Studio PC"));
            studio.Tokens.Add(pairedWith);
        }
        var vm = new SettingsViewModel(settings, new Said(), ConnectionMonitorTests.Strings(), new FakeBrowse(() => []),
            vault, lan.Client, new FakeTimeProvider(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero)));
        return (vm, lan, studio);
    }

    // A copy: the status row's own check may still be asking.
    private static void OnlyTheNumberWasAsked(FakeLan lan)
    {
        string[] asked;
        lock (lan.Requests) asked = [.. lan.Calls];
        Assert.All(asked, c => Assert.Contains(c, new[] { "GET /v1/health", "GET /v1/devices/me" }));
    }

    [Theory]
    [InlineData(0, UpdateBandroom)]
    [InlineData(null, UpdateBandroom)]
    [InlineData(2, UpdateApp)]
    public async Task Pairing_with_a_code_sends_no_pair_request(int? engine, string sentence)
    {
        var (vm, lan, studio) = Settings(engine);
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();

        Assert.Equal(sentence, vm.EngineStatus);
        Assert.Equal(0, studio.Pairings);
        Assert.False(vm.IsPaired);
        OnlyTheNumberWasAsked(lan);
        // Not words only: the pairing screen offers the page with the update, as the status row does.
        Assert.True(vm.HasEngineStatusLink);
        Assert.Equal(ConnectionMonitor.LatestRelease, vm.EngineStatusLink);
        Assert.Equal("Get the update", vm.EngineStatusLinkLabel);
        Assert.StartsWith("Opens the page", vm.EngineStatusLinkHelp);

        // After the update the pairing goes through, and the link is gone with the sentence.
        studio.InterfaceVersion = Wire.InterfaceVersion;
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();
        Assert.True(vm.IsPaired);
        Assert.False(vm.HasEngineStatusLink);
    }

    [Fact]
    public async Task Something_else_answering_at_a_typed_address_is_a_failure_to_connect_with_no_update_offered()
    {
        var (vm, lan, _) = Settings(Wire.InterfaceVersion);
        lan.At.Remove(Old);
        lan.NotAnEngine[Old] = "{}";
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();

        Assert.Equal("Something went wrong talking to your computer. Try again.", vm.EngineStatus);
        Assert.False(vm.HasEngineStatusLink);
        Assert.False(vm.IsPaired);
        OnlyTheNumberWasAsked(lan);
    }

    [Fact]
    public async Task A_link_whose_first_address_is_not_the_engine_is_tried_at_its_next_one()
    {
        var (vm, lan, studio) = Settings(Wire.InterfaceVersion);
        lan.At.Remove(Old);
        lan.NotAnEngine[Old] = "{}";
        lan.At[New] = studio;

        Assert.True(await vm.PairFromLinkAsync($"scribe://pair?v=1&id={StudioId}&name=Brasscribe%20on%20Studio%20PC&h=192.0.2.20:8765,192.0.2.44:8765&code=482913"));
        vm.Connection.Stop();

        Assert.Equal(New.ToString(), vm.EngineAddress);
        Assert.Equal(1, studio.Pairings);
        Assert.False(vm.HasEngineStatusLink);
    }

    [Fact]
    public async Task Asking_the_computer_sends_no_request_to_allow()
    {
        var (vm, lan, studio) = Settings(0);
        await vm.AskComputerCommand.ExecuteAsync(null);
        vm.Connection.Stop();

        Assert.Equal(UpdateBandroom, vm.EngineStatus);
        Assert.False(vm.IsAsking);
        Assert.Equal(ConnectionMonitor.LatestRelease, vm.EngineStatusLink);
        Assert.Equal(0, studio.Polls);
        OnlyTheNumberWasAsked(lan);
    }

    [Theory]
    [InlineData("&code=482913")]
    [InlineData("")]
    public async Task A_pairing_link_sends_no_pair_request(string code)
    {
        var (vm, lan, studio) = Settings(2);
        Assert.False(await vm.PairFromLinkAsync($"scribe://pair?v=1&id={StudioId}&name=Brasscribe%20on%20Studio%20PC&h=192.0.2.20:8765{code}"));
        vm.Connection.Stop();

        Assert.Equal(UpdateApp, vm.EngineStatus);
        Assert.Equal(0, studio.Pairings);
        Assert.Equal(0, studio.Polls);
        Assert.Equal(ConnectionMonitor.LatestRelease, vm.EngineStatusLink);
        Assert.Null(vm.Credentials.CurrentServerId);
        OnlyTheNumberWasAsked(lan);
    }

    [Theory]
    [InlineData("&h=192.0.2.44:8765")] // the link names the address
    [InlineData("")]                   // it is found on the network
    public async Task A_link_to_an_engine_with_another_version_leaves_the_pairing_in_use_as_it_was(string hosts)
    {
        var lan = new FakeLan();
        var studio = lan.At[Old] = new FakeLan.Engine(StudioId, "Studio PC");
        studio.Tokens.Add("tok-1");
        var band = lan.At[New] = new FakeLan.Engine(OtherId, "Band laptop") { InterfaceVersion = Wire.InterfaceVersion + 1 };
        var settings = new InMemorySettings();
        settings.Set("EngineAddress", Old.ToString());
        var vault = new InMemorySecretVault();
        new EngineCredentials(vault, settings).Save(new EngineCredential(StudioId, "tok-1", "Brasscribe on Studio PC"));
        var vm = new SettingsViewModel(settings, new Said(), ConnectionMonitorTests.Strings(),
            new FakeBrowse(() => [new DiscoveredEngine("Brasscribe on Band laptop", New, OtherId, "Band laptop")]),
            vault, lan.Client, new FakeTimeProvider(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero)));

        Assert.False(await vm.PairFromLinkAsync($"scribe://pair?v=1&id={OtherId}&name=Brasscribe%20on%20Band%20laptop{hosts}&code=482913"));
        vm.Connection.Stop();

        // The sentence names the link's computer, and everything about the engine in use is as it was.
        Assert.Equal("Update Brasscribe Play. Brasscribe on Band laptop is newer than this app, and they only work together when both are up to date.", vm.EngineStatus);
        // The status row is about the engine in use: the update for the link's engine is offered next to the sentence.
        Assert.Equal(ConnectionMonitor.LatestRelease, vm.EngineStatusLink);
        Assert.Equal(Old.ToString(), vm.EngineAddress);
        Assert.Equal(StudioId, vm.Credentials.CurrentServerId);
        Assert.Equal("tok-1", vm.EngineToken);
        Assert.True(vm.IsPaired);
        Assert.Null(vm.Credentials.Get(OtherId));
        Assert.Single(vm.Credentials.All());
        Assert.Equal(0, band.Pairings);
        Assert.Equal(0, band.Polls);
        (Uri Address, string Path, string? Token)[] asked;
        lock (lan.Requests) asked = [.. lan.Requests];
        Assert.All(asked.Where(r => r.Address == New), r => Assert.Equal("/v1/health", r.Path));
    }

    [Fact]
    public async Task Connect_keeps_the_stored_pairing_and_it_works_again_after_the_update()
    {
        var (vm, lan, studio) = Settings(0, pairedWith: "tok-1");
        Assert.True(vm.IsPaired);

        // A typed code is not sent either.
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();
        Assert.Equal(UpdateBandroom, vm.EngineStatus);
        Assert.Equal("tok-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.True(vm.IsPaired);
        OnlyTheNumberWasAsked(lan);

        studio.InterfaceVersion = Wire.InterfaceVersion;
        vm.PairingCode = "";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();
        Assert.Equal("Connected to Brasscribe on Studio PC.", vm.EngineStatus);
        Assert.Equal("tok-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.Equal(0, studio.Pairings);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(2)]
    public async Task Unpair_during_a_mismatch_forgets_on_this_pc_only_and_sends_the_engine_nothing(int engine)
    {
        var (vm, lan, studio) = Settings(engine, pairedWith: "tok-1");
        await vm.UnpairCommand.ExecuteAsync(null);
        vm.Connection.Stop();

        Assert.Null(vm.Credentials.Get(StudioId));
        Assert.False(vm.IsPaired);
        Assert.Equal("This PC is no longer paired with Brasscribe on Studio PC.", vm.EngineStatus);
        // The engine was not told: it still holds the device.
        Assert.Contains("tok-1", studio.Tokens);
        OnlyTheNumberWasAsked(lan);
    }
}

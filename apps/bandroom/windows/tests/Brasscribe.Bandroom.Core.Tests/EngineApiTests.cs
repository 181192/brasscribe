using System.Net;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class EngineApiTests
{
    private const string Pairing = """
        {"open":true,"code":"482913","expires_at":null,"single_use":true,"server_id":"3f9c2a7e11","server_name":"Brasscribe on Kalli's PC",
         "hosts":["192.168.1.20:8765"],"fingerprint":null,"uri":"brasscribe://pair?v=1&id=3f9c2a7e11&code=482913"}
        """;

    private static (EngineApi Api, StubHandler Handler) Make()
    {
        var h = new StubHandler();
        return (new EngineApi(new HttpClient(h), new Uri("http://127.0.0.1:8765/"), "admin-token"), h);
    }

    [Fact]
    public async Task Opening_pairing_sends_ttl_null_explicitly_and_the_admin_bearer()
    {
        var (api, h) = Make();
        h.Routes["POST /v1/pairing"] = (HttpStatusCode.OK, Pairing);
        var state = await api.OpenPairingAsync(new PairingOpenRequest(TtlS: null));
        var (req, body) = h.Seen.Single();
        Assert.Equal("""{"ttl_s":null,"single_use":true,"extend":false}""", body);
        Assert.Equal("Bearer", req.Headers.Authorization!.Scheme);
        Assert.Equal("admin-token", req.Headers.Authorization.Parameter);
        Assert.Equal("482913", state.Code);
        Assert.Null(state.ExpiresAt);
        Assert.Equal(["192.168.1.20:8765"], state.Hosts);
    }

    [Fact]
    public async Task Status_reads_the_contract_fields()
    {
        var (api, h) = Make();
        h.Routes["GET /v1/status"] = (HttpStatusCode.OK, """
            {"server_id":"3f9c2a7e11","server_name":"Brasscribe on Kalli's PC","version":"0.9.4","online_devices":2,
             "paired_devices":3,"pairing_open":false,"jobs_running":1,"jobs_queued":1}
            """);
        var s = await api.GetStatusAsync();
        Assert.Equal(new StatusInfo("3f9c2a7e11", "Brasscribe on Kalli's PC", "0.9.4", 2, 3, false, 1, 1), s);
    }

    [Fact]
    public async Task An_engine_without_status_is_read_from_health_devices_and_jobs()
    {
        var (api, h) = Make();
        h.Routes["GET /v1/health"] = (HttpStatusCode.OK, """
            {"status":"ok","version":"0.9.3","device":"cpu","auth_required":false,"server_id":"abc","server_name":"Brasscribe on Kalli's PC"}
            """);
        h.Routes["GET /v1/devices"] = (HttpStatusCode.OK, """
            [{"device_id":"d1","name":"Kari's iPhone","platform":"ios","paired_at":"2026-09-01T10:00:00Z","last_seen":"2026-09-27T11:59:30Z","rotated_at":null},
             {"device_id":"d2","name":"Band iPad","platform":"ios","paired_at":"2026-09-01T10:00:00Z","last_seen":"2026-09-24T11:59:30Z","online":true}]
            """);
        h.Routes["GET /v1/jobs"] = (HttpStatusCode.OK, """
            [{"id":"j1","profile":"p","title":"Old Hundredth","status":"running","created":1,"started":2,"finished":null,"progress":0.5,"stages":[]},
             {"id":"j2","profile":"p","title":null,"status":"queued","created":3,"started":null,"finished":null,"progress":0,"stages":[]}]
            """);
        var s = await api.GetStatusAsync();
        Assert.Equal(new StatusInfo("abc", "Brasscribe on Kalli's PC", "0.9.3", 1, 2, false, 1, 1), s);
        // Only asks once for /v1/status.
        await api.GetStatusAsync();
        Assert.Single(h.Seen, x => x.Request.RequestUri!.AbsolutePath == "/v1/status");
    }

    [Fact]
    public async Task Removing_a_device_that_is_already_gone_is_fine_and_other_errors_surface()
    {
        var (api, h) = Make();
        await api.RemoveDeviceAsync("gone");
        h.Routes["DELETE /v1/devices/d1"] = (HttpStatusCode.Forbidden, "{\"detail\":\"only on the computer running the engine\"}");
        var e = await Assert.ThrowsAsync<EngineHttpException>(() => api.RemoveDeviceAsync("d1"));
        Assert.Equal(HttpStatusCode.Forbidden, e.StatusCode);
    }

    [Fact]
    public async Task Deciding_a_request_posts_to_approve_or_deny()
    {
        var (api, h) = Make();
        h.Routes["POST /v1/pairing/requests/r1/approve"] = (HttpStatusCode.OK, """
            {"request_id":"r1","name":"Kari's iPhone","platform":"ios","match_code":"4719","created_at":"2026-09-27T12:00:00Z","status":"approved"}
            """);
        var r = await api.DecidePairRequestAsync("r1", approve: true);
        Assert.Equal("approved", r.Status);
        Assert.Equal("4719", r.MatchCode);
    }
}

public sealed class AdminCredentialTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("bandroom-cred").FullName;
    public void Dispose() => Directory.Delete(_dir, recursive: true);

    [Fact]
    public void Made_once_readable_only_by_this_user_and_reused()
    {
        var path = Path.Combine(_dir, "bandroom", "admin-token");
        var token = AdminCredential.LoadOrCreate(path);
        Assert.True(token.Length >= 43); // 256 bits, base64url
        Assert.DoesNotContain('=', token);
        Assert.True(AdminCredential.IsRestricted(path));
        Assert.Equal(token, AdminCredential.LoadOrCreate(path));
    }

    [Fact]
    public void A_damaged_file_is_replaced()
    {
        var path = Path.Combine(_dir, "admin-token");
        File.WriteAllText(path, "short");
        Assert.NotEqual("short", AdminCredential.LoadOrCreate(path));
    }
}

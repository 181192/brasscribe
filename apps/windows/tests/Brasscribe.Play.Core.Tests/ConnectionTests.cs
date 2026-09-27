using System.Net;
using System.Text.Json;
using System.Xml.Linq;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// A pretend local network of engines, answering like the real engine (api.py): /v1/health,
/// /v1/devices/me (401 for an unknown token, 404 without one on loopback), rotation, pairing and
/// approve-on-the-computer. Engines can be moved, stopped or made to forget a device.
/// </summary>
internal sealed class FakeLan
{
    public sealed class Engine(string serverId, string computer)
    {
        public string ServerId { get; } = serverId;
        public string ServerName { get; } = "Brasscribe on " + computer;
        public HashSet<string> Tokens { get; } = [];
        public bool AuthRequired { get; set; } = true;
        public string Code { get; set; } = "482913";
        public string RotateAfter { get; set; } = "2099-01-01T00:00:00Z";
        public int Rotations { get; set; }
        public int Pairings { get; set; }
        public List<string> Platforms { get; } = [];
        /// <summary>Approve-on-the-computer: the owner's answer after this many polls ("approved"/"denied"), null = never.</summary>
        public (int AfterPolls, string Answer)? Decision { get; set; }
        public int Polls { get; set; }
    }

    public Dictionary<Uri, Engine> At { get; } = [];
    public List<(Uri Address, string Path, string? Token)> Requests { get; } = [];

    public IEngineClient Client(Uri address, string? token) =>
        new EngineClient(new HttpClient(new FakeHandler((r, _) => Answer(address, r))), address) { Token = token };

    private HttpResponseMessage Answer(Uri address, HttpRequestMessage r)
    {
        var path = r.RequestUri!.AbsolutePath;
        string? token = r.Headers.Authorization?.Parameter;
        Requests.Add((address, path, token));
        if (!At.TryGetValue(address, out var e)) throw new HttpRequestException("connection refused");
        bool known = token is not null && e.Tokens.Contains(token);
        string Json(object o) => JsonSerializer.Serialize(o);
        switch (r.Method.Method, path)
        {
            case ("GET", "/v1/health"):
                return FakeHandler.Json(Json(new { version = "0.4.0", device = "cpu", auth_required = e.AuthRequired, server_id = e.ServerId, server_name = e.ServerName }));
            case ("GET", "/v1/devices/me"):
                if (!e.AuthRequired && token is null) return FakeHandler.Json("""{"detail":"not a paired device"}""", HttpStatusCode.NotFound);
                if (!known) return FakeHandler.Json("""{"detail":"unknown token"}""", HttpStatusCode.Unauthorized);
                return FakeHandler.Json(Json(new
                {
                    device_id = "d1", name = "PC", platform = "windows", paired_at = "2026-09-01T00:00:00Z", last_seen = "2026-09-27T00:00:00Z",
                    server_id = e.ServerId, rotate_after = e.RotateAfter, expires_if_idle_after = "2027-03-01T00:00:00Z",
                }));
            case ("POST", "/v1/devices/me/rotate"):
                if (!known) return FakeHandler.Json("{}", HttpStatusCode.Unauthorized);
                e.Rotations++;
                var fresh = $"tok-rotated-{e.Rotations}";
                e.Tokens.Add(fresh);
                return FakeHandler.Json(Json(new { token = fresh, device_id = "d1" }));
            case ("DELETE", "/v1/devices/me"):
                if (known) e.Tokens.Remove(token!);
                return new HttpResponseMessage(HttpStatusCode.NoContent);
            case ("POST", "/v1/pair"):
            {
                var body = JsonDocument.Parse(r.Content!.ReadAsStringAsync().Result).RootElement;
                if (body.GetProperty("code").GetString() != e.Code) return FakeHandler.Json("""{"detail":"wrong code"}""", HttpStatusCode.Forbidden);
                if (body.TryGetProperty("platform", out var p)) e.Platforms.Add(p.GetString()!);
                e.Pairings++;
                var t = $"tok-paired-{e.Pairings}";
                e.Tokens.Add(t);
                return FakeHandler.Json(Json(new { token = t, device_id = "d1", server_id = e.ServerId, server_name = e.ServerName }));
            }
            case ("POST", "/v1/pair/requests"):
                return FakeHandler.Json(Json(new { request_id = "req-1", name = "PC", platform = "windows", match_code = "4821", created_at = "now", status = "pending" }), HttpStatusCode.Accepted);
            case ("GET", "/v1/pair/requests/req-1"):
                e.Polls++;
                if (e.Decision is { } d && e.Polls >= d.AfterPolls)
                {
                    if (d.Answer == "approved")
                    {
                        e.Tokens.Add("tok-approved");
                        return FakeHandler.Json(Json(new { status = "approved", token = "tok-approved", device_id = "d2", server_id = e.ServerId, server_name = e.ServerName }));
                    }
                    return FakeHandler.Json(Json(new { status = d.Answer }));
                }
                return FakeHandler.Json("""{"status":"pending"}""");
        }
        return FakeHandler.Json("{}", HttpStatusCode.NotFound);
    }
}

internal sealed class FakeBrowse(Func<IReadOnlyList<DiscoveredEngine>> found) : IEngineDiscovery
{
    public int Browses { get; private set; }

    public Task<IReadOnlyList<DiscoveredEngine>> BrowseAsync(TimeSpan duration, CancellationToken ct = default)
    {
        Browses++;
        return Task.FromResult(found());
    }
}

internal sealed class Said : IAnnouncer
{
    public List<string> Items { get; } = [];
    public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Items.Add(text);
}

public class ConnectionMonitorTests
{
    private const string StudioId = "0123456789abcdef0123456789abcdef";
    private static readonly Uri Old = new("http://192.168.1.20:8765/");
    private static readonly Uri New = new("http://192.168.1.44:8765/");

    internal static IStrings Strings(string lang = "en-US") => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", lang, "Resources.resw"))));

    private sealed class Rig
    {
        public FakeLan Lan { get; } = new();
        public FakeTimeProvider Time { get; } = new(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero));
        public InMemorySettings Settings { get; } = new();
        public InMemorySecretVault Vault { get; } = new();
        public Said Said { get; } = new();
        public List<DiscoveredEngine> OnNetwork { get; } = [];
        public Uri Address { get; set; } = Old;
        public EngineCredentials Credentials { get; }
        public ConnectionMonitor Monitor { get; }
        public FakeBrowse Browse { get; }

        public Rig(string lang = "en-US")
        {
            Credentials = new EngineCredentials(Vault, Settings);
            Browse = new FakeBrowse(() => OnNetwork);
            Monitor = new ConnectionMonitor(Credentials, Lan.Client, Browse, () => Address, u => Address = u, Said, Strings(lang), Time);
        }

        public FakeLan.Engine Studio(Uri at, string token = "tok-1")
        {
            var e = new FakeLan.Engine(StudioId, "Studio PC");
            e.Tokens.Add(token);
            Lan.At[at] = e;
            return e;
        }
    }

    [Fact]
    public async Task A_valid_credential_is_connected_and_names_the_computer()
    {
        var rig = new Rig();
        rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1"));

        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal("Connected to Brasscribe on Studio PC", rig.Monitor.StatusText);
        Assert.False(rig.Monitor.HasAction);
        Assert.Equal(ConnectionMonitor.HeartbeatInterval, rig.Monitor.NextDelay);
        Assert.Contains(rig.Lan.Requests, r => r.Path == "/v1/devices/me" && r.Token == "tok-1");
        var stored = rig.Credentials.Get(StudioId)!;
        Assert.Equal(Old.ToString(), stored.LastAddress);
        Assert.Equal("Brasscribe on Studio PC", stored.ServerName);
        Assert.Empty(rig.Said.Items); // the first check is not news
    }

    [Fact]
    public async Task Norwegian_puts_the_computer_name_in_its_own_sentence()
    {
        var rig = new Rig("nb-NO");
        rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1"));
        await rig.Monitor.CheckAsync();
        Assert.Equal("Koblet til Brasscribe på Studio PC", rig.Monitor.StatusText);
    }

    [Fact]
    public async Task Only_a_401_asks_for_pairing_again_and_drops_the_credential()
    {
        var rig = new Rig();
        var studio = rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1", "Brasscribe on Studio PC"));
        await rig.Monitor.CheckAsync();
        bool asked = false;
        rig.Monitor.PairingNeeded += (_, _) => asked = true;

        studio.Tokens.Clear(); // revoked on the computer
        Assert.Equal(ConnectionState.NeedsPairing, await rig.Monitor.CheckAsync());
        Assert.True(asked);
        Assert.Null(rig.Credentials.Get(StudioId));
        Assert.Equal("The computer no longer recognises this PC.", rig.Monitor.StatusText);
        Assert.Equal("Pair this PC again", rig.Monitor.ActionText);
        Assert.Null(rig.Monitor.NextDelay);
        Assert.Equal(["The computer no longer recognises this PC."], rig.Said.Items);

        // A later check (network change) keeps saying so until the PC is paired.
        rig.Monitor.Kick();
        Assert.Equal(ConnectionState.NeedsPairing, await rig.Monitor.CheckAsync());
    }

    [Fact]
    public async Task On_the_same_computer_a_404_from_devices_me_is_still_connected()
    {
        var rig = new Rig();
        var studio = rig.Studio(Old);
        studio.AuthRequired = false; // loopback: trusted, no device record
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Contains(rig.Lan.Requests, r => r.Path == "/v1/health");

        // Even with a stored static token the 404 means "not a paired device", never "pair again".
        rig.Credentials.Save(new EngineCredential(StudioId, "static"));
        studio.AuthRequired = false;
        studio.Tokens.Add("static");
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
    }

    [Fact]
    public async Task Nothing_paired_and_no_local_engine_is_offline_with_connect()
    {
        var rig = new Rig();
        rig.Studio(Old); // needs pairing, and this PC has no credential
        Assert.Equal(ConnectionState.Offline, await rig.Monitor.CheckAsync());
        Assert.Equal("Not connected. You can still make scores on this PC.", rig.Monitor.StatusText);
        Assert.Equal("Connect", rig.Monitor.ActionText);
        Assert.True(rig.Monitor.HasAction);
    }

    [Fact]
    public async Task A_new_address_is_found_by_server_id_and_the_credential_is_kept()
    {
        var rig = new Rig();
        var studio = rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1"));
        await rig.Monitor.CheckAsync();

        // DHCP gave the computer a new address; an unrelated engine is also on the network.
        rig.Lan.At.Remove(Old);
        rig.Lan.At[New] = studio;
        rig.OnNetwork.Add(new DiscoveredEngine("Brasscribe on Other", new Uri("http://192.168.1.9:8765/"), "ffffffffffffffffffffffffffffffff", "Other"));
        rig.OnNetwork.Add(new DiscoveredEngine("Brasscribe on Studio PC (2)", New, StudioId, "Studio PC"));

        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal(New, rig.Address);
        Assert.Equal("tok-1", rig.Credentials.Get(StudioId)!.Token);
        Assert.Equal(New.ToString(), rig.Credentials.Get(StudioId)!.LastAddress);
        Assert.DoesNotContain(rig.Lan.Requests, r => r.Address.Host == "192.168.1.9");
    }

    [Fact]
    public async Task Another_engine_at_the_old_address_is_not_a_reason_to_pair_again()
    {
        var rig = new Rig();
        rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1"));
        await rig.Monitor.CheckAsync();

        rig.Lan.At[Old] = new FakeLan.Engine("ffffffffffffffffffffffffffffffff", "Laptop"); // answers 401 to our token
        var state = await rig.Monitor.CheckAsync();
        Assert.NotEqual(ConnectionState.NeedsPairing, state);
        Assert.NotNull(rig.Credentials.Get(StudioId));
    }

    [Fact]
    public async Task Missing_heartbeats_look_then_back_off_then_give_up_after_two_minutes()
    {
        var rig = new Rig();
        rig.Studio(Old);
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1", "Brasscribe on Studio PC"));
        await rig.Monitor.CheckAsync();
        rig.Lan.At.Clear(); // the computer went to sleep

        // One missed heartbeat keeps the row as it was, and checks again soon.
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal(TimeSpan.FromSeconds(2), rig.Monitor.NextDelay);
        Assert.Empty(rig.Said.Items);

        var waits = new List<TimeSpan?>();
        Assert.Equal(ConnectionState.Reconnecting, await rig.Monitor.CheckAsync());
        Assert.Equal("Looking for Brasscribe on Studio PC …", rig.Monitor.StatusText);
        Assert.Equal(["Looking for Brasscribe on Studio PC …"], rig.Said.Items);
        for (int i = 0; i < 5; i++)
        {
            waits.Add(rig.Monitor.NextDelay);
            rig.Time.Advance(rig.Monitor.NextDelay!.Value);
            await rig.Monitor.CheckAsync();
        }
        Assert.Equal([TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(16), TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(30)], waits);
        Assert.Single(rig.Said.Items); // repeated failures are not re-announced

        rig.Time.Advance(TimeSpan.FromMinutes(2));
        Assert.Equal(ConnectionState.Offline, await rig.Monitor.CheckAsync());
        Assert.Null(rig.Monitor.NextDelay); // gave up: until Connect or a network change
        Assert.Equal("Connect", rig.Monitor.ActionText);
        Assert.True(rig.Browse.Browses > 0); // it looked on the network by server id

        // Back again: Connect (a kick) finds it.
        rig.Studio(Old);
        rig.Monitor.Kick();
        Assert.Equal(ConnectionState.Connected, await rig.Monitor.CheckAsync());
        Assert.Equal("Connected to Brasscribe on Studio PC", rig.Said.Items[^1]);
    }

    [Fact]
    public async Task A_due_token_is_rotated_and_stored_before_it_is_used()
    {
        var rig = new Rig();
        var studio = rig.Studio(Old);
        studio.RotateAfter = "2026-09-01T00:00:00Z";
        rig.Credentials.Save(new EngineCredential(StudioId, "tok-1"));
        int changed = 0;
        rig.Monitor.CredentialChanged += (_, _) =>
        {
            changed++;
            Assert.Equal("tok-rotated-1", rig.Credentials.Get(StudioId)!.Token); // in the vault when announced
        };

        await rig.Monitor.CheckAsync();
        Assert.Equal(1, studio.Rotations);
        Assert.Equal(1, changed);

        studio.RotateAfter = "2026-10-27T00:00:00Z";
        await rig.Monitor.CheckAsync();
        Assert.Equal(1, studio.Rotations); // not due again
        Assert.Contains(rig.Lan.Requests, r => r.Path == "/v1/devices/me" && r.Token == "tok-rotated-1");
    }

    [Fact]
    public async Task A_token_moved_from_the_old_settings_file_is_filed_under_its_server_id()
    {
        var rig = new Rig();
        rig.Studio(Old, "tok-old");
        var settings = new InMemorySettings();
        settings.Set("EngineToken", "tok-old");
        settings.Set("EngineAddress", Old.ToString());
        var credentials = new EngineCredentials(rig.Vault, settings);
        var monitor = new ConnectionMonitor(credentials, rig.Lan.Client, rig.Browse, () => Old, _ => { }, rig.Said, Strings(), rig.Time);

        Assert.Equal(ConnectionState.Connected, await monitor.CheckAsync());
        Assert.Equal(StudioId, credentials.CurrentServerId);
        Assert.Equal("tok-old", credentials.Get(StudioId)!.Token);
        Assert.Null(credentials.Get(EngineCredentials.LegacyKey));
        Assert.Equal("Brasscribe on Studio PC", credentials.Get(StudioId)!.ServerName);
    }

    [Fact]
    public void Shown_state_for_screenshots_does_not_check()
    {
        var rig = new Rig();
        rig.Monitor.Show(ConnectionState.Connected, "Brasscribe on Studio PC");
        Assert.Equal("Connected to Brasscribe on Studio PC", rig.Monitor.StatusText);
        Assert.Empty(rig.Lan.Requests);
    }

    [Fact]
    public void Glyphs_differ_per_state_so_colour_is_never_the_only_cue()
    {
        var glyphs = Enum.GetValues<ConnectionState>().Select(Screens.ConnectionGlyph).ToList();
        Assert.Equal(glyphs.Count, glyphs.Distinct().Count());
    }
}

public class EngineCredentialsTests
{
    private const string StudioId = "0123456789abcdef0123456789abcdef";

    [Fact]
    public void The_old_plain_token_moves_to_the_vault_once_and_the_plain_copy_is_deleted()
    {
        var settings = new InMemorySettings();
        settings.Set("EngineToken", "tok-old");
        settings.Set("EngineAddress", "http://192.168.1.20:8765/");
        var vault = new InMemorySecretVault();

        var credentials = new EngineCredentials(vault, settings);
        Assert.Null(settings.Get<string?>("EngineToken", null));
        var legacy = credentials.Current!;
        Assert.Equal(EngineCredentials.LegacyKey, legacy.ServerId);
        Assert.Equal("tok-old", legacy.Token);
        Assert.Equal("http://192.168.1.20:8765/", legacy.LastAddress);
        Assert.Contains(EngineCredentials.LegacyKey, vault.Keys(EngineCredentials.Resource));

        // Again: nothing changes.
        var again = new EngineCredentials(vault, settings);
        Assert.Equal(legacy, again.Current);
    }

    [Fact]
    public void Migration_never_overwrites_a_newer_record()
    {
        var settings = new InMemorySettings();
        var vault = new InMemorySecretVault();
        new EngineCredentials(vault, settings).Save(new EngineCredential(StudioId, "tok-new"));
        settings.Set("EngineToken", "tok-stale"); // an old build wrote it back

        var credentials = new EngineCredentials(vault, settings);
        Assert.Equal("tok-new", credentials.Current!.Token);
        Assert.Null(credentials.Get(EngineCredentials.LegacyKey));
        Assert.Null(settings.Get<string?>("EngineToken", null));
    }

    private sealed class BrokenVault : ISecretVault
    {
        public string? Get(string resource, string key) => null;
        public void Set(string resource, string key, string secret) => throw new UnauthorizedAccessException();
        public void Remove(string resource, string key) { }
        public IReadOnlyList<string> Keys(string resource) => [];
    }

    [Fact]
    public void When_the_vault_fails_the_plain_copy_stays_rather_than_losing_the_pairing()
    {
        var settings = new InMemorySettings();
        settings.Set("EngineToken", "tok-old");
        _ = new EngineCredentials(new BrokenVault(), settings);
        Assert.Equal("tok-old", settings.Get<string?>("EngineToken", null));
    }

    [Fact]
    public void Several_engines_each_keep_their_own_record()
    {
        var credentials = new EngineCredentials(new InMemorySecretVault(), new InMemorySettings());
        credentials.Save(new EngineCredential(StudioId, "tok-studio"));
        credentials.Save(new EngineCredential("ffffffffffffffffffffffffffffffff", "tok-band"));
        Assert.Equal("tok-band", credentials.Current!.Token);
        Assert.Equal("tok-studio", credentials.Get(StudioId)!.Token);
        Assert.Equal(2, credentials.All().Count);
    }
}

public class PairingLinkTests
{
    private const string Id = "0123456789ABCDEF0123456789abcdef";

    [Fact]
    public void Parses_the_link_the_computer_shows()
    {
        // As companion.py writes it: urlencode(quote_via=quote, safe=":,").
        var text = $"brasscribe://pair?v=1&id={Id}&name=Brasscribe%20on%20Kalli%E2%80%99s%20Mac&h=192.168.1.20:8765,[fe80::1]:8765&code=482913";
        Assert.Equal(PairingLinkProblem.None, PairingLink.TryParse(text, out var link));
        Assert.Equal(Id.ToLowerInvariant(), link!.ServerId);
        Assert.Equal("Brasscribe on Kalli’s Mac", link.ServerName);
        Assert.Equal([new Uri("http://192.168.1.20:8765/"), new Uri("http://[fe80::1]:8765/")], link.Hosts);
        Assert.Equal("482913", link.Code);
        Assert.Equal("Kalli’s Mac", ServerNames.ComputerName(link.ServerName));
    }

    [Fact]
    public void Plus_is_a_space_unknown_keys_are_ignored_and_code_and_hosts_are_optional()
    {
        Assert.Equal(PairingLinkProblem.None, PairingLink.TryParse($"BRASSCRIBE://pair?v=1&id={Id}&name=Brasscribe+on+studio&future=1", out var link));
        Assert.Equal("Brasscribe on studio", link!.ServerName);
        Assert.Empty(link.Hosts);
        Assert.Null(link.Code);
    }

    [Theory]
    [InlineData("https://example.com/pair?v=1", PairingLinkProblem.NotAPairingLink)]
    [InlineData("brasscribe://open?v=1&id=0123456789abcdef0123456789abcdef", PairingLinkProblem.NotAPairingLink)]
    [InlineData("brasscribe://pair?id=0123456789abcdef0123456789abcdef", PairingLinkProblem.NotAPairingLink)]
    [InlineData("brasscribe://pair?v=2&id=0123456789abcdef0123456789abcdef", PairingLinkProblem.NewerVersion)]
    [InlineData("brasscribe://pair?v=1&id=1234", PairingLinkProblem.BadServerId)]
    [InlineData("brasscribe://pair?v=1&id=0123456789abcdef0123456789abcdeg", PairingLinkProblem.BadServerId)]
    [InlineData("brasscribe://pair?v=1&id=0123456789abcdef0123456789abcdef&fp=abc", PairingLinkProblem.NeedsPinning)]
    [InlineData("", PairingLinkProblem.NotAPairingLink)]
    public void Refuses_what_it_cannot_use_safely(string text, PairingLinkProblem expected)
    {
        Assert.Equal(expected, PairingLink.TryParse(text, out var link));
        Assert.Null(link);
    }

    [Theory]
    [InlineData("10.0.0.2:8765", "http://10.0.0.2:8765/")]
    [InlineData("[::1]:9000", "http://[::1]:9000/")]
    [InlineData("10.0.0.2", null)]
    [InlineData("10.0.0.2:0", null)]
    [InlineData("fe80::1:8765", null)]
    public void Host_addresses(string text, string? expected) =>
        Assert.Equal(expected, PairingLink.HostAddress(text)?.ToString());

    [Theory]
    [InlineData("Brasscribe on studio-mac", "studio-mac")]
    [InlineData("Brasscribe on studio-mac (2)", "studio-mac")]
    [InlineData("studio", "studio")]
    public void The_computer_part_of_a_server_name(string name, string computer) =>
        Assert.Equal(computer, ServerNames.ComputerName(name));
}

public class PairOnceTests
{
    private const string StudioId = "0123456789abcdef0123456789abcdef";
    private static readonly Uri Old = new("http://192.168.1.20:8765/");
    private static readonly Uri New = new("http://192.168.1.44:8765/");

    private static (SettingsViewModel Vm, FakeLan Lan, FakeLan.Engine Studio, InMemorySettings Settings, FakeTimeProvider Time, List<DiscoveredEngine> Network) Make()
    {
        var lan = new FakeLan();
        var studio = new FakeLan.Engine(StudioId, "Studio PC");
        lan.At[Old] = studio;
        var settings = new InMemorySettings();
        settings.Set("EngineAddress", Old.ToString());
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero));
        var network = new List<DiscoveredEngine>();
        var vm = new SettingsViewModel(settings, new Said(), ConnectionMonitorTests.Strings(), new FakeBrowse(() => network),
            new InMemorySecretVault(), lan.Client, time);
        return (vm, lan, studio, settings, time, network);
    }

    [Fact]
    public async Task Pairing_with_the_code_stores_the_credential_by_server_id_not_in_settings()
    {
        var (vm, lan, studio, settings, _, _) = Make();
        vm.PairingCode = "482 913".Replace(" ", "");
        await vm.ConnectCommand.ExecuteAsync(null);

        Assert.Equal("tok-paired-1", vm.EngineToken);
        Assert.Equal(StudioId, vm.Credentials.CurrentServerId);
        Assert.Equal("tok-paired-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.Null(settings.Get<string?>("EngineToken", null));
        Assert.Equal(["windows"], studio.Platforms);
        Assert.Equal("Connected to Brasscribe on Studio PC.", vm.EngineStatus);
        Assert.True(vm.IsPaired);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task A_valid_token_connects_without_pairing_again()
    {
        var (vm, _, studio, _, _, _) = Make();
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.PairingCode = "482913"; // typed again out of habit
        await vm.ConnectCommand.ExecuteAsync(null);
        Assert.Equal(1, studio.Pairings);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task A_stale_token_is_not_reported_as_connected_and_the_typed_code_pairs()
    {
        var (vm, _, studio, _, _, _) = Make();
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        studio.Tokens.Clear(); // the engine forgot this PC

        vm.PairingCode = "";
        await vm.ConnectCommand.ExecuteAsync(null);
        Assert.StartsWith("The computer no longer recognises this PC.", vm.EngineStatus);
        Assert.Null(vm.EngineToken);

        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        Assert.Equal(2, studio.Pairings);
        Assert.Equal("tok-paired-2", vm.EngineToken);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task A_wrong_code_says_so_in_plain_words()
    {
        var (vm, _, _, _, _, _) = Make();
        vm.PairingCode = "000000";
        await vm.ConnectCommand.ExecuteAsync(null);
        Assert.Equal("That code didn't work. Check the six digits on the computer and try again.", vm.EngineStatus);
        Assert.Null(vm.EngineToken);
    }

    [Fact]
    public async Task A_new_address_for_the_same_engine_keeps_the_token()
    {
        var (vm, _, _, _, _, _) = Make();
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        var token = vm.EngineToken;

        vm.UseEngineCommand.Execute(new DiscoveredEngine("Brasscribe on Studio PC", New, StudioId, "Studio PC"));
        Assert.Equal(New.ToString(), vm.EngineAddress);
        Assert.Equal(token, vm.EngineToken);
        Assert.Equal("Using Brasscribe on Studio PC. This PC is already paired with it.", vm.EngineStatus);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task Choosing_another_engine_keeps_the_first_ones_record_for_later()
    {
        var (vm, _, _, _, _, _) = Make();
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);

        var band = new DiscoveredEngine("Brasscribe on Band laptop", New, "ffffffffffffffffffffffffffffffff", "Band laptop");
        vm.UseEngineCommand.Execute(band);
        Assert.Null(vm.EngineToken);
        Assert.NotNull(vm.Credentials.Get(StudioId));

        vm.UseEngineCommand.Execute(new DiscoveredEngine("Brasscribe on Studio PC", Old, StudioId, "Studio PC"));
        Assert.Equal("tok-paired-1", vm.EngineToken);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task Allowing_on_the_computer_needs_no_code()
    {
        var (vm, _, studio, _, time, _) = Make();
        studio.Decision = (2, "approved");
        var ask = vm.AskComputerCommand.ExecuteAsync(null);
        await Until(() => vm.MatchCode is not null);
        Assert.Equal("4821", vm.MatchCode);
        Assert.Equal("4 8 2 1", vm.MatchCodeSpoken);
        Assert.Equal("On the computer, choose Allow when it shows this number: 4821", vm.EngineStatus);
        for (int i = 0; i < 3 && !ask.IsCompleted; i++)
        {
            time.Advance(SettingsViewModel.AskPollInterval);
            await Task.Delay(20);
        }
        await ask;
        Assert.Null(vm.MatchCode);
        Assert.Equal("tok-approved", vm.Credentials.Get(StudioId)!.Token);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task Not_allowed_and_expired_say_so_and_can_be_asked_again()
    {
        var (vm, _, studio, _, time, _) = Make();
        studio.Decision = (1, "denied");
        var ask = vm.AskComputerCommand.ExecuteAsync(null);
        await Until(() => vm.MatchCode is not null);
        time.Advance(SettingsViewModel.AskPollInterval);
        await ask;
        Assert.Equal("The computer didn't allow this PC. You can ask again.", vm.EngineStatus);
        Assert.False(vm.IsAsking);

        studio.Decision = null;
        studio.Polls = 0;
        ask = vm.AskComputerCommand.ExecuteAsync(null);
        await Until(() => vm.MatchCode is not null);
        for (int i = 0; i < 70 && !ask.IsCompleted; i++)
        {
            time.Advance(SettingsViewModel.AskPollInterval);
            await Task.Delay(5);
        }
        await ask;
        Assert.Equal("The computer didn't answer in time. You can ask again.", vm.EngineStatus);
    }

    [Fact]
    public async Task A_pairing_link_finds_its_engine_by_server_id_and_pairs_with_its_code()
    {
        var (vm, lan, studio, _, _, _) = Make();
        lan.At.Remove(Old);
        lan.At[New] = studio;
        lan.At[new Uri("http://10.0.0.5:8765/")] = new FakeLan.Engine("ffffffffffffffffffffffffffffffff", "Other");
        var link = $"brasscribe://pair?v=1&id={StudioId}&name=Brasscribe%20on%20Studio%20PC&h=10.0.0.5:8765,192.168.1.44:8765&code=482913";

        Assert.True(await vm.PairFromLinkAsync(link));
        Assert.Equal(New.ToString(), vm.EngineAddress);
        Assert.Equal("tok-paired-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.Equal(1, studio.Pairings);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task A_pairing_link_without_addresses_looks_on_the_network()
    {
        var (vm, lan, studio, _, _, network) = Make();
        lan.At.Remove(Old);
        lan.At[New] = studio;
        network.Add(new DiscoveredEngine("Brasscribe on Studio PC", New, StudioId, "Studio PC"));
        Assert.True(await vm.PairFromLinkAsync($"brasscribe://pair?v=1&id={StudioId}&name=Brasscribe%20on%20Studio%20PC&code=482913"));
        Assert.Equal(New.ToString(), vm.EngineAddress);
        vm.Connection.Stop();
    }

    [Fact]
    public async Task A_link_from_a_newer_app_or_with_a_pin_is_refused()
    {
        var (vm, lan, _, _, _, _) = Make();
        Assert.False(await vm.PairFromLinkAsync($"brasscribe://pair?v=2&id={StudioId}"));
        Assert.Equal("That link is from a newer Brasscribe. Update this app, then try again.", vm.EngineStatus);
        Assert.False(await vm.PairFromLinkAsync($"brasscribe://pair?v=1&id={StudioId}&h=192.168.1.20:8765&code=482913&fp=abc"));
        Assert.Empty(lan.Requests);
    }

    [Fact]
    public async Task Unpair_forgets_on_both_sides()
    {
        var (vm, _, studio, _, _, _) = Make();
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        await vm.UnpairCommand.ExecuteAsync(null);
        Assert.Empty(studio.Tokens);
        Assert.Null(vm.Credentials.Get(StudioId));
        Assert.False(vm.IsPaired);
        vm.Connection.Stop();
    }

    private static async Task Until(Func<bool> condition)
    {
        for (int i = 0; i < 200 && !condition(); i++) await Task.Delay(10);
        Assert.True(condition());
    }
}

using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The app and the engine must have the same interface version. When they differ the app says which of the two to
/// update and asks that engine for nothing but its health: no heartbeat on the device, no pairing, no job; the
/// stored pairing stays.
/// </summary>
public class InterfaceVersionTests
{
    private const string StudioId = "0123456789abcdef0123456789abcdef";
    private static readonly Uri Old = new("http://192.0.2.20:8765/");
    private static readonly Uri New = new("http://192.0.2.44:8765/");

    private const string UpdateBandroom = "Update Brasscribe on your computer. This app is newer than Brasscribe there, and they only work together when both are up to date.";
    private const string UpdateApp = "Update Brasscribe Play. Brasscribe on your computer is newer than this app, and they only work together when both are up to date.";

    [Theory]
    [InlineData(Wire.InterfaceVersion, InterfaceAnswer.Same)]
    [InlineData(Wire.InterfaceVersion + 1, InterfaceAnswer.UpdateApp)]
    [InlineData(Wire.InterfaceVersion - 1, InterfaceAnswer.UpdateBandroom)]
    [InlineData(null, InterfaceAnswer.UpdateBandroom)]
    public void The_engines_number_is_the_same_newer_older_or_missing(int? engine, InterfaceAnswer expected) =>
        Assert.Equal(expected, InterfaceMatch.Of(engine));

    [Fact]
    public async Task Health_carries_the_number_and_an_engine_from_before_it_has_none()
    {
        var lan = new FakeLan();
        var studio = lan.At[Old] = new FakeLan.Engine(StudioId, "Studio PC");
        Assert.Equal(Wire.InterfaceVersion, (await lan.Client(Old, null).GetHealthAsync()).InterfaceVersion);
        studio.InterfaceVersion = null;
        Assert.Null((await lan.Client(Old, null).GetHealthAsync()).InterfaceVersion);
    }

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
            Credentials.Save(new EngineCredential(StudioId, "tok-1"));
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
        // Not "pair again" and not "looking for": no button, and the pairing is kept.
        Assert.False(rig.Monitor.HasAction);
        Assert.Equal("", rig.Monitor.ActionText);
        Assert.False(asked);
        Assert.Equal("tok-1", rig.Credentials.Get(StudioId)!.Token);
        Assert.All(rig.Lan.Requests, r => Assert.Equal("/v1/health", r.Path));
        // The numbers are never the message.
        Assert.DoesNotContain(rig.Monitor.StatusText, char.IsDigit);
        // It keeps checking, so the row follows the update without pairing again.
        Assert.Equal(ConnectionMonitor.HeartbeatInterval, rig.Monitor.NextDelay);
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
    }

    [Fact]
    public async Task The_sentence_is_in_norwegian_too()
    {
        var rig = new Rig("nb-NO");
        rig.Studio.InterfaceVersion = 0;
        await rig.Monitor.CheckAsync();
        Assert.Equal("Oppdater Brasscribe på datamaskinen. Denne appen er nyere enn Brasscribe der, og de virker bare sammen når begge er oppdatert.", rig.Monitor.StatusText);
        rig.Studio.InterfaceVersion = 2;
        await rig.Monitor.CheckAsync();
        Assert.Equal("Oppdater Brasscribe Play. Brasscribe på datamaskinen er nyere enn denne appen, og de virker bare sammen når begge er oppdatert.", rig.Monitor.StatusText);
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
        Assert.DoesNotContain(rig.Lan.Requests, r => r.Address == New && r.Path != "/v1/health");
    }

    [Fact]
    public async Task Another_engine_at_the_address_is_not_ours_to_update()
    {
        var rig = new Rig();
        rig.Lan.At[Old] = new FakeLan.Engine("ffffffffffffffffffffffffffffffff", "Other") { InterfaceVersion = 0 };
        var state = await rig.Monitor.CheckAsync();
        Assert.False(rig.Monitor.NeedsUpdate);
        Assert.NotEqual(ConnectionState.NeedsPairing, state);
        Assert.NotNull(rig.Credentials.Get(StudioId));
    }

    [Fact]
    public async Task With_nothing_paired_the_row_still_says_which_to_update()
    {
        var rig = new Rig();
        rig.Credentials.Remove(StudioId);
        rig.Studio.InterfaceVersion = 0;
        rig.Studio.AuthRequired = false;
        Assert.Equal(ConnectionState.UpdateBandroom, await rig.Monitor.CheckAsync());
    }

    private static (SettingsViewModel Vm, FakeLan Lan, FakeLan.Engine Studio) Settings(int? engine, string? pairedWith = null)
    {
        var lan = new FakeLan();
        var studio = lan.At[Old] = new FakeLan.Engine(StudioId, "Studio PC") { InterfaceVersion = engine };
        var settings = new InMemorySettings();
        settings.Set("EngineAddress", Old.ToString());
        var vault = new InMemorySecretVault();
        if (pairedWith is not null) new EngineCredentials(vault, settings).Save(new EngineCredential(StudioId, pairedWith));
        var vm = new SettingsViewModel(settings, new Said(), ConnectionMonitorTests.Strings(), new FakeBrowse(() => []),
            vault, lan.Client, new FakeTimeProvider(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero)));
        return (vm, lan, studio);
    }

    // A copy: the status row's own check may still be asking health.
    private static void OnlyHealthWasAsked(FakeLan lan)
    {
        (Uri Address, string Path, string? Token)[] asked;
        lock (lan.Requests) asked = [.. lan.Requests];
        Assert.All(asked, r => Assert.Equal("/v1/health", r.Path));
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
        OnlyHealthWasAsked(lan);
    }

    [Fact]
    public async Task Asking_the_computer_sends_no_request_to_allow()
    {
        var (vm, lan, studio) = Settings(0);
        await vm.AskComputerCommand.ExecuteAsync(null);
        vm.Connection.Stop();

        Assert.Equal(UpdateBandroom, vm.EngineStatus);
        Assert.False(vm.IsAsking);
        Assert.Equal(0, studio.Polls);
        OnlyHealthWasAsked(lan);
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
        OnlyHealthWasAsked(lan);
    }

    [Fact]
    public async Task Connect_keeps_the_stored_pairing_and_it_works_again_after_the_update()
    {
        var (vm, lan, studio) = Settings(0, pairedWith: "tok-1");
        studio.Tokens.Add("tok-1");
        Assert.True(vm.IsPaired);

        // A typed code is not sent either, and the stored token is not tried.
        vm.PairingCode = "482913";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();
        Assert.Equal(UpdateBandroom, vm.EngineStatus);
        Assert.Equal("tok-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.True(vm.IsPaired);
        OnlyHealthWasAsked(lan);

        studio.InterfaceVersion = Wire.InterfaceVersion;
        vm.PairingCode = "";
        await vm.ConnectCommand.ExecuteAsync(null);
        vm.Connection.Stop();
        Assert.Equal("Connected to Brasscribe on Studio PC.", vm.EngineStatus);
        Assert.Equal("tok-1", vm.Credentials.Get(StudioId)!.Token);
        Assert.Equal(0, studio.Pairings);
    }
}

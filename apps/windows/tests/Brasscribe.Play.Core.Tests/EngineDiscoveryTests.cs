using System.Text;
using System.Xml.Linq;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

public class EngineDiscoveryTests
{
    /// <summary>A response like python-zeroconf's: PTR answer, SRV and A additionals, names compressed.</summary>
    private static byte[] Response(string instance, string host, int port, params byte[][] ips) => Response(instance, host, port, null, ips);

    private static byte[] Response(string instance, string host, int port, string[]? txt, params byte[][] ips)
    {
        var m = new List<byte> { 0, 0, 0x84, 0, 0, 0, 0, 1, 0, 0, 0, (byte)(1 + ips.Length + (txt is null ? 0 : 1)) };
        static List<byte> Labels(params string[] labels)
        {
            var b = new List<byte>();
            foreach (var l in labels) { var s = Encoding.UTF8.GetBytes(l); b.Add((byte)s.Length); b.AddRange(s); }
            return b;
        }
        int Record(ushort type, List<byte> rdata)
        {
            m.AddRange([(byte)(type >> 8), (byte)type, 0x80, 1, 0, 0, 0x11, 0x94, (byte)(rdata.Count >> 8), (byte)rdata.Count]);
            var at = m.Count;
            m.AddRange(rdata);
            return at;
        }

        var serviceAt = m.Count;
        m.AddRange([.. Labels("_brasscribe", "_tcp", "local"), 0]);
        var instanceAt = Record(12, [.. Labels(instance), 0xC0, (byte)serviceAt]);
        m.AddRange([0xC0, (byte)instanceAt]);
        Record(33, [0, 0, 0, 0, (byte)(port >> 8), (byte)port, .. Labels(host, "local"), 0]);
        if (txt is not null)
        {
            m.AddRange([0xC0, (byte)instanceAt]);
            Record(16, Labels(txt));
        }
        foreach (var ip in ips)
        {
            m.AddRange([.. Labels(host, "local"), 0]);
            Record(1, [.. ip]);
        }
        return [.. m];
    }

    [Fact]
    public void Ptr_query_asks_for_the_service_with_a_unicast_response()
    {
        var q = DnsSd.BuildPtrQuery(EngineDiscovery.ServiceType);
        Assert.Equal([0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 11], q[..13]);
        Assert.Equal([0, 0, 12, 0x80, 0x01], q[^5..]);
    }

    [Fact]
    public void Parses_ptr_srv_and_a_into_an_engine()
    {
        var records = new DnsSdRecords();
        records.Add(Response("Brasscribe on studio", "studio", 8765, [192, 168, 10, 95]));
        var engine = Assert.Single(records.Engines(EngineDiscovery.ServiceType));
        Assert.Equal("Brasscribe on studio", engine.Name);
        Assert.Equal(new Uri("http://192.168.10.95:8765/"), engine.BaseAddress);
    }

    [Fact]
    public void Reads_the_server_id_and_computer_name_from_the_txt_record()
    {
        var records = new DnsSdRecords();
        records.Add(Response("Brasscribe on Studio PC (2)", "studio", 8765,
            ["v=0.4.0", "api=/v1", "auth=pair", "id=0123456789abcdef0123456789abcdef", "host=Studio PC"], [192, 168, 10, 95]));
        var engine = Assert.Single(records.Engines(EngineDiscovery.ServiceType));
        Assert.Equal("0123456789abcdef0123456789abcdef", engine.ServerId);
        Assert.Equal("Studio PC", engine.Host);
        Assert.Equal("Studio PC", engine.ComputerName);
    }

    [Fact]
    public void Engines_without_a_txt_id_still_show_by_name()
    {
        var records = new DnsSdRecords();
        records.Add(Response("Brasscribe on studio (2)", "studio", 8765, [10, 0, 0, 2]));
        var engine = Assert.Single(records.Engines(EngineDiscovery.ServiceType));
        Assert.Null(engine.ServerId);
        Assert.Equal("studio", engine.ComputerName);
    }

    [Fact]
    public void Prefers_a_private_address_over_vpn_and_cgnat_ones()
    {
        var records = new DnsSdRecords();
        records.Add(Response("Brasscribe on studio", "studio", 8765, [100, 64, 0, 1], [192, 168, 10, 95]));
        var engine = Assert.Single(records.Engines(EngineDiscovery.ServiceType, a => EngineDiscovery.Rank(a, [])));
        Assert.Equal(new Uri("http://192.168.10.95:8765/"), engine.BaseAddress);
    }

    [Fact]
    public void Ignores_truncated_and_unrelated_messages()
    {
        var records = new DnsSdRecords();
        var full = Response("Brasscribe on studio", "studio", 8765, [10, 0, 0, 2]);
        records.Add(full[..40]);
        records.Add([1, 2, 3]);
        Assert.Empty(records.Engines(EngineDiscovery.ServiceType));
    }

    private sealed class FakeDiscovery(params DiscoveredEngine[] engines) : IEngineDiscovery
    {
        public Task<IReadOnlyList<DiscoveredEngine>> BrowseAsync(TimeSpan duration, CancellationToken ct = default) =>
            Task.FromResult<IReadOnlyList<DiscoveredEngine>>(engines);
    }

    private sealed class Silent : IAnnouncer
    {
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) { }
    }

    private static IStrings Strings() => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));

    [Fact]
    public async Task Choosing_a_found_engine_sets_the_address_and_keeps_its_credential()
    {
        var studio = new DiscoveredEngine("Brasscribe on studio", new Uri("http://192.168.10.95:8765/"), "0123456789abcdef0123456789abcdef", "studio");
        var vm = new SettingsViewModel(new InMemorySettings(), new Silent(), Strings(), new FakeDiscovery(studio));
        vm.Credentials.Save(new EngineCredential("0123456789abcdef0123456789abcdef", "tok", LastAddress: "http://192.168.10.20:8765/"));

        await vm.FindEnginesCommand.ExecuteAsync(null);
        Assert.Equal([studio], vm.DiscoveredEngines);
        Assert.Contains("Brasscribe on studio", vm.EngineStatus);

        // The same engine at another address: the credential belongs to its server id, not the address.
        vm.UseEngineCommand.Execute(studio);
        Assert.Equal("http://192.168.10.95:8765/", vm.EngineAddress);
        Assert.Equal("tok", vm.EngineToken);
    }
}

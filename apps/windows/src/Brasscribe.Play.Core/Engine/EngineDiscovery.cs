using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;

namespace Brasscribe.Play.Core.Engine;

/// <summary>An engine found on the local network.</summary>
public sealed record DiscoveredEngine(string Name, Uri BaseAddress)
{
    public string Address => BaseAddress.ToString();
}

public interface IEngineDiscovery
{
    Task<IReadOnlyList<DiscoveredEngine>> BrowseAsync(TimeSpan duration, CancellationToken ct = default);
}

/// <summary>
/// Finds engines that advertise <c>_brasscribe._tcp</c> over mDNS (<c>brasscribe serve --lan</c>).
/// Queries go out from an ephemeral port, so responders answer by unicast (RFC 6762 §6.7) and nothing
/// competes with the Windows mDNS service for port 5353. Discovery only suggests addresses; pairing is still required.
/// </summary>
public sealed class EngineDiscovery : IEngineDiscovery
{
    public const string ServiceType = "_brasscribe._tcp.local";
    private static readonly IPEndPoint Group = new(IPAddress.Parse("224.0.0.251"), 5353);

    public async Task<IReadOnlyList<DiscoveredEngine>> BrowseAsync(TimeSpan duration, CancellationToken ct = default)
    {
        var records = new DnsSdRecords();
        var query = DnsSd.BuildPtrQuery(ServiceType);
        var local = LocalAddresses().ToList();
        var clients = local.Select(a => Open(a.Address)).OfType<UdpClient>().ToList();
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(duration);
            var receivers = clients.Select(c => ReceiveAsync(c, records, cts.Token)).ToList();
            // A second query covers a lost first packet.
            for (var attempt = 0; attempt < 2 && !cts.IsCancellationRequested; attempt++)
            {
                foreach (var c in clients) await SendAsync(c, query);
                try { await Task.Delay(duration / 3, cts.Token); } catch (OperationCanceledException) { }
            }
            await Task.WhenAll(receivers);
        }
        finally
        {
            foreach (var c in clients) c.Dispose();
        }
        ct.ThrowIfCancellationRequested();
        lock (records) return records.Engines(ServiceType, a => Rank(a, local));
    }

    /// <summary>Engines often advertise VPN and virtual-adapter addresses too: prefer one on a local subnet, then a private one.</summary>
    internal static int Rank(IPAddress candidate, IReadOnlyList<UnicastIPAddressInformation> local)
    {
        var c = candidate.GetAddressBytes();
        foreach (var l in local)
        {
            var a = l.Address.GetAddressBytes();
            var mask = l.IPv4Mask.GetAddressBytes();
            if (mask.Length == 4 && mask.Any(b => b != 0) && mask.Any(b => b != 255) && Enumerable.Range(0, 4).All(i => (a[i] & mask[i]) == (c[i] & mask[i]))) return 0;
        }
        return c[0] == 10 || (c[0] == 172 && (c[1] & 0xF0) == 16) || (c[0] == 192 && c[1] == 168) ? 1 : 2;
    }

    private static IEnumerable<UnicastIPAddressInformation> LocalAddresses() =>
        NetworkInterface.GetAllNetworkInterfaces()
            .Where(n => n.OperationalStatus == OperationalStatus.Up && n.SupportsMulticast && n.NetworkInterfaceType != NetworkInterfaceType.Loopback)
            .SelectMany(n => n.GetIPProperties().UnicastAddresses)
            .Where(a => a.Address.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(a.Address));

    private static UdpClient? Open(IPAddress local)
    {
        try
        {
            var c = new UdpClient(new IPEndPoint(local, 0));
            c.Client.SetSocketOption(SocketOptionLevel.IP, SocketOptionName.MulticastInterface, local.GetAddressBytes());
            c.Client.SetSocketOption(SocketOptionLevel.IP, SocketOptionName.MulticastTimeToLive, 255);
            return c;
        }
        catch (SocketException) { return null; }
    }

    private static async Task SendAsync(UdpClient c, byte[] query)
    {
        try { await c.SendAsync(query, Group); } catch (SocketException) { }
    }

    private static async Task ReceiveAsync(UdpClient c, DnsSdRecords records, CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                var r = await c.ReceiveAsync(ct);
                lock (records) records.Add(r.Buffer);
            }
        }
        catch (OperationCanceledException) { }
        catch (SocketException) { }
        catch (ObjectDisposedException) { }
    }
}

/// <summary>The few DNS record types DNS-SD needs, gathered from any number of mDNS responses.</summary>
internal sealed class DnsSdRecords
{
    private readonly Dictionary<string, HashSet<string>> _ptr = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, (string Target, int Port)> _srv = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, List<IPAddress>> _a = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>Adds the records of one DNS message; malformed messages are ignored.</summary>
    public void Add(byte[] message)
    {
        try { DnsSd.Parse(message, this); } catch (Exception e) when (e is IndexOutOfRangeException or ArgumentOutOfRangeException or InvalidDataException) { }
    }

    internal void AddPtr(string name, string instance)
    {
        if (!_ptr.TryGetValue(name, out var set)) _ptr[name] = set = new(StringComparer.OrdinalIgnoreCase);
        set.Add(instance);
    }

    internal void AddSrv(string instance, string target, int port) => _srv[instance] = (target, port);
    internal void AddA(string host, IPAddress address)
    {
        if (!_a.TryGetValue(host, out var list)) _a[host] = list = [];
        if (!list.Contains(address)) list.Add(address);
    }

    /// <summary>One engine per advertised instance; <paramref name="rank"/> picks among its addresses (lowest wins).</summary>
    public IReadOnlyList<DiscoveredEngine> Engines(string serviceType, Func<IPAddress, int>? rank = null)
    {
        if (!_ptr.TryGetValue(serviceType, out var instances)) return [];
        var engines = new List<DiscoveredEngine>();
        foreach (var instance in instances.Order(StringComparer.OrdinalIgnoreCase))
        {
            if (!_srv.TryGetValue(instance, out var srv) || !_a.TryGetValue(srv.Target, out var ips)) continue;
            var ip = rank is null ? ips[0] : ips.OrderBy(rank).First();
            var name = instance.EndsWith("." + serviceType, StringComparison.OrdinalIgnoreCase) ? instance[..^(serviceType.Length + 1)] : instance;
            engines.Add(new DiscoveredEngine(name, new Uri($"http://{ip}:{srv.Port}/")));
        }
        return engines;
    }
}

internal static class DnsSd
{
    private const ushort TypeA = 1, TypePtr = 12, TypeSrv = 33;

    /// <summary>A one-question PTR query with the unicast-response bit set.</summary>
    public static byte[] BuildPtrQuery(string serviceType)
    {
        var bytes = new List<byte>(64) { 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0 };
        foreach (var label in serviceType.Split('.'))
        {
            var l = Encoding.UTF8.GetBytes(label);
            bytes.Add((byte)l.Length);
            bytes.AddRange(l);
        }
        bytes.AddRange([0, 0, (byte)TypePtr, 0x80, 0x01]);
        return [.. bytes];
    }

    public static void Parse(byte[] m, DnsSdRecords into)
    {
        if (m.Length < 12) throw new InvalidDataException();
        var questions = U16(m, 4);
        var records = U16(m, 6) + U16(m, 8) + U16(m, 10);
        var pos = 12;
        for (var i = 0; i < questions; i++)
        {
            ReadName(m, ref pos);
            pos += 4;
        }
        for (var i = 0; i < records; i++)
        {
            var name = ReadName(m, ref pos);
            var type = U16(m, pos);
            var length = U16(m, pos + 8);
            var data = pos + 10;
            if (data + length > m.Length) throw new InvalidDataException();
            switch (type)
            {
                case TypePtr:
                    var p = data;
                    into.AddPtr(name, ReadName(m, ref p));
                    break;
                case TypeSrv:
                    var s = data + 6;
                    into.AddSrv(name, ReadName(m, ref s), U16(m, data + 4));
                    break;
                case TypeA when length == 4:
                    into.AddA(name, new IPAddress(m.AsSpan(data, 4)));
                    break;
            }
            pos = data + length;
        }
    }

    private static int U16(byte[] m, int at) => (m[at] << 8) | m[at + 1];

    private static string ReadName(byte[] m, ref int pos)
    {
        var labels = new List<string>();
        var at = pos;
        var jumped = false;
        for (var hops = 0; ; hops++)
        {
            if (hops > 64) throw new InvalidDataException();
            int len = m[at];
            if (len == 0)
            {
                if (!jumped) pos = at + 1;
                break;
            }
            if ((len & 0xC0) == 0xC0)
            {
                if (!jumped) pos = at + 2;
                at = ((len & 0x3F) << 8) | m[at + 1];
                jumped = true;
                continue;
            }
            labels.Add(Encoding.UTF8.GetString(m, at + 1, len));
            at += 1 + len;
        }
        return string.Join('.', labels);
    }
}

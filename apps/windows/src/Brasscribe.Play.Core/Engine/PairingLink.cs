using System.Globalization;

namespace Brasscribe.Play.Core.Engine;

/// <summary>Why a pairing link was not used.</summary>
public enum PairingLinkProblem { None, NotAPairingLink, NewerVersion, BadServerId, NeedsPinning }

/// <summary>
/// The pairing payload the computer shows as a QR code and link:
/// <c>brasscribe://pair?v=1&amp;id=&lt;server_id&gt;&amp;name=&lt;name&gt;&amp;h=ip:port,...&amp;code=&lt;6 digits&gt;[&amp;fp=&lt;spki&gt;]</c>
/// (docs/plan/pairing-and-remote-access.md §4.2). Unknown keys are ignored.
/// </summary>
public sealed record PairingLink(string ServerId, string ServerName, IReadOnlyList<Uri> Hosts, string? Code, string? Fingerprint)
{
    public const string Scheme = "brasscribe";

    /// <summary>
    /// Parses a link. A major version other than 1 or a server id that is not 32 hex digits is refused.
    /// A link with a TLS fingerprint is refused too until this app can pin it: connecting unpinned would
    /// ignore the one thing the fingerprint is for.
    /// </summary>
    public static PairingLinkProblem TryParse(string? text, out PairingLink? link)
    {
        link = null;
        if (string.IsNullOrWhiteSpace(text) || !Uri.TryCreate(text.Trim(), UriKind.Absolute, out var uri)
            || !uri.Scheme.Equals(Scheme, StringComparison.OrdinalIgnoreCase)
            || !uri.Host.Equals("pair", StringComparison.OrdinalIgnoreCase))
            return PairingLinkProblem.NotAPairingLink;

        var q = Query(uri.Query);
        if (!q.TryGetValue("v", out var v) || !int.TryParse(v.Split('.')[0], NumberStyles.None, CultureInfo.InvariantCulture, out int major))
            return PairingLinkProblem.NotAPairingLink;
        if (major != 1) return PairingLinkProblem.NewerVersion;

        if (!q.TryGetValue("id", out var id) || id.Length != 32 || !id.All(Uri.IsHexDigit)) return PairingLinkProblem.BadServerId;
        if (q.TryGetValue("fp", out var fp) && fp.Length > 0) return PairingLinkProblem.NeedsPinning;

        var hosts = new List<Uri>();
        if (q.TryGetValue("h", out var h))
            foreach (var part in h.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                if (HostAddress(part) is { } address) hosts.Add(address);

        string? code = q.TryGetValue("code", out var c) ? new string(c.Where(char.IsAsciiDigit).ToArray()) : null;
        link = new PairingLink(id.ToLowerInvariant(), q.GetValueOrDefault("name") ?? "", hosts, string.IsNullOrEmpty(code) ? null : code, null);
        return PairingLinkProblem.None;
    }

    /// <summary>"192.0.2.20:8765" or "[fe80::1]:8765" as an http base address.</summary>
    public static Uri? HostAddress(string hostPort)
    {
        string host;
        string port;
        if (hostPort.StartsWith('['))
        {
            int close = hostPort.IndexOf(']');
            if (close < 0 || close + 1 >= hostPort.Length || hostPort[close + 1] != ':') return null;
            host = hostPort[..(close + 1)];
            port = hostPort[(close + 2)..];
        }
        else
        {
            int colon = hostPort.LastIndexOf(':');
            if (colon <= 0 || hostPort.IndexOf(':') != colon) return null;
            host = hostPort[..colon];
            port = hostPort[(colon + 1)..];
        }
        if (!int.TryParse(port, NumberStyles.None, CultureInfo.InvariantCulture, out int p) || p is < 1 or > 65535) return null;
        return Uri.TryCreate($"http://{host}:{p}/", UriKind.Absolute, out var u) ? u : null;
    }

    private static Dictionary<string, string> Query(string query)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            int eq = pair.IndexOf('=');
            string key = Decode(eq < 0 ? pair : pair[..eq]);
            string value = eq < 0 ? "" : Decode(pair[(eq + 1)..]);
            values.TryAdd(key, value);
        }
        return values;
    }

    // The engine percent-encodes (a space is %20), but "+" as a space is accepted too: a literal "+" is always %2B.
    private static string Decode(string s) => Uri.UnescapeDataString(s.Replace('+', ' '));
}

using Brasscribe.Bandroom.Core.Engine;

namespace Brasscribe.Bandroom.Core.ViewModels;

/// <summary>One row of Phones and tablets (§8).</summary>
public sealed record DeviceRow(string Id, string Name, string Subtitle, bool IsOnline, bool IsTablet, string RemoveText, string RemoveName, string TechLine)
{
    /// <summary>Row name for screen readers: "Kari's iPhone, Connected now".</summary>
    public string AccessibleName => Name + ", " + Subtitle;
}

public static class DeviceText
{
    /// <summary>Online when the engine says so; engines without presence count "seen in the last minute".</summary>
    public static bool IsOnline(DeviceInfo d, DateTimeOffset now) =>
        d.Online ?? (d.LastSeenAt is { } t && now - t <= TimeSpan.FromSeconds(60));

    public static bool IsTablet(DeviceInfo d) =>
        d.Name.Contains("iPad", StringComparison.OrdinalIgnoreCase) || d.Name.Contains("tablet", StringComparison.OrdinalIgnoreCase)
        || d.Name.Contains("nettbrett", StringComparison.OrdinalIgnoreCase) || d.Platform is "ipados";

    /// <summary>"Connected now", "Last used today", "Last used yesterday", "Last used 3 days ago", "Last used 26 September" / "26. september".</summary>
    public static string Subtitle(DeviceInfo d, DateTimeOffset now, IStrings s)
    {
        if (IsOnline(d, now)) return s["Devices_Connected"];
        if (d.LastSeenAt is not { } seen) return s["Devices_Connected_Never"];
        var local = seen.ToLocalTime().Date;
        int days = (int)(now.ToLocalTime().Date - local).TotalDays;
        string when = days switch
        {
            <= 0 => s["Devices_When_Today"],
            1 => s["Devices_When_Yesterday"],
            < 7 => s.Format("Devices_When_DaysAgo", days),
            _ => local.ToString(s.Language == "nb" ? "d. MMMM" : "d MMMM", s.Culture),
        };
        return s.Format("Devices_LastUsed", when);
    }

    /// <summary>Connected first, then by last use, newest first.</summary>
    public static IReadOnlyList<DeviceRow> Rows(IEnumerable<DeviceInfo> devices, DateTimeOffset now, IStrings s) =>
        devices
            .OrderByDescending(d => IsOnline(d, now))
            .ThenByDescending(d => d.LastSeenAt ?? DateTimeOffset.MinValue)
            .Select(d => new DeviceRow(d.DeviceId, d.Name, Subtitle(d, now, s), IsOnline(d, now), IsTablet(d),
                s["Devices_Remove"], s.Format("Devices_Remove_A11y", d.Name),
                $"{d.DeviceId[..Math.Min(8, d.DeviceId.Length)]} · {d.Platform} · {d.PairedAt}"))
            .ToList();

    /// <summary>"2 connected now · 3 paired" or "None connected now · 3 paired".</summary>
    public static string Summary(int online, int paired, IStrings s) =>
        online == 0 ? s.Format("Devices_Summary_None", paired) : s.Format("Devices_Summary", online, paired);
}

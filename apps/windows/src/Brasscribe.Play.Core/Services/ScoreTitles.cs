using System.Globalization;
using System.Text.RegularExpressions;

namespace Brasscribe.Play.Core.Services;

/// <summary>
/// Titles for "Your scores" (usability review 3, P1-C): never a bare timestamp such as
/// "20260815_155324". The name the player gave wins; otherwise a file name without its extension;
/// a microphone capture, or a file named only by its date and time, becomes "Recording, 26 Sep 19:02".
/// </summary>
public static partial class ScoreTitles
{
    /// <summary>The title to show for a stored or offered title and the time the score was made.</summary>
    public static string Display(string? title, DateTimeOffset made, IStrings s)
    {
        string t = (title ?? "").Trim();
        if (t.Length > 0 && Path.HasExtension(t) && KnownExtensions.Contains(Path.GetExtension(t).ToLowerInvariant()))
            t = Path.GetFileNameWithoutExtension(t).Trim();
        if (t.Length == 0 || t == s["Start_RecordingName"]) return Recording(made, s);
        if (TimestampRegex().Match(t) is { Success: true } m)
            return Recording(ParseStamp(m) ?? made, s);
        return t;
    }

    /// <summary>"Recording, 26 Sep 19:02" (nb "Opptak, 26. sep. 19:02").</summary>
    public static string Recording(DateTimeOffset when, IStrings s)
    {
        bool nb = s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || s.Language.StartsWith("no", StringComparison.OrdinalIgnoreCase);
        var culture = nb ? CultureInfo.GetCultureInfo("nb-NO") : CultureInfo.GetCultureInfo("en-GB");
        string stamp = when.ToLocalTime().ToString(nb ? "d. MMM HH:mm" : "d MMM HH:mm", culture);
        return s.Format("Library_RecordingTitle", stamp);
    }

    /// <summary>The same titles on several scores: which ones need the time added to tell them apart.</summary>
    public static HashSet<string> Duplicates(IEnumerable<string> titles) =>
        titles.GroupBy(t => t, StringComparer.CurrentCultureIgnoreCase).Where(g => g.Count() > 1).Select(g => g.Key)
            .ToHashSet(StringComparer.CurrentCultureIgnoreCase);

    private static readonly HashSet<string> KnownExtensions =
        [".wav", ".mp3", ".m4a", ".mp4", ".mov", ".aac", ".flac", ".ogg", ".wma", ".musicxml", ".mxl", ".xml"];

    private static DateTimeOffset? ParseStamp(Match m)
    {
        try
        {
            int year = int.Parse(m.Groups["y"].Value, CultureInfo.InvariantCulture);
            int month = int.Parse(m.Groups["mo"].Value, CultureInfo.InvariantCulture);
            int day = int.Parse(m.Groups["d"].Value, CultureInfo.InvariantCulture);
            int hour = m.Groups["h"].Success ? int.Parse(m.Groups["h"].Value, CultureInfo.InvariantCulture) : 0;
            int minute = m.Groups["mi"].Success ? int.Parse(m.Groups["mi"].Value, CultureInfo.InvariantCulture) : 0;
            var local = new DateTime(year, month, day, hour, minute, 0, DateTimeKind.Local);
            return new DateTimeOffset(local);
        }
        catch (Exception e) when (e is ArgumentOutOfRangeException or FormatException or OverflowException)
        {
            return null;
        }
    }

    /// <summary>
    /// A name that is only a date and time: "20260815_155324", "2026-08-15 15.53.24",
    /// "Recording 2026-08-15 155324", "REC_20260815-1553" and the like.
    /// </summary>
    [GeneratedRegex(@"^(?:(?:rec(?:ording)?|audio|voice|opptak|lyd|memo|img|vid)[\s_\-]*)?(?<y>20\d{2})[\-_.]?(?<mo>[01]\d)[\-_.]?(?<d>[0-3]\d)(?:[\sT_\-]*(?<h>[0-2]\d)[:._\-]?(?<mi>[0-5]\d)(?:[:._\-]?[0-5]\d)?(?:\d{0,3})?)?$",
        RegexOptions.IgnoreCase)]
    private static partial Regex TimestampRegex();
}

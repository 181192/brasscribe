using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// Something a catalogue check found on one screenshot.
/// </summary>
/// <param name="Shot">The screenshot's name (its file name without .png), e.g. "home--dark".</param>
/// <param name="Check">contrast, clipped, axe:&lt;rule&gt;, keyboard, contrast-theme.</param>
/// <param name="What">The element: its text, or its control type and name.</param>
/// <param name="Detail">What is wrong with it.</param>
public sealed record Finding(string Shot, string Check, string What, string Detail)
{
    public override string ToString() => $"{Shot}: {Check}: {What}: {Detail}";
}

/// <summary>
/// A finding that is known and accepted for now, with the issue that tracks it and why. An entry that matches nothing
/// any more is reported, so it is removed once its issue is fixed. Nothing is listed without an issue.
/// </summary>
/// <param name="Shot">A regular expression the whole screenshot name must match.</param>
/// <param name="What">A regular expression the whole element description must match.</param>
public sealed record KnownFinding(string Check, string Shot, string What, int Issue, string Why)
{
    public bool Matches(Finding f) =>
        f.Check == Check && Regex.IsMatch(f.Shot, $"^(?:{Shot})$") && Regex.IsMatch(f.What, $"^(?:{What})$");
}

/// <summary>What one run of a catalogue took and found (catalogue-&lt;run&gt;.json next to its screenshots).</summary>
public sealed class CatalogueRun
{
    /// <summary>The screenshots taken, by name.</summary>
    public List<string> Shots { get; set; } = [];

    /// <summary>
    /// Screens that did not keep still, from a catalogue that still kept a picture of them (the base of a comparison
    /// can be one): not compared. A screen that does not keep still is now not taken, and is in <see cref="Failed"/>.
    /// </summary>
    public List<string> Unsteady { get; set; } = [];

    /// <summary>Screens that could not be shown or captured, with why.</summary>
    public List<string> Failed { get; set; } = [];

    public List<Finding> Findings { get; set; } = [];

    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    public void Save(string path) => File.WriteAllText(path, JsonSerializer.Serialize(this, Json));

    public static CatalogueRun Load(string path) => JsonSerializer.Deserialize<CatalogueRun>(File.ReadAllText(path), Json) ?? new();

    /// <summary>The known findings; an entry without its issue is an error (InvalidDataException).</summary>
    public static List<KnownFinding> LoadKnown(string path)
    {
        var known = File.Exists(path) ? JsonSerializer.Deserialize<List<KnownFinding>>(File.ReadAllText(path), Json) ?? [] : [];
        foreach (var k in known)
            if (k.Issue <= 0 || string.IsNullOrWhiteSpace(k.Why))
                throw new InvalidDataException($"{path}: the known finding {k.Check} {k.Shot} {k.What} needs its issue and why");
        return known;
    }
}

/// <summary>The catalogue's answer over all its runs: what is new, what is known, and which known entries are stale.</summary>
public sealed record Verdict(int Shots, IReadOnlyList<string> Failed, IReadOnlyList<Finding> New, IReadOnlyList<Finding> Known,
    IReadOnlyList<KnownFinding> Stale, IReadOnlyList<string> Unsteady)
{
    /// <summary>
    /// 0 when every check passed, 2 when a check found something new, 3 when screens could not be taken (one that
    /// did not keep still is not taken either: nothing of it is compared).
    /// </summary>
    public int ExitCode => Shots == 0 || Failed.Count > 0 || Unsteady.Count > 0 ? 3 : New.Count > 0 ? 2 : 0;

    public static Verdict Of(IEnumerable<CatalogueRun> runs, IReadOnlyList<KnownFinding> known)
    {
        var all = runs.ToList();
        var findings = all.SelectMany(r => r.Findings).Distinct().ToList();
        var shots = all.SelectMany(r => r.Shots).ToList();
        return new Verdict(
            shots.Count,
            all.SelectMany(r => r.Failed).ToList(),
            findings.Where(f => !known.Any(k => k.Matches(f))).ToList(),
            findings.Where(f => known.Any(k => k.Matches(f))).ToList(),
            // Only entries for screenshots this catalogue took can be stale (a partial run says nothing of the rest).
            known.Where(k => !findings.Any(k.Matches) && shots.Any(s => Regex.IsMatch(s, $"^(?:{k.Shot})$"))).ToList(),
            all.SelectMany(r => r.Unsteady).ToList());
    }

    /// <summary>The findings as Markdown, for the job summary.</summary>
    public string Markdown(string title)
    {
        var lines = new List<string> { $"# {title}", "", $"{Shots} screenshots; {New.Count} new findings, {Known.Count} known, {Failed.Count + Unsteady.Count} screens not taken." };
        if (Failed.Count > 0) lines.AddRange(["", "## Not taken", .. Failed.Select(f => $"- {f}")]);
        if (New.Count > 0) lines.AddRange(["", "## New findings", .. New.Select(f => $"- `{f.Shot}` {f.Check}: {f.What}: {f.Detail}")]);
        if (Stale.Count > 0) lines.AddRange(["", "## Known findings that no longer occur (remove them from the list)", .. Stale.Select(k => $"- {k.Check} `{k.Shot}` `{k.What}` (#{k.Issue})")]);
        if (Known.Count > 0) lines.AddRange(["", "## Known findings", .. Known.Select(f => $"- `{f.Shot}` {f.Check}: {f.What}: {f.Detail}")]);
        if (Unsteady.Count > 0) lines.AddRange(["", "## Not compared (the screen did not keep still)", .. Unsteady.Select(s => $"- `{s}`")]);
        return string.Join("\n", lines) + "\n";
    }
}

using System.Text.Json;
using System.Text.RegularExpressions;

namespace Brasscribe.Play.Core.Playback;

/// <summary>A resolved part: the mapping.json part whose preset plays, which rule found it, and the sound.</summary>
public sealed record ResolvedPart(string Part, string Step, TrackSound Sound, string? Target);

/// <summary>
/// Score part → band SoundFont preset, following sounds/mapping.json <c>resolve</c> exactly (the
/// reference is sounds/partsound.py, the shared vectors sounds/partsound-vectors.json):
/// normalize, then exact part name, alias, first keyword contained in the name, instrument id or
/// MusicXML instrument-sound, 0-based GM program. A brass part never falls back to General MIDI;
/// only a non-brass program stays unresolved. A percussion part plays the kit its program selects
/// when that is in <c>kit_programs</c> (1, the pop kit), else the band kit; never silence.
/// </summary>
public sealed partial class PartSoundResolver
{
    private readonly Dictionary<string, (string Part, TrackSound Sound, string? Target)> _parts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _aliases = new(StringComparer.Ordinal);
    private readonly List<(string Text, string Part)> _keywords = [];
    private readonly Dictionary<string, string> _instruments = new(StringComparer.Ordinal);
    private readonly Dictionary<int, string> _programs = [];
    private readonly HashSet<int> _kitPrograms = [];

    public static PartSoundResolver Parse(string mappingJson)
    {
        using var doc = JsonDocument.Parse(mappingJson);
        var root = doc.RootElement;
        var r = new PartSoundResolver();
        foreach (var part in root.GetProperty("parts").EnumerateObject())
        {
            if (!part.Value.TryGetProperty("band_soundfont", out var b)) continue;
            int bank = b.GetProperty("bank").GetInt32();
            var sound = new TrackSound(b.GetProperty("program").GetInt32(), bank,
                b.TryGetProperty("channel_gain_db", out var g) ? g.GetDouble() : 0, bank == 128);
            string? target = part.Value.TryGetProperty("players", out var pl) && pl.GetArrayLength() > 0
                ? pl[0].GetProperty("target").GetString() : null;
            r._parts[Normalize(part.Name)] = (part.Name, sound, target);
        }
        if (root.TryGetProperty("resolve", out var res))
        {
            foreach (var a in res.GetProperty("aliases").EnumerateObject()) r._aliases[a.Name] = a.Value.GetString()!;
            foreach (var k in res.GetProperty("keywords").EnumerateArray()) r._keywords.Add((k[0].GetString()!, k[1].GetString()!));
            foreach (var i in res.GetProperty("instruments").EnumerateObject()) r._instruments[i.Name] = i.Value.GetString()!;
            foreach (var p in res.GetProperty("programs").EnumerateObject()) r._programs[int.Parse(p.Name)] = p.Value.GetString()!;
            if (res.TryGetProperty("kit_programs", out var kits))
                foreach (var k in kits.EnumerateArray()) r._kitPrograms.Add(k.GetInt32());
        }
        return r;
    }

    public static PartSoundResolver Load(string mappingPath) => Parse(File.ReadAllText(mappingPath));

    /// <summary>Every part name in mapping.json, as written there.</summary>
    public IEnumerable<string> PartNames => _parts.Values.Select(p => p.Part);

    public ResolvedPart? Resolve(string name, string? instrument = null, int? program = null)
    {
        string n = Normalize(name);
        string? hit = null, step = null;
        if (_parts.TryGetValue(n, out var exact)) (hit, step) = (exact.Part, "exact");
        else if (_aliases.TryGetValue(n, out var alias)) (hit, step) = (alias, "alias");
        else
            foreach (var (text, part) in _keywords)
                if (n.Contains(text, StringComparison.Ordinal)) { (hit, step) = (part, "keyword"); break; }
        if (hit is null && instrument is not null && _instruments.TryGetValue(instrument, out var byInst)) (hit, step) = (byInst, "instrument");
        if (hit is null && program is int p && _programs.TryGetValue(p, out var byProg)) (hit, step) = (byProg, "program");
        if (hit is null || !_parts.TryGetValue(Normalize(hit), out var found)) return null;
        var sound = found.Sound.Percussion && program is int kit && _kitPrograms.Contains(kit)
            ? found.Sound with { Program = kit } : found.Sound;
        return new ResolvedPart(found.Part, step!, sound, found.Target);
    }

    /// <summary>lowercase; ♭ → b, ♯ → #; every whitespace run (U+00A0 too) → one space; trim.</summary>
    public static string Normalize(string name) =>
        Whitespace().Replace(name.ToLowerInvariant().Replace("♭", "b").Replace("♯", "#").Replace(' ', ' '), " ").Trim();

    [GeneratedRegex(@"\s+")]
    private static partial Regex Whitespace();
}

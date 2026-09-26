using System.Text.Json;

namespace Brasscribe.Play.Core.Playback;

/// <summary>How one part sounds: preset (0-based program, bank) and its balance in the band.</summary>
public sealed record TrackSound(int Program, int Bank, double GainDb = 0, bool Percussion = false);

/// <summary>
/// The band SoundFont (sounds/band.py → brasscribe-band.sf2) with its part map from
/// sounds/mapping.json (parts[].band_soundfont): every brass part has its own preset at
/// (bank, GM program), drums are bank 128 program 0, and balance is applied as channel gain
/// (channel_gain_db), because it is not stored in the SoundFont.
/// </summary>
public sealed class BandSoundFont
{
    private readonly Dictionary<string, TrackSound> _parts;

    private BandSoundFont(Dictionary<string, TrackSound> parts, byte[]? soundFont)
    {
        _parts = parts;
        SoundFont = soundFont;
    }

    public byte[]? SoundFont { get; }
    public IReadOnlyDictionary<string, TrackSound> Parts => _parts;

    /// <summary>Reads the part map from mapping.json; the SoundFont file is optional (tests of the map need none).</summary>
    public static BandSoundFont Load(string mappingJson, string? soundFontPath = null)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(mappingJson));
        var parts = new Dictionary<string, TrackSound>(StringComparer.OrdinalIgnoreCase);
        foreach (var part in doc.RootElement.GetProperty("parts").EnumerateObject())
        {
            if (!part.Value.TryGetProperty("band_soundfont", out var b)) continue;
            int bank = b.GetProperty("bank").GetInt32();
            parts[Normalize(part.Name)] = new TrackSound(
                b.GetProperty("program").GetInt32(),
                bank,
                b.TryGetProperty("channel_gain_db", out var g) ? g.GetDouble() : 0,
                bank == 128);
        }
        return new BandSoundFont(parts, soundFontPath is not null && File.Exists(soundFontPath) ? File.ReadAllBytes(soundFontPath) : null);
    }

    /// <summary>The sound of a part by its name as the arranger writes it (E♭ Bass, 2nd Cornet …).</summary>
    public TrackSound? For(string partName) => _parts.TryGetValue(Normalize(partName), out var s) ? s : null;

    /// <summary>Routes the player's parts to this map and loads the SoundFont (parsing a band SF2 takes a moment, so the app does it off the UI thread).</summary>
    public Task ApplyTo(AlphaTabScorePlayer player, bool inBackground = false)
    {
        player.SoundMap = For;
        if (SoundFont is not { } bytes) return Task.CompletedTask;
        if (!inBackground)
        {
            player.LoadSoundFont(bytes);
            return Task.CompletedTask;
        }
        return Task.Run(() => player.LoadSoundFont(bytes));
    }

    private static string Normalize(string name) => name.Replace(' ', ' ').Replace("♭", "b").Replace("♯", "#").Trim();
}

/// <summary>
/// MIDI channel assignment. alphaTab gives each track two channels in import order, so a band
/// score wraps past 16: parts share channels (and so each other's program and bank) and one lands
/// on the drum channel. Here every track gets one channel of its own and percussion gets channel 10
/// (index 9). The synth has no 16-channel limit, only 9 (drums) and 16 (its metronome) are reserved;
/// a Standard MIDI File has 16 channels, so for export neighbouring parts that play the same program
/// at the same level share a channel until the band fits.
/// </summary>
public static class ChannelPlan
{
    public const int Drums = 9;
    public const int Metronome = 16;

    public sealed record Part(int Index, bool Percussion, int Program, double GainDb);

    public static int[] ForPlayback(IReadOnlyList<Part> parts)
    {
        var channels = new int[parts.Count];
        int next = 0;
        for (int i = 0; i < parts.Count; i++)
        {
            if (parts[i].Percussion)
            {
                channels[i] = Drums;
                continue;
            }
            while (next is Drums or Metronome) next++;
            channels[i] = next++;
        }
        return channels;
    }

    public static int[] ForMidiFile(IReadOnlyList<Part> parts)
    {
        // Groups of parts that will share a channel; start with one group per pitched part.
        var groups = parts.Where(p => !p.Percussion).Select(p => new List<Part> { p }).ToList();
        const int available = 15; // 16 minus the drum channel
        while (groups.Count > available)
        {
            // Merge the last neighbouring pair with the same program and level, else the same program, else the last pair.
            int at = FindMerge(groups, sameGain: true);
            if (at < 0) at = FindMerge(groups, sameGain: false);
            if (at < 0) at = groups.Count - 2;
            groups[at].AddRange(groups[at + 1]);
            groups.RemoveAt(at + 1);
        }
        var channels = new int[parts.Count];
        int ch = 0;
        foreach (var g in groups)
        {
            if (ch == Drums) ch++;
            foreach (var p in g) channels[parts.ToList().FindIndex(x => x.Index == p.Index)] = ch;
            ch++;
        }
        for (int i = 0; i < parts.Count; i++)
            if (parts[i].Percussion) channels[i] = Drums;
        return channels;
    }

    private static int FindMerge(List<List<Part>> groups, bool sameGain)
    {
        for (int i = groups.Count - 2; i >= 0; i--)
        {
            var a = groups[i][^1];
            var b = groups[i + 1][0];
            if (a.Program == b.Program && (!sameGain || Math.Abs(a.GainDb - b.GainDb) < 0.01) && groups[i].Count == 1 && groups[i + 1].Count == 1)
                return i;
        }
        return -1;
    }
}

/// <summary>
/// General MIDI drum numbers for unpitched notes that carry no &lt;midi-unpitched&gt;, from the
/// usual drum-set staff positions (F4 bass drum, C5 snare, G5 hi-hat …). Without this alphaTab
/// sends every such note as MIDI note 0, which no kit plays.
/// </summary>
public static class DrumMap
{
    /// <summary>GM note for a display pitch (0–127, C4 = 60).</summary>
    public static int ForDisplay(int displayMidi) => displayMidi switch
    {
        64 or 65 => 36, // E4/F4: bass drum
        72 => 38,       // C5: snare
        79 => 42,       // G5: closed hi-hat
        81 => 49,       // A5: crash
        77 => 51,       // F5: ride
        62 => 44,       // D4: pedal hi-hat
        76 => 48,       // E5: high tom
        74 => 47,       // D5: mid tom
        69 => 41,       // A4: floor tom
        67 => 43,       // G4: low floor tom
        71 => 45,       // B4: low tom
        _ => 38,
    };
}

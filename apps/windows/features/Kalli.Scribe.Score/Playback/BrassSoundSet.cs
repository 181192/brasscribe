using System.Buffers.Binary;
using System.Text;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// The baseline brass-band sounds: one SoundFont2 per instrument (sounds/ builds them as
/// &lt;instrument&gt;/&lt;instrument&gt;.sf2, each with a sustain preset on program 0 and a staccato
/// preset on program 1). Loaded together they would all answer program 0, so each file's presets
/// are moved to their own program pair in memory, and every part is pointed at its instrument.
/// <see cref="Load"/> only lists the files; <see cref="ApplyTo"/> reads them one at a time, patches
/// each in place, hands it to the synth and lets it go.
/// </summary>
public sealed class BrassSoundSet
{
    /// <summary>Part names (as written by the arranger) to instrument folders, first match whose folder is in the set wins.</summary>
    public static readonly (string PartContains, string Instrument)[] PartMap =
    [
        ("Soprano Cornet", "soprano-cornet"),
        // Solo Cornet and Trumpet have their own targets; a set built before them plays cornet-b.
        ("Solo Cornet", "solo-cornet"),
        ("Solo Cornet", "cornet-b"),
        ("Trumpet", "trumpet"),
        ("Trumpet", "cornet-b"),
        ("Cornet", "cornet-a"),
        ("Flugel", "flugelhorn"),
        ("Horn", "tenor-horn"),
        ("Baritone", "baritone"),
        ("Bass Trombone", "bass-trombone"),
        ("Trombone", "trombone"),
        ("Euphonium", "euphonium"),
        ("E♭ Bass", "eb-bass"),
        ("Eb Bass", "eb-bass"),
        ("B♭ Bass", "bb-bass"),
        ("Bb Bass", "bb-bass"),
    ];

    private readonly Dictionary<string, int> _programs = new(StringComparer.OrdinalIgnoreCase);
    private PartSoundResolver? _resolver;
    private readonly List<(string Path, int Program)> _files = [];

    public IReadOnlyDictionary<string, int> Programs => _programs;
    /// <summary>The SoundFonts in load order; none is read before <see cref="ApplyTo"/>.</summary>
    public IReadOnlyList<string> Files => _files.Select(f => f.Path).ToList();

    /// <summary>
    /// Lists every &lt;dir&gt;/*/*.sf2 (or *.sf2); instrument i moves to programs 2i and 2i+1.
    /// With mapping.json, parts are routed by the shared resolver (the part's first player's target);
    /// without it, by <see cref="PartMap"/>.
    /// </summary>
    public static BrassSoundSet Load(string dir, string? mappingJson = null)
    {
        var set = new BrassSoundSet { _resolver = mappingJson is not null && File.Exists(mappingJson) ? PartSoundResolver.Load(mappingJson) : null };
        var files = Directory.EnumerateFiles(dir, "*.sf2", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToList();
        foreach (var file in files)
        {
            int program = set._programs.Count * 2;
            if (program > 126) break;
            set._programs[Path.GetFileNameWithoutExtension(file)] = program;
            set._files.Add((file, program));
        }
        return set;
    }

    /// <summary>The program a part plays on, or null when no instrument matches (it keeps its GM program).</summary>
    public int? ProgramFor(string partName)
    {
        if (_resolver?.Resolve(partName)?.Target is { } target && _programs.TryGetValue(target, out int resolved))
            return resolved;
        foreach (var (contains, instrument) in PartMap)
            if (partName.Contains(contains, StringComparison.OrdinalIgnoreCase) && _programs.TryGetValue(instrument, out int p))
                return p;
        return null;
    }

    /// <summary>
    /// Routes the player's parts at once, then reads each SoundFont, moves its presets and loads it;
    /// only one file is held at a time. <paramref name="inBackground"/> does the reading off the
    /// calling thread (a dev build's set is about 270 MB). Call before <see cref="AlphaTabScorePlayer.LoadScore"/>.
    /// </summary>
    public Task ApplyTo(AlphaTabScorePlayer player, bool inBackground = false)
    {
        player.ProgramMap = ProgramFor;
        var files = _files.ToList();
        void Read()
        {
            for (int i = 0; i < files.Count; i++)
                player.LoadSoundFont(MovePresets(File.ReadAllBytes(files[i].Path), files[i].Program), append: i > 0);
        }
        if (!inBackground)
        {
            Read();
            return Task.CompletedTask;
        }
        return Task.Run(Read);
    }

    /// <summary>
    /// Adds <paramref name="offset"/> to the program number of every preset header (PHDR) in a
    /// SoundFont2, leaving the terminal "EOP" record alone. Bank numbers are unchanged. Patches
    /// <paramref name="sf2"/> in place and returns it (no copy of the file).
    /// </summary>
    public static byte[] MovePresets(byte[] sf2, int offset)
    {
        var data = sf2;
        int phdr = FindChunk(data, "phdr");
        if (phdr < 0) throw new InvalidDataException("SoundFont has no preset headers");
        int size = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(phdr + 4));
        int count = size / 38;
        for (int i = 0; i < count - 1; i++) // the last record is the terminator
        {
            int rec = phdr + 8 + i * 38;
            ushort program = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(rec + 20));
            BinaryPrimitives.WriteUInt16LittleEndian(data.AsSpan(rec + 20), (ushort)Math.Min(127, program + offset));
        }
        return data;
    }

    private static int FindChunk(byte[] data, string id)
    {
        var tag = Encoding.ASCII.GetBytes(id);
        // Walk RIFF chunks: "RIFF" size "sfbk", then LIST chunks; phdr lives in the pdta LIST.
        int pos = 12;
        while (pos + 8 <= data.Length)
        {
            var chunkId = data.AsSpan(pos, 4);
            int chunkSize = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(pos + 4));
            if (chunkId.SequenceEqual(tag)) return pos;
            if (chunkId.SequenceEqual("LIST"u8))
            {
                int inner = pos + 12, end = pos + 8 + chunkSize;
                while (inner + 8 <= end)
                {
                    if (data.AsSpan(inner, 4).SequenceEqual(tag)) return inner;
                    int s = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(inner + 4));
                    inner += 8 + s + (s & 1);
                }
            }
            pos += 8 + chunkSize + (chunkSize & 1);
        }
        return -1;
    }
}

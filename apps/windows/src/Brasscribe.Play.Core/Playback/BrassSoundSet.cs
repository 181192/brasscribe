using System.Buffers.Binary;
using System.Text;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// The baseline brass-band sounds: one SoundFont2 per instrument (sounds/ builds them as
/// &lt;instrument&gt;/&lt;instrument&gt;.sf2, each with a sustain preset on program 0 and a staccato
/// preset on program 1). Loaded together they would all answer program 0, so each file's presets
/// are moved to their own program pair in memory, and every part is pointed at its instrument.
/// </summary>
public sealed class BrassSoundSet
{
    /// <summary>Part names (as written by the arranger) to instrument folders, first match wins.</summary>
    public static readonly (string PartContains, string Instrument)[] PartMap =
    [
        ("Soprano Cornet", "soprano-cornet"),
        ("Solo Cornet", "cornet-b"),
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
    private readonly List<byte[]> _fonts = [];

    public IReadOnlyDictionary<string, int> Programs => _programs;
    public IReadOnlyList<byte[]> Fonts => _fonts;

    /// <summary>Reads every &lt;dir&gt;/*/*.sf2 (or *.sf2) and moves instrument i to programs 2i and 2i+1.</summary>
    public static BrassSoundSet Load(string dir)
    {
        var set = new BrassSoundSet();
        var files = Directory.EnumerateFiles(dir, "*.sf2", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToList();
        foreach (var file in files)
        {
            int program = set._programs.Count * 2;
            if (program > 126) break;
            set._programs[Path.GetFileNameWithoutExtension(file)] = program;
            set._fonts.Add(MovePresets(File.ReadAllBytes(file), program));
        }
        return set;
    }

    /// <summary>The program a part plays on, or null when no instrument matches (it keeps its GM program).</summary>
    public int? ProgramFor(string partName)
    {
        foreach (var (contains, instrument) in PartMap)
            if (partName.Contains(contains, StringComparison.OrdinalIgnoreCase) && _programs.TryGetValue(instrument, out int p))
                return p;
        return null;
    }

    /// <summary>Loads the fonts into a player and routes its parts; call before <see cref="AlphaTabScorePlayer.LoadScore"/>.</summary>
    public void ApplyTo(AlphaTabScorePlayer player)
    {
        for (int i = 0; i < _fonts.Count; i++) player.LoadSoundFont(_fonts[i], append: i > 0);
        player.ProgramMap = ProgramFor;
    }

    /// <summary>
    /// Adds <paramref name="offset"/> to the program number of every preset header (PHDR) in a
    /// SoundFont2, leaving the terminal "EOP" record alone. Bank numbers are unchanged.
    /// </summary>
    public static byte[] MovePresets(byte[] sf2, int offset)
    {
        var data = (byte[])sf2.Clone();
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

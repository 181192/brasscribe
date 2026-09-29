using System.Buffers.Binary;
using System.IO.Compression;
using System.Text;

namespace Brasscribe.Play.Core.Arrangement;

/// <summary>Frame-level SwiftF0 contour of the solo stem: where sustained solo notes really end.</summary>
/// <param name="Times">Frame times in seconds.</param>
/// <param name="PitchHz">SwiftF0 pitch per frame in Hz (0 or NaN where there is none).</param>
/// <param name="LoudnessDb">Frame loudness in dB.</param>
/// <param name="Confidence">SwiftF0 voicing confidence per frame, when the contour has it: which frames the core's
/// pitch-change onsets trust.</param>
public sealed record SoloContour(double[] Times, double[] PitchHz, double[] LoudnessDb, double[]? Confidence = null);

/// <summary>
/// What the layered arranger reads: six MIDI transcriptions (solo SwiftF0, solo MuScriptor, solo
/// Basic Pitch, bass, orchestra, drums), the four layer stems as WAV (solo, bass, drums, orchestra;
/// each optional), the beat table and optionally the solo contour. The file names are the ones the
/// engine's layered pipeline writes (solo-sw.mid, …, mix.beats, solo-sw.contour.npz).
/// </summary>
public sealed record LayerInputs(byte[][] Midi, byte[]?[] Wav, string Beats, SoloContour? Contour = null)
{
    public static readonly string[] MidiNames = ["solo-sw.mid", "solo-mus.mid", "solo-bp.mid", "bass-mus.mid", "orchestra-mus.mid", "drums-mus.mid"];
    public static readonly string[] WavNames = ["solo.wav", "bass.wav", "drums.wav", "orchestra.wav"];
    public const string BeatsName = "mix.beats";
    public const string ContourName = "solo-sw.contour.npz";

    /// <summary>Every file name the arranger can use.</summary>
    public static IEnumerable<string> FileNames => MidiNames.Concat(WavNames).Append(BeatsName).Append(ContourName);

    /// <summary>
    /// From named files (a stage-file listing or a folder). Null when a MIDI layer or the beats are
    /// missing; stems and contour are optional.
    /// </summary>
    public static LayerInputs? From(Func<string, byte[]?> file) =>
        From(file, () => file(ContourName) is { } npz ? ReadContour(npz) : null);

    private static LayerInputs? From(Func<string, byte[]?> file, Func<SoloContour?> contour)
    {
        var midi = new byte[MidiNames.Length][];
        for (int i = 0; i < MidiNames.Length; i++)
            if ((midi[i] = file(MidiNames[i])!) is null) return null;
        if (file(BeatsName) is not { } beats) return null;
        var wav = WavNames.Select(file).ToArray();
        return new LayerInputs(midi, wav, Encoding.UTF8.GetString(beats), contour());
    }

    /// <summary>
    /// From a folder holding the layer files, with the beats and contour next to them or one level up.
    /// Each file is read once into an array of its size (the C ABI takes each layer as one pointer and
    /// length); the contour is decoded straight from the archive on disk. Blocking: call it off the UI thread.
    /// </summary>
    public static LayerInputs? FromDirectory(string dir, string? beatsPath = null, string? contourPath = null)
    {
        string? PathOf(string name)
        {
            string? p = name switch
            {
                BeatsName when beatsPath is not null => beatsPath,
                ContourName when contourPath is not null => contourPath,
                _ => new[] { Path.Combine(dir, name), Path.Combine(Path.GetDirectoryName(Path.GetFullPath(dir)) ?? dir, name) }.FirstOrDefault(File.Exists),
            };
            return p is not null && File.Exists(p) ? p : null;
        }
        return From(name => PathOf(name) is { } p ? File.ReadAllBytes(p) : null, () =>
        {
            if (PathOf(ContourName) is not { } p) return null;
            using var file = File.OpenRead(p);
            return ReadContour(file);
        });
    }

    /// <summary>Reads the contour arrays (t, pitch_hz, loudness_db) from a NumPy .npz archive of little-endian float64 vectors.</summary>
    public static SoloContour ReadContour(byte[] npz) => ReadContour(new MemoryStream(npz, writable: false));

    /// <inheritdoc cref="ReadContour(byte[])"/>
    public static SoloContour ReadContour(Stream npz)
    {
        using var zip = new ZipArchive(npz, ZipArchiveMode.Read);
        double[] Array(string name)
        {
            var entry = zip.GetEntry(name + ".npy") ?? throw new InvalidDataException($"contour without {name}");
            using var s = entry.Open();
            var bytes = new byte[entry.Length];
            s.ReadExactly(bytes);
            return ReadNpy(bytes, name);
        }
        return new SoloContour(Array("t"), Array("pitch_hz"), Array("loudness_db"),
            zip.GetEntry("confidence.npy") is null ? null : Array("confidence"));
    }

    private static double[] ReadNpy(byte[] b, string name)
    {
        if (b.Length < 10 || b[0] != 0x93 || Encoding.ASCII.GetString(b, 1, 5) != "NUMPY")
            throw new InvalidDataException($"{name}: not a .npy array");
        int major = b[6];
        int headerLen = major == 1 ? BinaryPrimitives.ReadUInt16LittleEndian(b.AsSpan(8)) : (int)BinaryPrimitives.ReadUInt32LittleEndian(b.AsSpan(8));
        int start = (major == 1 ? 10 : 12) + headerLen;
        string header = Encoding.ASCII.GetString(b, major == 1 ? 10 : 12, headerLen);
        bool f4 = header.Contains("'<f4'");
        if (!f4 && !header.Contains("'<f8'")) throw new InvalidDataException($"{name}: expected float32 or float64, got {header.Trim()}");
        if (header.Contains("'fortran_order': True")) throw new InvalidDataException($"{name}: Fortran order is not supported");
        int size = f4 ? 4 : 8;
        var span = b.AsSpan(start);
        var result = new double[span.Length / size];
        for (int i = 0; i < result.Length; i++)
            result[i] = f4 ? BinaryPrimitives.ReadSingleLittleEndian(span[(i * 4)..]) : BinaryPrimitives.ReadDoubleLittleEndian(span[(i * 8)..]);
        return result;
    }
}

/// <summary>A score arranged from layer inputs: MusicXML, one MusicXML per part, the Composition and the separation check.</summary>
public sealed record BandArrangement(string CompositionJson, string MusicXml, IReadOnlyList<(string FileName, string MusicXml)> Parts, string? SeparationCheck);

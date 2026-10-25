using System.Buffers.Binary;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// Integrated loudness (ITU-R BS.1770 / EBU R128) of audio fed in chunks: K-weighting, 400 ms
/// blocks with 75 % overlap, the −70 LUFS absolute gate and the −10 LU relative gate. The filters
/// are pyloudnorm's, so the numbers match sounds/output-stage-vectors.json and the other Play apps.
/// </summary>
public sealed class LoudnessMeter
{
    private struct Biquad
    {
        public double B0, B1, B2, A1, A2, Z1, Z2;

        public double Run(double x)
        {
            double y = B0 * x + Z1;
            Z1 = B1 * x - A1 * y + Z2;
            Z2 = B2 * x - A2 * y;
            return y;
        }
    }

    private readonly Biquad[] _shelf, _highpass;
    private readonly int _subBlock;
    private readonly List<double> _subEnergy = [];
    private double _acc;
    private int _accCount;

    public LoudnessMeter(double sampleRate, int channels)
    {
        channels = Math.Max(1, channels);
        _shelf = new Biquad[channels];
        _highpass = new Biquad[channels];
        for (int c = 0; c < channels; c++) { _shelf[c] = Shelf(sampleRate); _highpass[c] = HighPass(sampleRate); }
        _subBlock = Math.Max(1, (int)Math.Round(sampleRate * 0.1));
    }

    public int Channels => _shelf.Length;

    private static Biquad Shelf(double rate)
    {
        double g = 4.0, q = 1 / Math.Sqrt(2), fc = 1500.0;
        double a = Math.Pow(10, g / 40), w = 2 * Math.PI * fc / rate, al = Math.Sin(w) / (2 * q), c = Math.Cos(w), s = Math.Sqrt(a);
        double a0 = (a + 1) - (a - 1) * c + 2 * s * al;
        return new Biquad
        {
            B0 = a * ((a + 1) + (a - 1) * c + 2 * s * al) / a0,
            B1 = -2 * a * ((a - 1) + (a + 1) * c) / a0,
            B2 = a * ((a + 1) + (a - 1) * c - 2 * s * al) / a0,
            A1 = 2 * ((a - 1) - (a + 1) * c) / a0,
            A2 = ((a + 1) - (a - 1) * c - 2 * s * al) / a0,
        };
    }

    private static Biquad HighPass(double rate)
    {
        double q = 0.5, fc = 38.0;
        double w = 2 * Math.PI * fc / rate, al = Math.Sin(w) / (2 * q), c = Math.Cos(w), a0 = 1 + al;
        return new Biquad { B0 = (1 + c) / 2 / a0, B1 = -(1 + c) / a0, B2 = (1 + c) / 2 / a0, A1 = -2 * c / a0, A2 = (1 - al) / a0 };
    }

    /// <summary>Feeds interleaved samples (whole frames, <see cref="Channels"/> per frame).</summary>
    public void ProcessInterleaved(ReadOnlySpan<float> samples)
    {
        int ch = Channels, frames = samples.Length / ch, i = 0;
        while (i < frames)
        {
            int n = Math.Min(frames - i, _subBlock - _accCount);
            for (int c = 0; c < ch; c++)
            {
                double s = 0;
                ref var f1 = ref _shelf[c];
                ref var f2 = ref _highpass[c];
                for (int k = i; k < i + n; k++) { double y = f2.Run(f1.Run(samples[k * ch + c])); s += y * y; }
                _acc += s;
            }
            _accCount += n;
            i += n;
            if (_accCount == _subBlock) { _subEnergy.Add(_acc); _acc = 0; _accCount = 0; }
        }
    }

    /// <summary>Integrated loudness in LUFS; −∞ for silence or less than 400 ms of audio.</summary>
    public double IntegratedLufs
    {
        get
        {
            if (_subEnergy.Count < 4) return double.NegativeInfinity;
            double n = _subBlock * 4.0;
            var blocks = new List<double>(_subEnergy.Count - 3);
            for (int j = 0; j + 4 <= _subEnergy.Count; j++)
                blocks.Add((_subEnergy[j] + _subEnergy[j + 1] + _subEnergy[j + 2] + _subEnergy[j + 3]) / n);
            static double Lufs(double z) => -0.691 + 10 * Math.Log10(z);
            var abs = blocks.Where(z => z > 0 && Lufs(z) > -70).ToList();
            if (abs.Count == 0) return double.NegativeInfinity;
            double rel = Lufs(abs.Average()) - 10;
            return Lufs(abs.Where(z => Lufs(z) > rel).Average());
        }
    }

    /// <summary>Integrated loudness of interleaved samples.</summary>
    public static double Integrated(ReadOnlySpan<float> interleaved, double sampleRate, int channels)
    {
        var m = new LoudnessMeter(sampleRate, channels);
        m.ProcessInterleaved(interleaved);
        return m.IntegratedLufs;
    }

    /// <summary>
    /// Integrated loudness of a WAV file (PCM 16/24/32-bit or 32-bit float), read in chunks. A mono
    /// file is measured as dual mono (+3 dB), the way it plays from two speakers.
    /// </summary>
    public static double IntegratedWav(string path)
    {
        LoudnessMeter? m = null;
        int channels = 0;
        ReadWav(path, (rate, ch) => { m = new LoudnessMeter(rate, ch); channels = ch; }, samples => m!.ProcessInterleaved(samples));
        return m!.IntegratedLufs + (channels == 1 ? 10 * Math.Log10(2) : 0);
    }

    /// <summary>
    /// Reads a WAV file (PCM 16/24/32-bit or 32-bit float) in chunks: <paramref name="onFormat"/> gets the sample rate and
    /// channel count once, then <paramref name="onSamples"/> the interleaved samples as floats in −1..1.
    /// </summary>
    internal static void ReadWav(string path, Action<int, int> onFormat, Action<ReadOnlySpan<float>> onSamples)
    {
        using var s = File.OpenRead(path);
        var head = new byte[12];
        if (s.Read(head, 0, 12) != 12 || !head.AsSpan(0, 4).SequenceEqual("RIFF"u8) || !head.AsSpan(8, 4).SequenceEqual("WAVE"u8))
            throw new InvalidDataException("not a WAV file");
        int format = 0, channels = 0, rate = 0, bits = 0;
        var chunk = new byte[8];
        while (s.Read(chunk, 0, 8) == 8)
        {
            string id = System.Text.Encoding.ASCII.GetString(chunk, 0, 4);
            long size = BinaryPrimitives.ReadUInt32LittleEndian(chunk.AsSpan(4));
            if (id == "fmt ")
            {
                var fmt = new byte[size];
                s.ReadExactly(fmt);
                format = BinaryPrimitives.ReadUInt16LittleEndian(fmt);
                channels = BinaryPrimitives.ReadUInt16LittleEndian(fmt.AsSpan(2));
                rate = BinaryPrimitives.ReadInt32LittleEndian(fmt.AsSpan(4));
                bits = BinaryPrimitives.ReadUInt16LittleEndian(fmt.AsSpan(14));
                if (format == 0xFFFE && size >= 26) format = BinaryPrimitives.ReadUInt16LittleEndian(fmt.AsSpan(24));
                if ((size & 1) == 1) s.ReadByte();
            }
            else if (id == "data")
            {
                if (channels == 0 || !(format == 1 && bits is 16 or 24 or 32 || format == 3 && bits == 32))
                    throw new InvalidDataException($"unsupported WAV format {format}/{bits}");
                onFormat(rate, channels);
                int bytes = bits / 8, frame = bytes * channels;
                var raw = new byte[frame * 8192];
                var f = new float[channels * 8192];
                long left = size == 0xFFFFFFFF ? long.MaxValue : size;
                while (left > 0)
                {
                    int want = (int)Math.Min(raw.Length, left / frame * frame);
                    if (want == 0) break;
                    int got = 0, r;
                    while (got < want && (r = s.Read(raw, got, want - got)) > 0) got += r;
                    got -= got % frame;
                    if (got == 0) break;
                    int count = got / bytes;
                    for (int i = 0; i < count; i++)
                    {
                        var b = raw.AsSpan(i * bytes, bytes);
                        f[i] = format == 3 ? BinaryPrimitives.ReadSingleLittleEndian(b)
                            : bits == 16 ? BinaryPrimitives.ReadInt16LittleEndian(b) / 32768f
                            : bits == 24 ? ((b[0] | b[1] << 8 | (sbyte)b[2] << 16)) / 8388608f
                            : BinaryPrimitives.ReadInt32LittleEndian(b) / 2147483648f;
                    }
                    onSamples(f.AsSpan(0, count));
                    left -= got;
                }
                return;
            }
            else
            {
                s.Seek(size + (size & 1), SeekOrigin.Current);
            }
        }
        throw new InvalidDataException("WAV file has no data");
    }
}

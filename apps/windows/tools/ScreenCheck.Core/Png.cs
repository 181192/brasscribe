using System.Buffers.Binary;
using System.IO.Compression;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// PNG files of screenshots: 8-bit RGBA, written without an image library, read back whatever filters a writer used
/// (8-bit RGB or RGBA, not interlaced: what this class and GDI+ write). Pixels are stored straight (not premultiplied);
/// a screenshot is opaque, so its alpha is written as 255.
/// </summary>
public static class Png
{
    private static readonly byte[] Signature = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

    /// <summary>The largest width or height read: a screenshot is far smaller; a file that says more is not one.</summary>
    public const int MaxSide = 16384;

    public static void Save(string path, Picture picture) => File.WriteAllBytes(path, Encode(picture));

    public static Picture Load(string path) => Decode(File.ReadAllBytes(path));

    /// <param name="filter">The PNG filter for every row: 0 (none) is what screenshots are written with; the others
    /// are for the tests of <see cref="Decode"/>.</param>
    public static byte[] Encode(Picture picture, byte filter = 0)
    {
        int w = picture.Width, h = picture.Height, stride = w * 4;
        var raw = new byte[(stride + 1) * h];
        var line = new byte[stride];
        var prev = new byte[stride];
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                int s = (y * w + x) * 4, d = x * 4;
                line[d] = picture.Bgra[s + 2];
                line[d + 1] = picture.Bgra[s + 1];
                line[d + 2] = picture.Bgra[s];
                line[d + 3] = 255;
            }
            int row = y * (stride + 1);
            raw[row] = filter;
            for (int i = 0; i < stride; i++)
            {
                int a = i >= 4 ? line[i - 4] : 0, b = prev[i], c = i >= 4 ? prev[i - 4] : 0;
                raw[row + 1 + i] = (byte)(line[i] - filter switch
                {
                    0 => 0,
                    1 => a,
                    2 => b,
                    3 => (a + b) / 2,
                    4 => Paeth(a, b, c),
                    _ => throw new ArgumentOutOfRangeException(nameof(filter)),
                });
            }
            (prev, line) = (line, prev);
        }
        using var data = new MemoryStream();
        using (var z = new ZLibStream(data, CompressionLevel.Optimal, leaveOpen: true)) z.Write(raw);

        using var png = new MemoryStream();
        png.Write(Signature);
        var header = new byte[13];
        BinaryPrimitives.WriteInt32BigEndian(header, w);
        BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(4), h);
        header[8] = 8; // bits per channel
        header[9] = 6; // RGBA
        Chunk(png, "IHDR", header);
        Chunk(png, "IDAT", data.ToArray());
        Chunk(png, "IEND", []);
        return png.ToArray();
    }

    public static Picture Decode(byte[] file)
    {
        if (file.Length < 8 || !file.AsSpan(0, 8).SequenceEqual(Signature)) throw new InvalidDataException("not a PNG");
        int w = 0, h = 0, channels = 0;
        using var idat = new MemoryStream();
        for (int at = 8; at + 12 <= file.Length;)
        {
            int length = BinaryPrimitives.ReadInt32BigEndian(file.AsSpan(at));
            if (length < 0 || length > file.Length - at - 12) throw new InvalidDataException("a chunk runs past the end of the file");
            string type = System.Text.Encoding.ASCII.GetString(file, at + 4, 4);
            var body = file.AsSpan(at + 8, length);
            if (at == 8 && type != "IHDR") throw new InvalidDataException("the PNG does not start with its header (IHDR)");
            if (type == "IHDR")
            {
                if (length != 13) throw new InvalidDataException("a header (IHDR) of the wrong length");
                w = BinaryPrimitives.ReadInt32BigEndian(body);
                h = BinaryPrimitives.ReadInt32BigEndian(body[4..]);
                if (w is < 1 or > MaxSide || h is < 1 or > MaxSide) throw new InvalidDataException($"a PNG of {w} x {h} is not a screenshot");
                if (body[8] != 8 || body[12] != 0) throw new InvalidDataException("only 8-bit, non-interlaced PNGs are read");
                channels = body[9] switch { 6 => 4, 2 => 3, _ => throw new InvalidDataException($"colour type {body[9]} is not read") };
            }
            else if (type == "IDAT") idat.Write(body);
            else if (type == "IEND") break;
            at += 12 + length;
        }
        if (channels == 0) throw new InvalidDataException("the PNG has no header (IHDR)");
        idat.Position = 0;
        using var z = new ZLibStream(idat, CompressionMode.Decompress);
        int stride = checked(w * channels);
        var raw = new byte[checked((stride + 1) * h)];
        z.ReadExactly(raw);

        var bgra = new byte[checked(w * h * 4)];
        var prev = new byte[stride];
        var line = new byte[stride];
        for (int y = 0; y < h; y++)
        {
            int row = y * (stride + 1);
            byte filter = raw[row];
            for (int i = 0; i < stride; i++)
            {
                int a = i >= channels ? line[i - channels] : 0, b = prev[i], c = i >= channels ? prev[i - channels] : 0;
                int v = raw[row + 1 + i];
                line[i] = (byte)(filter switch
                {
                    0 => v,
                    1 => v + a,
                    2 => v + b,
                    3 => v + (a + b) / 2,
                    4 => v + Paeth(a, b, c),
                    _ => throw new InvalidDataException($"filter {filter}"),
                });
            }
            for (int x = 0; x < w; x++)
            {
                int s = x * channels, d = (y * w + x) * 4;
                bgra[d] = line[s + 2];
                bgra[d + 1] = line[s + 1];
                bgra[d + 2] = line[s];
                bgra[d + 3] = channels == 4 ? line[s + 3] : (byte)255;
            }
            (prev, line) = (line, prev);
        }
        return new Picture(w, h, bgra);
    }

    private static int Paeth(int a, int b, int c)
    {
        int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
        return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
    }

    private static void Chunk(Stream png, string type, byte[] body)
    {
        Span<byte> four = stackalloc byte[4];
        BinaryPrimitives.WriteInt32BigEndian(four, body.Length);
        png.Write(four);
        var typed = new byte[4 + body.Length];
        System.Text.Encoding.ASCII.GetBytes(type, typed);
        body.CopyTo(typed, 4);
        png.Write(typed);
        BinaryPrimitives.WriteUInt32BigEndian(four, Crc32(typed));
        png.Write(four);
    }

    private static readonly uint[] Table = Enumerable.Range(0, 256).Select(n =>
    {
        uint c = (uint)n;
        for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        return c;
    }).ToArray();

    private static uint Crc32(byte[] bytes)
    {
        uint c = 0xFFFFFFFF;
        foreach (byte b in bytes) c = Table[(c ^ b) & 0xFF] ^ (c >> 8);
        return c ^ 0xFFFFFFFF;
    }
}

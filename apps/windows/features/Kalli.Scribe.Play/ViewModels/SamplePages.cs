using System.IO.Compression;
using System.Text;

namespace Kalli.Scribe.ViewModels;

/// <summary>
/// Pages of printed music for the sample scenes, invented here: a picture of a page with six staves (a real PNG, so the
/// row's small picture shows) and a one-page PDF. Nothing of anyone's music is in them.
/// </summary>
public static class SamplePages
{
    /// <summary>Writes <paramref name="count"/> pages to the temporary folder, the last one a PDF when <paramref name="withPdf"/>.</summary>
    public static IReadOnlyList<string> Write(string title, int count, bool withPdf = true)
    {
        var paths = new List<string>();
        for (int n = 1; n <= count; n++)
        {
            bool pdf = withPdf && n == count;
            string path = Path.Combine(Path.GetTempPath(), $"{title} page {n}.{(pdf ? "pdf" : "png")}");
            File.WriteAllBytes(path, pdf ? Pdf() : Png(n));
            paths.Add(path);
        }
        return paths;
    }

    /// <summary>A grey-scale PNG of a page: white, six staves of five lines, and <paramref name="n"/> marks for its number.</summary>
    public static byte[] Png(int n = 1)
    {
        const int w = 240, h = 320;
        var rows = new byte[h * (w + 1)];
        for (int y = 0; y < h; y++)
        {
            int at = y * (w + 1);
            rows[at] = 0; // no filter
            for (int x = 0; x < w; x++)
            {
                int ys = y - 40;
                bool line = x is >= 16 and < 224 && ys >= 0 && ys < 6 * 44 && ys % 44 < 25 && ys % 44 % 6 == 0;
                bool mark = y is >= 12 and < 22 && x >= 16 && x < 16 + n * 8 && x % 8 < 5;
                rows[at + 1 + x] = (byte)(line || mark ? 0 : 255);
            }
        }
        using var png = new MemoryStream();
        png.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        Chunk(png, "IHDR", [.. Be(w), .. Be(h), 8, 0, 0, 0, 0]); // 8-bit grey, no interlace
        using (var data = new MemoryStream())
        {
            using (var z = new ZLibStream(data, CompressionLevel.Optimal, leaveOpen: true)) z.Write(rows);
            Chunk(png, "IDAT", data.ToArray());
        }
        Chunk(png, "IEND", []);
        return png.ToArray();
    }

    /// <summary>A PDF of one A4 page with the same staves, drawn as lines.</summary>
    public static byte[] Pdf()
    {
        var draw = new StringBuilder();
        for (int s = 0; s < 6; s++)
            for (int l = 0; l < 5; l++)
            {
                int y = 760 - s * 120 - l * 8;
                draw.Append($"50 {y} m 545 {y} l S\n");
            }
        string content = draw.ToString();
        string[] objects =
        [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
            $"<< /Length {content.Length} >>\nstream\n{content}endstream",
        ];
        var pdf = new StringBuilder("%PDF-1.4\n");
        var offsets = new List<int>();
        for (int i = 0; i < objects.Length; i++)
        {
            offsets.Add(pdf.Length);
            pdf.Append($"{i + 1} 0 obj\n{objects[i]}\nendobj\n");
        }
        int xref = pdf.Length;
        pdf.Append($"xref\n0 {objects.Length + 1}\n0000000000 65535 f \n");
        foreach (int o in offsets) pdf.Append($"{o:D10} 00000 n \n");
        pdf.Append($"trailer\n<< /Size {objects.Length + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n");
        return Encoding.ASCII.GetBytes(pdf.ToString());
    }

    private static byte[] Be(int v) => [(byte)(v >> 24), (byte)(v >> 16), (byte)(v >> 8), (byte)v];

    private static void Chunk(Stream s, string type, byte[] data)
    {
        s.Write(Be(data.Length));
        byte[] typed = [.. Encoding.ASCII.GetBytes(type), .. data];
        s.Write(typed);
        s.Write(Be((int)Crc(typed)));
    }

    private static uint Crc(byte[] bytes)
    {
        uint c = 0xFFFFFFFF;
        foreach (byte b in bytes)
        {
            c ^= b;
            for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        }
        return c ^ 0xFFFFFFFF;
    }
}

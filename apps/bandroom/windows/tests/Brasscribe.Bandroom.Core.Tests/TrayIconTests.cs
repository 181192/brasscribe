using System.Buffers.Binary;
using System.IO.Compression;
using Brasscribe.Bandroom.Core.State;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class TrayIconTests
{
    private static readonly (byte, byte, byte) Ink = (0x1B, 0x1A, 0x17);

    private static int InkPixels(byte[] px) => Enumerable.Range(0, px.Length / 4).Count(i => px[i * 4 + 3] > 127);

    [Theory]
    [InlineData(16)]
    [InlineData(20)]
    [InlineData(24)]
    [InlineData(32)]
    public void Every_state_draws_a_different_icon_at_every_size(int size)
    {
        var icons = Enum.GetValues<TrayBadge>()
            .Select(b => Convert.ToHexString(TrayIconRaster.Render(size, b, b == TrayBadge.Pie ? 5 : 0, Ink)))
            .ToList();
        Assert.Equal(icons.Count, icons.Distinct().Count());
        Assert.All(Enum.GetValues<TrayBadge>(), b => Assert.True(InkPixels(TrayIconRaster.Render(size, b, 4, Ink)) > size * size / 8));
    }

    [Fact]
    public void The_pie_grows_in_eight_steps()
    {
        var counts = Enumerable.Range(0, 9).Select(e => InkPixels(TrayIconRaster.Render(32, TrayBadge.Pie, e, Ink))).ToList();
        Assert.Equal(counts.Order(), counts);
        Assert.True(counts[8] > counts[0]);
    }

    [Fact]
    public void The_mark_has_its_counter_open()
    {
        // The hole of the bowl (around 30, 45 in the mark's 64 units) is not ink; the stem (14, 30) is.
        Assert.False(TrayIconRaster.Inside(28, 44, TrayBadge.None, 0));
        Assert.True(TrayIconRaster.Inside(14, 30, TrayBadge.None, 0));
    }

    /// <summary>Writes a contact sheet of every state (BANDROOM_ICON_SHEET=path.png) for a visual check.</summary>
    [SkippableFact]
    public void Contact_sheet()
    {
        var path = Environment.GetEnvironmentVariable("BANDROOM_ICON_SHEET");
        Skip.If(string.IsNullOrEmpty(path), "opt-in visual check: set BANDROOM_ICON_SHEET to a .png path to write the contact sheet");
        var badges = Enum.GetValues<TrayBadge>();
        int[] sizes = [16, 20, 24, 32];
        int zoom = 6, cell = 32 * zoom + 8;
        int w = badges.Length * cell, h = sizes.Length * cell;
        var rgba = new byte[w * h * 4];
        Array.Fill(rgba, (byte)255);
        for (int bi = 0; bi < badges.Length; bi++)
        for (int si = 0; si < sizes.Length; si++)
        {
            int s = sizes[si];
            var px = TrayIconRaster.Render(s, badges[bi], 5, Ink);
            for (int y = 0; y < s * zoom; y++)
            for (int x = 0; x < s * zoom; x++)
            {
                int a = px[((y / zoom) * s + x / zoom) * 4 + 3];
                int o = ((si * cell + y) * w + bi * cell + x) * 4;
                byte c = (byte)(255 - a * (255 - 0x1B) / 255);
                rgba[o] = rgba[o + 1] = rgba[o + 2] = c;
            }
        }
        File.WriteAllBytes(path, Png(w, h, rgba));
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

    private static byte[] Png(int w, int h, byte[] rgba)
    {
        using var ms = new MemoryStream();
        ms.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        void Chunk(string type, byte[] data)
        {
            Span<byte> len = stackalloc byte[4];
            BinaryPrimitives.WriteInt32BigEndian(len, data.Length);
            ms.Write(len);
            var t = System.Text.Encoding.ASCII.GetBytes(type);
            ms.Write(t);
            ms.Write(data);
            BinaryPrimitives.WriteUInt32BigEndian(len, Crc([.. t, .. data]));
            ms.Write(len);
        }
        var ihdr = new byte[13];
        BinaryPrimitives.WriteInt32BigEndian(ihdr, w);
        BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(4), h);
        ihdr[8] = 8; ihdr[9] = 6;
        Chunk("IHDR", ihdr);
        using var raw = new MemoryStream();
        using (var z = new ZLibStream(raw, CompressionLevel.Optimal, leaveOpen: true))
            for (int y = 0; y < h; y++) { z.WriteByte(0); z.Write(rgba, y * w * 4, w * 4); }
        Chunk("IDAT", raw.ToArray());
        Chunk("IEND", []);
        return ms.ToArray();
    }
}

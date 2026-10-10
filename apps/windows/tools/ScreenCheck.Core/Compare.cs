namespace Brasscribe.ScreenCheck;

/// <summary>
/// What differs between two pictures of one screen taken in the same run (Home started in a theme against Home switched
/// to it, a screen before and after its dialog), counted as studio/catalogue/compare.mjs counts.
/// A pixel counts as changed when a channel moves by more than 2, except where each picture's shade is one found
/// around that place in the other (an anti-aliased edge a fraction of a pixel elsewhere) and moved by at most 16.
/// </summary>
public static class ImageDiff
{
    /// <summary>Changed pixels up to this many in one screenshot are noise (reported, not a change).</summary>
    public const int FloorPixels = 4;

    /// <summary>The number of changed pixels, and a picture of where: the after picture faded, what changed in red.</summary>
    public static (int Changed, Picture Diff) Of(Picture before, Picture after)
    {
        int w = Math.Max(before.Width, after.Width), h = Math.Max(before.Height, after.Height);
        var a = Pad(before, w, h);
        var b = Pad(after, w, h);
        var diff = new Picture(w, h, new byte[w * h * 4]);
        int n = 0;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                uint pa = a[x, y], pb = b[x, y];
                int d = Step(pa, pb);
                bool same = d <= 2 || (d <= 16 && Within(Lum(pb), Around(a, x, y)) && Within(Lum(pa), Around(b, x, y)));
                if (!same) n++;
                byte grey = (byte)(255 - (255 - ((pb >> 16 & 0xFF) + (pb >> 8 & 0xFF) + (pb & 0xFF)) / 3.0) * 0.25);
                diff[x, y] = same ? 0xFF000000u | (uint)grey << 16 | (uint)grey << 8 | grey : 0xFFDC0000;
            }
        return (n, diff);
    }

    private static Picture Pad(Picture p, int w, int h)
    {
        if (p.Width == w && p.Height == h) return p;
        var padded = new Picture(w, h, new byte[w * h * 4]);
        padded.Compose(new Picture(p.Width, p.Height, p.Bgra.Select((v, i) => i % 4 == 3 ? (byte)255 : v).ToArray()), 0, 0);
        return padded;
    }

    private static int Step(uint a, uint b)
    {
        int d = 0;
        for (int s = 0; s < 32; s += 8) d = Math.Max(d, Math.Abs((int)(a >> s & 0xFF) - (int)(b >> s & 0xFF)));
        return d;
    }

    private static double Lum(uint p) => 0.299 * (p >> 16 & 0xFF) + 0.587 * (p >> 8 & 0xFF) + 0.114 * (p & 0xFF);

    /// <summary>The light of the 3 × 3 pixels around one, in one picture, widened by 2.</summary>
    private static (double Lo, double Hi) Around(Picture p, int x, int y)
    {
        double lo = 255, hi = 0;
        for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++)
            {
                int xx = x + dx, yy = y + dy;
                if (xx < 0 || yy < 0 || xx >= p.Width || yy >= p.Height) continue;
                double v = Lum(p[xx, yy]);
                lo = Math.Min(lo, v);
                hi = Math.Max(hi, v);
            }
        return (lo - 2, hi + 2);
    }

    private static bool Within(double v, (double Lo, double Hi) r) => v >= r.Lo && v <= r.Hi;
}

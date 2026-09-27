namespace Brasscribe.Bandroom.Core.State;

/// <summary>
/// Draws the notification-area icon: the Brasscribe mark (design/brand/logo/mark.svg) plus a badge shape
/// per state (§6.1), in one colour, at 16, 20, 24 or 32 px. The badge sits bottom right with a clear ring
/// cut out of the mark, so the shape reads at 16 px. Returns straight-alpha BGRA rows, top-down.
/// Drawing is by supersampled inside-tests in the mark's 64-unit space; no graphics library needed.
/// </summary>
public static class TrayIconRaster
{
    private const int Samples = 4; // 4 x 4 per pixel

    public static byte[] Render(int size, TrayBadge badge, int pieEighths, (byte R, byte G, byte B) ink)
    {
        var px = new byte[size * size * 4];
        double scale = 64.0 / size;
        for (int y = 0; y < size; y++)
        for (int x = 0; x < size; x++)
        {
            int hits = 0;
            for (int sy = 0; sy < Samples; sy++)
            for (int sx = 0; sx < Samples; sx++)
            {
                double u = (x + (sx + 0.5) / Samples) * scale;
                double v = (y + (sy + 0.5) / Samples) * scale;
                if (Inside(u, v, badge, pieEighths)) hits++;
            }
            int a = hits * 255 / (Samples * Samples);
            int i = (y * size + x) * 4;
            px[i] = ink.B;
            px[i + 1] = ink.G;
            px[i + 2] = ink.R;
            px[i + 3] = (byte)a;
        }
        return px;
    }

    /// <summary>Whether a point (in the 64-unit space of mark.svg) is ink.</summary>
    public static bool Inside(double u, double v, TrayBadge badge, int pieEighths)
    {
        if (badge == TrayBadge.None) return InMark(u, v);
        double dx = u - BadgeX, dy = v - BadgeY;
        double d = Math.Sqrt(dx * dx + dy * dy);
        if (d <= BadgeR + Gap) return InBadge(dx, dy, badge, pieEighths);
        // With a badge the mark shrinks towards the top left, so its bowl stays readable.
        return InMark(u / MarkScale + 1, v / MarkScale - 2);
    }

    // The badge: a 30-unit circle area bottom right (about 8 px of a 16 px icon), with a 3.5-unit gap.
    private const double BadgeX = 49, BadgeY = 49, BadgeR = 15, Gap = 3.5, MarkScale = 0.8;

    private static bool InBadge(double dx, double dy, TrayBadge badge, int eighths)
    {
        double r = Math.Sqrt(dx * dx + dy * dy);
        switch (badge)
        {
            case TrayBadge.Pie:
            {
                // A ring with the done part filled clockwise from 12 o'clock, in 8 steps.
                if (r > BadgeR) return false;
                if (r >= BadgeR - 3) return true;
                double angle = (Math.Atan2(dx, -dy) + 2 * Math.PI) % (2 * Math.PI); // 0 at the top, clockwise
                return angle < eighths / 8.0 * 2 * Math.PI;
            }
            case TrayBadge.Square:
                return Math.Abs(dx) <= 11.5 && Math.Abs(dy) <= 11.5;
            case TrayBadge.Triangle:
            {
                // Point up; "!" cut out.
                double top = -14, bottom = 12, half = 15;
                if (dy < top || dy > bottom) return false;
                double w = half * (dy - top) / (bottom - top);
                if (Math.Abs(dx) > w) return false;
                bool bar = Math.Abs(dx) <= 2.2 && dy >= -5 && dy <= 3;
                bool dot = Math.Abs(dx) <= 2.2 && dy >= 6 && dy <= 9.5;
                return !(bar || dot);
            }
            case TrayBadge.Dots:
            {
                foreach (double cx in (double[])[-10.5, 0, 10.5])
                    if ((dx - cx) * (dx - cx) + (dy - 6) * (dy - 6) <= 4.2 * 4.2) return true;
                return false;
            }
            case TrayBadge.DownArrow:
            {
                bool shaft = Math.Abs(dx) <= 3.2 && dy >= -14 && dy <= 1;
                bool head = dy >= -1 && dy <= 12 && Math.Abs(dx) <= 12 * (12 - dy) / 13;
                return shaft || head;
            }
            case TrayBadge.CircularArrow:
            {
                // A ring open at the top right, with an arrowhead at 12 o'clock pointing clockwise.
                double angle = (Math.Atan2(dx, -dy) + 2 * Math.PI) % (2 * Math.PI);
                bool ring = r >= BadgeR - 5 && r <= BadgeR - 0.5 && angle > Math.PI / 3;
                double hx = dx, hy = dy + (BadgeR - 2.75);
                bool head = hx >= -2 && hx <= 8 && Math.Abs(hy) <= (8 - hx) * 0.75;
                return ring || head;
            }
            case TrayBadge.CrossCircle:
            {
                if (r > BadgeR) return false;
                // Knock out an X.
                double a = Math.Abs(dx - dy) / Math.Sqrt(2), b = Math.Abs(dx + dy) / Math.Sqrt(2);
                bool cross = (a <= 2.6 || b <= 2.6) && r <= BadgeR - 5;
                return !cross;
            }
            default:
                return false;
        }
    }

    // mark.svg: M9.5 10 a4.5 4.5 0 0 1 9 0 V31 C29.5 31 41.5 26 50.5 15 C52 13.5 54.5 14 54.5 16 V26
    //           C54.5 45 39.5 58 18.5 59 H9.5 Z   M18.5 41 V51 C31.5 49.5 40.5 42 44.5 31 C37.5 37 28.5 40.5 18.5 41 Z (even-odd)
    private static readonly (double X, double Y)[] Outer = BuildOuter();
    private static readonly (double X, double Y)[] Hole = BuildHole();

    private static (double, double)[] BuildOuter()
    {
        var p = new List<(double, double)>();
        for (int i = 0; i <= 16; i++) // the rounded top: centre (14, 10), radius 4.5, from left to right over the top
        {
            double t = Math.PI - Math.PI * i / 16;
            p.Add((14 + 4.5 * Math.Cos(t), 10 - 4.5 * Math.Sin(t)));
        }
        p.Add((18.5, 31));
        Bezier(p, (18.5, 31), (29.5, 31), (41.5, 26), (50.5, 15));
        Bezier(p, (50.5, 15), (52, 13.5), (54.5, 14), (54.5, 16));
        p.Add((54.5, 26));
        Bezier(p, (54.5, 26), (54.5, 45), (39.5, 58), (18.5, 59));
        p.Add((9.5, 59));
        return [.. p];
    }

    private static (double, double)[] BuildHole()
    {
        var p = new List<(double, double)> { (18.5, 41), (18.5, 51) };
        Bezier(p, (18.5, 51), (31.5, 49.5), (40.5, 42), (44.5, 31));
        Bezier(p, (44.5, 31), (37.5, 37), (28.5, 40.5), (18.5, 41));
        return [.. p];
    }

    private static void Bezier(List<(double, double)> p, (double X, double Y) a, (double X, double Y) b, (double X, double Y) c, (double X, double Y) d)
    {
        for (int i = 1; i <= 16; i++)
        {
            double t = i / 16.0, m = 1 - t;
            p.Add((m * m * m * a.X + 3 * m * m * t * b.X + 3 * m * t * t * c.X + t * t * t * d.X,
                   m * m * m * a.Y + 3 * m * m * t * b.Y + 3 * m * t * t * c.Y + t * t * t * d.Y));
        }
    }

    private static bool InMark(double u, double v) => InPolygon(Outer, u, v) ^ InPolygon(Hole, u, v);

    private static bool InPolygon((double X, double Y)[] poly, double x, double y)
    {
        bool inside = false;
        for (int i = 0, j = poly.Length - 1; i < poly.Length; j = i++)
        {
            var (xi, yi) = poly[i];
            var (xj, yj) = poly[j];
            if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
        }
        return inside;
    }
}

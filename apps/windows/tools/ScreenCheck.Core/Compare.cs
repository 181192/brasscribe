using System.Net;
using System.Text.Json;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// What changed between two screenshots of one screen, the way Studio's catalogue compares (studio/catalogue/compare.mjs).
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

/// <summary>
/// Compares a catalogue's screenshots taken at the merge base with the same taken here, and writes the report:
/// index.html (before, the difference and after for each changed screen), summary.md and result.json (written last;
/// without it the comparison did not finish).
/// </summary>
public static class ScreenshotReport
{
    public sealed record Result(int Screens, IReadOnlyList<string> Changed, IReadOnlyList<string> Added, IReadOnlyList<string> Gone,
        IReadOnlyList<string> Minor, string Summary)
    {
        public bool Any => Changed.Count + Added.Count + Gone.Count > 0;
    }

    /// <param name="load">Reads a PNG.</param>
    /// <param name="save">Writes a PNG.</param>
    /// <param name="skip">Screens that were not taken (or not steady when taken) on either side: not compared.</param>
    public static Result Write(string beforeDir, string afterDir, string reportDir, Func<string, Picture> load, Action<string, Picture> save,
        IReadOnlySet<string>? skip = null)
    {
        var images = Path.Combine(reportDir, "images");
        Directory.CreateDirectory(images);
        static List<string> Pngs(string dir) => Directory.Exists(dir)
            ? Directory.GetFiles(dir, "*.png").Select(f => Path.GetFileName(f)!).Order(StringComparer.Ordinal).ToList()
            : [];
        skip ??= new HashSet<string>();
        var had = Pngs(beforeDir).Where(f => !skip.Contains(Stem(f))).ToList();
        var now = Pngs(afterDir).Where(f => !skip.Contains(Stem(f))).ToList();
        var added = had.Count > 0 ? now.Except(had).ToList() : [];
        var gone = now.Count > 0 ? had.Except(now).ToList() : [];
        var changed = new List<string>();
        var minor = new List<string>();
        var counts = new Dictionary<string, (int N, double Share)>();
        foreach (var f in now.Intersect(had))
        {
            string pa = Path.Combine(beforeDir, f), pb = Path.Combine(afterDir, f);
            if (File.ReadAllBytes(pa).AsSpan().SequenceEqual(File.ReadAllBytes(pb))) continue;
            var a = load(pa);
            var b = load(pb);
            var (n, diff) = ImageDiff.Of(a, b);
            if (n == 0) continue;
            counts[f] = (n, (double)n / (diff.Width * diff.Height));
            bool resized = a.Width != b.Width || a.Height != b.Height;
            // A handful of pixels on an anti-aliased edge can come out differently from one run to the next on one
            // machine: under the floor a difference is reported, but is not a change.
            if (n <= ImageDiff.FloorPixels && !resized)
            {
                minor.Add(f);
                continue;
            }
            changed.Add(f);
            File.Copy(pa, Path.Combine(images, $"{Stem(f)}-before.png"), true);
            save(Path.Combine(images, $"{Stem(f)}-diff.png"), diff);
            File.Copy(pb, Path.Combine(images, $"{Stem(f)}-after.png"), true);
        }
        foreach (var f in added) File.Copy(Path.Combine(afterDir, f), Path.Combine(images, f), true);

        var lines = new List<string> { $"Screenshots: {now.Count} screens, {changed.Count} changed, {added.Count} new, {gone.Count} gone." };
        if (had.Count == 0) lines.Add("The commit compared with has no screen catalogue: there was nothing to compare with.");
        lines.AddRange(changed.Select(f => $"- changed: `{f}` ({counts[f].N} pixels, {counts[f].Share * 100:0.00} %)"));
        lines.AddRange(minor.Select(f => $"- within the noise floor, not a change: `{f}` ({counts[f].N} pixels)"));
        lines.AddRange(added.Select(f => $"- new: `{f}`"));
        lines.AddRange(gone.Select(f => $"- gone: `{f}`"));
        if (skip.Count > 0) lines.Add($"- not compared, the screen was not taken on one side: {string.Join(", ", skip.Order().Select(s => $"`{s}`"))}");
        string summary = string.Join("\n", lines) + "\n";
        File.WriteAllText(Path.Combine(reportDir, "summary.md"), "# Screenshots\n\n" + summary);

        static string E(string s) => WebUtility.HtmlEncode(s);
        static string Img(string src) => $"<img src=\"images/{E(src)}\" alt=\"\">";
        static string Block(string title, string rows) => rows.Length > 0 ? $"<h2>{E(title)}</h2>{rows}" : "";
        File.WriteAllText(Path.Combine(reportDir, "index.html"), string.Join("\n",
            "<!doctype html><meta charset=utf-8><title>Screenshots</title>",
            "<style>body{font:16px system-ui;margin:16px}.row{display:flex;gap:8px;align-items:flex-start}.row img{max-width:32%;border:1px solid #ccc}</style>",
            $"<h1>Screenshots</h1><p>{E(lines[0])}</p><p>Each changed screen: before, the difference (in red), after.</p>",
            Block("Changed", string.Concat(changed.Select(f =>
                $"<h3>{E(f)}</h3><div class=\"row\">{Img($"{Stem(f)}-before.png")}{Img($"{Stem(f)}-diff.png")}{Img($"{Stem(f)}-after.png")}</div>"))),
            Block("New", string.Concat(added.Select(f => $"<h3>{E(f)}</h3>{Img(f)}"))),
            Block("Gone", string.Concat(gone.Select(f => $"<p>{E(f)}</p>")))));

        var result = new Result(now.Count, changed, added, gone, minor, summary);
        File.WriteAllText(Path.Combine(reportDir, "result.json"), JsonSerializer.Serialize(new
        {
            any = result.Any,
            screens = now.Count,
            changed,
            added,
            gone,
            minor,
        }, new JsonSerializerOptions { WriteIndented = true }));
        return result;
    }

    private static string Stem(string file) => Path.GetFileNameWithoutExtension(file);
}

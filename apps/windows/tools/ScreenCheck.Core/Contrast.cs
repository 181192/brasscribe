namespace Brasscribe.ScreenCheck;

/// <summary>What a piece of text on screen is, for the contrast it needs (WCAG 1.4.3 and 1.4.11).</summary>
public enum TextKind
{
    /// <summary>Body text: 4.5:1.</summary>
    Normal,
    /// <summary>At least 18 pt, or 14 pt bold (24 px, or 18.66 px at weight 600 and up): 3:1.</summary>
    Large,
    /// <summary>An icon drawn from an icon font (Segoe Fluent Icons): a graphic, 3:1.</summary>
    Icon,
}

/// <summary>A piece of text the app shows, with where it is in the screenshot.</summary>
/// <param name="Text">The words (or the icon's code point), to name it in a finding.</param>
/// <param name="Box">Where it is, in the screenshot's pixels.</param>
/// <param name="Trimmed">The text does not fit and is cut off (an ellipsis or a clip).</param>
public sealed record ScreenText(string Text, Box Box, TextKind Kind, bool Trimmed = false)
{
    /// <summary>The kind for a font size in device-independent pixels, its weight (400 regular, 700 bold) and family.</summary>
    public static TextKind KindOf(double fontSize, int weight, string? fontFamily) =>
        fontFamily is not null && (fontFamily.Contains("Icons", StringComparison.OrdinalIgnoreCase) || fontFamily.Contains("MDL2", StringComparison.OrdinalIgnoreCase))
            ? TextKind.Icon
            : fontSize >= 24 || (fontSize >= 18.66 && weight >= 600) ? TextKind.Large : TextKind.Normal;
}

/// <summary>The colours of text in a screenshot, and their contrast.</summary>
public static class Contrast
{
    /// <summary>The contrast a kind of text needs.</summary>
    public static double Needed(TextKind kind) => kind == TextKind.Normal ? 4.5 : 3.0;

    /// <summary>WCAG relative luminance of an sRGB colour (0xAARRGGBB; alpha ignored).</summary>
    public static double Luminance(uint argb)
    {
        static double Channel(uint v)
        {
            double c = v / 255.0;
            return c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
        }
        return 0.2126 * Channel(argb >> 16 & 0xFF) + 0.7152 * Channel(argb >> 8 & 0xFF) + 0.0722 * Channel(argb & 0xFF);
    }

    public static double Ratio(uint a, uint b)
    {
        double la = Luminance(a), lb = Luminance(b);
        return (Math.Max(la, lb) + 0.05) / (Math.Min(la, lb) + 0.05);
    }

    /// <summary>
    /// The text and ground colours in a box of a screenshot: the ground is the commonest colour, the text the colour
    /// that stands out from it most among those that cover at least two pixels (anti-aliased edges are shades
    /// between the two, so they never stand out more than the text). Null when nothing in the box stands out (the
    /// text is not drawn there, or is the ground's colour).
    /// </summary>
    public static (uint Text, uint Ground, double Ratio)? Measure(Picture picture, Box box)
    {
        var b = box.Within(picture.Width, picture.Height);
        if (b.IsEmpty) return null;
        var counts = new Dictionary<uint, int>();
        for (int y = b.Y; y < b.Bottom; y++)
            for (int x = b.X; x < b.Right; x++)
            {
                uint c = picture[x, y] | 0xFF000000;
                counts[c] = counts.GetValueOrDefault(c) + 1;
            }
        uint ground = counts.MaxBy(kv => kv.Value).Key;
        uint text = ground;
        double best = 1;
        foreach (var (colour, n) in counts)
        {
            if (n < 2 || colour == ground) continue;
            double r = Ratio(colour, ground);
            if (r > best) (best, text) = (r, colour);
        }
        return text == ground ? null : (text, ground, best);
    }

    /// <summary>The texts whose contrast is under what their kind needs, and the ones cut off.</summary>
    public static IEnumerable<Finding> Check(string shot, Picture picture, IEnumerable<ScreenText> texts)
    {
        foreach (var t in texts)
        {
            if (t.Trimmed) yield return new Finding(shot, "clipped", Name(t), "the text does not fit and is cut off");
            if (Measure(picture, t.Box) is not { } m) continue;
            if (m.Ratio + 0.005 < Needed(t.Kind))
                yield return new Finding(shot, "contrast", Name(t),
                    $"{m.Ratio:0.00}:1 ({Hex(m.Text)} on {Hex(m.Ground)}), needs {Needed(t.Kind):0.#}:1");
        }
    }

    private static string Name(ScreenText t) => t.Kind == TextKind.Icon
        ? "icon " + string.Join(" ", t.Text.Select(c => $"U+{(int)c:X4}"))
        : '"' + (t.Text.Length > 40 ? t.Text[..40] + "…" : t.Text).ReplaceLineEndings(" ") + '"';

    public static string Hex(uint argb) => $"#{argb & 0xFFFFFF:X6}";
}

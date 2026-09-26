using System.Globalization;

namespace Brasscribe.Play.Core.Review;

public readonly record struct Rgb(byte R, byte G, byte B)
{
    public static Rgb Parse(string hex)
    {
        var h = hex.TrimStart('#');
        return new Rgb(
            byte.Parse(h[..2], NumberStyles.HexNumber, CultureInfo.InvariantCulture),
            byte.Parse(h[2..4], NumberStyles.HexNumber, CultureInfo.InvariantCulture),
            byte.Parse(h[4..6], NumberStyles.HexNumber, CultureInfo.InvariantCulture));
    }

    public override string ToString() => $"#{R:X2}{G:X2}{B:X2}";

    /// <summary>WCAG relative luminance.</summary>
    public double Luminance
    {
        get
        {
            static double Lin(byte c)
            {
                double s = c / 255.0;
                return s <= 0.04045 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4);
            }
            return 0.2126 * Lin(R) + 0.7152 * Lin(G) + 0.0722 * Lin(B);
        }
    }

    public static double Contrast(Rgb a, Rgb b)
    {
        double la = a.Luminance, lb = b.Luminance;
        return (Math.Max(la, lb) + 0.05) / (Math.Min(la, lb) + 0.05);
    }
}

public enum ThemeKind { Light, Dark, HighContrast }

/// <summary>
/// Colour tokens from docs/accessibility/visual-design-tokens.md (Okabe-Ito blue/orange pair,
/// darkened for light theme). In a Windows contrast theme the app uses system colours instead;
/// shape (ring, parentheses) always carries the level too.
/// </summary>
public sealed record UncertaintyPalette(
    ThemeKind Theme, Rgb Background, Rgb Surface, Rgb Text, Rgb Ink, Rgb Staff,
    Rgb Uncertain, Rgb VeryUncertain, Rgb Cursor, Rgb Focus, Rgb AdLibTint, Rgb LoopTint, Rgb LoopEdge, Rgb Error)
{
    public static readonly UncertaintyPalette Light = new(ThemeKind.Light,
        Rgb.Parse("#FFFFFF"), Rgb.Parse("#F4F4F2"), Rgb.Parse("#1A1A1A"), Rgb.Parse("#000000"), Rgb.Parse("#4D4D4D"),
        Rgb.Parse("#0063A6"), Rgb.Parse("#B04A00"), Rgb.Parse("#6B3FA0"), Rgb.Parse("#0050B3"),
        Rgb.Parse("#EEF3F8"), Rgb.Parse("#FFF3D6"), Rgb.Parse("#8A5A00"), Rgb.Parse("#B3261E"));

    public static readonly UncertaintyPalette Dark = new(ThemeKind.Dark,
        Rgb.Parse("#121212"), Rgb.Parse("#1E1E1E"), Rgb.Parse("#EDEDED"), Rgb.Parse("#F2F2F2"), Rgb.Parse("#A6A6A6"),
        Rgb.Parse("#56B4E9"), Rgb.Parse("#F0A04B"), Rgb.Parse("#C9A7F0"), Rgb.Parse("#8AB4F8"),
        Rgb.Parse("#1B2530"), Rgb.Parse("#33290F"), Rgb.Parse("#E0B65C"), Rgb.Parse("#F2B8B5"));

    public static readonly UncertaintyPalette HighContrast = new(ThemeKind.HighContrast,
        Rgb.Parse("#000000"), Rgb.Parse("#000000"), Rgb.Parse("#FFFFFF"), Rgb.Parse("#FFFFFF"), Rgb.Parse("#FFFFFF"),
        Rgb.Parse("#00FFFF"), Rgb.Parse("#FFFF00"), Rgb.Parse("#FF80FF"), Rgb.Parse("#FFFF00"),
        Rgb.Parse("#000000"), Rgb.Parse("#000000"), Rgb.Parse("#FFFF00"), Rgb.Parse("#FF8080"));

    public static UncertaintyPalette For(ThemeKind theme) => theme switch
    {
        ThemeKind.Dark => Dark,
        ThemeKind.HighContrast => HighContrast,
        _ => Light,
    };
}

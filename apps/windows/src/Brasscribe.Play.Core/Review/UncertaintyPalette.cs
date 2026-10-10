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
/// The score colours of design/tokens/tokens.json (the same values as design/dist/windows/BrasscribeTheme.xaml;
/// a test keeps them in step). Used where the notation is drawn outside XAML: alphaTab's glyph and staff
/// colours, the notehead colour of uncertain notes and the Skia preview. The level is always carried by
/// shape as well: a "?" above the note, boxed below 0.4. In a Windows contrast theme the app draws
/// with system colours instead (<see cref="HighContrast"/> is only a stand-in for tests and previews).
/// </summary>
public sealed record UncertaintyPalette(
    ThemeKind Theme, Rgb Background, Rgb Surface, Rgb Text, Rgb Ink, Rgb Staff,
    Rgb Uncertain, Rgb VeryUncertain, Rgb Cursor, Rgb Focus, Rgb AdLibTint, Rgb LoopTint, Rgb LoopEdge, Rgb Error,
    Rgb CursorTint, Rgb TextMuted)
{
    /// <summary>The selected note's column (<c>selection-tint</c>).</summary>
    public Rgb SelectionTint { get; init; } = Theme switch
    {
        ThemeKind.Dark => Rgb.Parse("#2C2A26"),
        ThemeKind.HighContrast => Rgb.Parse("#000000"),
        _ => Rgb.Parse("#E8E5DE"),
    };

    public static readonly UncertaintyPalette Light = new(ThemeKind.Light,
        Rgb.Parse("#FBFAF7"), Rgb.Parse("#F3F1EC"), Rgb.Parse("#1B1A17"), Rgb.Parse("#121110"), Rgb.Parse("#57534B"), Rgb.Parse("#0063A6"), Rgb.Parse("#B04A00"), Rgb.Parse("#6B3FA0"), Rgb.Parse("#1B1A17"), Rgb.Parse("#EFECE5"), Rgb.Parse("#FFF3D6"), Rgb.Parse("#8A5A00"), Rgb.Parse("#B3261E"), Rgb.Parse("#DED5E6"), Rgb.Parse("#5E5A52"));

    public static readonly UncertaintyPalette Dark = new(ThemeKind.Dark,
        Rgb.Parse("#131210"), Rgb.Parse("#1C1B18"), Rgb.Parse("#EDEBE6"), Rgb.Parse("#F2F0EB"), Rgb.Parse("#A6A29A"), Rgb.Parse("#56B4E9"), Rgb.Parse("#F0A04B"), Rgb.Parse("#C9A7F0"), Rgb.Parse("#EDEBE6"), Rgb.Parse("#221F1B"), Rgb.Parse("#2B2412"), Rgb.Parse("#E0B65C"), Rgb.Parse("#F2B8B5"), Rgb.Parse("#37303D"), Rgb.Parse("#B4B0A7"));

    public static readonly UncertaintyPalette HighContrast = new(ThemeKind.HighContrast,
        Rgb.Parse("#000000"), Rgb.Parse("#000000"), Rgb.Parse("#FFFFFF"), Rgb.Parse("#FFFFFF"), Rgb.Parse("#FFFFFF"),
        Rgb.Parse("#00FFFF"), Rgb.Parse("#00FFFF"), Rgb.Parse("#FFFF00"), Rgb.Parse("#FFFF00"),
        Rgb.Parse("#000000"), Rgb.Parse("#000000"), Rgb.Parse("#FFFF00"), Rgb.Parse("#FFFFFF"),
        Rgb.Parse("#000000"), Rgb.Parse("#FFFFFF"));

    /// <summary>
    /// Pink light (design/system.md §10): the notation is Light's, but for very uncertain, the same orange a shade
    /// darker (BrasscribePinkTheme.xaml), so a note and the preview's "?" match the boxed "?" the XAML draws.
    /// </summary>
    public static readonly UncertaintyPalette PinkLight = Light with { VeryUncertain = Rgb.Parse("#A04300") };

    /// <summary>The score colours of <paramref name="theme"/>, in the Pink palette when <paramref name="pink"/> (Pink dark's are Dark's).</summary>
    public static UncertaintyPalette For(ThemeKind theme, bool pink) => pink && theme == ThemeKind.Light ? PinkLight : For(theme);

    public static UncertaintyPalette For(ThemeKind theme) => theme switch
    {
        ThemeKind.Dark => Dark,
        ThemeKind.HighContrast => HighContrast,
        _ => Light,
    };
}

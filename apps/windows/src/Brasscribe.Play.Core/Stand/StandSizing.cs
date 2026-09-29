namespace Brasscribe.Play.Core.Stand;

/// <summary>
/// The stand's sizing contract (design/music-stand.md §3): the bars per system and the systems per
/// page decide the staff size, not the other way round. When the text size or the zoom grows, bars per
/// system drop first, and a page always keeps at least two systems.
/// </summary>
public static class StandSizing
{
    public const int MinSystems = 2;

    /// <summary>Two pages side by side on a wide, landscape screen (tablet on its side, desktop full screen).</summary>
    public static bool UseSpread(double width, double height) => width >= 1000 && width > height * 1.2;

    /// <summary>4 bars per system; 3 from 150 % text or zoom; 2 from 200 %.</summary>
    public static int BarsPerRow(double textScale, double zoom = 1.0)
    {
        double grow = Math.Max(1.0, textScale) * Math.Max(1.0, zoom);
        return grow >= 2.0 ? 2 : grow >= 1.5 ? 3 : 4;
    }

    /// <summary>
    /// Systems per page to aim for: 7 upright, 5 on its side or per page of a spread, 2 for a score of
    /// several staves (each system is a whole band). Larger text keeps fewer, never below two.
    /// </summary>
    public static double TargetSystems(bool upright, int staves, double textScale = 1.0)
    {
        if (staves > 1) return MinSystems;
        double target = upright ? 7 : 5;
        return Math.Max(MinSystems, target / Math.Max(1.0, textScale));
    }

    /// <summary>
    /// The notation scale that fits the target systems in the page height, from a layout at
    /// <paramref name="currentScale"/> whose systems were <paramref name="systemHeight"/> tall. The width
    /// caps it so the bars of a system never crowd (at least <paramref name="minBarWidth"/> per bar at scale 1).
    /// </summary>
    public static double FitScale(double currentScale, double systemHeight, double pageHeight, double targetSystems,
        double width, int barsPerRow, double minBarWidth = 150)
    {
        if (systemHeight <= 0 || pageHeight <= 0 || targetSystems <= 0) return currentScale;
        double fromHeight = currentScale * pageHeight / (targetSystems * systemHeight);
        double fromWidth = width > 0 && barsPerRow > 0 ? width / (barsPerRow * minBarWidth) : double.PositiveInfinity;
        return Math.Clamp(Math.Min(fromHeight, fromWidth), 0.6, 3.0);
    }

    /// <summary>A new layout is worth it only when the scale moves by more than 8 %.</summary>
    public static bool NeedsRelayout(double current, double fitted) => Math.Abs(fitted - current) > current * 0.08;
}

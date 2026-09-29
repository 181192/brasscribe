namespace Brasscribe.Play.Core.Stand;

/// <summary>The stand's swipe (design/music-stand.md §5.2): a horizontal swipe on the music turns a page.</summary>
public static class StandGesture
{
    /// <summary>A swipe that starts within this of an edge belongs to the system (edge gestures) and never turns a page.</summary>
    public const double EdgeMargin = 24;

    /// <summary>How far the finger has to travel.</summary>
    public const double MinDistance = 48;

    /// <summary>+1 for the next page (a swipe to the left), -1 for the previous page, 0 for no turn.</summary>
    public static int Swipe(double startX, double width, double dx, double dy)
    {
        if (startX < EdgeMargin || startX > width - EdgeMargin) return 0;
        if (Math.Abs(dx) < MinDistance || Math.Abs(dx) < Math.Abs(dy) * 1.5) return 0;
        return dx < 0 ? 1 : -1;
    }
}

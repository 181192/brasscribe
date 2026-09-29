namespace Brasscribe.Play.Core.Stand;

/// <summary>One system (line of music) of the laid-out score, in score-surface coordinates; bars are 0-based.</summary>
public readonly record struct StandSystem(double Top, double Bottom, int FirstBar, int LastBar)
{
    public double Height => Bottom - Top;
    public bool Holds(int bar) => bar >= FirstBar && bar <= LastBar;
}

/// <summary>A page of the stand: whole systems from <see cref="FirstSystem"/> to <see cref="LastSystem"/>.</summary>
public readonly record struct StandPage(int FirstSystem, int LastSystem, double Top, double Bottom, int FirstBar, int LastBar);

/// <summary>
/// The music stand's page model (design/music-stand.md §3). A page is the whole systems that fit the
/// page height. On a single page a turn keeps the last system: the next page starts with it, so the
/// player never loses their place. In a spread (two pages side by side) pages follow on without
/// overlap and a turn moves the right page to the left, so the next line is always in view.
/// </summary>
public sealed class StandPages
{
    private readonly IReadOnlyList<StandSystem> _systems;

    private StandPages(IReadOnlyList<StandSystem> systems, IReadOnlyList<StandPage> pages, bool spread)
    {
        _systems = systems;
        Pages = pages;
        IsSpread = spread;
    }

    public IReadOnlyList<StandPage> Pages { get; }
    public IReadOnlyList<StandSystem> Systems => _systems;
    public bool IsSpread { get; }
    public int Count => Pages.Count;

    public static StandPages Empty { get; } = new([], [], false);

    public static StandPages Build(IReadOnlyList<StandSystem> systems, double pageHeight, bool spread)
    {
        var pages = new List<StandPage>();
        int n = systems.Count, i = 0;
        while (i < n)
        {
            int start = i, end = i;
            double top = systems[start].Top;
            while (end + 1 < n && systems[end + 1].Bottom - top <= pageHeight) end++;
            pages.Add(new StandPage(start, end, top, systems[end].Bottom, systems[start].FirstBar, systems[end].LastBar));
            if (end == n - 1) break;
            // A single page keeps its last system as the next page's first (when it has more than one).
            i = !spread && end > start ? end : end + 1;
        }
        return new StandPages(systems, pages, spread);
    }

    /// <summary>The highest page that can be on the left: in a spread the last view is the last two pages.</summary>
    public int LastLeftPage => IsSpread ? Math.Max(0, Count - 2) : Math.Max(0, Count - 1);

    public int Clamp(int page) => Math.Clamp(page, 0, LastLeftPage);

    /// <summary>Index of the system holding a bar, or -1.</summary>
    public int SystemOf(int bar)
    {
        for (int s = 0; s < _systems.Count; s++)
            if (_systems[s].Holds(bar)) return s;
        return -1;
    }

    /// <summary>
    /// The page for a bar: the page whose top system holds it, else the page that shows it. That is also
    /// the turn rule while playing: when the cursor reaches the last system of a single page (the first
    /// system of the next), or the right-hand page of a spread, the view turns.
    /// </summary>
    public int PageOfBar(int bar)
    {
        if (Count == 0) return 0;
        int system = SystemOf(bar);
        if (system < 0) return bar < _systems[0].FirstBar ? 0 : LastLeftPage;
        for (int p = 0; p < Count; p++)
            if (Pages[p].FirstSystem == system) return Clamp(p);
        for (int p = 0; p < Count; p++)
            if (Pages[p].FirstSystem <= system && system <= Pages[p].LastSystem) return Clamp(p);
        return LastLeftPage;
    }

    /// <summary>Whether a bar is on the page (or the two pages of a spread) now shown.</summary>
    public bool IsInView(int page, int bar)
    {
        if (Count == 0) return false;
        page = Clamp(page);
        int last = IsSpread && page + 1 < Count ? page + 1 : page;
        return bar >= Pages[page].FirstBar && bar <= Pages[last].LastBar;
    }

    /// <summary>The bars shown with a page on the left: its first bar to the last bar of the view.</summary>
    public (int First, int Last) BarsInView(int page)
    {
        if (Count == 0) return (0, 0);
        page = Clamp(page);
        int last = IsSpread && page + 1 < Count ? page + 1 : page;
        return (Pages[page].FirstBar, Pages[last].LastBar);
    }

    /// <summary>
    /// The obscured-area contract (§4.3): the top of the visible window for a page when the control layer
    /// covers <paramref name="obscured"/> at the bottom. When the current system would fall under it, the
    /// window moves down just enough for that system to sit above the layer; nothing is laid out again.
    /// </summary>
    public static double WindowTop(double pageTop, StandSystem? current, double viewportHeight, double obscured, double gap = 12)
    {
        if (current is not { } s) return pageTop;
        double visibleBottom = pageTop + viewportHeight - Math.Max(0, obscured);
        if (s.Bottom + gap <= visibleBottom) return pageTop;
        // Never scroll the current system off the top either.
        double top = s.Bottom + gap - (viewportHeight - Math.Max(0, obscured));
        return Math.Min(top, s.Top);
    }
}

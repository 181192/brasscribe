using System.Collections.Concurrent;
using AlphaTab;
using AlphaTab.Model;
using AlphaTab.Rendering;
using AlphaTab.Rendering.Utils;

namespace Brasscribe.Play.Core.Playback;

/// <summary>One page (alphaTab partial) of a laid-out score: where it goes and which bars it holds.</summary>
public sealed record ScorePageSlot(string Id, double X, double Y, double Width, double Height, int FirstBar, int LastBar);

public sealed record ScoreLayout(int Generation, double Width, double Height, IReadOnlyList<ScorePageSlot> Pages, BoundsLookup? Bounds);

/// <summary>
/// Renders notation off the UI thread and only where it is needed. A layout pass (alphaTab lazy
/// loading) places every page and fills the bounds lookup; pages are then drawn and PNG-encoded one
/// at a time on request, so the view asks only for the pages in or near its viewport. All alphaTab
/// work runs on one worker thread (alphaTab shares static state and is not safe to call concurrently);
/// callers get tasks and never block. A newer layout makes older page requests return null.
/// </summary>
public sealed class LazyScoreRenderer : IDisposable
{
    private readonly BlockingCollection<Action> _queue = new();
    private readonly Thread _worker;
    private readonly string _engine;
    private ScoreRenderer? _renderer;
    private readonly Dictionary<string, object> _results = [];
    private int _generation;

    public LazyScoreRenderer(string engine = "skia")
    {
        _engine = engine;
        _worker = new Thread(() =>
        {
            foreach (var work in _queue.GetConsumingEnumerable()) work();
        }) { IsBackground = true, Name = "Score renderer" };
        _worker.Start();
    }

    public int Generation => Volatile.Read(ref _generation);

    /// <summary>
    /// Lays out the score for the given tracks. <paramref name="prepare"/> runs first on the worker (styling, transposition display).
    /// <paramref name="width"/>, the result and its bounds are in view units (DIPs); the pages are drawn at
    /// <paramref name="pixelScale"/> pixels per unit (the display's scale, 1.5 at 150 %), so they stay sharp when shown at their size in units.
    /// </summary>
    public Task<ScoreLayout> LayoutAsync(Score score, IReadOnlyList<int> tracks, double width, double scale, LayoutMode mode, Action<Score>? prepare = null,
        Review.UncertaintyPalette? theme = null, int barsPerRow = -1, double pixelScale = 1)
    {
        int generation = Interlocked.Increment(ref _generation);
        double px = double.IsFinite(pixelScale) ? Math.Clamp(pixelScale, 1, 4) : 1;
        return Run(() =>
        {
            prepare?.Invoke(score);
            Release();
            var settings = new Settings();
            settings.Core.Engine = _engine;
            settings.Core.EnableLazyLoading = true;
            settings.Core.IncludeNoteBounds = true;
            settings.Display.Scale = Math.Clamp(scale, 0.5, 4.0) * px;
            settings.Display.LayoutMode = mode;
            settings.Display.BarsPerRow = barsPerRow; // the music stand fixes bars per system; -1 lets alphaTab choose
            settings.Player.EnableCursor = false;
            if (theme is not null) ScoreStyler.ApplyTheme(settings, theme);
            ScoreStyler.HideHeader(settings); // the screen shows the title itself
            // The page padding is in pixels, not scaled with the notation: keep it the same in view units.
            if (px != 1 && settings.Display.Padding is { } padding)
                settings.Display.Padding = padding.Select(p => p * px).ToList();
            var renderer = new ScoreRenderer(settings) { Width = width * px };
            var pages = new List<ScorePageSlot>();
            double totalW = 0, totalH = 0;
            Exception? error = null;
            renderer.PartialLayoutFinished.On((RenderFinishedEventArgs e) =>
                pages.Add(new ScorePageSlot(e.Id, e.X / px, e.Y / px, e.Width / px, e.Height / px, (int)e.FirstMasterBarIndex, (int)e.LastMasterBarIndex)));
            renderer.PartialRenderFinished.On((RenderFinishedEventArgs e) =>
            {
                if (e.RenderResult is not null) _results[e.Id] = e.RenderResult;
            });
            renderer.RenderFinished.On((RenderFinishedEventArgs e) =>
            {
                totalW = e.TotalWidth / px;
                totalH = e.TotalHeight / px;
            });
            renderer.Error.On((Exception e) => error = e);
            renderer.RenderScore(score, tracks.Select(i => (double)i).ToList(), null!);
            if (error is not null) throw new InvalidOperationException("alphaTab could not lay out the score", error);
            _renderer = renderer;
            if (renderer.BoundsLookup is { } bounds && px != 1) ScaleBounds(bounds, 1 / px);
            return new ScoreLayout(generation, totalW, totalH, pages, renderer.BoundsLookup);
        });
    }

    /// <summary>Every rectangle of a bounds lookup times <paramref name="factor"/> (pixels to view units), each one once.</summary>
    internal static void ScaleBounds(BoundsLookup lookup, double factor)
    {
        var done = new HashSet<Bounds>(ReferenceEqualityComparer.Instance);
        void S(Bounds? b)
        {
            if (b is null || !done.Add(b)) return;
            b.X *= factor;
            b.Y *= factor;
            b.W *= factor;
            b.H *= factor;
        }
        foreach (var system in lookup.StaffSystems)
        {
            S(system.VisualBounds);
            S(system.RealBounds);
            foreach (var master in system.Bars)
            {
                S(master.VisualBounds);
                S(master.RealBounds);
                S(master.LineAlignedBounds);
                foreach (var bar in master.Bars)
                {
                    S(bar.VisualBounds);
                    S(bar.RealBounds);
                    foreach (var beat in bar.Beats)
                    {
                        S(beat.VisualBounds);
                        S(beat.RealBounds);
                        beat.OnNotesX *= factor;
                        if (beat.Notes is null) continue;
                        foreach (var note in beat.Notes) S(note.NoteHeadBounds);
                    }
                }
            }
        }
    }

    /// <summary>
    /// One PNG of a few bars of one part with the design overlays (the review snippet). Runs on the
    /// renderer's thread like everything else that touches alphaTab.
    /// </summary>
    public Task<byte[]> SnippetAsync(Score score, int track, int firstBar, int barCount, double scale,
        Review.UncertaintyPalette theme, Func<RenderOutput, IReadOnlyList<OverlayItem>> overlay, Action<Score>? prepare = null) => Run(() =>
    {
        prepare?.Invoke(score);
        var service = new ScoreRenderService("skia", scale, pageLayout: false).WithTheme(theme);
        var output = service.Render(score, [track], 100000);
        var view = ScorePreview.BarsViewport(output, firstBar - 1, firstBar - 2 + barCount);
        try { return ScorePreview.Compose(output, overlay(output), theme, pad: 16, viewport: view); }
        finally { ScoreRenderService.Release(output); }
    });

    /// <summary>PNG of one page of the current layout; null when a newer layout replaced it.</summary>
    public Task<byte[]?> RenderPageAsync(int generation, string pageId) => Run(() =>
    {
        if (generation != Generation || _renderer is null) return null;
        if (!_results.TryGetValue(pageId, out var result))
        {
            _renderer.RenderResult(pageId);
            if (!_results.TryGetValue(pageId, out result)) return null;
        }
        var png = ScoreRenderService.ToPng(result);
        if (result is IDisposable d) d.Dispose();
        _results.Remove(pageId);
        return png;
    });

    private Task<T> Run<T>(Func<T> work)
    {
        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        _queue.Add(() =>
        {
            try { tcs.SetResult(work()); }
            catch (Exception e) { tcs.SetException(e); }
        });
        return tcs.Task;
    }

    private void Release()
    {
        foreach (var r in _results.Values)
            if (r is IDisposable d) d.Dispose();
        _results.Clear();
        _renderer?.Destroy();
        _renderer = null;
    }

    public void Dispose()
    {
        _queue.Add(Release);
        _queue.CompleteAdding();
    }
}

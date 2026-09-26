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

    /// <summary>Lays out the score for the given tracks. <paramref name="prepare"/> runs first on the worker (styling, transposition display).</summary>
    public Task<ScoreLayout> LayoutAsync(Score score, IReadOnlyList<int> tracks, double width, double scale, LayoutMode mode, Action<Score>? prepare = null)
    {
        int generation = Interlocked.Increment(ref _generation);
        return Run(() =>
        {
            prepare?.Invoke(score);
            Release();
            var settings = new Settings();
            settings.Core.Engine = _engine;
            settings.Core.EnableLazyLoading = true;
            settings.Core.IncludeNoteBounds = true;
            settings.Display.Scale = Math.Clamp(scale, 0.5, 4.0);
            settings.Display.LayoutMode = mode;
            settings.Player.EnableCursor = false;
            var renderer = new ScoreRenderer(settings) { Width = width };
            var pages = new List<ScorePageSlot>();
            double totalW = 0, totalH = 0;
            Exception? error = null;
            renderer.PartialLayoutFinished.On((RenderFinishedEventArgs e) =>
                pages.Add(new ScorePageSlot(e.Id, e.X, e.Y, e.Width, e.Height, (int)e.FirstMasterBarIndex, (int)e.LastMasterBarIndex)));
            renderer.PartialRenderFinished.On((RenderFinishedEventArgs e) =>
            {
                if (e.RenderResult is not null) _results[e.Id] = e.RenderResult;
            });
            renderer.RenderFinished.On((RenderFinishedEventArgs e) =>
            {
                totalW = e.TotalWidth;
                totalH = e.TotalHeight;
            });
            renderer.Error.On((Exception e) => error = e);
            renderer.RenderScore(score, tracks.Select(i => (double)i).ToList(), null!);
            if (error is not null) throw new InvalidOperationException("alphaTab could not lay out the score", error);
            _renderer = renderer;
            return new ScoreLayout(generation, totalW, totalH, pages, renderer.BoundsLookup);
        });
    }

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

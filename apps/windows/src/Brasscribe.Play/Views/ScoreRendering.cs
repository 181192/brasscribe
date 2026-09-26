using Brasscribe.Play.Core.Playback;

namespace Brasscribe.Play.Views;

/// <summary>
/// The one notation renderer of the app. alphaTab shares static state and is not safe to call from
/// two threads, so the score screen and the review snippet queue their work on the same worker.
/// </summary>
public static class ScoreRendering
{
    public static LazyScoreRenderer Renderer { get; } = new("skia");
}

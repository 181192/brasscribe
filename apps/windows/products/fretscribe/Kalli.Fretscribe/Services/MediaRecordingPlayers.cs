using Kalli.Scribe.Tab;
using Microsoft.UI.Dispatching;
using Windows.Media.Core;
using Windows.Media.Playback;

namespace Kalli.Fretscribe.Services;

/// <summary>The song's recording through Windows' media player: any speed with the pitch kept, and the bars repeated.</summary>
public sealed class MediaRecordingPlayers(DispatcherQueue queue) : IRecordingPlayers
{
    public IRecordingPlayer Open(string path, IRecordingPlayerListener listener) => new MediaRecordingPlayer(path, listener, queue);
}

/// <summary>
/// One recording in a <see cref="MediaPlayer"/>. The player's events arrive off the UI thread and are passed on there;
/// a timer on the UI thread brings it back to the start of the stretch being repeated.
/// </summary>
internal sealed class MediaRecordingPlayer : IRecordingPlayer
{
    /// <summary>How often the repeat's end is looked for.</summary>
    private static readonly TimeSpan Watch = TimeSpan.FromMilliseconds(25);

    private readonly MediaPlayer _player;
    private readonly IRecordingPlayerListener _listener;
    private readonly DispatcherQueue _queue;
    private readonly DispatcherQueueTimer _timer;
    private bool _disposed;
    private double _speed = 1.0;

    public MediaRecordingPlayer(string path, IRecordingPlayerListener listener, DispatcherQueue queue)
    {
        _listener = listener;
        _queue = queue;
        _player = new MediaPlayer
        {
            AutoPlay = false,
            AudioCategory = MediaPlayerAudioCategory.Media,
            Source = MediaSource.CreateFromUri(new Uri(path)),
        };
        _player.PlaybackSession.PlaybackStateChanged += (s, _) =>
        {
            bool playing = s.PlaybackState is MediaPlaybackState.Playing;
            Post(() => { if (playing != Playing) { Playing = playing; _listener.OnPlaying(playing); } });
        };
        _player.MediaEnded += (_, _) => Post(() =>
        {
            Asked = false;
            Playing = false;
            _listener.OnEnded();
        });
        _player.MediaFailed += (_, _) => Post(_listener.OnFailed);
        _timer = queue.CreateTimer();
        _timer.Interval = Watch;
        _timer.Tick += (_, _) => Loop();
    }

    private void Post(Action action) => _queue.TryEnqueue(() => { if (!_disposed) action(); });

    public bool Playing { get; private set; }
    public bool Asked { get; private set; }
    public double Position => _player.PlaybackSession.Position.TotalSeconds;
    public double Duration => _player.PlaybackSession.NaturalDuration.TotalSeconds;

    public double Speed
    {
        get => _speed;
        set
        {
            _speed = value;
            _player.PlaybackSession.PlaybackRate = value;
        }
    }

    public SecondsRange? Repeat { get; set; }

    public void Play()
    {
        Asked = true;
        _player.PlaybackSession.PlaybackRate = _speed;
        _player.Play();
        _timer.Start();
    }

    public void Pause()
    {
        Asked = false;
        _player.Pause();
        _timer.Stop();
    }

    public void SeekTo(double seconds) => _player.PlaybackSession.Position = TimeSpan.FromSeconds(Math.Max(seconds, 0));

    /// <summary>At the end of the stretch: back to its start, playing on.</summary>
    private void Loop()
    {
        if (Repeat is { } r && Asked && Position >= r.End) SeekTo(r.Start);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _timer.Stop();
        _player.Pause();
        _player.Dispose();
    }
}

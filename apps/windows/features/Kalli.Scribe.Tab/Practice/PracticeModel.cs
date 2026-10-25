using CommunityToolkit.Mvvm.ComponentModel;
using Kalli.Scribe.Engine;

namespace Kalli.Scribe.Tab;

/// <summary>
/// Practice: the recording of the song on screen, where it is, how fast it plays and which bars it repeats. It
/// outlives the tab's views and is kept for each song while the app runs, and on this device
/// (<see cref="PracticePlaces"/>) for every song in Your songs, so a song opened after the app was closed is where it
/// was left. Used from the UI thread: its awaits come back there, and the files are read and written off it.
/// </summary>
public sealed class PracticeModel(PracticeRecordings store, PracticePlaces places, IRecordingPlayers players)
    : ObservableObject, IRecordingPlayerListener, IDisposable
{
    /// <summary>How near the end of a stretch counts as its end, in seconds.</summary>
    private const double Edge = 0.05;

    private readonly Dictionary<string, PracticePlace> _left = [];
    private IRecordingPlayer? _player;
    private TabClock? _clock;
    private string? _song;
    private string? _job;
    private int _looking;
    private CancellationTokenSource? _fetching;
    /// <summary>Counts the player's changes: a place read from disk is not taken over one made since it was asked for.</summary>
    private int _changes;
    /// <summary>The song on screen has a place on disk that is not read yet.</summary>
    private bool _unread;
    /// <summary>The speed and repeat before <see cref="PlayBarSlowly"/>, and the bar it repeats.</summary>
    private (PracticePlace Was, RepeatBars Bar)? _beforeSlow;
    /// <summary>The places are written one at a time, in order, off the UI thread: an older one never lands after a newer one.</summary>
    private Task _lastWrite = Task.CompletedTask;

    private RecordingState _recording = RecordingState.Looking;
    private bool _playing;
    private int _speed = PracticeSpeed.Full;
    private RepeatBars? _repeat;
    private double _at;
    private int _jumps;

    public RecordingState Recording { get => _recording; private set => SetProperty(ref _recording, value); }
    public bool Playing { get => _playing; private set => SetProperty(ref _playing, value); }
    /// <summary>Per cent of the recording's own speed.</summary>
    public int Speed { get => _speed; private set => SetProperty(ref _speed, value); }
    public RepeatBars? Repeat { get => _repeat; private set => SetProperty(ref _repeat, value); }
    /// <summary>The second of the recording the song is at while it is not playing; while it plays, <see cref="Now"/> says.</summary>
    public double At { get => _at; private set => SetProperty(ref _at, value); }
    /// <summary>Counts the times the player moved the song: a bar back or on, to the start, into a repeat. The page then shows where it went.</summary>
    public int Jumps { get => _jumps; private set => SetProperty(ref _jumps, value); }

    /// <summary>The second of the recording the song is at.</summary>
    public double Now() => _player is { } p && Playing ? p.Position : At;

    /// <summary>
    /// The song on screen: <paramref name="song"/> names it, <paramref name="job"/> is its job on the computer (the
    /// recording is kept and fetched by it), <paramref name="clock"/> follows the recording in its tab, and
    /// <paramref name="inHand"/> is the recording's file when the app has it. <paramref name="songs"/>: the jobs of Your
    /// songs, when the list is known; the recordings of the others go.
    /// </summary>
    public Task OpenAsync(string song, string? job, TabClock? clock, string? inHand, IReadOnlySet<string>? songs = null)
    {
        _clock = clock;
        if (song != _song)
        {
            Remember();
            Release();
            _song = song;
            var was = _left.GetValueOrDefault(song);
            // Not in memory: the place kept on disk is read with the recording.
            _unread = was is null;
            Take(was ?? new PracticePlace(0.0, PracticeSpeed.Full, null));
        }
        _job = job;
        Repeat = Repeat is { } r && Fits(r) ? r : null;
        if (_player is not null || _fetching is not null) { Stretch(); return Task.CompletedTask; }
        string? file = inHand is not null && File.Exists(inHand) && new FileInfo(inHand).Length > 0 ? inHand : null;
        int look = ++_looking;
        int since = _changes;
        bool ask = _unread;
        Recording = RecordingState.Looking;
        // The recordings and places of the songs no longer in Your songs go, in order with the writes of the places: a
        // prune never runs beside a write.
        var pruned = job is not null && songs is not null && songs.Contains(job)
            ? Write(() => { store.Prune(songs); places.Prune(songs); })
            : Task.CompletedTask;
        return LookAsync(look, since, ask, job, file, pruned);
    }

    private async Task LookAsync(int look, int since, bool ask, string? job, string? file, Task pruned)
    {
        var (found, kept) = await Task.Run(async () =>
        {
            await pruned.ConfigureAwait(false);
            string? found = job is null ? file : file is not null ? store.Keep(job, file) : store.Find(job);
            return (found, job is not null && ask ? places.Read(job) : null);
        });
        if (look != _looking) return;
        if (_unread && kept is not null && _changes == since)
        {
            Take(kept);
            Repeat = Repeat is { } r && Fits(r) ? r : null;
            // The page goes to where the song was left, as it does when the player moves it.
            Jumps++;
        }
        _unread = false;
        if (found is not null) Load(found); else Recording = RecordingState.NotHere;
    }

    private void Take(PracticePlace place)
    {
        At = place.At;
        Speed = Math.Clamp(place.Speed, PracticeSpeed.Min, PracticeSpeed.Max);
        Repeat = place.Repeat;
    }

    /// <summary><paramref name="bars"/> are bars of the tab on screen.</summary>
    private bool Fits(RepeatBars bars) => _clock is null || (bars.First >= 0 && bars.First <= bars.Last && bars.Last < _clock.Bars);

    private void Load(string file)
    {
        var player = players.Open(file, this);
        _player = player;
        player.Speed = Speed / 100.0;
        if (At > 0) player.SeekTo(At);
        Stretch();
        Recording = RecordingState.Here;
    }

    /// <summary>Gives the player the seconds of the bars to repeat.</summary>
    private void Stretch()
    {
        if (_player is { } p) p.Repeat = Repeat is { } r && _clock is { } c ? c.Span(r) : null;
    }

    /// <summary>Copies the recording from the computer, which holds what it was sent.</summary>
    public async Task FetchAsync(IEngineClient engine)
    {
        if (_job is not { } job) return;
        // One fetch at a time: a second press while one runs does nothing.
        if (_fetching is not null || _player is not null) return;
        int look = ++_looking;
        Recording = RecordingState.Getting;
        using var cancel = new CancellationTokenSource();
        _fetching = cancel;
        // This fetch's own file: a fetch given up on leaving the screen clears it, also after the next one has begun.
        string? part = null;
        string? got = null;
        try
        {
            got = await Task.Run(async () =>
            {
                string into = store.Arriving(job) ?? throw new InvalidOperationException("no place to keep the recording");
                part = into;
                await using (var input = await engine.GetJobInputAsync(job, cancel.Token).ConfigureAwait(false))
                await using (var output = File.Create(into))
                    await input.CopyToAsync(output, cancel.Token).ConfigureAwait(false);
                return store.Arrived(job, into) ?? throw new IOException("the recording came empty");
            }, cancel.Token);
        }
        catch (OperationCanceledException) when (cancel.IsCancellationRequested)
        {
            await Task.Run(() => PracticeRecordings.Dropped(part));
        }
        catch (Exception e)
        {
            System.Diagnostics.Trace.TraceWarning($"the recording could not be fetched: {e.Message}");
            var why = await Task.Run(() => { PracticeRecordings.Dropped(part); return PracticeRecordings.WhyNot(e, store.Room); });
            if (look == _looking) Recording = why;
        }
        finally
        {
            if (_fetching == cancel) _fetching = null;
        }
        if (got is not null && look == _looking) Load(got);
    }

    public void Toggle()
    {
        if (_player is not { } p) return;
        if (Playing || p.Playing) { p.Pause(); return; }
        // Asked to play while the system holds the sound back: asked again, from the start of the asking.
        if (p.Asked) p.Pause();
        // From the end, or from outside the bars being repeated, it starts over.
        SecondsRange? span = Repeat is { } r && _clock is { } c ? c.Span(r) : null;
        double? end = _clock?.End;
        if (span is { } s && (At < s.Start - Edge || At >= s.End - Edge)) Seek(s.Start);
        else if (end is { } e && At >= e - Edge) Seek(0.0);
        p.Play();
    }

    public void Pause() => _player?.Pause();

    private void Seek(double seconds)
    {
        _changes++;
        double to = Math.Max(seconds, 0.0);
        _player?.SeekTo(to);
        At = to;
        Jumps++;
        Remember();
    }

    /// <summary>To the line of <paramref name="bar"/>, kept inside the bars being repeated.</summary>
    public void ToBar(int bar)
    {
        if (_clock is not { } clock) return;
        int within = Repeat is { } r ? Math.Clamp(bar, r.First, r.Last) : Math.Clamp(bar, 0, clock.Bars - 1);
        Seek(clock.SecondsAt(within));
    }

    /// <summary>A bar back or on from the bar the song is in. In the last bar (of the tab, or of the bars being repeated) there is no bar on: nothing happens.</summary>
    public void Step(int bars)
    {
        if (_clock is not { } clock) return;
        int bar = clock.PlaceAt(Now()).Bar;
        if (bars > 0 && !HasBarOn(bar)) return;
        ToBar(bar + bars);
    }

    /// <summary>There is a bar after <paramref name="bar"/> to step on to: it is not the last of the tab, nor the last of the bars being repeated.</summary>
    public bool HasBarOn(int bar) => _clock is { } clock && bar < (Repeat?.Last ?? clock.Bars - 1);

    /// <summary>Back to where the repeat starts; to the start of the tab when nothing is repeated.</summary>
    public void ToStart() => ToBar(Repeat?.First ?? 0);

    public void Slower() => SpeedTo(PracticeSpeed.Slower(Speed));
    public void Faster() => SpeedTo(PracticeSpeed.Faster(Speed));

    private void SpeedTo(int percent)
    {
        _changes++;
        Speed = percent;
        if (_player is { } p) p.Speed = percent / 100.0;
        Remember();
    }

    /// <summary>
    /// One bar again and again, slowly, from its start: to listen to a note the tab is not sure of.
    /// <paramref name="bar"/> is counted from 0; it plays when the recording is on this device.
    /// </summary>
    public void PlayBarSlowly(int bar)
    {
        if (_clock is not { } clock || bar < 0 || bar >= clock.Bars) return;
        var one = new RepeatBars(bar, bar);
        // The player's own speed and repeat, to go back to when the note is left (the first of several bars played slowly).
        _beforeSlow = _beforeSlow is { } slow && Speed == PracticeSpeed.Slow && Repeat == slow.Bar
            ? (slow.Was, one)
            : (new PracticePlace(At, Speed, Repeat), one);
        SpeedTo(PracticeSpeed.Slow);
        SetRepeat(one);
        ToBar(bar);
        if (!Playing) Toggle();
    }

    /// <summary>
    /// The note a bar was played slowly for is left: the speed and repeat the player had come back, unless the player
    /// changed them since. The song plays on, or stays paused, where it is.
    /// </summary>
    public void EndSlowly()
    {
        if (_beforeSlow is not { } slow) return;
        _beforeSlow = null;
        if (Speed != PracticeSpeed.Slow || Repeat != slow.Bar) return;
        SpeedTo(slow.Was.Speed);
        SetRepeat(slow.Was.Repeat);
    }

    /// <summary>Repeats <paramref name="bars"/>; null plays on. The song goes to the first of them when it is outside them.</summary>
    public void SetRepeat(RepeatBars? bars)
    {
        _changes++;
        Repeat = bars;
        Stretch();
        if (bars is not null && _clock is { } clock)
        {
            int bar = clock.PlaceAt(Now()).Bar;
            if (bar < bars.First || bar > bars.Last) ToBar(bars.First);
        }
        Remember();
    }

    /// <summary>The tab is left: the sound stops, a fetch that is running is given up, and the song is kept where it was.</summary>
    public void Leave()
    {
        _looking++;
        _fetching?.Cancel();
        _fetching = null;
        Remember();
        Release();
        Recording = RecordingState.Looking;
    }

    private void Release()
    {
        if (_player is { } p)
        {
            if (Playing) At = p.Position;
            p.Dispose();
        }
        _player = null;
        Playing = false;
    }

    private void Remember()
    {
        if (_song is not { } song) return;
        var place = new PracticePlace(Now(), Speed, Repeat);
        _left[song] = place;
        // Not before the place kept on disk was read: what is there is not written over with the defaults.
        if (_job is not { } job || _unread) return;
        Write(() => places.Save(job, place));
    }

    /// <summary>Runs <paramref name="write"/> after every write asked for before it.</summary>
    private Task Write(Action write) => _lastWrite = _lastWrite.ContinueWith(_ => write(), CancellationToken.None,
        TaskContinuationOptions.None, TaskScheduler.Default);

    /// <summary>The last write of a place, for the tests.</summary>
    internal Task LastWrite => _lastWrite;

    void IRecordingPlayerListener.OnPlaying(bool playing)
    {
        if (!playing && _player is { } p) At = p.Position;
        Playing = playing;
        if (!playing) Remember();
    }

    void IRecordingPlayerListener.OnEnded()
    {
        if (_player is { } p) At = p.Position;
        Playing = false;
    }

    void IRecordingPlayerListener.OnFailed()
    {
        Release();
        Recording = RecordingState.Unplayable;
    }

    /// <summary>The model is no longer needed: the sound stops. Writes that are under way still finish.</summary>
    public void Dispose() => Release();

    /// <summary>As a new start of the app would be: nothing in memory, only what is kept on disk. For the tests.</summary>
    internal void ForgetAllButTheDisk()
    {
        Leave();
        _left.Clear();
        _song = null;
        _job = null;
        At = 0.0;
        Speed = PracticeSpeed.Full;
        Repeat = null;
    }

    /// <summary>The player, for the tests that listen to what it does.</summary>
    internal IRecordingPlayer? RecordingPlayer => _player;
}

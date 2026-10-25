using System.Net;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>Practice with a recording (<see cref="PracticeModel"/>), on a player that only remembers what it was told.</summary>
public class PracticeModelTests : TempFolderTest, IAsyncLifetime
{
    private readonly List<PracticeModel> _models = [];

    public Task InitializeAsync() => Task.CompletedTask;

    /// <summary>The places still being written land before the folder goes.</summary>
    public async Task DisposeAsync()
    {
        foreach (var m in _models) await m.LastWrite;
    }

    private sealed class FakePlayer(IRecordingPlayerListener listener) : IRecordingPlayer
    {
        public bool Playing { get; private set; }
        public bool Asked { get; private set; }
        public double Position { get; set; }
        public double Duration => 60;
        public double Speed { get; set; } = 1;
        public SecondsRange? Repeat { get; set; }
        public bool Released { get; private set; }

        public void Play() { Asked = true; Playing = true; listener.OnPlaying(true); }
        public void Pause() { Asked = false; Playing = false; listener.OnPlaying(false); }
        public void SeekTo(double seconds) => Position = seconds;
        public void Dispose() => Released = true;
    }

    private sealed class FakePlayers : IRecordingPlayers
    {
        public List<(string Path, FakePlayer Player)> Opened { get; } = [];

        public IRecordingPlayer Open(string path, IRecordingPlayerListener listener)
        {
            var p = new FakePlayer(listener);
            Opened.Add((path, p));
            return p;
        }
    }

    /// <summary>An engine that answers only the recording of a job, or fails with <paramref name="status"/>.</summary>
    private sealed class InputEngine(byte[]? input, HttpStatusCode status = HttpStatusCode.NotFound) : IEngineClient
    {
        public Uri BaseAddress => new("http://engine.test/");
        public string? Token { get; set; }
        public int Asked { get; private set; }

        public Task<Stream> GetJobInputAsync(string jobId, CancellationToken ct = default)
        {
            Asked++;
            return input is null ? throw new EngineException("no", status) : Task.FromResult<Stream>(new MemoryStream(input));
        }

        public Task<Health> GetHealthAsync(CancellationToken ct = default) => throw new NotSupportedException();
        public Task<IReadOnlyList<ProfileInfo>> ListProfilesAsync(CancellationToken ct = default) => throw new NotSupportedException();
        public Task<AudioRef> UploadAudioAsync(Stream audio, string filename, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Job> CreateJobAsync(JobCreate request, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Job> GetJobAsync(string jobId, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Job> CancelJobAsync(string jobId, CancellationToken ct = default) => throw new NotSupportedException();
        public IAsyncEnumerable<JobEvent> StreamEventsAsync(string jobId, int after = -1, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Composition> GetCompositionAsync(string jobId, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<IReadOnlyList<Artifact>> ListArtifactsAsync(string jobId, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Stream> DownloadAsync(string jobId, JobDownload what, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Stream> GetArtifactAsync(string jobId, string name, CancellationToken ct = default) => throw new NotSupportedException();
        public Task<Stream> DownloadBrailleAsync(string jobId, string? part = null, CancellationToken ct = default) => throw new NotSupportedException();
    }

    /// <summary>Eight bars of four at 120 a minute, from the first second: bar n starts at 1 + 2n seconds.</summary>
    private static TabClock Clock() => new([.. Enumerable.Range(0, 40).Select(i => 1.0 + i * 0.5)], 0,
        [.. Enumerable.Range(0, 8).Select(i => new TabMeasure($"{i + 1}", 4 * TabIndex.Ticks, 4, TabIndex.Ticks))], 0);

    private readonly FakePlayers _players = new();

    private PracticeModel Model()
    {
        var model = new PracticeModel(new PracticeRecordings(Path.Combine(Dir, "recordings")), new PracticePlaces(Path.Combine(Dir, "practice")), _players);
        _models.Add(model);
        return model;
    }

    private string Take()
    {
        string path = Path.Combine(Dir, "take.wav");
        File.WriteAllBytes(path, new byte[100]);
        return path;
    }

    [Fact]
    public async Task A_recording_in_hand_is_kept_and_plays_from_where_it_is()
    {
        using var model = Model();
        await model.OpenAsync("riff", "job-1", Clock(), Take());
        Assert.Equal(RecordingState.Here, model.Recording);
        var (path, player) = Assert.Single(_players.Opened);
        Assert.StartsWith(Path.Combine(Dir, "recordings"), path);
        model.Toggle();
        Assert.True(model.Playing);
        player.Position = 4.2;
        Assert.Equal(4.2, model.Now());
        // A bar on from the second bar is the third: its line is 5 seconds in.
        model.Step(1);
        Assert.Equal(5.0, model.At, 9);
        Assert.Equal(5.0, player.Position, 9);
        Assert.Equal(1, model.Jumps);
        model.Toggle();
        Assert.False(model.Playing);
        // In the last bar there is no bar on.
        model.ToBar(7);
        Assert.False(model.HasBarOn(7));
        model.Step(1);
        Assert.Equal(15.0, model.At, 9);
    }

    [Fact]
    public async Task Repeated_bars_play_again_and_again_and_steps_stay_inside_them()
    {
        using var model = Model();
        await model.OpenAsync("riff", "job-1", Clock(), Take());
        var player = _players.Opened.Single().Player;
        model.SetRepeat(new RepeatBars(2, 3));
        // The song was outside them: it goes to the first.
        Assert.Equal(5.0, model.At, 9);
        Assert.Equal(new SecondsRange(5.0, 9.0), player.Repeat);
        model.ToBar(6);
        Assert.Equal(7.0, model.At, 9);
        Assert.False(model.HasBarOn(3));
        model.ToStart();
        Assert.Equal(5.0, model.At, 9);
        // Played from outside them, it starts over at their start.
        model.SetRepeat(null);
        model.ToBar(0);
        model.SetRepeat(new RepeatBars(4, 4));
        Assert.Equal(9.0, model.At, 9);
    }

    [Fact]
    public async Task A_bar_played_slowly_goes_back_to_the_speed_and_repeat_it_had()
    {
        using var model = Model();
        await model.OpenAsync("riff", "job-1", Clock(), Take());
        var player = _players.Opened.Single().Player;
        model.Faster();
        Assert.Equal(105, model.Speed);
        Assert.Equal(1.05, player.Speed, 9);
        model.PlayBarSlowly(2);
        Assert.Equal(PracticeSpeed.Slow, model.Speed);
        Assert.Equal(new RepeatBars(2, 2), model.Repeat);
        Assert.True(model.Playing);
        // The next mark's bar: the speed and repeat to go back to are still the player's own.
        model.PlayBarSlowly(5);
        Assert.Equal(new RepeatBars(5, 5), model.Repeat);
        model.EndSlowly();
        Assert.Equal(105, model.Speed);
        Assert.Null(model.Repeat);
        // Changed by the player since: left as the player made it.
        model.PlayBarSlowly(1);
        model.Slower();
        model.EndSlowly();
        Assert.Equal(PracticeSpeed.Slow - PracticeSpeed.Step, model.Speed);
        Assert.Equal(new RepeatBars(1, 1), model.Repeat);
    }

    [Fact]
    public async Task A_song_opens_where_it_was_left_after_the_app_was_closed()
    {
        using (var model = Model())
        {
            await model.OpenAsync("riff", "job-1", Clock(), Take());
            model.SetRepeat(new RepeatBars(3, 4));
            model.Slower();
            model.Leave();
            Assert.Equal(RecordingState.Looking, model.Recording);
            Assert.True(_players.Opened.Single().Player.Released);
            model.ForgetAllButTheDisk();
            await model.LastWrite;
        }
        using var again = Model();
        // The recording kept for the job plays, and the place kept on disk is where the song starts.
        await again.OpenAsync("riff", "job-1", Clock(), null, new HashSet<string> { "job-1" });
        Assert.Equal(RecordingState.Here, again.Recording);
        Assert.Equal((7.0, 95, new RepeatBars(3, 4)), (again.At, again.Speed, again.Repeat));
        Assert.Equal(1, again.Jumps);
        Assert.Equal(7.0, _players.Opened[^1].Player.Position, 9);
        // A song that is no longer in Your songs takes its recording and its place with it.
        using var other = Model();
        await other.OpenAsync("other", "job-2", Clock(), null, new HashSet<string> { "job-2" });
        Assert.Equal(RecordingState.NotHere, other.Recording);
        Assert.Null(new PracticeRecordings(Path.Combine(Dir, "recordings")).Find("job-1"));
        Assert.Null(new PracticePlaces(Path.Combine(Dir, "practice")).Read("job-1"));
    }

    [Fact]
    public async Task A_song_without_its_recording_gets_it_from_the_computer_or_says_why_not()
    {
        using var model = Model();
        await model.OpenAsync("riff", "job-1", Clock(), null);
        Assert.Equal(RecordingState.NotHere, model.Recording);
        await model.FetchAsync(new InputEngine(null));
        Assert.Equal(RecordingState.Gone, model.Recording);
        Assert.Empty(_players.Opened);
        await model.FetchAsync(new InputEngine(null, HttpStatusCode.InternalServerError));
        Assert.Equal(RecordingState.NoAnswer, model.Recording);
        var engine = new InputEngine([1, 2, 3, 4]);
        await model.FetchAsync(engine);
        Assert.Equal(RecordingState.Here, model.Recording);
        Assert.Equal(4L, new FileInfo(_players.Opened.Single().Path).Length);
        // Here already: nothing more is asked for.
        await model.FetchAsync(engine);
        Assert.Equal(1, engine.Asked);
        // Nothing of the tries is left beside the recording.
        Assert.Single(Directory.GetFiles(Path.Combine(Dir, "recordings")));
    }

    [Fact]
    public async Task A_recording_that_cannot_be_played_says_so()
    {
        using var model = Model();
        await model.OpenAsync("riff", "job-1", Clock(), Take());
        ((IRecordingPlayerListener)model).OnFailed();
        Assert.Equal(RecordingState.Unplayable, model.Recording);
        Assert.True(_players.Opened.Single().Player.Released);
    }
}

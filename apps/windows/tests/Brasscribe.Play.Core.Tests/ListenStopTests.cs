using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>A score player driven by the test: positions and state changes happen when the test says so.</summary>
internal sealed class ScriptedPlayer : IScorePlayer
{
    public List<string> Calls { get; } = [];
    public IReadOnlyList<TrackInfo> Tracks { get; } = [new TrackInfo(0, "Solo Cornet", false, 0), new TrackInfo(1, "Horn", false, 0)];
    public int BarCount => 8;
    public bool IsReady { get; set; } = true;
    public PlaybackState State { get; private set; } = PlaybackState.Stopped;
    public PlaybackPosition Position { get; private set; } = new(0, 0, 0, 16);
    public double Speed { get; set; } = 1;
    public bool Metronome { get; set; }
    public bool CountIn { get; set; }
    public int Transpose { get; set; }
    public (int First, int Last)? Loop { get; private set; }
    public event EventHandler<PlaybackPosition>? PositionChanged;
    public event EventHandler<PlaybackState>? StateChanged;
    public event EventHandler? Finished;

    public void LoadScore(byte[] musicXml) { }
    public void LoadSoundFont(byte[] soundFont, bool append = false) { }
    public void Play() { Calls.Add("play"); Set(PlaybackState.Playing); }
    public void Pause() { Calls.Add("pause"); Set(PlaybackState.Paused); }
    public void Stop() { Calls.Add("stop"); Set(PlaybackState.Stopped); }
    public void SeekToBar(int barIndex) { Calls.Add($"seek {barIndex}"); Position = Position with { BarIndex = barIndex }; }
    public void SeekToTick(double tick) { }
    public void SetLoop(int? firstBar, int? lastBar) { Calls.Add($"loop {firstBar}-{lastBar}"); Loop = firstBar is { } f && lastBar is { } l ? (f, l) : null; }
    public void SetMute(int track, bool mute) { }
    public void SetSolo(int track, bool solo) { }
    public void SetVolume(int track, double volume) { }
    public bool IsMuted(int track) => false;
    public bool IsSolo(int track) => false;
    public byte[] ExportMidi() => [];
    public void Dispose() { }

    public void MoveTo(int barIndex)
    {
        Position = Position with { BarIndex = barIndex };
        PositionChanged?.Invoke(this, Position);
    }

    public void End()
    {
        Set(PlaybackState.Stopped);
        Finished?.Invoke(this, EventArgs.Empty);
    }

    private void Set(PlaybackState state)
    {
        if (State == state) return;
        State = state;
        StateChanged?.Invoke(this, state);
    }
}

internal sealed class ScriptedOriginal : IOriginalPlayer
{
    public List<string> Calls { get; } = [];
    public bool HasMedia { get; set; } = true;
    public bool HasVideo => false;
    public void Open(string path, bool hasVideo) { }
    public void PlayRange(TimeSpan start, TimeSpan end, bool loop) { Calls.Add($"range {start.TotalSeconds}-{end.TotalSeconds} loop={loop}"); IsPlaying = true; }
    public void Play() => IsPlaying = true;
    public void Pause() => IsPlaying = false;
    public void Stop() { Calls.Add("stop"); IsPlaying = false; }
    public bool IsPlaying { get; private set; }
    public bool IsMuted { get; set; }
    public double Rate { get; set; } = 1;
    public double Volume { get; set; } = 1;
    public TimeSpan Position { get; set; }
    public event EventHandler? RangeEnded;

    public void ReachEnd()
    {
        IsPlaying = false;
        RangeEnded?.Invoke(this, EventArgs.Empty);
    }
}

public class ListenStopTests
{
    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    private static (ScoreViewModel Score, ReviewViewModel Review, ScriptedPlayer Player, Said Said) Make(IOriginalPlayer? original = null)
    {
        var strings = ConnectionMonitorTests.Strings();
        var said = new Said();
        var player = new ScriptedPlayer();
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, said, strings, new Inline()), said, strings, original);
        score.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), null);
        var doc = score.Document!;
        doc.Parts[0].Bars[1].Events[0].Confidence = 0.3;
        doc.Parts[0].Bars[2].Events[0].Confidence = 0.3;
        score.RefreshUncertain();
        var review = new ReviewViewModel(score, said, strings);
        review.Load();
        said.Items.Clear();
        return (score, review, player, said);
    }

    [Fact]
    public void Listen_becomes_stop_and_stop_stops()
    {
        var (score, review, player, said) = Make();
        int bar = review.Current!.BarNumber;
        Assert.Equal("Listen to this bar", review.ListenLabel);

        var changed = new List<string?>();
        review.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        review.ListenCommand.Execute(null);
        Assert.True(review.IsListening);
        Assert.Equal("Stop", review.ListenLabel);
        Assert.Contains(nameof(ReviewViewModel.ListenLabel), changed);
        Assert.Equal($"Playing bar {bar}", said.Items[^1]);
        Assert.Contains($"seek {bar - 1}", player.Calls);
        Assert.Contains("play", player.Calls);
        Assert.Null(player.Loop); // once, not looped

        review.ListenCommand.Execute(null); // the same button (Space or Enter)
        Assert.False(review.IsListening);
        Assert.Equal("Listen to this bar", review.ListenLabel);
        Assert.Equal(PlaybackState.Paused, player.State);
        Assert.Equal("Stopped", said.Items[^1]);
    }

    [Fact]
    public void It_goes_back_to_listen_when_the_bar_ends()
    {
        var (_, review, player, said) = Make();
        int index = review.Current!.BarIndex;
        review.ListenCommand.Execute(null);

        // A stale position from before the seek does not end it; leaving the bar after being in it does.
        player.MoveTo(index + 3);
        Assert.True(review.IsListening);
        player.MoveTo(index);
        Assert.True(review.IsListening);
        player.MoveTo(index + 1);
        Assert.False(review.IsListening);
        Assert.Equal(PlaybackState.Paused, player.State);
        Assert.Equal($"End of bar {review.Current.BarNumber}", said.Items[^1]);
    }

    [Fact]
    public void The_end_of_the_score_ends_it_too()
    {
        var (_, review, player, _) = Make();
        review.ListenCommand.Execute(null);
        player.End();
        Assert.False(review.IsListening);
    }

    [Fact]
    public void The_practice_loop_is_left_as_it_was()
    {
        var (score, review, player, _) = Make();
        score.Player.LoopStart = 2;
        score.Player.LoopEnd = 3;
        score.Player.SetLoopCommand.Execute(null);
        review.ListenCommand.Execute(null);
        Assert.Null(player.Loop);
        review.ListenCommand.Execute(null);
        Assert.Equal((1, 2), player.Loop);
        Assert.True(score.Player.IsLooping);
        Assert.Equal(2, score.Player.LoopStart);
    }

    [Fact]
    public void Another_note_or_leaving_the_screen_stops_it_quietly()
    {
        var (score, review, player, said) = Make();
        review.ListenCommand.Execute(null);
        said.Items.Clear();
        review.SkipCommand.Execute(null);
        Assert.False(score.IsListeningToBar);
        Assert.Equal(PlaybackState.Paused, player.State);
        Assert.DoesNotContain("Stopped", said.Items);

        review.ListenCommand.Execute(null);
        score.StopListening(announce: false); // what MainViewModel does on a screen change
        Assert.False(review.IsListening);
    }

    [Fact]
    public void Moving_the_score_cursor_to_another_bar_stops_it()
    {
        var (score, _, _, _) = Make();
        score.GoToBar(2);
        score.ListenToBarCommand.Execute(null);
        Assert.True(score.IsListeningToBar);
        score.GoToBar(4);
        Assert.False(score.IsListeningToBar);
    }

    [Fact]
    public void From_the_recording_it_plays_the_range_once_and_ends_with_it()
    {
        var original = new ScriptedOriginal();
        var (score, review, _, said) = Make(original);
        foreach (var part in score.Document!.Parts)
            for (int b = 0; b < part.Bars.Count; b++)
                if (part.Bars[b].Events.FirstOrDefault() is { } first) first.TimeS = b * 2.0;

        review.ListenCommand.Execute(null);
        Assert.True(review.IsListening);
        Assert.Contains("loop=False", original.Calls[^1]);
        Assert.Contains("from the recording", said.Items[^1]);
        original.ReachEnd();
        Assert.False(review.IsListening);

        review.ListenCommand.Execute(null);
        review.ListenCommand.Execute(null);
        Assert.Equal("stop", original.Calls[^1]);
        Assert.False(original.IsPlaying);
    }

    /// <summary>
    /// "Change note…" → Save stays on the note and Listen plays the score, so the new note is heard
    /// (the recording has the old one); Undo goes back to the recording; Keep moves on.
    /// </summary>
    [Fact]
    public void A_changed_note_stays_and_listens_from_the_score()
    {
        var original = new ScriptedOriginal();
        var strings = ConnectionMonitorTests.Strings();
        var said = new Said();
        var player = new ScriptedPlayer();
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, said, strings, new Inline()), said, strings, original);
        // The uncertain note comes from the Composition, so it is still uncertain after the score is reloaded.
        score.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), Scores.CompositionJson.Parse("""
            {"title":"Tune","ticks_per_beat":480,"meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0}],
             "voices":[{"id":"melody","role":"melody","notes":[{"pitch":68,"start":480,"dur":240,"confidence":0.3,"onset_s":0.44}]}]}
            """));
        var review = new ReviewViewModel(score, said, strings);
        review.Load();
        void Timed()
        {
            foreach (var part in score.Document!.Parts)
                for (int b = 0; b < part.Bars.Count; b++)
                    if (part.Bars[b].Events.FirstOrDefault() is { } first) first.TimeS = b * 2.0;
        }
        var item = review.Current!;
        (int Part, int Bar, int Event) at = (item.Part, item.BarIndex, item.EventIndex);
        string was = review.ChangedText;
        Assert.Equal("", was);

        Assert.True(review.ChangeNote(2));
        Assert.Equal(at, (review.Current!.Part, review.Current.BarIndex, review.Current.EventIndex));
        Assert.False(review.Current.IsKept);
        Assert.True(review.IsChanged);
        Assert.Matches(@"^Changed to \S+\d \(was \S+\d\)$", review.ChangedText);
        Assert.Equal(review.ChangedText, said.Items[^1]);
        Timed();
        player.Calls.Clear();
        original.Calls.Clear();
        review.ListenCommand.Execute(null);
        Assert.Contains("play", player.Calls);
        Assert.Empty(original.Calls);
        review.ListenCommand.Execute(null);

        // Change again: "was" stays what Brasscribe wrote.
        string first = review.ChangedText;
        Assert.True(review.ChangeNote(1));
        Assert.Equal(first[first.IndexOf("(was ")..], review.ChangedText[review.ChangedText.IndexOf("(was ")..]);

        // Undo: the recording again, still this note.
        review.UndoChangeCommand.Execute(null);
        Assert.False(review.IsChanged);
        Assert.StartsWith("Back to ", said.Items[^1]);
        Assert.Equal(at, (review.Current!.Part, review.Current.BarIndex, review.Current.EventIndex));
        Timed();
        original.Calls.Clear();
        review.ListenCommand.Execute(null);
        Assert.Contains("loop=False", Assert.Single(original.Calls));
        review.ListenCommand.Execute(null);

        // Keep checks it and moves on: this score has one note to check, so the review is done.
        Assert.True(review.ChangeNote(1));
        review.KeepCommand.Execute(null);
        Assert.Null(review.Current);
        Assert.Equal(0, review.Left);
    }

    [Fact]
    public void Not_ready_says_so_and_does_not_show_stop()
    {
        var (_, review, player, said) = Make();
        player.IsReady = false;
        review.ListenCommand.Execute(null);
        Assert.False(review.IsListening);
        Assert.Contains(said.Items, t => t.Length > 0);
    }
}

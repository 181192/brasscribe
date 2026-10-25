using System.Xml.Linq;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Original-versus-score switching and the video following the score.</summary>
[Collection(AlphaTabCollection.Name)]
public class SourceSyncTests
{
    /// <summary>A recording clock: plays in real time only when told to (tests move it by hand).</summary>
    private sealed class FakeOriginal : IOriginalPlayer
    {
        public bool HasMedia { get; private set; }
        public bool HasVideo { get; private set; }
        public bool IsPlaying { get; private set; }
        public bool IsMuted { get; set; }
        public double Rate { get; set; } = 1;
        public TimeSpan Position { get; set; }
        public int Seeks { get; private set; }
        public void Open(string path, bool hasVideo) { HasMedia = true; HasVideo = hasVideo; }
        public void PlayRange(TimeSpan start, TimeSpan end, bool loop) { Position = start; IsPlaying = true; }
        public void Play() => IsPlaying = true;
        public void Pause() => IsPlaying = false;
        public void Stop() { IsPlaying = false; Position = TimeSpan.Zero; }
    }

    // Beats every 0.5 s from 2.0 s: bar 1 starts 2.0 s into the recording (a 120 bpm take with a lead-in).
    private static Composition Take() => CompositionJson.Parse(
        """{"title":"t","voices":[],"meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0}],"first_downbeat":4,""" +
        "\"beat_times\":[" + string.Join(",", Enumerable.Range(0, 40).Select(i => (i * 0.5).ToString(System.Globalization.CultureInfo.InvariantCulture))) + "]}");

    [Fact]
    public void Score_ticks_map_to_recording_seconds_and_back()
    {
        var map = new ScoreTimeMap(Take());
        Assert.Equal(2.0, map.SecondsAtTick(0), 6);        // bar 1, beat 1
        Assert.Equal(4.0, map.SecondsAtTick(3840), 6);     // bar 2 (4 quarters later)
        Assert.Equal(1920, map.TickAtSeconds(3.0), 6);     // beat 3 of bar 1
        Assert.Equal(0, map.TickAtSeconds(0.5), 6);        // the lead-in clamps to the start
    }

    [Fact]
    public void Video_follows_the_score_muted_at_its_speed_and_seeks_only_on_drift()
    {
        var video = new FakeOriginal();
        video.Open("take.mp4", hasVideo: true);
        var follow = new VideoFollower(video, new ScoreTimeMap(Take()));

        Assert.True(follow.Follow(PlaybackState.Playing, 3840, 0.75));
        Assert.Equal(TimeSpan.FromSeconds(4), video.Position);
        Assert.True(video.IsPlaying && video.IsMuted);
        Assert.Equal(0.75, video.Rate);

        video.Position = TimeSpan.FromSeconds(4.1);                       // small drift: left alone
        Assert.False(follow.Follow(PlaybackState.Playing, 3840, 0.75));
        video.Position = TimeSpan.FromSeconds(6);                         // big drift: corrected
        Assert.True(follow.Follow(PlaybackState.Playing, 3840, 0.75));
        Assert.False(follow.Follow(PlaybackState.Paused, 3840, 0.75));
        Assert.False(video.IsPlaying);
    }

    [Fact]
    public void Switching_keeps_the_position_in_both_directions()
    {
        var strings = new ReswStrings(ReswStrings.Parse(XDocument.Load(
            Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));
        var said = new List<string>();
        var announcer = new ListAnnouncer(said);
        var original = new FakeOriginal();
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var vm = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, announcer, strings, new Inline()), announcer, strings, original);
        vm.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), Take());

        vm.SwitchSource();
        Assert.Contains("no recording to hear", said.Last()); // nothing opened yet
        original.Open("take.wav", hasVideo: false);

        player.SeekToTick(3840); // bar 2
        vm.SwitchSource();
        Assert.Equal(ListeningSource.Original, vm.ListeningTo);
        Assert.Equal(4.0, original.Position.TotalSeconds, 2);
        Assert.False(original.IsMuted);

        original.Position = TimeSpan.FromSeconds(6); // bar 3 in the recording
        Assert.True(vm.Execute(ScoreCommand.SwitchSource));
        Assert.Equal(ListeningSource.Score, vm.ListeningTo);
        Assert.Equal("Playing the band", said.Last());
    }

    private sealed class Inline : IUiDispatcher
    {
        public void Post(Action action) => action();
    }

    private sealed class ListAnnouncer(List<string> said) : IAnnouncer
    {
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => said.Add(text);
    }
}

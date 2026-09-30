using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Playback;

namespace Brasscribe.Play.Core.Tests;

/// <summary>The audio device opens only while the band plays; loopback recordings keep their silences.</summary>
public class AudioDeviceTests
{
    [Fact]
    public void Play_asks_for_the_device_and_a_played_out_pause_lets_it_go_once()
    {
        var output = new BufferedSynthOutput();
        output.Open(100);
        int plays = 0, drained = 0;
        output.PlayRequested += (_, _) => plays++;
        output.Drained += (_, _) => drained++;

        output.Play();
        Assert.Equal(1, plays);
        var buffer = new float[1024];
        output.Read(buffer);
        Assert.Equal(0, drained);

        output.Pause();
        for (int i = 0; i < 20; i++) output.Read(buffer); // the 80 ms fade, then silence
        Assert.Equal(1, drained);

        output.Play();
        output.Pause();
        output.Read(buffer);
        output.Read(buffer);
        Assert.Equal(2, plays);
        Assert.Equal(2, drained);
    }

    [Fact]
    public void Loopback_gaps_are_filled_up_to_just_short_of_the_clock()
    {
        const int rate = 48000;
        // Normal delivery a few packets behind: nothing to fill.
        Assert.Equal(0, LoopbackGap.FramesToFill(TimeSpan.FromSeconds(1), rate - rate / 20, rate));
        // Nothing arrived for 3 s after the first second: fill to 50 ms short of the clock.
        Assert.Equal(3 * rate - rate / 20, LoopbackGap.FramesToFill(TimeSpan.FromSeconds(4), rate, rate));
    }

    [Fact]
    public void Silence_ticks_from_the_gap_filler_say_nothing_is_playing()
    {
        var watch = new SilenceWatch(TimeSpan.FromSeconds(4));
        CaptureNotice? notice = null;
        for (int i = 1; i <= 50 && notice is null; i++) notice = watch.Feed(new CaptureLevel(TimeSpan.FromMilliseconds(100 * i), 0, true));
        Assert.Equal(CaptureNoticeKind.NothingPlaying, notice!.Kind);
    }
}

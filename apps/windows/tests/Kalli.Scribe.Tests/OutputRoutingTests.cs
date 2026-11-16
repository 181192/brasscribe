using Kalli.Scribe.Playback;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Where the band's sound goes when Windows' devices change (<see cref="OutputRouting"/>, which the Windows output
/// asks): it follows the default output for media, comes back after its device went away, and a stream that could
/// not open is tried again when a device appears.
/// </summary>
public class OutputRoutingTests
{
    private static OutputRouting OpenOn(string deviceId)
    {
        var routing = new OutputRouting();
        routing.Opening();
        routing.Opened(deviceId);
        return routing;
    }

    [Fact]
    public void Headphones_plugged_in_while_the_band_plays_move_the_sound_to_them()
    {
        var routing = OpenOn("speakers");
        Assert.Equal(OutputAction.Reopen, routing.DefaultChanged(mediaOutput: true, "headphones", playing: true));
        // The output closes and opens again on the new default; then the device that arrived asks for nothing more.
        routing.Closed();
        routing.Opening();
        routing.Opened("headphones");
        Assert.Equal(OutputAction.None, routing.DeviceArrived(playing: true));
    }

    [Fact]
    public void A_new_default_while_paused_closes_the_stream_and_the_next_play_opens_it_there()
    {
        var routing = OpenOn("speakers");
        Assert.Equal(OutputAction.Close, routing.DefaultChanged(mediaOutput: true, "headphones", playing: false));
        routing.Closed();
        Assert.Equal(OutputAction.None, routing.DeviceArrived(playing: false));
    }

    [Fact]
    public void The_same_default_again_or_another_kind_of_default_changes_nothing()
    {
        var routing = OpenOn("speakers");
        Assert.Equal(OutputAction.None, routing.DefaultChanged(mediaOutput: true, "speakers", playing: true));
        // The microphone's default, or the default for calls, is not where the band plays.
        Assert.Equal(OutputAction.None, routing.DefaultChanged(mediaOutput: false, "headset", playing: true));
    }

    [Fact]
    public void A_default_change_with_no_stream_open_opens_nothing_by_itself()
    {
        var routing = new OutputRouting();
        Assert.Equal(OutputAction.None, routing.DefaultChanged(mediaOutput: true, "headphones", playing: true));
    }

    [Fact]
    public void A_device_unplugged_while_the_band_plays_moves_the_sound_to_the_next_default()
    {
        var routing = OpenOn("usb-speakers");
        Assert.Equal(OutputAction.Reopen, routing.StreamEnded(playing: true));
        routing.Closed();
        routing.Opening();
        routing.Opened("speakers");
        Assert.True(routing.IsOpen);
    }

    [Fact]
    public void A_device_unplugged_while_paused_closes_the_stream()
    {
        var routing = OpenOn("usb-speakers");
        Assert.Equal(OutputAction.Close, routing.StreamEnded(playing: false));
    }

    [Fact]
    public void With_no_device_at_all_the_stream_opens_when_one_appears_while_the_band_plays()
    {
        var routing = new OutputRouting();
        routing.Opening(); // and it threw: no output device
        Assert.Equal(OutputAction.Open, routing.DeviceArrived(playing: true));
        Assert.Equal(OutputAction.None, routing.DeviceArrived(playing: false));
    }

    [Fact]
    public void An_unplugged_device_that_could_not_be_replaced_opens_when_one_appears()
    {
        var routing = OpenOn("usb-speakers");
        routing.StreamEnded(playing: true);
        routing.Closed();
        routing.Opening(); // no other output to open on
        Assert.False(routing.IsOpen);
        Assert.Equal(OutputAction.Open, routing.DeviceArrived(playing: true));
    }

    [Fact]
    public void A_device_appearing_does_nothing_to_a_stream_that_plays()
    {
        var routing = OpenOn("speakers");
        Assert.Equal(OutputAction.None, routing.DeviceArrived(playing: true));
    }
}

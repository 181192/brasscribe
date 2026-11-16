namespace Kalli.Scribe.Playback;

/// <summary>What the output does with its stream when Windows' devices change.</summary>
public enum OutputAction
{
    /// <summary>Nothing changes.</summary>
    None,
    /// <summary>Open a stream on the default output.</summary>
    Open,
    /// <summary>Close the stream.</summary>
    Close,
    /// <summary>Close the stream and open one on the (new) default output.</summary>
    Reopen,
}

/// <summary>
/// Where the band's sound goes when Windows' devices change, apart from the device code (the Windows output asks this,
/// then does it): a stream follows Windows' default output for media, a stream that ended by itself is opened again
/// while the band plays, and one that could not open (no device at all) is tried again when a device appears. A
/// closed stream with the band paused stays closed: the next Play opens it on whatever the default is then.
/// </summary>
public sealed class OutputRouting
{
    private string? _deviceId;
    private bool _failed;

    /// <summary>Whether a stream is open.</summary>
    public bool IsOpen { get; private set; }

    /// <summary>An open is being tried: until it plays, it counts as failed (no device, or one that refused).</summary>
    public void Opening() => _failed = true;

    /// <summary>The stream plays, on <paramref name="deviceId"/>.</summary>
    public void Opened(string deviceId)
    {
        IsOpen = true;
        _deviceId = deviceId;
        _failed = false;
    }

    /// <summary>The stream was closed.</summary>
    public void Closed()
    {
        IsOpen = false;
        _deviceId = null;
    }

    /// <summary>Windows' default device changed. Only the default output for media moves the stream.</summary>
    public OutputAction DefaultChanged(bool mediaOutput, string? deviceId, bool playing)
    {
        if (!mediaOutput || !IsOpen || deviceId == _deviceId) return OutputAction.None;
        return playing ? OutputAction.Reopen : OutputAction.Close;
    }

    /// <summary>A device appeared, or became usable: a stream that could not open tries again while the band plays.</summary>
    public OutputAction DeviceArrived(bool playing) =>
        _failed && !IsOpen && playing ? OutputAction.Open : OutputAction.None;

    /// <summary>The open stream ended by itself (the device unplugged, disabled or taken for exclusive use).</summary>
    public OutputAction StreamEnded(bool playing)
    {
        _failed = true;
        return playing ? OutputAction.Reopen : OutputAction.Close;
    }
}

namespace Brasscribe.Play.Core.Capture;

/// <summary>
/// Waits for a capture device to report that it stopped, without holding the calling thread. NAudio
/// raises RecordingStopped through the synchronization context that started the recording (the UI
/// thread), so a blocking wait there can only end by timing out.
/// </summary>
public static class StopWait
{
    /// <summary>How long a stop may take before the recording is closed anyway.</summary>
    public static readonly TimeSpan Limit = TimeSpan.FromSeconds(2);

    /// <summary>
    /// True when <paramref name="stopped"/> completed within <paramref name="timeout"/>, false when the
    /// time ran out (the caller carries on and closes the file). Cancellation throws.
    /// </summary>
    public static async Task<bool> WithinAsync(Task stopped, TimeSpan timeout, CancellationToken ct = default, TimeProvider? time = null)
    {
        try
        {
            await stopped.WaitAsync(timeout, time ?? TimeProvider.System, ct).ConfigureAwait(false);
            return true;
        }
        catch (TimeoutException)
        {
            return false;
        }
    }
}

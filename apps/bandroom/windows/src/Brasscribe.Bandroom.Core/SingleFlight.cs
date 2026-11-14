namespace Brasscribe.Bandroom.Core;

/// <summary>
/// One run at a time: asking again while one runs joins it instead of starting another. Setup and updates go through
/// one of these, so a second click on Finish setting up can't run two <c>pixi install</c>s or undo a swap in progress.
/// </summary>
public sealed class SingleFlight
{
    private readonly Lock _gate = new();
    private Task? _running;
    private string? _kind;

    public bool IsRunning
    {
        get { lock (_gate) return _running is { IsCompleted: false }; }
    }

    /// <summary>
    /// Starts <paramref name="work"/>, or returns the run already going. <paramref name="kind"/> names a run that is
    /// not everybody's to join (<see cref="RunAfterAsync"/>).
    /// </summary>
    public Task RunAsync(Func<Task> work, string? kind = null)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_gate)
        {
            if (_running is { IsCompleted: false } running) return running;
            _running = done.Task;
            _kind = kind;
        }
        return RunCoreAsync(work, done);
    }

    /// <summary>
    /// As <see cref="RunAsync"/>, but a run of <paramref name="kind"/> that is going is not joined: it does something
    /// else than what is asked for here, so <paramref name="work"/> starts once it has ended, however it ended. (The
    /// reader of printed music's install goes through the gate setup uses; Finish setting up pressed meanwhile must
    /// still finish setting up.)
    /// </summary>
    public async Task RunAfterAsync(string kind, Func<Task> work)
    {
        while (true)
        {
            Task? other;
            lock (_gate) other = _running is { IsCompleted: false } running && _kind == kind ? running : null;
            if (other is null) break;
            try { await other.ConfigureAwait(false); }
            catch (Exception) { } // its own caller hears of it
        }
        await RunAsync(work).ConfigureAwait(false);
    }

    private static async Task RunCoreAsync(Func<Task> work, TaskCompletionSource done)
    {
        try
        {
            await work();
            done.SetResult();
        }
        catch (OperationCanceledException e)
        {
            done.SetCanceled(e.CancellationToken);
            throw;
        }
        catch (Exception e)
        {
            done.SetException(e);
            throw;
        }
    }
}

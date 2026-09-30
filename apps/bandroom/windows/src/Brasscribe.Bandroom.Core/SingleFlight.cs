namespace Brasscribe.Bandroom.Core;

/// <summary>
/// One run at a time: asking again while one runs joins it instead of starting another. Setup and updates go through
/// one of these, so a second click on Finish setting up can't run two <c>pixi install</c>s or undo a swap in progress.
/// </summary>
public sealed class SingleFlight
{
    private readonly Lock _gate = new();
    private Task? _running;

    public bool IsRunning
    {
        get { lock (_gate) return _running is { IsCompleted: false }; }
    }

    /// <summary>Starts <paramref name="work"/>, or returns the run already going.</summary>
    public Task RunAsync(Func<Task> work)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_gate)
        {
            if (_running is { IsCompleted: false } running) return running;
            _running = done.Task;
        }
        return RunCoreAsync(work, done);
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

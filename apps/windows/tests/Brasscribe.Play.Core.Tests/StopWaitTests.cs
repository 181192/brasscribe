using System.Collections.Concurrent;
using System.Diagnostics;
using Brasscribe.Play.Core.Capture;
using Microsoft.Extensions.Time.Testing;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Stopping a recording: WASAPI capture reports RecordingStopped through the context that started it
/// (the UI thread). The wait for it must leave that thread free, or it always runs to the time limit.
/// </summary>
public sealed class StopWaitTests
{
    [Fact]
    public async Task A_device_that_stops_in_time_is_waited_for()
    {
        var stopped = new TaskCompletionSource();
        var time = new FakeTimeProvider();
        var wait = StopWait.WithinAsync(stopped.Task, StopWait.Limit, time: time);
        Assert.False(wait.IsCompleted);
        time.Advance(TimeSpan.FromSeconds(1));
        stopped.SetResult();
        Assert.True(await wait);
    }

    [Fact]
    public async Task A_device_that_never_stops_is_given_up_on_at_the_limit()
    {
        var time = new FakeTimeProvider();
        var wait = StopWait.WithinAsync(new TaskCompletionSource().Task, StopWait.Limit, time: time);
        time.Advance(StopWait.Limit - TimeSpan.FromMilliseconds(1));
        Assert.False(wait.IsCompleted);
        time.Advance(TimeSpan.FromMilliseconds(1));
        Assert.False(await wait);
    }

    [Fact]
    public async Task Cancelling_the_stop_throws()
    {
        using var cts = new CancellationTokenSource();
        var wait = StopWait.WithinAsync(new TaskCompletionSource().Task, StopWait.Limit, cts.Token, new FakeTimeProvider());
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => wait);
    }

    /// <summary>
    /// A pretend UI thread; the device posts its "stopped" to it, as NAudio does. Awaiting frees the
    /// thread and the stop ends at once; the old blocking wait on the same thread ran to its limit.
    /// </summary>
    [Fact]
    public void On_the_ui_thread_the_stop_ends_when_the_device_says_so_not_at_the_limit()
    {
        // Long enough that a slow first run on a CI runner (JIT, a busy machine) stays far below half of it.
        var limit = TimeSpan.FromSeconds(2);
        using var ui = new SingleThreadContext();

        var (awaited, awaitedMs) = ui.Run(async () =>
        {
            var stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var context = SynchronizationContext.Current!;
            var clock = Stopwatch.StartNew();
            context.Post(_ => stopped.TrySetResult(), null); // StopRecording → RecordingStopped via the UI context
            bool ok = await StopWait.WithinAsync(stopped.Task, limit);
            return (ok, clock.ElapsedMilliseconds);
        });
        Assert.True(awaited);
        Assert.True(awaitedMs < limit.TotalMilliseconds / 2, $"awaited stop took {awaitedMs} ms");

        var (blocked, blockedMs) = ui.Run(() =>
        {
            var stopped = new TaskCompletionSource();
            var clock = Stopwatch.StartNew();
            SynchronizationContext.Current!.Post(_ => stopped.TrySetResult(), null);
            bool ok = stopped.Task.Wait(limit); // what StopAsync did before
            return Task.FromResult((ok, clock.ElapsedMilliseconds));
        });
        Assert.False(blocked);
        Assert.True(blockedMs >= limit.TotalMilliseconds - 50, $"blocking stop took {blockedMs} ms");
    }

    /// <summary>One thread that runs posted work in order, like a dispatcher.</summary>
    private sealed class SingleThreadContext : SynchronizationContext, IDisposable
    {
        private readonly BlockingCollection<(SendOrPostCallback, object?)> _queue = [];
        private readonly Thread _thread;

        public SingleThreadContext()
        {
            _thread = new Thread(() =>
            {
                SetSynchronizationContext(this);
                foreach (var (callback, state) in _queue.GetConsumingEnumerable()) callback(state);
            }) { IsBackground = true };
            _thread.Start();
        }

        public override void Post(SendOrPostCallback d, object? state) => _queue.Add((d, state));

        public T Run<T>(Func<Task<T>> work)
        {
            var result = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            Post(async _ =>
            {
                try { result.SetResult(await work()); }
                catch (Exception e) { result.SetException(e); }
            }, null);
            return result.Task.WaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
        }

        public void Dispose()
        {
            _queue.CompleteAdding();
            _thread.Join(TimeSpan.FromSeconds(5));
            _queue.Dispose();
        }
    }
}

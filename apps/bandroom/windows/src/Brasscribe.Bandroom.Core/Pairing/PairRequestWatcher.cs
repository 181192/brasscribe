using System.Net;
using Brasscribe.Bandroom.Core.Engine;

namespace Brasscribe.Bandroom.Core.Pairing;

/// <summary>How an Allow or Don't allow went.</summary>
public enum PairDecision
{
    /// <summary>The engine took the answer.</summary>
    Done,
    /// <summary>The request had lapsed, or was answered elsewhere.</summary>
    Lapsed,
    /// <summary>The answer didn't get through; the request is still waiting.</summary>
    Failed,
}

/// <summary>
/// Phones that chose this computer and wait to be allowed (§3.4 way 1). Polled every few seconds
/// whether or not the Pair window is open: a request lapses after two minutes and someone is waiting.
/// </summary>
public sealed class PairRequestWatcher
{
    public static readonly TimeSpan Lifetime = TimeSpan.FromMinutes(2);
    private readonly Dictionary<string, PairRequestInfo> _pending = [];
    private readonly TimeProvider _time;

    public PairRequestWatcher(TimeProvider? time = null) => _time = time ?? TimeProvider.System;

    /// <summary>A new request to allow.</summary>
    public event Action<PairRequestInfo>? Arrived;
    /// <summary>A request that lapsed or was answered elsewhere (the id).</summary>
    public event Action<string>? Gone;

    public IReadOnlyCollection<PairRequestInfo> Pending { get { lock (_pending) return [.. _pending.Values]; } }

    public async Task PollAsync(IEngineApi api, CancellationToken ct = default)
    {
        IReadOnlyList<PairRequestInfo> list;
        try { list = await api.GetPairRequestsAsync(ct).ConfigureAwait(false); }
        catch (EngineHttpException e) when (e.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Forbidden) { return; }
        Update(list);
    }

    /// <summary>Raises Gone and Arrived once per request, however many polls and decisions overlap.</summary>
    public void Update(IReadOnlyList<PairRequestInfo> list)
    {
        var now = _time.GetUtcNow();
        var live = list.Where(r => r.Status == "pending" && !IsExpired(r, now)).ToDictionary(r => r.RequestId);
        List<string> gone;
        List<PairRequestInfo> arrived;
        lock (_pending)
        {
            gone = _pending.Keys.Where(id => !live.ContainsKey(id)).ToList();
            foreach (var id in gone) _pending.Remove(id);
            arrived = live.Values.Where(r => _pending.TryAdd(r.RequestId, r)).ToList();
        }
        foreach (var id in gone) Gone?.Invoke(id);
        foreach (var r in arrived) Arrived?.Invoke(r);
    }

    public bool IsExpired(PairRequestInfo r, DateTimeOffset now) => r.CreatedAtTime is { } t && now - t >= Lifetime;

    /// <summary>
    /// Allow or don't allow. <see cref="PairDecision.Lapsed"/> when the request had already lapsed (404, or no longer
    /// pending); <see cref="PairDecision.Failed"/> when the answer didn't get through (no answer in time, an error
    /// answer): the request stays, so the person can try again.
    /// </summary>
    public async Task<PairDecision> DecideAsync(IEngineApi api, string requestId, bool approve, CancellationToken ct = default)
    {
        try
        {
            var r = await api.DecidePairRequestAsync(requestId, approve, ct).ConfigureAwait(false);
            Forget(requestId);
            return r.Status == (approve ? "approved" : "denied") ? PairDecision.Done : PairDecision.Lapsed;
        }
        catch (EngineHttpException e) when (e.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Gone or HttpStatusCode.Conflict)
        {
            Forget(requestId);
            return PairDecision.Lapsed;
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or EngineHttpException or System.Text.Json.JsonException)
        {
            return PairDecision.Failed;
        }
    }

    private void Forget(string requestId)
    {
        lock (_pending) _pending.Remove(requestId);
    }
}

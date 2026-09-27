using System.Net;
using Brasscribe.Bandroom.Core.Engine;

namespace Brasscribe.Bandroom.Core.Pairing;

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

    public IReadOnlyCollection<PairRequestInfo> Pending => _pending.Values;

    public async Task PollAsync(IEngineApi api, CancellationToken ct = default)
    {
        IReadOnlyList<PairRequestInfo> list;
        try { list = await api.GetPairRequestsAsync(ct).ConfigureAwait(false); }
        catch (EngineHttpException e) when (e.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Forbidden) { return; }
        Update(list);
    }

    public void Update(IReadOnlyList<PairRequestInfo> list)
    {
        var now = _time.GetUtcNow();
        var live = list.Where(r => r.Status == "pending" && !IsExpired(r, now)).ToDictionary(r => r.RequestId);
        foreach (var id in _pending.Keys.Where(id => !live.ContainsKey(id)).ToList())
        {
            _pending.Remove(id);
            Gone?.Invoke(id);
        }
        foreach (var (id, r) in live)
        {
            if (_pending.TryAdd(id, r)) Arrived?.Invoke(r);
        }
    }

    public bool IsExpired(PairRequestInfo r, DateTimeOffset now) => r.CreatedAtTime is { } t && now - t >= Lifetime;

    /// <summary>Allow or don't allow. Returns false when the request had already lapsed (404 or no longer pending).</summary>
    public async Task<bool> DecideAsync(IEngineApi api, string requestId, bool approve, CancellationToken ct = default)
    {
        try
        {
            var r = await api.DecidePairRequestAsync(requestId, approve, ct).ConfigureAwait(false);
            _pending.Remove(requestId);
            return r.Status == (approve ? "approved" : "denied");
        }
        catch (EngineHttpException e) when (e.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Gone or HttpStatusCode.Conflict)
        {
            _pending.Remove(requestId);
            return false;
        }
    }
}

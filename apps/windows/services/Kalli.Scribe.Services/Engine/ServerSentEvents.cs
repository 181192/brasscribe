using System.Text;

namespace Brasscribe.Play.Core.Engine;

/// <summary>One parsed Server-Sent Event.</summary>
public sealed record ServerSentEvent(string? Id, string EventType, string Data);

/// <summary>
/// Incremental text/event-stream parser (WHATWG HTML §9.2): data lines are joined with '\n',
/// comment lines (":") are ignored, a blank line dispatches, and the last id is remembered for resume.
/// </summary>
public sealed class ServerSentEventParser
{
    private readonly StringBuilder _data = new();
    private string _eventType = "";
    private bool _hasData;

    public string? LastEventId { get; private set; }

    /// <summary>Feeds one line (without its terminator); returns an event when the line ends one.</summary>
    public ServerSentEvent? Feed(string line)
    {
        if (line.Length == 0)
        {
            if (!_hasData)
            {
                _eventType = "";
                return null;
            }
            var ev = new ServerSentEvent(LastEventId, _eventType.Length == 0 ? "message" : _eventType, _data.ToString());
            _data.Clear();
            _hasData = false;
            _eventType = "";
            return ev;
        }
        if (line[0] == ':') return null;

        int colon = line.IndexOf(':');
        string field = colon < 0 ? line : line[..colon];
        string value = colon < 0 ? "" : line[(colon + 1)..];
        if (value.StartsWith(' ')) value = value[1..];

        switch (field)
        {
            case "data":
                if (_hasData) _data.Append('\n');
                _data.Append(value);
                _hasData = true;
                break;
            case "event":
                _eventType = value;
                break;
            case "id":
                if (!value.Contains('\0')) LastEventId = value;
                break;
        }
        return null;
    }

    /// <summary>
    /// The events on a stream. With <paramref name="idleTimeout"/>, a stream that sends no line at all
    /// (comments such as keepalives count) for that long ends with a <see cref="TimeoutException"/>.
    /// </summary>
    public static async IAsyncEnumerable<ServerSentEvent> ReadAsync(
        Stream stream,
        ServerSentEventParser? parser = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default,
        TimeSpan? idleTimeout = null)
    {
        parser ??= new ServerSentEventParser();
        using var reader = new StreamReader(stream, Encoding.UTF8);
        using var idle = CancellationTokenSource.CreateLinkedTokenSource(ct);
        while (true)
        {
            if (idleTimeout is { } t) idle.CancelAfter(t);
            string? line;
            try
            {
                line = await reader.ReadLineAsync(idle.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException e) when (!ct.IsCancellationRequested)
            {
                throw new TimeoutException("The event stream sent nothing in time.", e);
            }
            if (line is null) yield break;
            var ev = parser.Feed(line);
            if (ev is not null) yield return ev;
        }
    }
}

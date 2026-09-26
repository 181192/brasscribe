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

    public static async IAsyncEnumerable<ServerSentEvent> ReadAsync(
        Stream stream,
        ServerSentEventParser? parser = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        parser ??= new ServerSentEventParser();
        using var reader = new StreamReader(stream, Encoding.UTF8);
        while (true)
        {
            string? line = await reader.ReadLineAsync(ct).ConfigureAwait(false);
            if (line is null) yield break;
            var ev = parser.Feed(line);
            if (ev is not null) yield return ev;
        }
    }
}

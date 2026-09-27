namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// The engine's output and Bandroom's own supervision notes, in logs\engine.log under the data folder.
/// The file rolls to engine.1.log past <see cref="MaxBytes"/>; the last lines are kept in memory for
/// "Copy diagnostics".
/// </summary>
public sealed class EngineLog
{
    private readonly object _lock = new();
    private readonly Queue<string> _tail = new();
    private readonly TimeProvider _time;
    private readonly int _tailLines;

    public EngineLog(string? directory, TimeProvider? time = null, long maxBytes = 5 * 1024 * 1024, int tailLines = 200)
    {
        _time = time ?? TimeProvider.System;
        _tailLines = tailLines;
        MaxBytes = maxBytes;
        if (directory is not null)
        {
            Directory.CreateDirectory(directory);
            FilePath = Path.Combine(directory, "engine.log");
        }
    }

    public string? FilePath { get; }
    public long MaxBytes { get; }

    public void Write(string line)
    {
        string stamped = $"{_time.GetLocalNow():yyyy-MM-dd HH:mm:ss} {line}";
        lock (_lock)
        {
            _tail.Enqueue(stamped);
            while (_tail.Count > _tailLines) _tail.Dequeue();
            if (FilePath is null) return;
            try
            {
                var info = new FileInfo(FilePath);
                if (info.Exists && info.Length > MaxBytes)
                    File.Move(FilePath, Path.Combine(info.DirectoryName!, "engine.1.log"), overwrite: true);
                File.AppendAllText(FilePath, stamped + Environment.NewLine);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }

    public IReadOnlyList<string> Tail(int lines = 40)
    {
        lock (_lock) return _tail.Skip(Math.Max(0, _tail.Count - lines)).ToList();
    }
}

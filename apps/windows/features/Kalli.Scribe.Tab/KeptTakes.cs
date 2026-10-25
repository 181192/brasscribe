using System.Text.Json;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tab;

/// <summary>A recording kept in Your songs before it has a tab: it opens What is this? again with the recording.</summary>
public sealed record KeptTake(string Id, string Title, string WavPath, TimeSpan Duration, DateTimeOffset Kept)
{
    /// <summary>The recording as the flow takes it.</summary>
    public SourceAudio Source => new(WavPath, Title, Duration, null, false);
}

/// <summary>
/// The recordings kept in Your songs: a take whose tab was not made (it failed, or was stopped), so it can be written down
/// again without recording it again. One folder each under the app's own folder, holding the recording and
/// <c>take.json</c>. A take kept longer than <see cref="KeepFor"/> is deleted when the app starts, unless it is the one in
/// hand. The recording is copied in, so the take the app is working with stays where it was.
/// </summary>
public sealed class KeptTakes(string root)
{
    /// <summary>How long a take without a tab is kept.</summary>
    public static readonly TimeSpan KeepFor = TimeSpan.FromDays(30);

    private const string Details = "take.json";

    private sealed record Stored(string Title, string File, double Seconds, DateTimeOffset Kept);

    public string Root { get; } = root;

    /// <summary>Changed: a take was kept, renamed or removed.</summary>
    public event EventHandler? Changed;

    /// <summary>The kept takes, the newest first; a folder that can't be read is left out (and left alone).</summary>
    public IReadOnlyList<KeptTake> List()
    {
        if (!Directory.Exists(Root)) return [];
        var found = new List<KeptTake>();
        foreach (var dir in Directory.EnumerateDirectories(Root))
            if (Read(dir) is { } take) found.Add(take);
        return [.. found.OrderByDescending(t => t.Kept)];
    }

    /// <summary>The take with <paramref name="id"/>; null when it is gone.</summary>
    public KeptTake? Find(string id) => List().FirstOrDefault(t => t.Id == id);

    /// <summary>The kept take whose recording <paramref name="source"/> is; null for a recording that isn't kept.</summary>
    public KeptTake? Of(SourceAudio source) => List().FirstOrDefault(t => string.Equals(t.WavPath, source.WavPath, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Keeps <paramref name="source"/>: a copy of its recording, under its title. A recording that is kept already keeps its
    /// folder. When it throws, nothing is listed for it.
    /// </summary>
    public KeptTake Keep(SourceAudio source, DateTimeOffset now)
    {
        if (Of(source) is { } kept) return kept;
        string id = Guid.NewGuid().ToString("N")[..12];
        string dir = Path.Combine(Root, id);
        Directory.CreateDirectory(dir);
        try
        {
            string file = "take" + (Path.GetExtension(source.WavPath) is { Length: > 0 } ext ? ext.ToLowerInvariant() : ".wav");
            File.Copy(source.WavPath, Path.Combine(dir, file));
            // The details last: a folder without them is never listed.
            File.WriteAllText(Path.Combine(dir, Details), JsonSerializer.Serialize(new Stored(Title(source), file, source.Duration.TotalSeconds, now)));
        }
        catch
        {
            TryDelete(dir);
            throw;
        }
        Changed?.Invoke(this, EventArgs.Empty);
        return Read(dir) ?? throw new IOException("the kept take could not be read back");
    }

    /// <summary>The title of a take: the recording's name without its extension.</summary>
    private static string Title(SourceAudio source) => Path.GetFileNameWithoutExtension(source.DisplayName) is { Length: > 0 } t ? t : source.DisplayName;

    public void Rename(string id, string title)
    {
        string dir = Path.Combine(Root, id);
        if (Read(dir) is not { } take) return;
        var stored = new Stored(title, Path.GetFileName(take.WavPath), take.Duration.TotalSeconds, take.Kept);
        File.WriteAllText(Path.Combine(dir, Details), JsonSerializer.Serialize(stored));
        Changed?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>The take is gone: its tab was made, or the player deleted it.</summary>
    public void Remove(string id)
    {
        if (!Directory.Exists(Path.Combine(Root, id))) return;
        TryDelete(Path.Combine(Root, id));
        Changed?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>Takes kept longer than <see cref="KeepFor"/> go, but the one in hand (<paramref name="inHand"/>, its recording's path).</summary>
    public void Prune(DateTimeOffset now, string? inHand = null)
    {
        foreach (var take in List())
            if (now - take.Kept > KeepFor && !string.Equals(take.WavPath, inHand, StringComparison.OrdinalIgnoreCase))
                TryDelete(Path.Combine(Root, take.Id));
    }

    private static KeptTake? Read(string dir)
    {
        try
        {
            var stored = JsonSerializer.Deserialize<Stored>(File.ReadAllText(Path.Combine(dir, Details)));
            if (stored is null) return null;
            string wav = Path.Combine(dir, Path.GetFileName(stored.File));
            return File.Exists(wav) ? new KeptTake(Path.GetFileName(dir), stored.Title, wav, TimeSpan.FromSeconds(stored.Seconds), stored.Kept) : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return null; }
    }

    private static void TryDelete(string dir)
    {
        try { Directory.Delete(dir, recursive: true); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}

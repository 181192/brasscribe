using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// Which build a workspace is: <c>.brasscribe-workspace.json</c>. <see cref="Stamp"/> hashes every file's path and
/// content (never dates); the build writes the commit and version next to the app's workspace, and the stamp is
/// computed from the files at launch. The copy in the data folder carries the stamp it was installed with.
/// </summary>
public sealed record WorkspaceStamp(
    [property: JsonPropertyName("stamp")] string? Stamp,
    [property: JsonPropertyName("lock")] string? Lock = null,
    [property: JsonPropertyName("commit")] string? Commit = null,
    [property: JsonPropertyName("version")] string? Version = null)
{
    public const string FileName = ".brasscribe-workspace.json";

    private static readonly JsonSerializerOptions Json = new() { DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull };

    public static WorkspaceStamp? Read(string workspace)
    {
        try { return JsonSerializer.Deserialize<WorkspaceStamp>(File.ReadAllText(Path.Combine(workspace, FileName)), Json); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return null; }
    }

    public void Write(string path) => File.WriteAllText(path, JsonSerializer.Serialize(this, Json));

    /// <summary>
    /// The files' stamp, with the commit and version the build wrote. Paths are relative with "/", in ordinal
    /// order; each line is "&lt;sha256&gt;  ./&lt;path&gt;" as <c>shasum</c> prints it (the macOS build's recipe).
    /// </summary>
    public static WorkspaceStamp Compute(string dir)
    {
        using var all = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var files = Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(dir, f).Replace('\\', '/'))
            .Where(rel => rel != FileName && !rel.EndsWith(".DS_Store", StringComparison.Ordinal))
            .Order(StringComparer.Ordinal);
        foreach (var rel in files)
            all.AppendData(Encoding.UTF8.GetBytes($"{FileHash(Path.Combine(dir, rel))}  ./{rel}\n"));
        var lockFile = Path.Combine(dir, "pixi.lock");
        var meta = Read(dir);
        return new WorkspaceStamp(Convert.ToHexStringLower(all.GetHashAndReset()),
            File.Exists(lockFile) ? FileHash(lockFile) : null, meta?.Commit, meta?.Version);
    }

    public static string FileHash(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    /// <summary>"0cf2582 · 5faffacca071": the commit and the start of the stamp, for the tech-person details.</summary>
    public string Short => string.Join(" · ", new[] { Commit, Stamp?[..Math.Min(12, Stamp.Length)] }.Where(s => !string.IsNullOrEmpty(s)));
}

/// <summary>
/// Replaces the code in the data folder's workspace with the app's, all or nothing (spec §3.8).
/// Only the app workspace's top-level entries are replaced (engine, music, eval, ml, pixi.toml, pixi.lock and the
/// stamp). The pixi environments (<c>.pixi</c>) and anything else in the folder stay; runs, models, paired devices
/// and Bandroom's own state are outside it. The new copy is staged next to the old (same volume, so moves are
/// renames); the old entries move aside, the new ones move in, stamp last. Until <see cref="Commit"/> the old
/// entries are kept, so a failed <c>pixi install</c> can still <see cref="Rollback"/>. A journal names the replaced
/// entries, so an update cut short (the app quit, a power cut) is undone by <see cref="Recover"/> at the next start;
/// deleting the journal is the commit.
/// </summary>
public sealed class WorkspaceSwap
{
    public const string WorkDir = ".bandroom-update";
    private const string JournalName = "journal.json";

    /// <summary>
    /// Fetched at run time into folders the swap replaces: carried over into the new copy when the app has none
    /// (run_adapter.py clones the Mega-53 MSST code where a build didn't ship it).
    /// </summary>
    public static readonly string[] Preserved = ["ml/adapters/mega53/msst"];

    public sealed record Entry(string Name, bool HadOld);

    public string Workspace { get; }
    /// <summary>This update's own folder under <see cref="WorkDir"/>, so leftovers of an earlier one never get in the way.</summary>
    public string Work { get; }
    public string Journal => Path.Combine(Work, JournalName);
    public string Backup => Path.Combine(Work, "old");

    private WorkspaceSwap(string workspace)
    {
        Workspace = workspace;
        Work = Path.Combine(workspace, WorkDir, Guid.NewGuid().ToString("N"));
    }

    /// <summary>Makes a move that antivirus or the indexer holds for a moment wait a little and try again.</summary>
    public static Func<int, TimeSpan> RetryDelay { get; set; } = attempt => TimeSpan.FromMilliseconds(50 << attempt);
    private const int MoveAttempts = 5;

    /// <summary>
    /// Stages <paramref name="bundled"/> and moves it into <paramref name="workspace"/> with <paramref name="stamp"/>
    /// as its stamp file. On any error the old copy is back as it was. <paramref name="beforeMove"/> runs before each
    /// entry moves in (tests use it to fail part-way).
    /// </summary>
    public static WorkspaceSwap Install(string bundled, string workspace, WorkspaceStamp stamp, Action<string>? beforeMove = null)
    {
        if (!Directory.Exists(bundled)) throw new DirectoryNotFoundException("the app's workspace is missing: " + bundled);
        Recover(workspace);
        Directory.CreateDirectory(workspace);
        var names = Directory.EnumerateFileSystemEntries(bundled).Select(Path.GetFileName).OfType<string>()
            .Where(n => n != WorkDir && n != WorkspaceStamp.FileName && n != ".DS_Store")
            .Order(StringComparer.Ordinal).Append(WorkspaceStamp.FileName).ToList();
        var entries = names.Select(n => new Entry(n, Exists(Path.Combine(workspace, n)))).ToList();
        var swap = new WorkspaceSwap(workspace);
        string staging = Path.Combine(swap.Work, "new");
        try
        {
            Directory.CreateDirectory(staging);
            Directory.CreateDirectory(swap.Backup);
            foreach (var e in entries)
            {
                string src = Path.Combine(bundled, e.Name), dst = Path.Combine(staging, e.Name);
                if (e.Name == WorkspaceStamp.FileName) stamp.Write(dst);
                else if (Directory.Exists(src)) CopyDirectory(src, dst);
                else File.Copy(src, dst);
            }
            foreach (var rel in Preserved.Where(r => names.Contains(r.Split('/')[0])))
            {
                string old = Path.Combine(workspace, rel), fresh = Path.Combine(staging, rel);
                if (Directory.Exists(old) && !Exists(fresh)) CopyDirectory(old, fresh);
            }
            WriteJournal(swap.Journal, entries);
            foreach (var e in entries)
            {
                if (e.HadOld) Move(Path.Combine(workspace, e.Name), Path.Combine(swap.Backup, e.Name));
                beforeMove?.Invoke(e.Name);
                Move(Path.Combine(staging, e.Name), Path.Combine(workspace, e.Name));
            }
        }
        catch
        {
            try { Recover(workspace); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
            throw;
        }
        return swap;
    }

    /// <summary>
    /// Written through to the disk before the first entry moves: after a power cut the journal is there, whole, for
    /// every rename that happened.
    /// </summary>
    private static void WriteJournal(string path, List<Entry> entries)
    {
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough);
        JsonSerializer.Serialize(stream, entries);
        stream.Flush(flushToDisk: true);
    }

    /// <summary>The update is done: the journal goes first (that is the commit), then the old copy, as far as it can.</summary>
    public void Commit()
    {
        File.Delete(Journal);
        DeleteQuietly(Work);
        DeleteQuietly(Path.Combine(Workspace, WorkDir), onlyIfEmpty: true);
    }

    /// <summary>Puts the old copy back.</summary>
    public void Rollback() => Recover(Workspace);

    /// <summary>
    /// Undoes every update that didn't commit: each replaced entry gets its old self back, entries new in the update
    /// go. A folder without a journal holds nothing to undo (never swapped, or committed) and is removed as far as it
    /// can be: files the old engine still holds never block the next update. A journal that is there but can't be read
    /// leaves its folder alone once anything was moved aside: <c>old</c> may hold the only copy of what the update
    /// replaced.
    /// </summary>
    public static void Recover(string workspace, Action<string>? log = null)
    {
        var root = Path.Combine(workspace, WorkDir);
        if (!Directory.Exists(root)) return;
        foreach (var work in Directory.EnumerateDirectories(root).ToList())
        {
            var journal = Path.Combine(work, JournalName);
            if (File.Exists(journal))
            {
                List<Entry>? entries = null;
                try { entries = JsonSerializer.Deserialize<List<Entry>>(File.ReadAllText(journal)); }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { log?.Invoke($"bandroom: can't read {journal}: {e.Message}"); }
                if (entries is null)
                {
                    // Nothing moved aside yet (the journal was cut short while being written): nothing to lose.
                    string moved = Path.Combine(work, "old");
                    if (!Directory.Exists(moved) || !Directory.EnumerateFileSystemEntries(moved).Any())
                    {
                        DeleteQuietly(work);
                        continue;
                    }
                    log?.Invoke($"bandroom: keeping {work} as it is: its journal can't be read");
                    continue;
                }
                foreach (var e in Enumerable.Reverse(entries))
                {
                    string live = Path.Combine(workspace, e.Name), old = Path.Combine(work, "old", e.Name);
                    if (e.HadOld)
                    {
                        // Not moved aside yet (or already back): the original is in place.
                        if (!Exists(old)) continue;
                        Delete(live);
                        Move(old, live);
                    }
                    else Delete(live);
                }
                File.Delete(journal);
            }
            DeleteQuietly(work);
        }
        DeleteQuietly(root, onlyIfEmpty: true);
    }

    private static void DeleteQuietly(string dir, bool onlyIfEmpty = false)
    {
        try
        {
            if (!Directory.Exists(dir) || (onlyIfEmpty && Directory.EnumerateFileSystemEntries(dir).Any())) return;
            Directory.Delete(dir, recursive: true);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    private static bool Exists(string path) => File.Exists(path) || Directory.Exists(path);

    private static void Delete(string path)
    {
        if (Directory.Exists(path)) Directory.Delete(path, recursive: true);
        else if (File.Exists(path)) File.Delete(path);
    }

    private static void Move(string from, string to)
    {
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                if (Directory.Exists(from)) Directory.Move(from, to);
                else File.Move(from, to);
                return;
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException && attempt < MoveAttempts - 1 && Exists(from))
            {
                Thread.Sleep(RetryDelay(attempt));
            }
        }
    }

    private static void CopyDirectory(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (var dir in Directory.EnumerateDirectories(from, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(Path.Combine(to, Path.GetRelativePath(from, dir)));
        foreach (var file in Directory.EnumerateFiles(from, "*", SearchOption.AllDirectories))
        {
            var dst = Path.Combine(to, Path.GetRelativePath(from, file));
            File.Copy(file, dst);
            File.SetLastWriteTimeUtc(dst, File.GetLastWriteTimeUtc(file));
        }
    }
}

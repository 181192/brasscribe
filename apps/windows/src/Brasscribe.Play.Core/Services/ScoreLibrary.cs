using System.Text.Json;
using System.Text.Json.Serialization;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Services;

/// <summary>A score in "Your scores": where its files are and what the list row says.</summary>
/// <remarks><c>MyPart</c> is the part chosen for this score with "Make this my part" (its own name); null follows the seat.</remarks>
public sealed record LibraryEntry(
    string Id,
    string Title,
    string MusicXmlPath,
    string? CompositionPath,
    DateTimeOffset Updated,
    int Parts,
    int Bars,
    int NotesToCheck,
    string? JobId = null,
    string? EvidencePath = null,
    string? Lineup = null,
    string? MyPart = null)
{
    /// <summary>
    /// The file was there when "Your scores" was read. An opened file on a drive that is not connected stays listed, and
    /// opens again once it is back. Checked once, not on every refresh: a missing network share can take seconds to answer.
    /// </summary>
    [JsonIgnore]
    public bool IsAvailable { get; init; } = true;
}

/// <summary>
/// A note changed in Review: how far it has moved since Brasscribe wrote it, and what Brasscribe wrote, as
/// the card named it and as a written MIDI pitch (so another arrangement of the score names it again).
/// </summary>
public sealed record ReviewChange(string Was, int Shift, int? WrittenMidi = null);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, WriteIndented = true)]
[JsonSerializable(typeof(List<LibraryEntry>))]
[JsonSerializable(typeof(Dictionary<string, ReviewChange>))]
internal sealed partial class LibraryJsonContext : JsonSerializerContext;

/// <summary>
/// "Your scores": finished scores and opened score files, newest first, kept as a JSON index in the
/// work directory. Scores made by Brasscribe are copied into the library folder (MusicXML plus the
/// Composition behind it); opened files are referenced where they are until the first change (a
/// corrected note, a new title), which goes to a copy in the library: the player's own file is never
/// written. Nothing leaves the computer.
/// </summary>
public sealed class ScoreLibrary
{
    private readonly string _root;
    private readonly List<LibraryEntry> _entries;

    public ScoreLibrary(string root)
    {
        _root = root;
        Directory.CreateDirectory(root);
        _entries = Load();
    }

    private string IndexPath => Path.Combine(_root, "library.json");

    public IReadOnlyList<LibraryEntry> Entries => _entries;

    public event EventHandler? Changed;

    /// <summary>Stores a score Brasscribe made; the same job replaces its earlier entry.</summary>
    /// <remarks><paramref name="lineup"/> is the engine's name of the lineup it was arranged for (full, minimal, quartet).</remarks>
    public LibraryEntry AddMade(string title, string musicXml, Composition? composition, int parts, int bars, int notesToCheck, string? jobId,
        Engine.Evidence? evidence = null, string? lineup = null)
    {
        string id = jobId is { Length: > 0 } ? Safe(jobId) : Guid.NewGuid().ToString("N")[..12];
        string dir = Path.Combine(_root, id);
        Directory.CreateDirectory(dir);
        string xmlPath = Path.Combine(dir, "score.musicxml");
        File.WriteAllText(xmlPath, musicXml);
        string? compPath = null;
        if (composition is not null)
        {
            compPath = Path.Combine(dir, "composition.json");
            File.WriteAllText(compPath, CompositionJson.Serialize(composition));
        }
        string? evidencePath = null;
        if (evidence is not null)
        {
            evidencePath = Path.Combine(dir, "evidence.json");
            File.WriteAllText(evidencePath, Engine.Evidence.Serialize(evidence));
        }
        return Put(new LibraryEntry(id, title, xmlPath, compPath, DateTimeOffset.Now, parts, bars, notesToCheck, jobId, evidencePath, lineup));
    }

    /// <summary>Confidence and what each transcriber heard, when the score came with it.</summary>
    public Engine.Evidence? LoadEvidence(LibraryEntry entry)
    {
        try
        {
            return entry.EvidencePath is { } p && File.Exists(p) ? Engine.Evidence.Parse(File.ReadAllText(p)) : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public void SaveEvidence(string id, Engine.Evidence evidence)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0) return;
        string path = _entries[i].EvidencePath ?? Path.Combine(Path.GetDirectoryName(_entries[i].MusicXmlPath)!, "evidence.json");
        if (_entries[i].EvidencePath is null && !IsInside(path)) return; // an opened file: don't write beside it
        WriteAtomically(path, Engine.Evidence.Serialize(evidence));
        if (_entries[i].EvidencePath != path)
        {
            _entries[i] = _entries[i] with { EvidencePath = path };
            Save();
        }
    }

    private string? ReviewChangesPath(string id)
    {
        var entry = _entries.FirstOrDefault(e => e.Id == id);
        if (entry is null) return null;
        string path = Path.Combine(Path.GetDirectoryName(entry.MusicXmlPath)!, "review-changes.json");
        return IsInside(path) ? path : null; // an opened file: nothing is written beside it
    }

    /// <summary>The notes changed in Review for this score, by change key; empty when there are none.</summary>
    public IReadOnlyDictionary<string, ReviewChange> LoadReviewChanges(string id)
    {
        try
        {
            return ReviewChangesPath(id) is { } p && File.Exists(p)
                ? JsonSerializer.Deserialize(File.ReadAllText(p), LibraryJsonContext.Default.DictionaryStringReviewChange) ?? []
                : new Dictionary<string, ReviewChange>();
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException)
        {
            return new Dictionary<string, ReviewChange>();
        }
    }

    /// <summary>Keeps the notes changed in Review with the score; none removes the file.</summary>
    public void SaveReviewChanges(string id, IReadOnlyDictionary<string, ReviewChange> changes)
    {
        if (ReviewChangesPath(id) is not { } path) return;
        try
        {
            if (changes.Count == 0) { File.Delete(path); return; }
            WriteAtomically(path, JsonSerializer.Serialize(new Dictionary<string, ReviewChange>(changes), LibraryJsonContext.Default.DictionaryStringReviewChange));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>Remembers a score file the player opened.</summary>
    public LibraryEntry AddOpened(string path, string title, int parts, int bars, int notesToCheck)
    {
        var existing = _entries.FirstOrDefault(e => string.Equals(e.MusicXmlPath, path, StringComparison.OrdinalIgnoreCase));
        return Put(new LibraryEntry(existing?.Id ?? Guid.NewGuid().ToString("N")[..12], title, path, null, DateTimeOffset.Now, parts, bars, notesToCheck));
    }

    /// <summary>"Make this my part": the part (by its own name) is the player's in this score from now on.</summary>
    public void SetMyPart(string id, string? part)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0 || _entries[i].MyPart == part) return;
        _entries[i] = _entries[i] with { MyPart = part };
        Save();
    }

    /// <summary>Updates how many notes are still to check.</summary>
    public void SetNotesToCheck(string id, int count)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0 || _entries[i].NotesToCheck == count) return;
        _entries[i] = _entries[i] with { NotesToCheck = count };
        Save();
    }

    /// <summary>
    /// An opened file moves into the library before it is changed: the entry points at a copy from now on,
    /// and the file where the player keeps it stays as it was.
    /// </summary>
    private void OwnCopy(int i)
    {
        var entry = _entries[i];
        if (IsInside(entry.MusicXmlPath)) return;
        string dir = Path.Combine(_root, Safe(entry.Id));
        Directory.CreateDirectory(dir);
        string copy = Path.Combine(dir, "score.musicxml");
        File.Copy(entry.MusicXmlPath, copy, overwrite: true);
        _entries[i] = entry with { MusicXmlPath = copy };
    }

    public void SaveMusicXml(string id, string musicXml, string? compositionJson = null, string? lineup = null)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0) return;
        OwnCopy(i);
        WriteAtomically(_entries[i].MusicXmlPath, musicXml);
        if (compositionJson is not null && _entries[i].CompositionPath is { } compositionPath)
        {
            var composition = CompositionJson.Parse(compositionJson);
            composition.Title = _entries[i].Title;
            WriteAtomically(compositionPath, CompositionJson.Serialize(composition));
        }
        _entries[i] = _entries[i] with { Updated = DateTimeOffset.Now, Lineup = lineup ?? _entries[i].Lineup };
        Save();
    }

    public void Rename(string id, string title)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0) return;
        OwnCopy(i);
        var entry = _entries[i];
        WriteAtomically(entry.MusicXmlPath, MusicXmlNoteEditor.ReplaceTitle(File.ReadAllText(entry.MusicXmlPath), title));
        if (entry.CompositionPath is { } compositionPath && File.Exists(compositionPath))
        {
            var composition = CompositionJson.Parse(File.ReadAllText(compositionPath));
            composition.Title = title;
            WriteAtomically(compositionPath, CompositionJson.Serialize(composition));
        }
        _entries[i] = entry with { Title = title, Updated = DateTimeOffset.Now };
        Save();
    }

    /// <summary>Forgets a score; a score Brasscribe made is deleted with its folder, an opened file is left where it is.</summary>
    public void Remove(string id)
    {
        var entry = _entries.FirstOrDefault(e => e.Id == id);
        if (entry is null) return;
        _entries.Remove(entry);
        string dir = Path.GetDirectoryName(entry.MusicXmlPath)!;
        if (IsInside(entry.MusicXmlPath) && !string.Equals(Path.GetFullPath(dir), Path.GetFullPath(_root), StringComparison.OrdinalIgnoreCase))
        {
            try { Directory.Delete(dir, recursive: true); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
        Save();
    }

    private bool IsInside(string path) =>
        Path.GetFullPath(path).StartsWith(Path.GetFullPath(_root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    private LibraryEntry Put(LibraryEntry entry)
    {
        // The same score again (the same job, the same file) keeps the part chosen for it.
        if (entry.MyPart is null && _entries.FirstOrDefault(e => e.Id == entry.Id)?.MyPart is { } mine) entry = entry with { MyPart = mine };
        _entries.RemoveAll(e => e.Id == entry.Id);
        _entries.Insert(0, entry);
        Save();
        return entry;
    }

    private List<LibraryEntry> Load()
    {
        try
        {
            if (!File.Exists(IndexPath)) return [];
            var list = JsonSerializer.Deserialize(File.ReadAllText(IndexPath), LibraryJsonContext.Default.ListLibraryEntry) ?? [];
            // A score gone from the library folder is gone; an opened file may be on a drive that is not connected now.
            return list.Select(e => e with { IsAvailable = File.Exists(e.MusicXmlPath) })
                .Where(e => e.IsAvailable || !IsInside(e.MusicXmlPath)).OrderByDescending(e => e.Updated).ToList();
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException)
        {
            return [];
        }
    }

    private void Save()
    {
        string tmp = IndexPath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(_entries, LibraryJsonContext.Default.ListLibraryEntry));
        File.Move(tmp, IndexPath, overwrite: true);
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private static void WriteAtomically(string path, string contents)
    {
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, contents);
        File.Move(tmp, path, overwrite: true);
    }

    private static string Safe(string id) => string.Concat(id.Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '_'));
}

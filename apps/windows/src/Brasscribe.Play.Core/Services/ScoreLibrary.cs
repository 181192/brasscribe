using System.Text.Json;
using System.Text.Json.Serialization;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Services;

/// <summary>A score in "Your scores": where its files are and what the list row says.</summary>
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
    string? Lineup = null);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, WriteIndented = true)]
[JsonSerializable(typeof(List<LibraryEntry>))]
internal sealed partial class LibraryJsonContext : JsonSerializerContext;

/// <summary>
/// "Your scores": finished scores and opened score files, newest first, kept as a JSON index in the
/// work directory. Scores made by Brasscribe are copied into the library folder (MusicXML plus the
/// Composition behind it); opened files are referenced where they are. Nothing leaves the computer.
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

    /// <summary>Remembers a score file the player opened.</summary>
    public LibraryEntry AddOpened(string path, string title, int parts, int bars, int notesToCheck)
    {
        var existing = _entries.FirstOrDefault(e => string.Equals(e.MusicXmlPath, path, StringComparison.OrdinalIgnoreCase));
        return Put(new LibraryEntry(existing?.Id ?? Guid.NewGuid().ToString("N")[..12], title, path, null, DateTimeOffset.Now, parts, bars, notesToCheck));
    }

    /// <summary>Updates how many notes are still to check.</summary>
    public void SetNotesToCheck(string id, int count)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0 || _entries[i].NotesToCheck == count) return;
        _entries[i] = _entries[i] with { NotesToCheck = count };
        Save();
    }

    public void SaveMusicXml(string id, string musicXml, string? compositionJson = null, string? lineup = null)
    {
        int i = _entries.FindIndex(e => e.Id == id);
        if (i < 0) return;
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
            return list.Where(e => File.Exists(e.MusicXmlPath)).OrderByDescending(e => e.Updated).ToList();
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

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
    string? JobId = null);

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
    public LibraryEntry AddMade(string title, string musicXml, Composition? composition, int parts, int bars, int notesToCheck, string? jobId)
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
        return Put(new LibraryEntry(id, title, xmlPath, compPath, DateTimeOffset.Now, parts, bars, notesToCheck, jobId));
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

    public void Remove(string id)
    {
        if (_entries.RemoveAll(e => e.Id == id) > 0) Save();
    }

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

    private static string Safe(string id) => string.Concat(id.Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '_'));
}

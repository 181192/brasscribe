using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using Kalli.Scribe.Engine;

namespace Kalli.Scribe.Tab;

/// <summary>What is known of the recording of the song on screen.</summary>
public enum RecordingState
{
    /// <summary>Being looked for on this device.</summary>
    Looking,
    /// <summary>On this device, and it plays.</summary>
    Here,
    /// <summary>Not on this device: the song was opened from the computer's list, or its file is gone.</summary>
    NotHere,
    /// <summary>Being copied from the computer.</summary>
    Getting,
    /// <summary>The computer does not have it either.</summary>
    Gone,
    /// <summary>The computer could not be asked.</summary>
    NoAnswer,
    /// <summary>The computer was not asked: this app is older than the computer's side.</summary>
    UpdateApp,
    /// <summary>The computer was not asked: the computer's side is older than this app.</summary>
    UpdateComputer,
    /// <summary>The device has no room to keep it.</summary>
    NoRoom,
    /// <summary>It is larger than this device takes.</summary>
    TooLarge,
    /// <summary>On this device, and it cannot be played.</summary>
    Unplayable,
}

/// <summary>
/// The recordings of the songs practised on this device, one file to a song, by the id of the song's job on the
/// computer: a song's recording is copied here when its tab is first opened with the recording in hand, or when it is
/// fetched from the computer, so the song can be practised when it is opened again.
/// </summary>
public sealed class PracticeRecordings(string dir)
{
    private const string Part = ".part";

    /// <summary>Less room than this after a fetch failed: the disk is full.</summary>
    public const long FullBytes = 16L << 20;

    private string? Named(string job) => FileName(job) is { } name ? Path.Combine(dir, name) : null;

    public string? Find(string job) => Named(job) is { } path && File.Exists(path) && new FileInfo(path).Length > 0 ? path : null;

    /// <summary>
    /// Where a recording being fetched or copied is written, until it is whole (<see cref="Arrived"/>): a file of this
    /// try's own, so a try that was given up and clears up after itself late never takes the file of the try after it.
    /// </summary>
    public string? Arriving(string job)
    {
        if (Named(job) is not { } path) return null;
        try
        {
            Directory.CreateDirectory(dir);
            string part = $"{path}.{Guid.NewGuid():N}{Part}";
            using (File.Create(part)) { }
            return part;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>The try that wrote <paramref name="part"/> did not get through: what there is of it goes.</summary>
    public static void Dropped(string? part)
    {
        if (part is null) return;
        try { File.Delete(part); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>Room left for recordings, in bytes.</summary>
    public long Room
    {
        get
        {
            try
            {
                var at = new DirectoryInfo(Path.GetFullPath(dir));
                while (at is not null && !at.Exists) at = at.Parent;
                return at is null ? 0 : new DriveInfo(at.Root.FullName).AvailableFreeSpace;
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException)
            {
                return 0;
            }
        }
    }

    /// <summary><paramref name="part"/>, written whole, becomes <paramref name="job"/>'s recording; one that came empty goes.</summary>
    public string? Arrived(string job, string part)
    {
        var to = Named(job);
        try
        {
            if (to is not null && File.Exists(part) && new FileInfo(part).Length > 0)
            {
                File.Move(part, to, overwrite: true);
                return to;
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        Dropped(part);
        return null;
    }

    /// <summary>A copy of <paramref name="from"/> kept for <paramref name="job"/>; <paramref name="from"/> itself when it cannot be copied.</summary>
    public string Keep(string job, string from)
    {
        if (Find(job) is { } kept && new FileInfo(kept).Length == new FileInfo(from).Length) return kept;
        if (Arriving(job) is not { } part) return from;
        try
        {
            File.Copy(from, part, overwrite: true);
            if (Arrived(job, part) is { } arrived) return arrived;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        Dropped(part);
        return from;
    }

    /// <summary>
    /// Drops the recordings of every song but <paramref name="jobs"/>: a song deleted from Your songs takes its recording
    /// with it. What a fetch or a copy that did not finish left behind goes too (none is running when this is asked).
    /// </summary>
    public void Prune(IEnumerable<string> jobs) => PruneFolder(dir, jobs);

    internal static void PruneFolder(string dir, IEnumerable<string> jobs)
    {
        var kept = jobs.Select(FileName).OfType<string>().ToHashSet();
        try
        {
            if (!Directory.Exists(dir)) return;
            foreach (var file in Directory.GetFiles(dir))
                if (!kept.Contains(Path.GetFileName(file)))
                    Dropped(file);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>
    /// The name of <paramref name="job"/>'s file: what a file name can hold of the id, and a short hash of the whole id,
    /// so two ids that read the same once their other characters are gone, or past the length kept, are still two files.
    /// </summary>
    public static string? FileName(string job)
    {
        if (job.Length == 0) return null;
        string plain = new([.. job.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_').Take(60)]);
        string hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(job)).AsSpan(0, 4));
        return $"{plain}.{hash}";
    }

    /// <summary>
    /// Why a recording did not come from the computer, from what went wrong (<paramref name="error"/>) and the
    /// <paramref name="room"/> left: the computer does not have it; it is larger than this device takes; this device
    /// could not keep it (no room, or the file could not be written); the computer was not asked because one of the two
    /// needs an update; or the computer was not reached.
    /// </summary>
    public static RecordingState WhyNot(Exception error, long room) => error switch
    {
        EngineException { Interface: InterfaceAnswer.UpdateApp } => RecordingState.UpdateApp,
        EngineException { Interface: InterfaceAnswer.UpdateBandroom } => RecordingState.UpdateComputer,
        EngineException { Status: HttpStatusCode.NotFound } => RecordingState.Gone,
        EngineException { Status: HttpStatusCode.RequestEntityTooLarge } => RecordingState.TooLarge,
        EngineException => RecordingState.NoAnswer,
        FileNotFoundException or DirectoryNotFoundException or UnauthorizedAccessException or InvalidOperationException => RecordingState.NoRoom,
        _ when room < FullBytes => RecordingState.NoRoom,
        _ => RecordingState.NoAnswer,
    };

    /// <summary>
    /// The kind of sound file <paramref name="path"/> is, as a file name's extension, read from its first bytes (a kept
    /// recording's name says nothing of it): WAV, MP4 sound (M4A), MP3, Ogg, FLAC or WebM; "wav" when it is none of these.
    /// </summary>
    public static string ExtensionOf(string path)
    {
        var head = new byte[12];
        try
        {
            using var s = File.OpenRead(path);
            _ = s.Read(head, 0, head.Length);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return "wav";
        }
        bool At(int offset, string text) => text.Select((c, i) => head[offset + i] == (byte)c).All(b => b);
        if (At(0, "RIFF") && At(8, "WAVE")) return "wav";
        if (At(4, "ftyp")) return "m4a";
        if (At(0, "ID3") || (head[0] == 0xFF && (head[1] & 0xE0) == 0xE0)) return "mp3";
        if (At(0, "OggS")) return "ogg";
        if (At(0, "fLaC")) return "flac";
        if (head[0] == 0x1A && head[1] == 0x45 && head[2] == 0xDF && head[3] == 0xA3) return "webm";
        return "wav";
    }
}

/// <summary>Where a song was left in practice: the second of the recording, the speed in per cent, and the bars repeated.</summary>
public sealed record PracticePlace(double At, int Speed, RepeatBars? Repeat);

/// <summary>
/// Where each song was left in practice, kept on this device beside the song's recording (<see cref="PracticeRecordings"/>),
/// by the id of the song's job: one small file to a song. A song deleted from Your songs keeps its file until a song that
/// is still in Your songs is next opened on the tab, when the places of the songs no longer there are pruned.
/// </summary>
public sealed class PracticePlaces(string dir)
{
    private string? Named(string job) => PracticeRecordings.FileName(job) is { } name ? Path.Combine(dir, name) : null;

    /// <summary>Where <paramref name="job"/>'s song was left; null when it was never practised, or what is kept can't be read.</summary>
    public PracticePlace? Read(string job)
    {
        if (Named(job) is not { } path || !File.Exists(path)) return null;
        string[] words;
        try { words = File.ReadAllText(path).Trim().Split(' '); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
        var inv = CultureInfo.InvariantCulture;
        if (!double.TryParse(words[0], NumberStyles.Float, inv, out double at) || !double.IsFinite(at) || at < 0) return null;
        if (words.Length < 2 || !int.TryParse(words[1], NumberStyles.Integer, inv, out int speed)) return null;
        int? first = words.Length > 2 && int.TryParse(words[2], NumberStyles.Integer, inv, out int f) ? f : null;
        int? last = words.Length > 3 && int.TryParse(words[3], NumberStyles.Integer, inv, out int l) ? l : null;
        return new PracticePlace(at, speed, first is { } a && last is { } b && a >= 0 && a <= b ? new RepeatBars(a, b) : null);
    }

    /// <summary>Keeps <paramref name="place"/> for <paramref name="job"/>'s song: written whole, then put in the place of what was there.</summary>
    public void Save(string job, PracticePlace place)
    {
        if (Named(job) is not { } to) return;
        string part = to + ".part";
        try
        {
            Directory.CreateDirectory(dir);
            var inv = CultureInfo.InvariantCulture;
            var words = new List<string> { place.At.ToString("R", inv), place.Speed.ToString(inv) };
            if (place.Repeat is { } r) { words.Add(r.First.ToString(inv)); words.Add(r.Last.ToString(inv)); }
            File.WriteAllText(part, string.Join(' ', words));
            File.Move(part, to, overwrite: true);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            PracticeRecordings.Dropped(part);
            System.Diagnostics.Trace.TraceWarning($"where the song was left could not be kept: {e.Message}");
        }
    }

    /// <summary>Drops the places of every song but <paramref name="jobs"/>: a song deleted from Your songs takes its place with it.</summary>
    public void Prune(IEnumerable<string> jobs) => PracticeRecordings.PruneFolder(dir, jobs);
}

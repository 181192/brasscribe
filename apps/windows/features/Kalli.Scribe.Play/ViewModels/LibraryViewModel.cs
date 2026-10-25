using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Services;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Kalli.Scribe.ViewModels;

/// <summary>A row of the library: a result on this PC, or a finished one on the paired computer.</summary>
public sealed record LibraryItem(string Id, string Title, string Subtitle, bool OnComputer = false, string? JobId = null)
{
    public bool OnThisPc => !OnComputer;
}

/// <summary>What a finished job on the computer gave, downloaded to open it here.</summary>
public sealed record ComputerResult(Job Job, Composition Composition, string MusicXml, Evidence? Evidence);

/// <summary>
/// The library as the app lists it: this PC's results and the computer's finished jobs of the app's target (the
/// computer serves other apps too), newest first, with renaming and deleting in both places. What an entry is
/// called under its title comes from the app (<c>subtitle</c>); opening one is the app's.
/// </summary>
public sealed partial class LibraryViewModel : ObservableObject
{
    private readonly Target _target;
    private readonly Func<IEngineClient> _engine;
    private readonly ConnectionMonitor _connection;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly Func<LibraryEntry, string> _subtitle;
    private IReadOnlyList<Job> _computerJobs = [];

    public LibraryViewModel(ScoreLibrary? store, Target target, Func<IEngineClient> engine, ConnectionMonitor connection,
        IAnnouncer announcer, IStrings strings, Func<LibraryEntry, string> subtitle)
    {
        Store = store;
        _target = target;
        _engine = engine;
        _connection = connection;
        _announcer = announcer;
        _s = strings;
        _subtitle = subtitle;
        Refresh();
        if (store is not null) store.Changed += (_, _) => Refresh();
        // Every change of the connection: the computer's results are fetched again when it is connected, and gone
        // from the list when it is not.
        connection.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName != nameof(ConnectionMonitor.State)) return;
            if (!connection.IsConnected)
            {
                _computerJobs = [];
                Refresh();
            }
            // A state shown as sample content has no computer behind it to ask.
            else if (!connection.IsPreview) _ = RefreshComputerAsync();
        };
    }

    /// <summary>This PC's library; null when the app keeps none (tests).</summary>
    public ScoreLibrary? Store { get; }

    /// <summary>The rows, newest first.</summary>
    public System.Collections.ObjectModel.ObservableCollection<LibraryItem> Items { get; } = [];

    /// <summary>The library has rows (else Home shows the empty state).</summary>
    [ObservableProperty] public partial bool HasItems { get; set; }

    /// <summary>Something went wrong that the player should see; the window shows it in its notice bar.</summary>
    public event EventHandler<string>? ProblemNoticed;

    /// <summary>Rows the app keeps elsewhere (a recording kept before it has a result), listed with the others by date.</summary>
    public Func<IEnumerable<(DateTimeOffset When, LibraryItem Item)>>? MoreRows { get; set; }

    /// <summary>
    /// A write to the library that must not end what the player is doing: a full disk or a file another app holds
    /// is said (and shown through <see cref="ProblemNoticed"/>), and what is on screen stays as it is.
    /// </summary>
    public void Keep(Action write)
    {
        try { write(); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            string text = _s["Library_SaveFailed"];
            _announcer.Announce(text, AnnouncementKind.Important);
            ProblemNoticed?.Invoke(this, text);
        }
    }

    /// <summary>
    /// Fetches the computer's finished results of this app's target; only this PC's are listed when the computer can't
    /// be reached or has another interface version (its client asks that first, and then sends nothing more).
    /// </summary>
    public async Task RefreshComputerAsync()
    {
        try
        {
            _computerJobs = [.. (await _engine().ListJobsAsync()).Where(j => _target.Makes(j.Target))];
        }
        catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException or TaskCanceledException
                                   or System.Text.Json.JsonException)
        {
            _computerJobs = [];
        }
        Refresh();
    }

    /// <summary>Downloads a finished job's result from the computer: the job, its composition, its MusicXML and, when it has them, its notes' evidence.</summary>
    public async Task<ComputerResult> DownloadAsync(string jobId)
    {
        var engine = _engine();
        var job = await engine.GetJobAsync(jobId);
        var composition = await engine.GetCompositionAsync(jobId);
        string xml;
        await using (var stream = await engine.DownloadAsync(jobId, JobDownload.MusicXml))
        using (var reader = new StreamReader(stream))
            xml = await reader.ReadToEndAsync();
        Evidence? evidence = null;
        try { evidence = await engine.GetEvidenceAsync(jobId); }
        catch (Exception e) when (e is EngineException or NotSupportedException or System.Text.Json.JsonException) { }
        return new ComputerResult(job, composition, xml, evidence);
    }

    /// <summary>Renames a run on the computer; false when it could not be (said through <see cref="SayUpdate"/> for another interface version).</summary>
    public async Task<bool> RenameOnComputerAsync(string jobId, string title)
    {
        try
        {
            await _engine().RenameRunAsync(jobId, title);
            return true;
        }
        catch (EngineException e) when (e.Interface is { } answer)
        {
            SayUpdate(answer);
            return false;
        }
        catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException)
        {
            return false;
        }
    }

    /// <summary>Renames this PC's entry; false (and said) when the file can't be written.</summary>
    public bool RenameHere(string id, string title)
    {
        try
        {
            Store?.Rename(id, title);
            return Store is not null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Xml.XmlException or FormatException)
        {
            _announcer.Announce(_s.Format("Score_RenameFailed", title), AnnouncementKind.Important);
            return false;
        }
    }

    /// <summary>"Delete" on a row: this PC's copy, or the run on the computer. Says what happened, after <paramref name="removedHere"/> for this PC's.</summary>
    public async Task<bool> DeleteAsync(LibraryItem item, Action? removedHere = null)
    {
        if (item.OnComputer)
        {
            try
            {
                if (item.JobId is { } jobId) await _engine().DeleteRunAsync(jobId);
            }
            catch (EngineException e) when (e.Interface is { } answer)
            {
                SayUpdate(answer);
                return false;
            }
            catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException)
            {
                _announcer.Announce(_s.Format("Library_DeleteFailed", item.Title), AnnouncementKind.Important);
                return false;
            }
            await RefreshComputerAsync();
        }
        else
        {
            Keep(() => Store?.Remove(item.Id));
            removedHere?.Invoke();
        }
        _announcer.Announce(_s.Format("Library_Deleted", item.Title));
        return true;
    }

    /// <summary>
    /// A request was refused because the engine has another interface version: says which of the two to update, in the
    /// status row's words (also in the window's notice bar, unless the screen shows them itself), and the row checks
    /// again at once.
    /// </summary>
    public string SayUpdate(InterfaceAnswer answer, bool notice = true)
    {
        string text = _connection.UpdateText(answer);
        _announcer.Announce(text, AnnouncementKind.Important);
        if (notice) ProblemNoticed?.Invoke(this, text);
        _connection.Kick();
        return text;
    }

    /// <summary>The rows again from this PC's library and the computer's jobs last fetched.</summary>
    public void Refresh()
    {
        Items.Clear();
        var rows = new List<(DateTimeOffset When, LibraryItem Item)>();
        if (Store is not null)
            rows.AddRange(Store.Entries.Select(e => (e.Updated, new LibraryItem(e.Id, ScoreTitles.Display(e.Title, e.Updated, _s), _subtitle(e)))));
        // The computer's finished runs not already here; re-runs of one recording collapse to the latest.
        var downloaded = Store?.Entries.Select(e => e.JobId).OfType<string>().ToHashSet() ?? [];
        var seenAudio = new HashSet<string>();
        foreach (var j in _computerJobs.OrderByDescending(j => j.Created))
        {
            if (j.Status != JobStatus.Succeeded || !(j.Outputs ?? []).Any(o => o.EndsWith(".musicxml", StringComparison.OrdinalIgnoreCase))) continue;
            if (j.AudioId is { } audio && !seenAudio.Add(audio)) continue;
            if (downloaded.Contains(j.Id)) continue;
            var when = DateTimeOffset.FromUnixTimeMilliseconds((long)(j.Created * 1000)).ToLocalTime();
            rows.Add((when, new LibraryItem("job:" + j.Id, ScoreTitles.Display(j.Title, when, _s), _s.Format("Library_OnComputer", WhenText(when)), true, j.Id)));
        }
        if (MoreRows is { } more) rows.AddRange(more());
        MarkDuplicateTimes(rows);
        foreach (var (_, item) in rows.OrderByDescending(r => r.When).Take(20)) Items.Add(item);
        HasItems = Items.Count > 0;
    }

    /// <summary>"Today", "Yesterday" or the date, for a row's subtitle.</summary>
    public static string WhenText(DateTimeOffset when, IStrings s) => when.Date == DateTimeOffset.Now.Date ? s["Library_Today"]
        : when.Date == DateTimeOffset.Now.Date.AddDays(-1) ? s["Library_Yesterday"]
        : when.ToString(s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) ? "d. MMMM" : "d MMM", System.Globalization.CultureInfo.CurrentUICulture);

    private string WhenText(DateTimeOffset when) => WhenText(when, _s);

    /// <summary>Same titles get the time as well ("Today 19:02"), so the recordings can be told apart.</summary>
    private void MarkDuplicateTimes(List<(DateTimeOffset When, LibraryItem Item)> rows)
    {
        var dupes = ScoreTitles.Duplicates(rows.Select(r => r.Item.Title));
        for (int i = 0; i < rows.Count; i++)
            if (dupes.Contains(rows[i].Item.Title))
                rows[i] = (rows[i].When, rows[i].Item with
                {
                    Subtitle = rows[i].Item.Subtitle.Replace(WhenText(rows[i].When),
                        WhenText(rows[i].When) + " " + rows[i].When.ToLocalTime().ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)),
                });
    }
}

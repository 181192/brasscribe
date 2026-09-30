using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>What to share or print: the conductor's score, one PDF per player, or the player's own part.</summary>
public enum ExportScope { MyPart, EveryPart, Conductor }

/// <summary>A format row: name, what it is for, whether it can be made now.</summary>
public sealed partial class ExportChoice : ObservableObject
{
    public ExportChoice(string key, string label, string description, bool available, string? reason)
    {
        Key = key;
        Label = label;
        Description = description;
        Available = available;
        Reason = reason;
    }

    /// <summary>Pdf, MusicXml, Audio, Midi, TalkingScore or Braille.</summary>
    public string Key { get; }
    public string Label { get; }
    public string Description { get; }
    public bool Available { get; }
    public string? Reason { get; }
    public string Detail => Available ? Description : Reason ?? Description;

    [ObservableProperty] public partial bool IsSelected { get; set; }
}

/// <summary>
/// "Share or print" (design/reviews/usability-review.md P1-5): it starts with the player's own part
/// as a PDF, the thing most players want. Scope and formats are chosen with labelled toggles; the
/// primary action prints the PDF, and "Save" writes every chosen file (to a folder when there are
/// several). Uncertain notes keep their "?" marks in every file.
/// </summary>
public sealed partial class ExportViewModel(ExportService exports, IFileDialogs dialogs, IAnnouncer announcer, IStrings s, IPrinter? printer = null)
    : ObservableObject
{
    private ExportSources? _sources;
    private TalkingScoreSettings _settings = new();
    private int _myPart;
    private int _partCount;

    public ObservableCollection<ExportChoice> Formats { get; } = [];
    public ObservableCollection<ScorePartItem> Parts { get; } = [];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Summary), nameof(SaveLabel), nameof(FileCount))]
    [NotifyCanExecuteChangedFor(nameof(SaveCommand), nameof(PrintCommand))]
    public partial ExportScope Scope { get; set; } = ExportScope.MyPart;

    /// <summary>"Euphonium (you)": the player's part, not the part that happens to be shown.</summary>
    [ObservableProperty] public partial string MyPartLabel { get; set; } = "";

    /// <summary>A part is the player's; with "I conduct or listen" there is none, and Every part is the default.</summary>
    [ObservableProperty] public partial bool HasMyPart { get; set; }
    [ObservableProperty] public partial string? StatusText { get; set; }

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SaveCommand), nameof(PrintCommand))]
    public partial bool IsExporting { get; set; }

    public int FileCount => Formats.Where(f => f.IsSelected && f.Available).Sum(f => FilesFor(f.Key));
    public string SaveLabel => FileCount <= 1 ? s["Export_SaveOne"] : s.Format("Export_SaveMany", FileCount);
    public string Summary => s.Format(FileCount == 1 ? "Export_SummaryOne" : "Export_SummaryMany", FileCount);
    public bool CanPrintNow => printer is { CanPrint: true } && Formats.Any(f => f.Key == "Pdf" && f.Available);

    /// <summary>"Conductor's score" for a band; a quartet has no conductor: "Score (all 4 parts)".</summary>
    [ObservableProperty] public partial string ConductorLabel { get; set; } = "";

    /// <remarks><paramref name="lineup"/> is the lineup the score was arranged for, null when not known.</remarks>
    public void Prepare(ScoreViewModel score, AlphaTabScorePlayer? player, IEngineClient? engine, string? jobId, IReadOnlyCollection<string>? outputs,
        Lineup? lineup = null)
    {
        _sources = new ExportSources(score.MusicXml, score.Document, player, engine, jobId, outputs);
        _settings = new TalkingScoreSettings(score.Language, score.ConcertPitch ? PitchMode.Concert : PitchMode.Written);
        Parts.Clear();
        foreach (var p in score.Parts) Parts.Add(p);
        _partCount = Parts.Count;
        _myPart = score.MyPartIndex;
        HasMyPart = _myPart >= 0 && _myPart < Parts.Count;
        ConductorLabel = lineup switch
        {
            Lineup.Quartet => s["Export_Scope_QuartetScore"],
            Lineup.FullBand or Lineup.MinimalBand or null => s["Export_Scope_Conductor"],
            _ => throw new ArgumentOutOfRangeException(nameof(lineup), lineup, null),
        };
        // The part names are already in the score's language ("1. kornett (deg)").
        MyPartLabel = HasMyPart ? s.Format("Export_Scope_MyPart", Parts[_myPart].Name) : "";

        var options = exports.Options(_sources).ToDictionary(o => o.Format);
        Formats.Clear();
        void Add(string key, params ExportFormat[] formats)
        {
            var available = formats.Select(f => options[f]).FirstOrDefault(o => o.Available);
            var any = options[formats[0]];
            var choice = new ExportChoice(key, s[$"Export_{key}"], s[$"Export_{key}_For"], available is not null,
                available is null && any.UnavailableReasonKey is { } r ? s[r] : null);
            choice.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName != nameof(ExportChoice.IsSelected)) return;
                OnPropertyChanged(nameof(FileCount));
                OnPropertyChanged(nameof(SaveLabel));
                OnPropertyChanged(nameof(Summary));
                SaveCommand.NotifyCanExecuteChanged();
            };
            Formats.Add(choice);
        }
        Add("Pdf", ExportFormat.Pdf, ExportFormat.PdfPart);
        Add("MusicXml", ExportFormat.MusicXmlScore, ExportFormat.MusicXmlPart);
        Add("Audio", ExportFormat.Audio);
        Add("Midi", ExportFormat.Midi);
        Add("TalkingScore", ExportFormat.TalkingScoreHtml);
        Add("Braille", ExportFormat.Braille);
        // Your own part as a PDF, or as MusicXML when no PDF can be made here.
        var first = Formats.FirstOrDefault(f => f.Key == "Pdf" && f.Available) ?? Formats.FirstOrDefault(f => f.Key == "MusicXml" && f.Available);
        if (first is not null) first.IsSelected = true;
        Scope = HasMyPart ? ExportScope.MyPart : ExportScope.EveryPart;
        StatusText = null;
        OnPropertyChanged(nameof(CanPrintNow));
        OnPropertyChanged(nameof(FileCount));
        OnPropertyChanged(nameof(SaveLabel));
        OnPropertyChanged(nameof(Summary));
    }

    /// <summary>The files a format makes for the scope (audio and MIDI are always one file).</summary>
    private int FilesFor(string key) => key is "Audio" or "Midi" ? 1 : Scope == ExportScope.EveryPart ? Math.Max(1, _partCount) : 1;

    /// <summary>What to write: format, part (null = whole score) and file name.</summary>
    internal IReadOnlyList<(ExportFormat Format, int? Part, string FileName)> Plan()
    {
        if (_sources is null) return [];
        var options = exports.Options(_sources).ToDictionary(o => o.Format);
        string title = Sanitize(_sources.TalkingScore?.Title ?? "score");
        var parts = Scope switch
        {
            ExportScope.EveryPart => Enumerable.Range(0, _partCount).Select(i => (int?)i).ToList(),
            ExportScope.MyPart when HasMyPart => [_myPart],
            _ => new List<int?> { null },
        };
        var plan = new List<(ExportFormat, int?, string)>();
        foreach (var f in Formats.Where(f => f.IsSelected && f.Available))
        {
            switch (f.Key)
            {
                case "Audio": plan.Add((ExportFormat.Audio, null, $"{title}.mp3")); break;
                case "Midi": plan.Add((ExportFormat.Midi, null, $"{title}.mid")); break;
                default:
                    foreach (var part in parts)
                    {
                        var format = (f.Key, part) switch
                        {
                            ("Pdf", null) => ExportFormat.Pdf,
                            ("Pdf", _) when options[ExportFormat.PdfPart].Available => ExportFormat.PdfPart,
                            ("Pdf", _) => ExportFormat.Pdf,
                            ("MusicXml", null) => ExportFormat.MusicXmlScore,
                            ("MusicXml", _) => ExportFormat.MusicXmlPart,
                            ("TalkingScore", _) => ExportFormat.TalkingScoreHtml,
                            _ => ExportFormat.Braille,
                        };
                        string name = part is { } i && i < Parts.Count ? $"{title} - {Sanitize(Parts[i].Name)}" : title;
                        plan.Add((format, part, name + options[format].Extension));
                    }
                    break;
            }
        }
        return plan;
    }

    private bool CanSave() => FileCount > 0 && !IsExporting;

    [RelayCommand(CanExecute = nameof(CanSave))]
    private async Task SaveAsync()
    {
        if (_sources is null) return;
        var plan = Plan();
        if (plan.Count == 0) return;
        IsExporting = true;
        try
        {
            if (plan.Count == 1)
            {
                var (format, part, fileName) = plan[0];
                var option = exports.Options(_sources).Single(o => o.Format == format);
                var target = await dialogs.PickSaveAsync(fileName, option.Extension, s[$"Export_{KeyOf(format)}"]);
                if (target is null) return;
                await using (target.Stream)
                    await exports.ExportAsync(format, _sources, target.Stream, part, _settings);
                Done(s.Format("Export_Done", target.DisplayName));
                return;
            }
            var folder = await dialogs.PickFolderAsync();
            if (folder is null) return;
            foreach (var (format, part, fileName) in plan)
            {
                await using var stream = File.Create(Path.Combine(folder, fileName));
                await exports.ExportAsync(format, _sources, stream, part, _settings);
            }
            Done(s.Format("Export_DoneMany", plan.Count, folder));
        }
        catch (Exception e) when (e is IOException or EngineException or InvalidOperationException or UnauthorizedAccessException)
        {
            Done(s.Format("Export_Failed", Reason(e)));
        }
        finally
        {
            IsExporting = false;
        }
    }

    /// <summary>Why an export failed, in the player's words where the app has them.</summary>
    private string Reason(Exception e) => e switch
    {
        EngineException ee => EngineErrors.Message(ee, s),
        InvalidOperationException { Message: var key } when key.StartsWith("Export_Reason_", StringComparison.Ordinal) => s[key],
        _ => e.Message,
    };

    private bool CanPrint() => CanPrintNow && !IsExporting;

    /// <summary>Prints the PDF of the chosen scope (every part: each part's PDF).</summary>
    [RelayCommand(CanExecute = nameof(CanPrint))]
    private async Task PrintAsync()
    {
        if (_sources is null || printer is null) return;
        IsExporting = true;
        try
        {
            var pdf = Formats.First(f => f.Key == "Pdf");
            bool wasSelected = pdf.IsSelected;
            var only = Formats.Where(f => f.IsSelected).ToList();
            foreach (var f in only) f.IsSelected = false;
            pdf.IsSelected = true;
            var plan = Plan();
            foreach (var f in only) f.IsSelected = true;
            pdf.IsSelected = wasSelected;

            string dir = Path.Combine(Path.GetTempPath(), "Brasscribe", "print");
            Directory.CreateDirectory(dir);
            foreach (var (format, part, fileName) in plan)
            {
                string path = Path.Combine(dir, fileName);
                await using (var stream = File.Create(path))
                    await exports.ExportAsync(format, _sources, stream, part, _settings);
                await printer.PrintAsync(path);
            }
            Done(s["Export_Printing"]);
        }
        catch (Exception e) when (e is IOException or EngineException or InvalidOperationException or UnauthorizedAccessException)
        {
            Done(s.Format("Export_Failed", Reason(e)));
        }
        finally
        {
            IsExporting = false;
        }
    }

    private void Done(string text)
    {
        StatusText = text;
        announcer.Announce(text, AnnouncementKind.Important);
    }

    private static string KeyOf(ExportFormat f) => f switch
    {
        ExportFormat.Pdf or ExportFormat.PdfPart => "Pdf",
        ExportFormat.MusicXmlScore or ExportFormat.MusicXmlPart => "MusicXml",
        ExportFormat.Audio => "Audio",
        ExportFormat.Midi => "Midi",
        ExportFormat.Braille => "Braille",
        _ => "TalkingScore",
    };

    private static string Sanitize(string name)
    {
        var bad = Path.GetInvalidFileNameChars().Concat(['\\', '/', ':', '*', '?', '"', '<', '>', '|']).ToHashSet();
        return new string(name.Select(c => bad.Contains(c) ? '-' : c).ToArray()).Trim();
    }
}

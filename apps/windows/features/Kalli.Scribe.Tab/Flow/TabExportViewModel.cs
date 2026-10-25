using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tab;

/// <summary>What a tab can be saved as.</summary>
public enum TabExportFormat { Pdf, MusicXml, Midi, TextTab, Instructions }

/// <summary>One way to save the tab: its words, and whether it can be had now (and why not).</summary>
public sealed partial class TabExportOption(TabExportFormat format, string label, string description, string extension) : ObservableObject
{
    public TabExportFormat Format { get; } = format;
    public string Label { get; } = label;
    public string Description { get; } = description;
    public string Extension { get; } = extension;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HelpText))]
    public partial bool IsAvailable { get; set; }

    /// <summary>Why it can't be had now; null when it can.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HelpText))]
    public partial string? Reason { get; set; }

    /// <summary>The line under the label: what it is for, or why it can't be had.</summary>
    public string HelpText => Reason ?? Description;

    /// <summary>The Save button's name for a screen reader: "Save PDF".</summary>
    public string SaveName { get; init; } = label;
}

/// <summary>
/// "Share or print" for a tab: the PDF to print or keep, the MusicXML (strings and frets kept, for Guitar Pro, MuseScore
/// and the like), MIDI, the tab as text, and the playing instructions in words (for a screen reader or a braille
/// display). The MusicXML is the copy on this PC; the others come from the computer that wrote the tab.
/// </summary>
public sealed partial class TabExportViewModel : ObservableObject
{
    private readonly IFileDialogs _dialogs;
    private readonly IPrinter? _printer;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private string _title = "";
    private string _musicXml = "";
    private string? _job;
    private IEngineClient? _engine;

    public TabExportViewModel(IFileDialogs dialogs, IPrinter? printer, IAnnouncer announcer, IStrings strings)
    {
        _dialogs = dialogs;
        _printer = printer;
        _announcer = announcer;
        _s = strings;
        foreach (var (format, ext) in new[] { (TabExportFormat.Pdf, ".pdf"), (TabExportFormat.MusicXml, ".musicxml"), (TabExportFormat.Midi, ".mid"),
                     (TabExportFormat.TextTab, ".txt"), (TabExportFormat.Instructions, ".txt") })
            Options.Add(new TabExportOption(format, strings[$"Tab_Export_{format}"], strings[$"Tab_Export_{format}_For"], ext)
            {
                SaveName = strings.Format("Tab_Export_Save", strings[$"Tab_Export_{format}"]),
            });
    }

    public ObservableCollection<TabExportOption> Options { get; } = [];

    /// <summary>What was saved or printed, or what went wrong, in words.</summary>
    [ObservableProperty] public partial string? StatusText { get; set; }

    /// <summary>A PDF can be printed: it comes from the computer, and Windows has a way to print it.</summary>
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(PrintCommand))]
    public partial bool CanPrint { get; set; }

    /// <summary>The playing instructions in the app's language, as the computer names them.</summary>
    private string InstructionsName => $"tab-instructions.{(_s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) ? "nb" : "en")}.txt";

    /// <summary>
    /// The tab on screen: its title, its MusicXML, its job on the computer and what the job wrote (<paramref name="outputs"/>,
    /// null when not known), and the computer's client when it is connected.
    /// </summary>
    public void Prepare(string title, string musicXml, string? job, IReadOnlyCollection<string>? outputs, IEngineClient? engine)
    {
        _title = title;
        _musicXml = musicXml;
        _job = job;
        _engine = job is null ? null : engine;
        StatusText = null;
        bool there = _engine is not null;
        bool Has(string name) => outputs is null || outputs.Contains(name, StringComparer.OrdinalIgnoreCase);
        foreach (var o in Options)
        {
            (o.IsAvailable, o.Reason) = o.Format switch
            {
                TabExportFormat.MusicXml => (true, null),
                _ when job is null => (false, _s["Tab_Export_NotFromComputer"]),
                _ when !there => (false, _s["Tab_Export_NeedsComputer"]),
                TabExportFormat.Pdf when !Has("tab.pdf") => (false, _s["Tab_Export_NotMade"]),
                TabExportFormat.Midi when !Has("tab.mid") => (false, _s["Tab_Export_NotMade"]),
                TabExportFormat.TextTab when !Has("tab.txt") => (false, _s["Tab_Export_NotMade"]),
                TabExportFormat.Instructions when !Has(InstructionsName) => (false, _s["Tab_Export_NotMade"]),
                _ => (true, (string?)null),
            };
        }
        CanPrint = _printer?.CanPrint == true && Options.Single(o => o.Format == TabExportFormat.Pdf).IsAvailable;
    }

    [RelayCommand]
    private async Task SaveAsync(TabExportOption? option)
    {
        if (option is not { IsAvailable: true }) return;
        StatusText = null;
        string name = Safe(_title) + (option.Format == TabExportFormat.Instructions ? " " + _s["Tab_Export_InstructionsSuffix"] : "") + option.Extension;
        SaveTarget? target;
        try { target = await _dialogs.PickSaveAsync(name, option.Extension, option.Label); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            Say(_s.Format("Tab_Export_Failed", option.Label));
            return;
        }
        if (target is null) return;
        try
        {
            await using (target.Stream)
            {
                if (option.Format == TabExportFormat.MusicXml)
                {
                    await using var writer = new StreamWriter(target.Stream, leaveOpen: true);
                    await writer.WriteAsync(_musicXml);
                }
                else
                {
                    await using var from = await OpenAsync(option.Format);
                    await from.CopyToAsync(target.Stream);
                }
            }
            Say(_s.Format("Tab_Export_Saved", target.DisplayName), AnnouncementKind.Important);
        }
        catch (EngineException e)
        {
            Say(_s.Format("Tab_Export_Failed", option.Label) + " " + EngineErrors.Message(e, _s));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or HttpRequestException or TaskCanceledException)
        {
            Say(_s.Format("Tab_Export_Failed", option.Label));
        }
    }

    [RelayCommand(CanExecute = nameof(CanPrint))]
    private async Task PrintAsync()
    {
        if (_printer is null) return;
        StatusText = null;
        try
        {
            string dir = Path.Combine(Path.GetTempPath(), "scribe-print");
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, Safe(_title) + ".pdf");
            await using (var from = await OpenAsync(TabExportFormat.Pdf))
            await using (var to = File.Create(path))
                await from.CopyToAsync(to);
            await _printer.PrintAsync(path);
        }
        catch (EngineException e)
        {
            Say(_s["Tab_Export_PrintFailed"] + " " + EngineErrors.Message(e, _s));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or HttpRequestException or TaskCanceledException)
        {
            Say(_s["Tab_Export_PrintFailed"]);
        }
    }

    private Task<Stream> OpenAsync(TabExportFormat format)
    {
        if (_engine is not { } engine || _job is not { } job) throw new IOException("no computer to get it from");
        return format switch
        {
            TabExportFormat.Pdf => engine.DownloadAsync(job, JobDownload.Pdf),
            TabExportFormat.Midi => engine.DownloadAsync(job, JobDownload.Midi),
            TabExportFormat.TextTab => engine.GetArtifactAsync(job, "tab.txt"),
            TabExportFormat.Instructions => engine.GetArtifactAsync(job, InstructionsName),
            _ => throw new ArgumentOutOfRangeException(nameof(format)),
        };
    }

    private void Say(string text, AnnouncementKind kind = AnnouncementKind.Important)
    {
        StatusText = text;
        _announcer.Announce(text, kind);
    }

    /// <summary>A file name from the title: what Windows refuses in a name is left out.</summary>
    private string Safe(string title)
    {
        var bad = Path.GetInvalidFileNameChars().Concat(['<', '>', ':', '"', '/', '\\', '|', '?', '*']).ToHashSet();
        string name = new string(title.Where(c => !bad.Contains(c)).ToArray()).Trim();
        return name.Length > 0 ? name : _s["Tab_Song"];
    }
}

using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public sealed record ExportChoice(ExportFormat Format, string Label, bool Available, string? Reason, bool NeedsPart);

/// <summary>Export dialog: pick a format (and a part where it applies), then a save location.</summary>
public sealed partial class ExportViewModel(ExportService exports, IFileDialogs dialogs, IAnnouncer announcer, IStrings s) : ObservableObject
{
    private ExportSources? _sources;
    private TalkingScoreSettings _settings = new();

    public ObservableCollection<ExportChoice> Formats { get; } = [];
    public ObservableCollection<ScorePartItem> Parts { get; } = [];

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ExportCommand))]
    public partial ExportChoice? SelectedFormat { get; set; }

    [ObservableProperty] public partial ScorePartItem? SelectedPart { get; set; }
    [ObservableProperty] public partial string? StatusText { get; set; }
    [ObservableProperty] public partial bool IsExporting { get; set; }

    public void Prepare(ScoreViewModel score, AlphaTabScorePlayer? player, IEngineClient? engine, string? jobId, IReadOnlyCollection<string>? outputs)
    {
        _sources = new ExportSources(score.MusicXml, score.Document, player, engine, jobId, outputs);
        _settings = new TalkingScoreSettings(score.Language, score.ConcertPitch ? PitchMode.Concert : PitchMode.Written);
        Formats.Clear();
        foreach (var o in exports.Options(_sources))
        {
            bool needsPart = o.Format is ExportFormat.MusicXmlPart or ExportFormat.Braille;
            Formats.Add(new ExportChoice(o.Format, s[$"Export_Format_{o.Format}"], o.Available,
                o.UnavailableReasonKey is null ? null : s[o.UnavailableReasonKey], needsPart));
        }
        Parts.Clear();
        foreach (var p in score.Parts) Parts.Add(p);
        SelectedPart = score.SelectedPartIndex >= 0 && score.SelectedPartIndex < Parts.Count ? Parts[score.SelectedPartIndex] : Parts.FirstOrDefault();
        SelectedFormat = Formats.FirstOrDefault(f => f.Available);
        StatusText = null;
    }

    private bool CanExport() => SelectedFormat is { Available: true } && !IsExporting;

    [RelayCommand(CanExecute = nameof(CanExport))]
    private async Task ExportAsync()
    {
        if (_sources is null || SelectedFormat is null) return;
        var option = exports.Options(_sources).Single(o => o.Format == SelectedFormat.Format);
        string partName = SelectedPart?.Name ?? "";
        string baseName = Sanitize(_sources.TalkingScore?.Title ?? "score");
        if (SelectedFormat.NeedsPart && partName.Length > 0) baseName += " - " + Sanitize(partName);

        var target = await dialogs.PickSaveAsync(baseName + option.Extension, option.Extension, SelectedFormat.Label);
        if (target is null) return;
        IsExporting = true;
        try
        {
            await using (target.Stream)
                await exports.ExportAsync(SelectedFormat.Format, _sources, target.Stream,
                    SelectedFormat.NeedsPart || SelectedFormat.Format is ExportFormat.TalkingScoreHtml or ExportFormat.TalkingScoreText
                        ? SelectedPart?.Index : null,
                    _settings);
            StatusText = s.Format("Export_Done", SelectedFormat.Label, target.DisplayName);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
        catch (Exception e) when (e is IOException or EngineException or InvalidOperationException or UnauthorizedAccessException)
        {
            StatusText = s.Format("Export_Failed", e.Message);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
        finally
        {
            IsExporting = false;
            ExportCommand.NotifyCanExecuteChanged();
        }
    }

    private static string Sanitize(string name)
    {
        var bad = Path.GetInvalidFileNameChars().Concat(['\\', '/', ':', '*', '?', '"', '<', '>', '|']).ToHashSet();
        return new string(name.Select(c => bad.Contains(c) ? '-' : c).ToArray()).Trim();
    }
}

using System.Text;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Export;

public enum ExportFormat
{
    MusicXmlScore,
    MusicXmlPart,
    Pdf,
    /// <summary>One part's PDF, from the engine job's parts/NN-Name.pdf.</summary>
    PdfPart,
    Midi,
    Audio,
    TalkingScoreHtml,
    TalkingScoreText,
    Braille,
}

public sealed record ExportOption(ExportFormat Format, string Extension, string MediaType, bool Available, string? UnavailableReasonKey);

/// <summary>Everything an export can draw on; any source may be missing (offline, no engine job).</summary>
public sealed record ExportSources(
    string? MusicXml,
    TalkingScoreDocument? TalkingScore,
    AlphaTabScorePlayer? Player,
    IEngineClient? Engine,
    string? JobId,
    IReadOnlyCollection<string>? JobOutputs);

/// <summary>
/// Decides which export formats are possible now and writes them. Score, parts and MIDI work
/// offline; PDF, audio and braille (BRF, score or one part) come from the engine job.
/// </summary>
public sealed class ExportService
{
    public const string ReasonNeedsEngine = "Export_Reason_NeedsEngine";
    public const string ReasonNoScore = "Export_Reason_NoScore";

    public IReadOnlyList<ExportOption> Options(ExportSources s)
    {
        bool score = s.MusicXml is not null;
        bool job = s.Engine is not null && s.JobId is not null;
        bool brf = job; // the engine writes braille (BRF) for the score or a part on request
        return
        [
            new(ExportFormat.MusicXmlScore, ".musicxml", "application/vnd.recordare.musicxml+xml", score, score ? null : ReasonNoScore),
            new(ExportFormat.MusicXmlPart, ".musicxml", "application/vnd.recordare.musicxml+xml", score, score ? null : ReasonNoScore),
            new(ExportFormat.Pdf, ".pdf", "application/pdf", job, job ? null : ReasonNeedsEngine),
            new(ExportFormat.PdfPart, ".pdf", "application/pdf", job && PartPdfs(s).Count > 0, job ? null : ReasonNeedsEngine),
            new(ExportFormat.Midi, ".mid", "audio/midi", score && s.Player is not null || job, score || job ? null : ReasonNoScore),
            new(ExportFormat.Audio, ".mp3", "audio/mpeg", job, job ? null : ReasonNeedsEngine),
            new(ExportFormat.TalkingScoreHtml, ".html", "text/html", s.TalkingScore is not null, s.TalkingScore is not null ? null : ReasonNoScore),
            new(ExportFormat.TalkingScoreText, ".txt", "text/plain", s.TalkingScore is not null, s.TalkingScore is not null ? null : ReasonNoScore),
            new(ExportFormat.Braille, ".brf", "text/plain", brf, brf ? null : ReasonNeedsEngine),
        ];
    }

    /// <summary>Writes one export to <paramref name="destination"/>. partIndex selects the part where it applies.</summary>
    public async Task ExportAsync(ExportFormat format, ExportSources s, Stream destination, int? partIndex,
        TalkingScoreSettings settings, CancellationToken ct = default)
    {
        var option = Options(s).Single(o => o.Format == format);
        if (!option.Available) throw new InvalidOperationException(option.UnavailableReasonKey);

        switch (format)
        {
            case ExportFormat.MusicXmlScore:
                await WriteText(destination, s.MusicXml!, ct);
                break;
            case ExportFormat.MusicXmlPart:
            {
                var parts = MusicXmlParts.List(s.MusicXml!);
                int i = Math.Clamp(partIndex ?? 0, 0, parts.Count - 1);
                await WriteText(destination, MusicXmlParts.Extract(s.MusicXml!, parts[i].Id), ct);
                break;
            }
            case ExportFormat.Midi when s.Player is not null:
                await destination.WriteAsync(s.Player.ExportMidi(), ct);
                break;
            case ExportFormat.Midi:
                await CopyFromEngine(s, JobDownload.Midi, destination, ct);
                break;
            case ExportFormat.Pdf:
                await CopyFromEngine(s, JobDownload.Pdf, destination, ct);
                break;
            case ExportFormat.PdfPart:
            {
                var pdfs = PartPdfs(s);
                string name = pdfs[Math.Clamp(partIndex ?? 0, 0, pdfs.Count - 1)];
                await using var src = await s.Engine!.GetArtifactAsync(s.JobId!, name, ct);
                await src.CopyToAsync(destination, ct);
                break;
            }
            case ExportFormat.Audio:
                await CopyFromEngine(s, JobDownload.Audio, destination, ct);
                break;
            case ExportFormat.TalkingScoreHtml:
                await WriteText(destination, TalkingScoreExport.ToHtml(s.TalkingScore!, settings, partIndex is { } p ? [p] : null), ct);
                break;
            case ExportFormat.TalkingScoreText:
                await WriteText(destination, TalkingScoreExport.ToText(s.TalkingScore!, settings, partIndex is { } q ? [q] : null), ct);
                break;
            case ExportFormat.Braille:
            {
                // The engine numbers parts from 1 in score order; no part means the whole score.
                string? part = partIndex is { } i ? (i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture) : null;
                await using var src = await s.Engine!.DownloadBrailleAsync(s.JobId!, part, ct);
                await src.CopyToAsync(destination, ct);
                break;
            }
        }
    }

    /// <summary>The job's part PDFs in score order (the engine names them parts/01-Soprano-Cornet.pdf, …).</summary>
    public static IReadOnlyList<string> PartPdfs(ExportSources s) =>
        (s.JobOutputs ?? []).Where(o => o.StartsWith("parts/", StringComparison.Ordinal) && o.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
            .Order(StringComparer.Ordinal).ToList();

    private static async Task CopyFromEngine(ExportSources s, JobDownload what, Stream destination, CancellationToken ct)
    {
        await using var src = await s.Engine!.DownloadAsync(s.JobId!, what, ct);
        await src.CopyToAsync(destination, ct);
    }

    private static Task WriteText(Stream destination, string text, CancellationToken ct) =>
        destination.WriteAsync(Encoding.UTF8.GetBytes(text), ct).AsTask();
}

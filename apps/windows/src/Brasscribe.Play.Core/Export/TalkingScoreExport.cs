using System.Net;
using System.Text;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Export;

/// <summary>
/// The talking-score text export (spec §6): a heading per part, a sub-heading per bar and one line
/// per event in standard verbosity. HTML uses h1/h2/h3/ul so screen readers can jump by heading;
/// plain text is the fallback.
/// </summary>
public static class TalkingScoreExport
{
    public static string ToHtml(TalkingScoreDocument doc, TalkingScoreSettings settings, IEnumerable<int>? partIndexes = null)
    {
        var sb = new StringBuilder();
        string lang = settings.Nb ? "nb" : "en";
        sb.Append("<!DOCTYPE html>\n<html lang=\"").Append(lang).Append("\">\n<head><meta charset=\"utf-8\"><title>")
          .Append(WebUtility.HtmlEncode(doc.Title)).Append("</title></head>\n<body>\n<h1>")
          .Append(WebUtility.HtmlEncode(doc.Title)).Append("</h1>\n");
        foreach (var (part, bars) in Walk(doc, settings, partIndexes))
        {
            sb.Append("<h2>").Append(WebUtility.HtmlEncode(part)).Append("</h2>\n");
            foreach (var (heading, lines) in bars)
            {
                sb.Append("<h3>").Append(WebUtility.HtmlEncode(heading)).Append("</h3>\n<ul>\n");
                foreach (var l in lines) sb.Append("<li>").Append(WebUtility.HtmlEncode(l)).Append("</li>\n");
                sb.Append("</ul>\n");
            }
        }
        sb.Append("</body>\n</html>\n");
        return sb.ToString();
    }

    public static string ToText(TalkingScoreDocument doc, TalkingScoreSettings settings, IEnumerable<int>? partIndexes = null)
    {
        var sb = new StringBuilder();
        sb.Append(doc.Title).Append("\n\n");
        foreach (var (part, bars) in Walk(doc, settings, partIndexes))
        {
            sb.Append(part).Append('\n').Append(new string('=', part.Length)).Append("\n\n");
            foreach (var (heading, lines) in bars)
            {
                sb.Append(heading).Append('\n');
                foreach (var l in lines) sb.Append("  ").Append(l).Append('\n');
                sb.Append('\n');
            }
        }
        return sb.ToString();
    }

    private static IEnumerable<(string Part, List<(string Heading, List<string> Lines)> Bars)> Walk(
        TalkingScoreDocument doc, TalkingScoreSettings settings, IEnumerable<int>? partIndexes)
    {
        var indexes = partIndexes?.ToList() ?? Enumerable.Range(0, doc.Parts.Count).ToList();
        foreach (int p in indexes)
        {
            var nav = new ScoreNavigator(doc, settings);
            nav.GoToPart(p);
            nav.FirstBar();
            var part = doc.Parts[p];
            var bars = new List<(string, List<string>)>();
            string name = settings.Nb ? part.NameNb ?? part.Name : part.Name;
            int lastBar = -1;
            List<string>? current = null;
            string text = nav.Text;
            while (true)
            {
                if (nav.BarIndex != lastBar)
                {
                    lastBar = nav.BarIndex;
                    current = [];
                    var ev = nav.Event;
                    string heading = ev is { Kind: EventKind.BarRest, Bars: > 1 }
                        ? (settings.Nb ? $"Takt {part.Bars[lastBar].Number}–{part.Bars[lastBar].Number + ev.Bars - 1}" : $"Bars {part.Bars[lastBar].Number}–{part.Bars[lastBar].Number + ev.Bars - 1}")
                        : (settings.Nb ? $"Takt {part.Bars[lastBar].Number}" : $"Bar {part.Bars[lastBar].Number}");
                    bars.Add((heading, current));
                }
                current!.Add(text);
                var r = nav.NextNote();
                if (!r.Moved) break;
                text = r.Text;
            }
            yield return (name, bars);
        }
    }
}

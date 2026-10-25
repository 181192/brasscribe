using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Review;

/// <summary>
/// Puts the Composition's review groups on the printed notes: every note of a group gets its index,
/// the first note of the group in each part is the lead (one "?" and one review item stand for the
/// group), and notes outside every group are not marked. Without groups nothing changes and each
/// note is judged on its own confidence.
/// </summary>
public static class ReviewGroups
{
    public static void Attach(TalkingScoreDocument doc, Composition? composition)
    {
        if (composition?.Review is not { Count: > 0 } spans) return;
        // A group the musician kept (all its notes at confidence 1) is no longer marked.
        var open = spans.Select(sp => NotesOf(composition, sp).Any(n => n.Confidence < 1.0)).ToList();
        // Only the parts the arranger marked play the reviewed voices; other parts that happen to share a
        // pitch at the same time (doublings, harmony) are not reviewed for them.
        bool anyPrinted = doc.Parts.Any(p => p.Bars.Any(b => b.Events.Any(e => e.PrintedMark)));
        foreach (var part in doc.Parts)
        {
            bool marked = !anyPrinted || part.Bars.Any(b => b.Events.Any(e => e.PrintedMark));
            var leads = new Dictionary<int, TsEvent>();
            for (int b = 0; b < part.Bars.Count; b++)
                foreach (var ev in part.Bars[b].Events)
                {
                    ev.ReviewGroup = TsEvent.NotInReviewGroup;
                    ev.ReviewLead = false;
                    if (!marked || ev.CompositionVoiceId is not { } voice || ev.CompositionNoteStart is not { } start) continue;
                    int g = spans.FindIndex(sp => sp.Voice == voice && start >= sp.Start && start < sp.End);
                    if (g < 0 || !open[g]) continue;
                    ev.ReviewGroup = g;
                    ev.ReviewVery = spans[g].Very;
                    if (ev.Tie is { Stop: true }) continue;
                    if (!leads.TryGetValue(g, out var lead))
                    {
                        ev.ReviewLead = true;
                        ev.ReviewNotes = Math.Max(1, spans[g].Notes);
                        ev.ReviewEndBar = b;
                        leads[g] = ev;
                    }
                    else lead.ReviewEndBar = b;
                }
        }
    }

    /// <summary>The Composition notes a group covers.</summary>
    public static IEnumerable<Note> NotesOf(Composition composition, ReviewSpan span) =>
        composition.Voices.Where(v => v.Id == span.Voice).SelectMany(v => v.Notes).Where(n => n.Start >= span.Start && n.Start < span.End);

    /// <summary>The printed notes of one group in a part, in order.</summary>
    public static IEnumerable<(int Bar, TsEvent Event)> Members(TsPart part, int group)
    {
        for (int b = 0; b < part.Bars.Count; b++)
            foreach (var ev in part.Bars[b].Events)
                if (ev.ReviewGroup == group) yield return (b, ev);
    }
}

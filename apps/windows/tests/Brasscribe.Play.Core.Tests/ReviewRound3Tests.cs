using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The third usability review: score titles that are never a bare timestamp, review by
/// Composition.review groups (one item and one "?" per group, Keep keeps the group), very unsure
/// first, "Keep the rest of this bar", the "most are probably right" lead, and the selected note as a
/// tint column with a caret instead of a box.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class ReviewRound3Tests(ITestOutputHelper log)
{
    private sealed class Quiet : IAnnouncer { public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) { } }
    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    private static IStrings Strings() => new ReswStrings(ReswStrings.Parse(System.Xml.Linq.XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));

    [Theory]
    [InlineData("20260815_155324", "Recording, 15 Aug 15:53")]
    [InlineData("2026-08-15 15.53.24.m4a", "Recording, 15 Aug 15:53")]
    [InlineData("REC_20260815-1553", "Recording, 15 Aug 15:53")]
    [InlineData("Old Hundredth.musicxml", "Old Hundredth")]
    [InlineData("  Abide with Me  ", "Abide with Me")]
    [InlineData("Band 2026", "Band 2026")]
    public void Titles_are_never_a_bare_timestamp(string stored, string shown) =>
        Assert.Equal(shown, ScoreTitles.Display(stored, new DateTimeOffset(2026, 9, 26, 19, 2, 0, TimeSpan.Zero), Strings()));

    [Fact]
    public void A_microphone_capture_is_named_by_its_time()
    {
        var s = Strings();
        var when = new DateTimeOffset(2026, 9, 26, 19, 2, 0, TimeZoneInfo.Local.GetUtcOffset(new DateTime(2026, 9, 26)));
        Assert.Equal("Recording, 26 Sep 19:02", ScoreTitles.Display("", when, s));
        Assert.Equal("Recording, 26 Sep 19:02", ScoreTitles.Display("Recording", when, s));
        Assert.Contains("Old Hundredth", ScoreTitles.Duplicates(["Old Hundredth", "old hundredth", "Other"]));
    }

    [Fact]
    public void Selection_is_a_tint_column_and_a_caret_not_a_box()
    {
        var items = ScoreOverlay.Selection(new Box(100, 60, 10, 8), new Box(80, 40, 200, 40));
        var tint = Assert.Single(items, i => i.Kind == OverlayKind.SelectionTint);
        var caret = Assert.Single(items, i => i.Kind == OverlayKind.SelectionCaret);
        Assert.True(tint.Box.Y <= 40 && tint.Box.Y + tint.Box.H >= 80); // over the staff's height
        Assert.True(caret.Box.Y > 80); // under the staff
        Assert.DoesNotContain(items, i => i.Kind == OverlayKind.Outline);
    }

    private static (ScoreViewModel Score, ReviewViewModel Review, Composition Composition)? Golden(ICoreBridge core)
    {
        var xmlPath = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        if (xmlPath is null || json is null) return null;
        var composition = CompositionJson.Parse(File.ReadAllText(json));
        if (composition.Review is not { Count: > 0 }) return null;
        var strings = Strings();
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var score = new ScoreViewModel(core, new PlayerViewModel(player, new Quiet(), strings, new Inline()), new Quiet(), strings);
        score.Load(File.ReadAllText(xmlPath), composition);
        return (score, new ReviewViewModel(score, new Quiet(), strings), composition);
    }

    [Fact]
    public void The_golden_is_reviewed_by_group()
    {
        if (Golden(new ManagedCoreBridge()) is not { } g) return;
        var (score, review, composition) = g;
        review.Load(ReviewScope.AllParts);
        int groups = composition.Review!.Count;
        log.WriteLine($"{groups} review groups; {review.AllItems.Count} review items; {score.UncertainLeft} marks on the score");
        foreach (var p in review.AllItems.GroupBy(i => i.PartName)) log.WriteLine($"  {p.Key}: {p.Count()} ({p.Select(i => i.Event.ReviewGroup).Distinct().Count()} groups)");
        // One item per group in each part that plays the voice (the solo is in Solo Cornet only).
        Assert.InRange(review.AllItems.Count, groups * 9 / 10, groups);
        Assert.Equal(review.AllItems.Count, score.UncertainLeft);
        Assert.True(review.AllItems.Count(i => i.IsVeryUncertain) >= composition.Review.Count(r => r.Very) * 9 / 10);
        // Very unsure first within the part.
        var solo = review.Items.Where(i => i.IsMine).ToList();
        Assert.True(solo.TakeWhile(i => i.IsVeryUncertain).Count() == solo.Count(i => i.IsVeryUncertain));
        // More than 50 places: the lead line. Most of the golden's are very unsure, so it only says where to start.
        int very = review.Items.Count(i => i.IsVeryUncertain);
        Assert.Equal(very * 2 > review.Items.Count ? $"Start with the {very} very unsure ones." : $"Most of these are probably right. Start with the {very} very unsure ones.",
            review.LeadText);

        // A group of several notes is one item; Keep keeps all its notes.
        var group = review.AllItems.First(i => i.IsGroup);
        review.Select(group);
        Assert.StartsWith($"{group.NoteCount} notes together", review.NoteLine);
        var span = composition.Review![group.Event.ReviewGroup];
        review.KeepCommand.Execute(null);
        Assert.All(ReviewGroups.NotesOf(composition, span), n => Assert.Equal(1.0, n.Confidence));
        Assert.All(ReviewGroups.Members(score.Document!.Parts[group.Part], group.Event.ReviewGroup), m => Assert.False(m.Event.IsUncertain));
        int left = score.UncertainLeft;

        // It stays kept when the score is loaded again.
        score.Load(score.MusicXml!, composition);
        Assert.Equal(left, score.UncertainLeft);
    }

    /// <summary>The same with the native core's talking score (the links come from the managed reading).</summary>
    [Fact]
    public void The_golden_is_reviewed_by_group_with_the_native_core()
    {
        if (Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is not { Length: > 0 } || NativeCoreBridge.TryCreate() is not { } native) return;
        if (Golden(native) is not { } g) return;
        g.Review.Load(ReviewScope.AllParts);
        Assert.Equal(g.Composition.Review!.Count, g.Review.AllItems.Count);
    }

    /// <summary>
    /// The tune printed an octave down (the cornet's limit) lands on a pitch the harmony plays at the same time.
    /// The coloured note is the tune's uncertain note, not the harmony's certain one, so its review group keeps it.
    /// </summary>
    [Fact]
    public void A_marked_note_an_octave_down_stays_with_the_uncertain_tune()
    {
        const string xml = """
            <?xml version="1.0" encoding="UTF-8"?>
            <score-partwise version="4.0">
              <part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part></part-list>
              <part id="P1"><measure number="1">
                <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
                <note color="#B45309"><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type></note>
              </measure></part>
            </score-partwise>
            """;
        var composition = CompositionJson.Parse("""
            {"title":"t","ticks_per_beat":12,
             "voices":[
               {"id":"strings","layer":"strings","notes":[{"start":0,"duration":48,"pitch":62,"confidence":1.0}]},
               {"id":"solo","layer":"solo","notes":[{"start":0,"duration":48,"pitch":74,"confidence":0.4}]}],
             "review":[{"voice":"solo","start":0,"end":48,"notes":1}]}
            """);
        var doc = MusicXmlTalkingScoreBuilder.Build(xml, composition);
        ReviewGroups.Attach(doc, composition);
        var ev = doc.Parts[0].Bars[0].Events.Single(e => e.Kind != EventKind.Rest);
        Assert.Equal("solo", ev.CompositionVoiceId);
        Assert.True(ev.ReviewLead);
        Assert.Equal(0, ev.ReviewGroup);

        // An unmarked note keeps the plain rule: the exact pitch.
        var plain = MusicXmlTalkingScoreBuilder.Build(xml.Replace(" color=\"#B45309\"", ""), composition);
        Assert.Equal("strings", plain.Parts[0].Bars[0].Events.Single(e => e.Kind != EventKind.Rest).CompositionVoiceId);
    }

    [Fact]
    public void Keep_the_rest_of_this_bar_keeps_the_other_marks_in_it()
    {
        if (Golden(new ManagedCoreBridge()) is not { } g) return;
        var (score, review, _) = g;
        review.Load(ReviewScope.AllParts);
        var bar = review.AllItems.GroupBy(i => (i.Part, i.BarIndex)).FirstOrDefault(b => b.Count() > 1);
        if (bar is null) return;
        review.Select(bar.First());
        Assert.True(review.CanKeepBar);
        Assert.Equal($"Keep the rest of this bar ({bar.Count()})", review.KeepBarText);
        int before = review.AllItems.Count(i => !i.IsKept);
        review.KeepRestOfBarCommand.Execute(null);
        Assert.All(bar, i => Assert.True(i.IsKept));
        Assert.Equal(before - bar.Count(), review.AllItems.Count(i => !i.IsKept));
    }

    [Fact]
    public void Without_review_groups_each_note_is_judged_on_its_own()
    {
        var ev = new TsEvent { Confidence = 0.5 };
        Assert.True(ev.IsUncertain);
        Assert.False(ev.IsVeryUncertain);
        ev.ReviewGroup = TsEvent.NotInReviewGroup;
        Assert.False(ev.IsUncertain);
        ev.ReviewGroup = 3;
        Assert.False(ev.IsUncertain); // only the group's lead carries the mark
        ev.ReviewLead = true;
        ev.ReviewVery = true;
        Assert.True(ev.IsUncertain && ev.IsVeryUncertain);
    }
}

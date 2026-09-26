using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The second usability review's items: review triage (your part first, very unsure first, the
/// count follows the scope, accompaniment last), kept notes written to the Composition, and the key
/// shown as concert key plus the written key for the player's instrument.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class ReviewTriageTests
{
    private sealed class Quiet : IAnnouncer { public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) { } }
    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    private static IStrings Strings() => new ReswStrings(ReswStrings.Parse(System.Xml.Linq.XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));

    private static (ScoreViewModel Score, ReviewViewModel Review) Load()
    {
        var strings = Strings();
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, new Quiet(), strings, new Inline()), new Quiet(), strings);
        score.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), null);
        // Make notes uncertain in both pitched parts: some very uncertain in the horn, one in the cornet.
        var doc = score.Document!;
        doc.Parts[0].Bars[1].Events[0].Confidence = 0.55;
        doc.Parts[0].Bars[2].Events[0].Confidence = 0.2;
        doc.Parts[1].Bars[0].Events[0].Confidence = 0.3;
        score.RefreshUncertain();
        return (score, new ReviewViewModel(score, new Quiet(), strings));
    }

    [Fact]
    public void Starts_in_your_part_with_the_very_unsure_notes_first()
    {
        var (score, review) = Load();
        review.Load();
        Assert.Equal(ReviewScope.MyPart, review.Scope);
        Assert.All(review.Items, i => Assert.Equal(0, i.Part)); // Solo Cornet is the player's part
        Assert.True(review.Items[0].IsVeryUncertain);
        int mine = review.Items.Count, veryUnsure = review.Items.Count(i => i.IsVeryUncertain);
        Assert.Equal($"Check your part first: {mine} notes in Solo Cornet, {veryUnsure} very unsure", review.TriageText);
        Assert.Equal($"Your part ({mine})", review.MyPartScopeLabel);
        Assert.Equal($"All parts ({review.AllItems.Count})", review.AllPartsScopeLabel);
        Assert.StartsWith($"{mine} NOTE", review.CountHeading);

        // The count follows the scope; the other parts come after yours.
        review.Scope = ReviewScope.AllParts;
        Assert.Equal(review.AllItems.Count, review.Items.Count);
        Assert.StartsWith($"{review.AllItems.Count} NOTE", review.CountHeading);
        Assert.True(review.Items.TakeWhile(i => i.IsMine).Count() == mine);
        Assert.Contains(review.Items, i => i.Part == 1);
    }

    [Fact]
    public void When_your_part_is_done_the_review_goes_on_with_the_others()
    {
        var (_, review) = Load();
        review.Load();
        int mine = review.Items.Count;
        for (int i = 0; i < mine; i++) review.KeepCommand.Execute(null);
        Assert.Equal(ReviewScope.AllParts, review.Scope);
        Assert.NotNull(review.Current);
        Assert.False(review.Current!.IsMine);
    }

    [Fact]
    public void A_kept_note_is_kept_in_the_Composition_too()
    {
        var strings = Strings();
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, new Quiet(), strings, new Inline()), new Quiet(), strings);
        var composition = new Composition { Title = "x" };
        score.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), composition);
        var ev = score.Document!.Parts[0].Bars[0].Events.First(e => e.Written is not null);
        var voice = new Voice { Id = "solo", Role = VoiceRole.Melody };
        var note = new Note { Pitch = 70, Start = 0, Dur = 12, Confidence = 0.3 };
        voice.Notes.Add(note);
        composition.Voices.Add(voice);
        ev.CompositionVoiceId = "solo";
        ev.CompositionNoteStart = 0;
        string? saved = null;
        score.PersistEditedScore = (_, json) => saved = json;
        score.KeepInComposition(ev);
        Assert.Equal(1.0, note.Confidence);
        Assert.NotNull(saved);
        Assert.Contains("\"confidence\":1", saved);
    }

    [Fact]
    public void Key_names_give_the_written_key_for_the_instrument()
    {
        Assert.Equal("C major", KeyNames.Name(KeyNames.TonicOf(0, false), false, false));
        Assert.Equal("D major", KeyNames.Name(KeyNames.WrittenOf(0, -2), false, false)); // B♭ cornet
        Assert.Equal("A major", KeyNames.Name(KeyNames.WrittenOf(0, -9), false, false)); // E♭ horn
        Assert.Equal("B♭", KeyNames.InstrumentKey(-2, false));
        Assert.Equal("E♭", KeyNames.InstrumentKey(-21, false)); // E♭ bass
        Assert.Null(KeyNames.InstrumentKey(0, false));
        Assert.Equal("a minor", KeyNames.Name(KeyNames.TonicOf(0, true), true, false).ToLowerInvariant());
        Assert.Equal("B-dur", KeyNames.Name(10, false, true));
        Assert.Equal("fiss-moll", KeyNames.Name(6, true, true));
        Assert.Equal(10, KeyNames.PitchClassOf("Bbm"));
    }

    [Fact]
    public void Key_display_says_the_concert_key_and_yours()
    {
        var strings = Strings();
        var output = new OutputOptionsViewModel(new ManagedCoreBridge(), new Quiet(), strings);
        var composition = new Composition { Title = "x", Keys = [new KeySig { Tick = 0, Fifths = 0 }] };
        output.SetScoreContext(composition, -2);
        Assert.Equal("C major (concert)", output.KeyLabel);
        Assert.Equal("As recorded · D major for B♭ instruments", output.KeyDetail);
        output.KeyDownCommand.Execute(null);
        Assert.Equal("B major (concert)", output.KeyLabel);
        Assert.Equal("D♭ major for B♭ instruments", output.KeyDetail);
        Assert.Equal("B", output.Options.Key);
        output.KeyUpCommand.Execute(null);
        Assert.Equal(0, output.KeyIndex); // back to the recorded key
        Assert.Null(output.Options.Key);
        output.SetScoreContext(composition, 0);
        Assert.Equal("As recorded", output.KeyDetail); // a C instrument reads what sounds
    }
}

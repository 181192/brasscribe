using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>One note Brasscribe wasn't sure about, as the review list shows it.</summary>
public sealed partial class ReviewItem : ObservableObject
{
    public ReviewItem(int part, string partName, int barIndex, int eventIndex, int barNumber, TsEvent ev, string label, string listName,
        bool isMine = false, bool isAccompaniment = false)
    {
        IsMine = isMine;
        IsAccompaniment = isAccompaniment;
        Part = part;
        PartName = partName;
        BarIndex = barIndex;
        EventIndex = eventIndex;
        BarNumber = barNumber;
        Event = ev;
        Label = label;
        ListName = listName;
    }

    public int Part { get; }
    public string PartName { get; }
    public int BarIndex { get; }
    public int EventIndex { get; }
    public int BarNumber { get; }
    public TsEvent Event { get; }
    /// <summary>"G, half note".</summary>
    public string Label { get; }
    /// <summary>"Bar 14 · G", with the level for screen readers in <see cref="AccessibleName"/>.</summary>
    public string ListName { get; }
    /// <summary>In the player's own part.</summary>
    public bool IsMine { get; }
    /// <summary>In an accompaniment layer (drums, orchestra, strings): checked last.</summary>
    public bool IsAccompaniment { get; }
    public bool IsVeryUncertain => Event.Confidence is < Note.VeryUncertainBelow;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsOpen))]
    public partial bool IsKept { get; set; }

    [ObservableProperty] public partial bool IsCurrent { get; set; }
    [ObservableProperty] public partial string AccessibleName { get; set; } = "";

    public bool IsOpen => !IsKept;
}

/// <summary>A part heading in the review list with its notes.</summary>
public sealed record ReviewGroup(string PartName, IReadOnlyList<ReviewItem> Items);

/// <summary>Which notes the review goes through: the player's own part first, or every part.</summary>
public enum ReviewScope { MyPart, AllParts }

/// <summary>What one transcriber heard at the note: "SwiftF0 · Same, G" or "Basic Pitch · A".</summary>
public sealed record EvidenceRow(string Name, string Heard, bool Agrees)
{
    public bool Differs => !Agrees;
    public string AccessibleName => $"{Name}: {Heard}";
}

/// <summary>A pitch to change the note to in "Change note…", as a shift from the written note.</summary>
public sealed record NoteChoice(string Label, int Shift);

/// <summary>
/// "Check the notes": one uncertain note at a time (design/system.md §5, Review list). The note is
/// shown with its bar, part, name and duration, the level in words and what else it could be; the
/// player listens to the bar, keeps the note (the "?" goes) or skips it. "Finish later" asks first,
/// because the notes left keep their marks; the score view offers "Check them" to come back.
/// Triage (usability review 2, P1-10): it starts in the player's own part with the very uncertain
/// notes first, the count follows the chosen scope, and accompaniment layers come last. A kept note
/// is written to the Composition, so it stays kept when the score is arranged again.
/// </summary>
public sealed partial class ReviewViewModel(ScoreViewModel score, IAnnouncer announcer, IStrings s) : ObservableObject
{
    private List<ReviewItem> _all = [];

    public ObservableCollection<ReviewGroup> Groups { get; } = [];

    /// <summary>The notes in the chosen scope, in checking order.</summary>
    public IReadOnlyList<ReviewItem> Items { get; private set; } = [];

    /// <summary>Every uncertain note of the score.</summary>
    public IReadOnlyList<ReviewItem> AllItems => _all;

    /// <summary>With many marks: "Most of these are probably right. Start with the 12 very unsure ones."</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasLead))]
    public partial string LeadText { get; set; } = "";

    public bool HasLead => LeadText.Length > 0;

    /// <summary>"Keep the rest of this bar (3)": the other open notes in the current note's bar and part.</summary>
    [ObservableProperty] public partial string KeepBarText { get; set; } = "";
    [ObservableProperty] public partial bool CanKeepBar { get; set; }

    /// <summary>"Check your part first: 12 notes in Solo Cornet, 4 very unsure".</summary>
    [ObservableProperty] public partial string TriageText { get; set; } = "";

    /// <summary>"Your part (12)" and "All parts (215)", the scope choices.</summary>
    [ObservableProperty] public partial string MyPartScopeLabel { get; set; } = "";
    [ObservableProperty] public partial string AllPartsScopeLabel { get; set; } = "";
    [ObservableProperty] public partial bool HasMyPart { get; set; }
    [ObservableProperty] public partial ReviewScope Scope { get; set; } = ReviewScope.MyPart;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasCurrent))]
    public partial ReviewItem? Current { get; set; }

    public bool HasCurrent => Current is not null;

    [ObservableProperty] public partial string Heading { get; set; } = "";
    [ObservableProperty] public partial string Overline { get; set; } = "";
    [ObservableProperty] public partial string NoteLine { get; set; } = "";
    [ObservableProperty] public partial string LevelLine { get; set; } = "";
    [ObservableProperty] public partial string CountHeading { get; set; } = "";
    [ObservableProperty] public partial string FinishLaterText { get; set; } = "";

    /// <summary>True while the "Finish later?" confirmation is shown.</summary>
    [ObservableProperty] public partial bool IsConfirmingFinish { get; set; }

    [ObservableProperty] public partial string ConfirmText { get; set; } = "";

    /// <summary>The note has evidence: how sure Brasscribe is and what each transcriber heard.</summary>
    [ObservableProperty] public partial bool HasEvidence { get; set; }
    [ObservableProperty] public partial double ConfidencePercent { get; set; }
    [ObservableProperty] public partial string ConfidenceText { get; set; } = "";
    public ObservableCollection<EvidenceRow> Heard { get; } = [];

    /// <summary>Notes not yet kept, in every part.</summary>
    public int Left => _all.Count(i => !i.IsKept);

    /// <summary>Raised when the player is done here (all kept, or finishing later confirmed).</summary>
    public event EventHandler? Finished;

    /// <summary>Raised when <see cref="Current"/> changes, so the view can draw its bars.</summary>
    public event EventHandler<ReviewItem>? CurrentChanged;

    /// <summary>Collects the uncertain notes of the loaded score and starts in the player's own part.</summary>
    public void Load(ReviewScope? scope = null)
    {
        var all = new List<ReviewItem>();
        int mine = score.MyPartIndex;
        if (score.Document is { } doc)
        {
            var settings = new TalkingScoreSettings(score.Language, score.ConcertPitch ? PitchMode.Concert : PitchMode.Written);
            for (int p = 0; p < doc.Parts.Count; p++)
            {
                var part = doc.Parts[p];
                string partName = settings.Nb ? part.NameNb ?? part.Name : part.Name;
                for (int b = 0; b < part.Bars.Count; b++)
                    for (int e = 0; e < part.Bars[b].Events.Count; e++)
                    {
                        var ev = part.Bars[b].Events[e];
                        if (!ev.IsUncertain || ev.Tie is { Stop: true }) continue;
                        string label = Announcer.NoteLabel(ev, settings);
                        string pitch = label.Split(',')[0];
                        var item = new ReviewItem(p, partName, b, e, part.Bars[b].Number, ev, label, s.Format("Review_ListItem", part.Bars[b].Number, pitch),
                            p == mine, IsAccompaniment(part, ev));
                        item.AccessibleName = s.Format(item.IsVeryUncertain ? "Review_ListItemVeryUncertain" : "Review_ListItemUncertain",
                            part.Bars[b].Number, pitch);
                        all.Add(item);
                    }
            }
        }
        _all = all;
        var myItems = all.Where(i => i.IsMine).ToList();
        HasMyPart = myItems.Count > 0;
        MyPartScopeLabel = s.Format("Review_ScopeMine", myItems.Count);
        AllPartsScopeLabel = s.Format("Review_ScopeAll", all.Count);
        TriageText = HasMyPart ? s.Format("Review_Triage", myItems.Count, myItems[0].PartName, myItems.Count(i => i.IsVeryUncertain)) : "";
        IsConfirmingFinish = false;
        var wanted = scope ?? (HasMyPart ? ReviewScope.MyPart : ReviewScope.AllParts);
        if (Scope != wanted) Scope = wanted; // applies the scope
        else Apply();
    }

    partial void OnScopeChanged(ReviewScope value) => Apply();

    /// <summary>More marks than this and the review leads with "Most of these are probably right" (usability review 3, P1-A).</summary>
    public const int ManyMarks = 50;

    /// <summary>
    /// Order: your part, the other brass parts, accompaniment last; in each part the very unsure
    /// notes first, then the rest by bar.
    /// </summary>
    private void Apply()
    {
        var inScope = Scope == ReviewScope.MyPart && HasMyPart ? _all.Where(i => i.IsMine) : _all;
        var ordered = inScope
            .OrderBy(i => i.IsMine ? 0 : i.IsAccompaniment ? 2 : 1)
            .ThenBy(i => i.Part)
            .ThenBy(i => i.IsVeryUncertain ? 0 : 1)
            .ThenBy(i => i.BarIndex).ThenBy(i => i.EventIndex)
            .ToList();
        int veryUnsure = ordered.Count(i => i.IsVeryUncertain);
        LeadText = ordered.Count > ManyMarks && veryUnsure > 0
            ? s.Format(veryUnsure == 1 ? "Review_LeadManyOne" : "Review_LeadMany", veryUnsure)
            : "";
        Items = ordered;
        Groups.Clear();
        string accompaniment = s["Review_Accompaniment"].ToUpperInvariant();
        foreach (var g in ordered.GroupBy(i => i.IsAccompaniment ? accompaniment : i.PartName.ToUpperInvariant()))
            Groups.Add(new ReviewGroup(g.Key, g.ToList()));
        CountHeading = s.Format(ordered.Count == 1 ? "Review_CountOne" : "Review_Count", ordered.Count).ToUpperInvariant();
        OnPropertyChanged(nameof(Items));
        Select(ordered.FirstOrDefault(i => !i.IsKept) ?? ordered.FirstOrDefault());
    }

    /// <summary>Accompaniment: drum parts, and notes that come only from the backing layers (orchestra, strings, drums).</summary>
    private static bool IsAccompaniment(TsPart part, TsEvent ev) =>
        part.Percussion || ev.Kind == EventKind.Unpitched
        || ev.Sources.Count > 0 && ev.Sources.All(src => src is "strings" or "drums" or "brass" or "orchestra" or "harmony");

    public void Select(ReviewItem? item)
    {
        if (Current is { } old) old.IsCurrent = false;
        Current = item;
        UpdateTexts();
        if (item is null) return;
        item.IsCurrent = true;
        score.FocusEvent(item.Part, item.BarIndex, item.EventIndex);
        CurrentChanged?.Invoke(this, item);
    }

    [RelayCommand]
    private void Keep()
    {
        if (Current is not { } item) return;
        score.FocusEvent(item.Part, item.BarIndex, item.EventIndex);
        score.KeepCurrent();
        score.KeepInComposition(item.Event);
        item.IsKept = true;
        announcer.Announce(s.Format("Review_Kept", item.BarNumber, Left));
        MoveNext(item);
    }

    /// <summary>Keeps every open note in the current note's bar (the note itself included) and goes on.</summary>
    [RelayCommand]
    private void KeepRestOfBar()
    {
        if (Current is not { } item) return;
        var bar = _all.Where(i => !i.IsKept && i.Part == item.Part && i.BarIndex == item.BarIndex).ToList();
        foreach (var i in bar)
        {
            score.FocusEvent(i.Part, i.BarIndex, i.EventIndex);
            score.KeepCurrent();
            score.KeepInComposition(i.Event);
            i.IsKept = true;
        }
        announcer.Announce(s.Format("Review_KeptBar", bar.Count, item.BarNumber, Left));
        MoveNext(item);
    }

    [RelayCommand]
    private void Skip()
    {
        if (Current is not { } item) return;
        MoveNext(item);
    }

    [RelayCommand]
    private void Listen()
    {
        if (Current is not { } item) return;
        score.FocusEvent(item.Part, item.BarIndex, item.EventIndex);
        score.ListenToBarCommand.Execute(null);
    }

    /// <summary>
    /// "Change note…": moves the note by <paramref name="shift"/> semitones (0 keeps it as written), saves the
    /// score and keeps the note, so its "?" goes. The same on every platform.
    /// </summary>
    public bool ChangeNote(int shift)
    {
        if (Current is not { } selected) return false;
        if (shift != 0)
        {
            if (!score.CorrectPitch(selected.Part, selected.BarIndex, selected.EventIndex, shift)) return false;
            int sourceNoteIndex = selected.Event.MusicXmlNoteIndex;
            var kept = _all.Where(i => i.IsKept).Select(i => (i.Part, i.Event.MusicXmlNoteIndex)).ToHashSet();
            Load(Scope);
            foreach (var i in _all) i.IsKept = kept.Contains((i.Part, i.Event.MusicXmlNoteIndex));
            Select(Items.FirstOrDefault(x => x.Part == selected.Part && x.Event.MusicXmlNoteIndex == sourceNoteIndex));
            announcer.Announce(s.Format("Review_Changed", PitchNameAt(Current!, 0)));
        }
        Keep();
        return true;
    }

    /// <summary>The current note moved by <paramref name="shift"/> semitones, named as the review shows it.</summary>
    public string ChangeLabel(int shift) => Current is { } item ? PitchNameAt(item, shift) : "";

    /// <summary>What the transcribers heard at the current note, as choices for "Change note…".</summary>
    public IReadOnlyList<NoteChoice> ChangeChoices()
    {
        if (Current is not { } item || EvidenceFor(item) is not { } evidence) return [];
        return evidence.Models.Where(m => m.Pitch is not null)
            .Select(m => new NoteChoice($"{m.Name}: {PitchNameAt(item, m.Pitch!.Value - evidence.Pitch)}", m.Pitch!.Value - evidence.Pitch))
            .ToList();
    }

    /// <summary>The evidence behind a review item: its Composition note, matched by voice, start and pitch class.</summary>
    private Engine.NoteEvidence? EvidenceFor(ReviewItem item)
    {
        var ev = item.Event;
        if (score.Evidence is not { } evidence || ev.CompositionVoiceId is not { } voice || ev.CompositionNoteStart is not { } start) return null;
        var pitch = ev.Concert ?? ev.Written;
        return pitch is null ? null : evidence.NoteAt(voice, start, Announcer.Midi(pitch));
    }

    /// <summary>"G", "B♭" (Norwegian "G", "B"): the note as shown (written or concert) moved by <paramref name="shift"/>.</summary>
    private string PitchNameAt(ReviewItem item, int shift)
    {
        bool concert = score.ConcertPitch;
        var ev = item.Event;
        var shown = concert ? ev.Concert ?? ev.Written : ev.Written ?? ev.Concert;
        if (shown is null || score.Document is not { } doc) return "";
        if (shift == 0) return Announcer.PitchLabel(shown, Nb);
        var part = doc.Parts[item.Part];
        int fifths = part.Bars[item.BarIndex].KeyFifths;
        if (concert) fifths = Announcer.ConcertKey(fifths, part.Transpose);
        var spelled = MusicXmlNoteEditor.Spell(Announcer.Midi(shown) + shift, fifths);
        return Announcer.PitchLabel(spelled, Nb);
    }

    private bool Nb => s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase);

    /// <summary>"an A", "a B" in English; Norwegian names the note bare.</summary>
    private string WithArticle(string name) =>
        Nb || name.Length == 0 ? name : (name[0] is 'A' or 'E' or 'F' ? "an " : "a ") + name;

    /// <summary>"Finish later (9 left)": asks first while notes are left; with none left it finishes.</summary>
    [RelayCommand]
    private void FinishLater()
    {
        if (Left == 0)
        {
            Finish();
            return;
        }
        ConfirmText = s.Format(Left == 1 ? "Review_FinishConfirmOne" : "Review_FinishConfirm", Left);
        IsConfirmingFinish = true;
        announcer.Announce(ConfirmText, AnnouncementKind.Important);
    }

    [RelayCommand]
    private void ConfirmFinish()
    {
        IsConfirmingFinish = false;
        Finish();
    }

    [RelayCommand]
    private void CancelFinish() => IsConfirmingFinish = false;

    private void Finish()
    {
        score.RefreshUncertain();
        Finished?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>After your part is done, the review goes on with the other parts before finishing.</summary>
    private void MoveNext(ReviewItem from)
    {
        int i = Items.ToList().IndexOf(from);
        var next = Items.Skip(i + 1).FirstOrDefault(x => !x.IsKept) ?? Items.Take(i).FirstOrDefault(x => !x.IsKept);
        if (next is null && Scope == ReviewScope.MyPart && _all.Any(x => !x.IsKept))
        {
            announcer.Announce(s["Review_MyPartDone"], AnnouncementKind.Important);
            Scope = ReviewScope.AllParts;
            return;
        }
        if (next is null)
        {
            Select(null);
            announcer.Announce(s["Review_AllDone"], AnnouncementKind.Important);
            Finish();
            return;
        }
        Select(next);
        announcer.Announce(Heading + ". " + NoteLine);
    }

    private void UpdateTexts()
    {
        FinishLaterText = s.Format("Review_FinishLater", Left);
        Heard.Clear();
        if (Current is not { } item)
        {
            Heading = Overline = NoteLine = LevelLine = ConfidenceText = "";
            HasEvidence = false;
            return;
        }
        int inBar = _all.Count(i => !i.IsKept && i.Part == item.Part && i.BarIndex == item.BarIndex);
        CanKeepBar = inBar > 1;
        KeepBarText = s.Format("Review_KeepBar", inBar);
        int index = Items.ToList().IndexOf(item) + 1;
        Overline = s.Format("Review_Overline", index, Items.Count, item.PartName).ToUpperInvariant();
        Heading = s.Format("Review_BarHeading", item.BarNumber);
        NoteLine = s.Format(score.ConcertPitch ? "Review_NoteConcert" : "Review_NoteWritten", item.Label);
        var evidence = EvidenceFor(item);
        HasEvidence = evidence is not null;
        if (evidence is not null)
        {
            ConfidencePercent = Math.Round(Math.Clamp(evidence.Confidence, 0, 1) * 100);
            ConfidenceText = Screens.Percent(ConfidencePercent, s.Language);
            foreach (var m in evidence.Models)
            {
                string heard = m.Pitch is not { } p ? s["Review_HeardNothing"]
                    : m.Agrees ? s.Format("Review_HeardSame", PitchNameAt(item, p - evidence.Pitch))
                    : PitchNameAt(item, p - evidence.Pitch);
                Heard.Add(new EvidenceRow(m.Name, heard, m.Agrees));
            }
        }
        LevelLine = evidence?.AlternativeShift is { } shift
            ? s.Format("Review_LevelAlternative", s[item.IsVeryUncertain ? "Review_WordVeryUncertain" : "Review_WordUncertain"],
                WithArticle(PitchNameAt(item, shift)))
            : s[item.IsVeryUncertain ? "Review_LevelVeryUncertain" : "Review_LevelUncertain"];
    }
}

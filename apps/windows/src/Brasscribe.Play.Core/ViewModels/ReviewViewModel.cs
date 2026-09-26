using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Review;
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
        Part = part;
        PartName = partName;
        BarIndex = barIndex;
        EventIndex = eventIndex;
        BarNumber = barNumber;
        Event = ev;
        Label = label;
        ListName = listName;
        IsMine = isMine;
        IsAccompaniment = isAccompaniment;
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

/// <summary>A note changed in the review: the item, the Composition note behind it and the chosen alternative.</summary>
public sealed record NoteChange(ReviewItem Item, Voice Voice, Note Note, NoteAlternative Alternative);

/// <summary>
/// "Check the notes": one uncertain note at a time (design/system.md §5, Review list). Triage
/// (usability review 2, P1-10): it starts in the player's own part with the very uncertain notes
/// first, the count follows the chosen scope, and accompaniment layers come last. For each note it
/// says what else it could be ("It could also be an A") and "Change note…" offers the alternatives
/// (P1-9); a change or a kept note is written to the Composition, so it survives arranging again.
/// "Finish later" asks first, because the notes left keep their marks.
/// </summary>
public sealed partial class ReviewViewModel(ScoreViewModel score, IAnnouncer announcer, IStrings s) : ObservableObject
{
    private List<ReviewItem> _all = [];

    public ObservableCollection<ReviewGroup> Groups { get; } = [];

    /// <summary>The notes in the chosen scope, in checking order.</summary>
    public IReadOnlyList<ReviewItem> Items { get; private set; } = [];

    /// <summary>Every uncertain note of the score.</summary>
    public IReadOnlyList<ReviewItem> AllItems => _all;

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

    /// <summary>"Check your part first: 12 notes in Solo Cornet, 4 very unsure".</summary>
    [ObservableProperty] public partial string TriageText { get; set; } = "";

    /// <summary>"Your part (12)" and "All parts (215)", the scope choices.</summary>
    [ObservableProperty] public partial string MyPartScopeLabel { get; set; } = "";
    [ObservableProperty] public partial string AllPartsScopeLabel { get; set; } = "";
    [ObservableProperty] public partial bool HasMyPart { get; set; }

    [ObservableProperty] public partial ReviewScope Scope { get; set; } = ReviewScope.MyPart;

    /// <summary>True while the "Finish later?" confirmation is shown.</summary>
    [ObservableProperty] public partial bool IsConfirmingFinish { get; set; }

    [ObservableProperty] public partial string ConfirmText { get; set; } = "";

    /// <summary>What "Change note…" offers for the current note.</summary>
    public ObservableCollection<NoteAlternative> Alternatives { get; } = [];

    /// <summary>A change can be made: the score has its Composition and can be arranged again here.</summary>
    [ObservableProperty] public partial bool CanChangeNote { get; set; }

    /// <summary>The other transcriptions of a layer (by the role of its voice), for the alternatives; null when not at hand.</summary>
    public Func<VoiceRole, Task<IReadOnlyList<IReadOnlyList<HeardNote>>?>>? Listenings { get; set; }

    /// <summary>Set by the app: whether a changed note can be arranged again (the native core is there).</summary>
    public bool CanArrange { get; set; }

    public int Left => Items.Count(i => !i.IsKept);

    /// <summary>Raised when the player is done here (all kept, or finishing later confirmed).</summary>
    public event EventHandler? Finished;

    /// <summary>Raised when <see cref="Current"/> changes, so the view can draw its bars.</summary>
    public event EventHandler<ReviewItem>? CurrentChanged;

    /// <summary>Raised when a note was changed; the app writes it into the score and arranges again.</summary>
    public event EventHandler<NoteChange>? NoteChanged;

    private bool Nb => score.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase);

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
        string myName = HasMyPart ? myItems[0].PartName : "";
        MyPartScopeLabel = s.Format("Review_ScopeMine", myItems.Count);
        AllPartsScopeLabel = s.Format("Review_ScopeAll", all.Count);
        TriageText = HasMyPart
            ? s.Format("Review_Triage", myItems.Count, myName, myItems.Count(i => i.IsVeryUncertain))
            : "";
        IsConfirmingFinish = false;
        Scope = scope ?? (HasMyPart ? ReviewScope.MyPart : ReviewScope.AllParts);
        Apply();
    }

    partial void OnScopeChanged(ReviewScope value)
    {
        if (_all.Count > 0 || Items.Count > 0) Apply();
    }

    /// <summary>Order: your part (very unsure first, then by bar), the other brass parts by part and bar, accompaniment last.</summary>
    private void Apply()
    {
        var inScope = Scope == ReviewScope.MyPart && HasMyPart ? _all.Where(i => i.IsMine) : _all;
        var ordered = inScope
            .OrderBy(i => i.IsMine ? 0 : i.IsAccompaniment ? 2 : 1)
            .ThenBy(i => i.IsMine && !i.IsVeryUncertain ? 1 : 0)
            .ThenBy(i => i.Part).ThenBy(i => i.BarIndex).ThenBy(i => i.EventIndex)
            .ToList();
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
        Alternatives.Clear();
        UpdateTexts();
        if (item is null) return;
        item.IsCurrent = true;
        score.FocusEvent(item.Part, item.BarIndex, item.EventIndex);
        CurrentChanged?.Invoke(this, item);
        _ = LoadAlternativesAsync(item);
    }

    /// <summary>The alternatives of the current note, and the hint from the other transcriptions.</summary>
    private async Task LoadAlternativesAsync(ReviewItem item)
    {
        if (score.Composition is not { } composition || NoteAlternatives.SourceOf(composition, item.Event) is not { } source || item.Event.Written is not { } written)
        {
            CanChangeNote = false;
            return;
        }
        IReadOnlyList<IReadOnlyList<HeardNote>>? heard = null;
        if (Listenings is { } listen)
        {
            try { heard = await listen(source.Voice.Role); }
            catch (Exception e) when (e is IOException or InvalidDataException or Engine.EngineException or NotSupportedException) { heard = null; }
        }
        if (!ReferenceEquals(item, Current)) return;
        int keyFifths = score.Document?.Parts[item.Part].Bars[item.BarIndex].KeyFifths ?? 0;
        var list = NoteAlternatives.For(source.Note, Announcer.Midi(written), keyFifths, Nb, heard);
        Alternatives.Clear();
        foreach (var a in list) Alternatives.Add(a);
        CanChangeNote = CanArrange;
        if (list.FirstOrDefault(a => a.Kind == AlternativeKind.OtherListening) is { } hint)
            LevelLine = s.Format(item.IsVeryUncertain ? "Review_LevelVeryUncertainHint" : "Review_LevelUncertainHint", hint.Name);
    }

    [RelayCommand]
    private void Keep()
    {
        if (Current is not { } item) return;
        score.FocusEvent(item.Part, item.BarIndex, item.EventIndex);
        score.KeepCurrent();
        item.IsKept = true;
        // Written to the Composition too, so the note stays kept when the score is arranged again.
        if (score.Composition is { } c && NoteAlternatives.SourceOf(c, item.Event) is { } source) source.Note.Confidence = 1.0;
        announcer.Announce(s.Format("Review_Kept", item.BarNumber, Left));
        MoveNext(item);
    }

    /// <summary>"Change note…": the note becomes the chosen alternative, is kept, and the score is arranged again.</summary>
    [RelayCommand]
    private void ChangeNote(NoteAlternative? alternative)
    {
        if (alternative is null || Current is not { } item || score.Composition is not { } c) return;
        if (NoteAlternatives.SourceOf(c, item.Event) is not { } source) return;
        source.Note.Pitch += alternative.Semitones;
        source.Note.Confidence = 1.0;
        if (!source.Note.Sources.Contains("player")) source.Note.Sources.Add("player");
        item.IsKept = true;
        announcer.Announce(s.Format("Review_Changed", item.BarNumber, alternative.Name), AnnouncementKind.Important);
        NoteChanged?.Invoke(this, new NoteChange(item, source.Voice, source.Note, alternative));
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

    /// <summary>"Finish later (9 left)": asks first while notes are left; with none left it finishes.</summary>
    [RelayCommand]
    private void FinishLater()
    {
        int left = _all.Count(i => !i.IsKept);
        if (left == 0)
        {
            Finish();
            return;
        }
        ConfirmText = s.Format(left == 1 ? "Review_FinishConfirmOne" : "Review_FinishConfirm", left);
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
        FinishLaterText = s.Format("Review_FinishLater", _all.Count(i => !i.IsKept));
        if (Current is not { } item)
        {
            Heading = Overline = NoteLine = LevelLine = "";
            return;
        }
        int index = Items.ToList().IndexOf(item) + 1;
        Overline = s.Format("Review_Overline", index, Items.Count, item.PartName).ToUpperInvariant();
        Heading = s.Format("Review_BarHeading", item.BarNumber);
        NoteLine = s.Format(score.ConcertPitch ? "Review_NoteConcert" : "Review_NoteWritten", item.Label);
        LevelLine = s[item.IsVeryUncertain ? "Review_LevelVeryUncertain" : "Review_LevelUncertain"];
    }
}

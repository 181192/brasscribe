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
    public ReviewItem(int part, string partName, int barIndex, int eventIndex, int barNumber, TsEvent ev, string label, string listName)
    {
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
/// </summary>
public sealed partial class ReviewViewModel(ScoreViewModel score, IAnnouncer announcer, IStrings s) : ObservableObject
{
    public ObservableCollection<ReviewGroup> Groups { get; } = [];
    public IReadOnlyList<ReviewItem> Items { get; private set; } = [];

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

    public int Left => Items.Count(i => !i.IsKept);

    /// <summary>Raised when the player is done here (all kept, or finishing later confirmed).</summary>
    public event EventHandler? Finished;

    /// <summary>Raised when <see cref="Current"/> changes, so the view can draw its bars.</summary>
    public event EventHandler<ReviewItem>? CurrentChanged;

    /// <summary>Collects the uncertain notes of the loaded score, sorted by part and then bar.</summary>
    public void Load()
    {
        Groups.Clear();
        var items = new List<ReviewItem>();
        if (score.Document is { } doc)
        {
            var settings = new TalkingScoreSettings(score.Language, score.ConcertPitch ? PitchMode.Concert : PitchMode.Written);
            for (int p = 0; p < doc.Parts.Count; p++)
            {
                var part = doc.Parts[p];
                string partName = settings.Nb ? part.NameNb ?? part.Name : part.Name;
                var mine = new List<ReviewItem>();
                for (int b = 0; b < part.Bars.Count; b++)
                    for (int e = 0; e < part.Bars[b].Events.Count; e++)
                    {
                        var ev = part.Bars[b].Events[e];
                        if (!ev.IsUncertain || ev.Tie is { Stop: true }) continue;
                        string label = Announcer.NoteLabel(ev, settings);
                        string pitch = label.Split(',')[0];
                        var item = new ReviewItem(p, partName, b, e, part.Bars[b].Number, ev, label, s.Format("Review_ListItem", part.Bars[b].Number, pitch));
                        item.AccessibleName = s.Format(item.IsVeryUncertain ? "Review_ListItemVeryUncertain" : "Review_ListItemUncertain",
                            part.Bars[b].Number, pitch);
                        mine.Add(item);
                    }
                if (mine.Count > 0) Groups.Add(new ReviewGroup(partName.ToUpperInvariant(), mine));
                items.AddRange(mine);
            }
        }
        Items = items;
        IsConfirmingFinish = false;
        CountHeading = s.Format(items.Count == 1 ? "Review_CountOne" : "Review_Count", items.Count).ToUpperInvariant();
        Select(items.FirstOrDefault());
    }

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
        item.IsKept = true;
        announcer.Announce(s.Format("Review_Kept", item.BarNumber, Left));
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
            var kept = Items.Where(i => i.IsKept).Select(i => (i.Part, i.Event.MusicXmlNoteIndex)).ToHashSet();
            Load();
            foreach (var i in Items) i.IsKept = kept.Contains((i.Part, i.Event.MusicXmlNoteIndex));
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

    private void MoveNext(ReviewItem from)
    {
        int i = Items.ToList().IndexOf(from);
        var next = Items.Skip(i + 1).FirstOrDefault(x => !x.IsKept) ?? Items.Take(i).FirstOrDefault(x => !x.IsKept);
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

namespace Brasscribe.ScreenCheck;

/// <summary>A screen could not be taken as the screen that was asked for: no screenshot of it is kept to compare.</summary>
public sealed class ScreenNotTakenException(string why) : Exception(why);

/// <summary>
/// What a catalogue reads off a screen next to a take of it: its shape (the window's size, the page, the open dialog,
/// the theme: whatever says which screen this is) and where its text is. Read before and after each take; a take
/// counts only when both readings are the same, so the picture and the text boxes are of one moment.
/// </summary>
/// <param name="Texts">Null when the text was not read for this take (reading it through UI Automation is slow).</param>
public sealed record Look(string Shape, IReadOnlyList<ScreenText>? Texts)
{
    public bool SameAs(Look other) =>
        Shape == other.Shape && (Texts is null) == (other.Texts is null) && (Texts is null || Texts.SequenceEqual(other.Texts!));
}

/// <summary>
/// One screenshot of a screen, taken only when it is the screen that was asked for. The catalogue feeds it takes
/// (<see cref="Pause"/> apart) until <see cref="Done"/>, or gives up after <see cref="Bound"/> with <see cref="Waiting"/>
/// as the reason. A take counts when:
/// the catalogue's own conditions held before it (otherwise <see cref="NotReady"/>); the screen read the same before
/// and after it; its text is drawn in the picture (a window that has not presented its first frame is one flat
/// colour, and keeps perfectly still); and, for a dialog, the picture is not the screen without it. The screenshot
/// is the last of <see cref="Needed"/> such takes in a row with the same pixels and the same reading, the last one
/// with its text read.
/// </summary>
public sealed class SteadyShot(Picture? without = null)
{
    /// <summary>Takes in a row that must be the same.</summary>
    public const int Needed = 6;

    public static readonly TimeSpan Pause = TimeSpan.FromMilliseconds(250);

    /// <summary>How long a screen gets to become the screen asked for and keep still.</summary>
    public static readonly TimeSpan Bound = TimeSpan.FromSeconds(30);

    private readonly Dictionary<string, int> _waits = [];
    private Look? _look;
    private int _same;

    /// <summary>The screenshot, once <see cref="Done"/>; before that the last take, to look at when it was not taken.</summary>
    public Picture? Picture { get; private set; }

    /// <summary>The text on the screenshot, read around the take it is.</summary>
    public IReadOnlyList<ScreenText> Texts { get; private set; } = [];

    public bool Done { get; private set; }

    /// <summary>What it last waited for: the reason when the screen is not taken.</summary>
    public string Waiting { get; private set; } = "its first take";

    public int Takes { get; private set; }

    /// <summary>The next take can be the screenshot, so its text must be read (before and after it).</summary>
    public bool WantsTexts => _same >= Needed - 2;

    /// <summary>The screen is not the one asked for yet: the takes so far do not count.</summary>
    public void NotReady(string why)
    {
        Waiting = why;
        _waits[why] = _waits.GetValueOrDefault(why) + 1;
        _look = null;
        _same = 0;
    }

    /// <summary>A take, with the screen as read before and after it.</summary>
    public void Take(Picture picture, Look before, Look after)
    {
        if (Done) return;
        Takes++;
        var last = Picture;
        Picture = picture;
        if (!before.SameAs(after)) { NotReady("it changed while its picture was taken"); return; }
        if (before.Texts is { } texts && !Presented.Shows(picture, texts)) { NotReady("its text is not drawn in the picture yet"); return; }
        if (without is not null && picture.SameAs(without)) { NotReady("its dialog is not in the picture yet"); return; }
        bool still = _look is not null && last is not null && _look.Shape == before.Shape && picture.SameAs(last)
                     && (_look.Texts is null || before.Texts is null || _look.Texts.SequenceEqual(before.Texts));
        if (!still && _look is not null) NotReady("it does not keep still");
        _same = still ? _same + 1 : 0;
        // A reading with text is kept over a later one without: the next take with text is compared with it.
        _look = before.Texts is null && _look?.Texts is not null && still ? _look : before;
        if (_same >= Needed - 1 && before.Texts is not null)
        {
            Texts = before.Texts;
            Done = true;
        }
    }

    /// <summary>One line for the run's log: how long the screen took and what it waited for.</summary>
    public string Summary(string shot, TimeSpan took)
    {
        string waits = _waits.Count == 0 ? "" : "; waited for: " + string.Join(", ", _waits.Select(w => $"{w.Key} (×{w.Value})"));
        return $"{shot}: {(Done ? "taken" : "NOT taken")} after {took.TotalSeconds:0.0} s and {Takes} takes{waits}";
    }

    /// <summary>The exception for a screen that was not taken within <see cref="Bound"/>.</summary>
    public ScreenNotTakenException NotTaken() => new($"screen not taken: {Waiting} (after {Takes} takes in {Bound.TotalSeconds:0} s)");
}

/// <summary>Whether a picture of a screen shows the screen: its text is drawn in it.</summary>
public static class Presented
{
    /// <summary>
    /// The picture has ink where at least half of the screen's texts are. A window before its first frame is one
    /// colour all over, so none of its text has ink; a screen with no text at all cannot be told from one, and does
    /// not count as shown.
    /// </summary>
    public static bool Shows(Picture picture, IReadOnlyCollection<ScreenText> texts)
    {
        if (texts.Count == 0) return false;
        int drawn = texts.Count(t => Contrast.Measure(picture, t.Box) is not null);
        return drawn * 2 >= texts.Count;
    }
}

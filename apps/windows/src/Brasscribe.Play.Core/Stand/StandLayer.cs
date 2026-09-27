namespace Brasscribe.Play.Core.Stand;

/// <summary>What the stand's control layer needs to know before it may hide by itself.</summary>
public readonly record struct StandContext(
    bool Playing,
    bool ScreenReader = false,
    bool FocusInLayer = false,
    bool KeepVisible = false,
    bool TextInputOrTouchKeyboard = false);

/// <summary>
/// Showing and hiding the stand's control layer (design/music-stand.md §4.2), without a UI framework:
/// <list type="bullet">
/// <item>a tap on the music toggles it (on pointer-up); a key shows it; it shows on entry while paused;</item>
/// <item>it hides by itself <see cref="HideDelay"/> after the last touch, and only while the music plays;</item>
/// <item>never by itself with a screen reader, focus in the layer, a text field or the touch keyboard, or
/// Settings → Keep the stand controls visible (WCAG 2.2.1, 2.4.11);</item>
/// <item>the first time it hides, a hint says how to bring it back; the first tap dismisses it for good.</item>
/// </list>
/// </summary>
public sealed class StandLayer
{
    public static readonly TimeSpan HideDelay = TimeSpan.FromSeconds(4);

    public StandLayer(bool hintSeen = false) => HintSeen = hintSeen;

    public bool IsShown { get; private set; }
    public bool HintShown { get; private set; }
    public bool HintSeen { get; private set; }

    /// <summary>Raised when <see cref="IsShown"/>, <see cref="HintShown"/> or <see cref="HintSeen"/> change.</summary>
    public event EventHandler? Changed;

    /// <summary>Entering the stand: the layer shows while paused, or whenever it may not hide by itself.</summary>
    public void Enter(StandContext context)
    {
        HintShown = false;
        Set(!context.Playing || MustStay(context));
    }

    /// <summary>A tap on the music: the hint goes for good, and the layer toggles.</summary>
    public void Tap()
    {
        if (HintShown)
        {
            HintShown = false;
            HintSeen = true;
            Set(true);
            return;
        }
        if (!IsShown)
        {
            Set(true);
            return;
        }
        if (!HintSeen) HintShown = true;
        Set(false);
    }

    /// <summary>Tab, Space or any mapped key shows the layer.</summary>
    public void Key() => Set(true);

    public void Show() => Set(true);

    /// <summary>Whether the layer must stay whatever the timer says.</summary>
    public static bool MustStay(StandContext c) => c.ScreenReader || c.FocusInLayer || c.KeepVisible || c.TextInputOrTouchKeyboard;

    public bool CanAutoHide(StandContext c) => IsShown && c.Playing && !MustStay(c);

    /// <summary>The timer ran out; returns true when the layer hid.</summary>
    public bool AutoHide(StandContext c)
    {
        if (!CanAutoHide(c)) return false;
        if (!HintSeen) HintShown = true;
        Set(false);
        return true;
    }

    private void Set(bool shown)
    {
        IsShown = shown;
        Changed?.Invoke(this, EventArgs.Empty);
    }
}

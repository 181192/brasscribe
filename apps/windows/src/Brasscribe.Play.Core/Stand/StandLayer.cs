namespace Brasscribe.Play.Core.Stand;

/// <summary>What the stand's control layer needs to know before it may hide by itself.</summary>
public readonly record struct StandContext(
    bool Playing,
    bool ScreenReader = false,
    bool FocusInLayer = false,
    bool KeepVisible = false,
    bool TextInputOrTouchKeyboard = false,
    bool Keyboard = false);

/// <summary>
/// Showing and hiding the stand's control layer (design/music-stand.md §4.2), without a UI framework:
/// <list type="bullet">
/// <item>a tap on the music toggles it (on pointer-up); a key shows it; it shows on entry while paused;</item>
/// <item>it hides by itself <see cref="HideDelay"/> after the last touch, and only while the music plays;</item>
/// <item>never by itself with a screen reader, focus in the layer, a text field or the touch keyboard, after Tab or
/// Space until the next touch, or Settings → Keep the stand controls visible (WCAG 2.2.1, 2.4.11);</item>
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
        FromKeyboard = false;
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

    /// <summary>
    /// Tab or Space shows the layer (<see cref="ShowsLayer"/>), and it stays until the next touch: the player is on the
    /// keyboard. A pedal's page keys keep nothing up.
    /// </summary>
    public void Key()
    {
        FromKeyboard = true;
        Set(true);
    }

    /// <summary>Tab or Space showed the layer since the last touch.</summary>
    public bool FromKeyboard { get; private set; }

    /// <summary>A press on the stand (pointer or touch): the layer may hide by itself again.</summary>
    public void Touched() => FromKeyboard = false;

    /// <summary>
    /// Whether a key pressed in the stand shows the layer and starts the hide wait again: Space does (Tab too, handled
    /// on its own as it moves into the layer). The page keys (arrows, Page Up/Down, Home/End) turn the page and leave
    /// the layer and its timer as they are: a Bluetooth page turner or pedal is a keyboard that sends them, and a pedal
    /// press must not put controls over the music (design/music-stand.md §4.2). No other key shows it either.
    /// </summary>
    public static bool ShowsLayer(ViewModels.ScoreKey? key) => key == ViewModels.ScoreKey.Space;

    public void Show() => Set(true);

    /// <summary>Whether the layer must stay whatever the timer says.</summary>
    public static bool MustStay(StandContext c) => c.ScreenReader || c.FocusInLayer || c.KeepVisible || c.TextInputOrTouchKeyboard || c.Keyboard;

    public bool CanAutoHide(StandContext c) => IsShown && c.Playing && !MustStay(c with { Keyboard = c.Keyboard || FromKeyboard });

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

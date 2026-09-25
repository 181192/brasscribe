namespace Brasscribe.Play.Core.ViewModels;

public enum ScoreCommand
{
    NextNote, PreviousNote, NextBeat, PreviousBeat, NextBar, PreviousBar, NextPart, PreviousPart,
    FirstBar, LastBar, NextUncertain, PreviousUncertain, MarkChecked, ReadBar, WhereAmI,
    PlayBar, PlayFrom, PlayPause, LoopStartHere, LoopEndHere, ToggleLoop,
    Slower, Faster, ResetSpeed, ToggleMute, ToggleSolo, ToggleCountIn, ToggleMetronome,
    ZoomIn, ZoomOut, ZoomReset, GoToBar, LeaveScore,
}

/// <summary>Keys the score view reacts to, independent of the UI framework's key enum.</summary>
public enum ScoreKey
{
    Left, Right, Up, Down, Home, End, Space, Escape,
    U, C, R, P, W, L, M, S, K, T, G,
    OpenBracket, CloseBracket, Minus, Plus, D0,
}

[Flags]
public enum KeyModifiers { None = 0, Ctrl = 1, Shift = 2, Alt = 4 }

/// <summary>
/// The shortcut list of qa/screen-reader-scripts/keyboard-desktop.md for Windows. Single-character
/// keys work only while the score has focus and can be turned off (WCAG 2.1.4); arrows, Space,
/// Home/End and modifier shortcuts always work there.
/// </summary>
public static class ScoreKeyMap
{
    public static ScoreCommand? Map(ScoreKey key, KeyModifiers mods, bool singleKeyShortcuts = true)
    {
        bool ctrl = mods.HasFlag(KeyModifiers.Ctrl), shift = mods.HasFlag(KeyModifiers.Shift), alt = mods.HasFlag(KeyModifiers.Alt);
        if (alt) return null;

        var command = (key, ctrl, shift) switch
        {
            (ScoreKey.Right, false, false) => ScoreCommand.NextNote,
            (ScoreKey.Left, false, false) => ScoreCommand.PreviousNote,
            (ScoreKey.Right, true, false) => ScoreCommand.NextBeat,
            (ScoreKey.Left, true, false) => ScoreCommand.PreviousBeat,
            (ScoreKey.Down, true, false) => ScoreCommand.NextBar,
            (ScoreKey.Up, true, false) => ScoreCommand.PreviousBar,
            (ScoreKey.Down, true, true) => ScoreCommand.NextPart,
            (ScoreKey.Up, true, true) => ScoreCommand.PreviousPart,
            (ScoreKey.Home, false, false) => ScoreCommand.FirstBar,
            (ScoreKey.End, false, false) => ScoreCommand.LastBar,
            (ScoreKey.Space, false, false) => ScoreCommand.PlayPause,
            (ScoreKey.Escape, _, _) => ScoreCommand.LeaveScore,
            (ScoreKey.G, true, false) => ScoreCommand.GoToBar,
            (ScoreKey.Plus, true, false) => ScoreCommand.ZoomIn,
            (ScoreKey.Minus, true, false) => ScoreCommand.ZoomOut,
            (ScoreKey.D0, true, false) => ScoreCommand.ZoomReset,
            _ => (ScoreCommand?)null,
        };
        if (command is not null || ctrl || !singleKeyShortcuts) return command;

        return (key, shift) switch
        {
            (ScoreKey.U, false) => ScoreCommand.NextUncertain,
            (ScoreKey.U, true) => ScoreCommand.PreviousUncertain,
            (ScoreKey.C, false) => ScoreCommand.MarkChecked,
            (ScoreKey.R, false) => ScoreCommand.ReadBar,
            (ScoreKey.P, false) => ScoreCommand.PlayBar,
            (ScoreKey.P, true) => ScoreCommand.PlayFrom,
            (ScoreKey.W, false) => ScoreCommand.WhereAmI,
            (ScoreKey.OpenBracket, false) => ScoreCommand.LoopStartHere,
            (ScoreKey.CloseBracket, false) => ScoreCommand.LoopEndHere,
            (ScoreKey.L, false) => ScoreCommand.ToggleLoop,
            (ScoreKey.Minus, false) => ScoreCommand.Slower,
            (ScoreKey.Plus, false) => ScoreCommand.Faster,
            (ScoreKey.D0, false) => ScoreCommand.ResetSpeed,
            (ScoreKey.M, false) => ScoreCommand.ToggleMute,
            (ScoreKey.S, false) => ScoreCommand.ToggleSolo,
            (ScoreKey.K, false) => ScoreCommand.ToggleCountIn,
            (ScoreKey.T, false) => ScoreCommand.ToggleMetronome,
            _ => null,
        };
    }
}

using System.Diagnostics;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// One screenshot of a window of another process, taken only when it is that window with its content drawn
/// (<see cref="SteadyShot"/>): the process runs, the window is shown and not minimised, it has the same place and size
/// before and after each take, and the text UI Automation finds in it is drawn in the picture (a window that has not
/// presented its first frame is one flat colour and keeps perfectly still).
/// </summary>
internal static class WindowShot
{
    /// <param name="client">The client area only (as Play's catalogue takes its screenshots); otherwise the whole window.</param>
    /// <param name="notTaken">Where the last take goes when the window is not taken, to look at (never compared).</param>
    /// <exception cref="ScreenNotTakenException">The window was not taken within <see cref="SteadyShot.Bound"/>.</exception>
    public static SteadyShot Take(Process process, nint hwnd, string shot, bool client = false, string? notTaken = null)
    {
        var steady = new SteadyShot();
        var clock = Stopwatch.StartNew();
        using var automation = new UIA3Automation();
        while (!steady.Done && clock.Elapsed < SteadyShot.Bound)
        {
            Thread.Sleep(SteadyShot.Pause);
            // Reading the text through UI Automation is slow: only around the take that can be the screenshot.
            bool texts = steady.WantsTexts;
            var before = Read(automation, process, hwnd, client, texts, out string? waiting);
            if (before is null) { steady.NotReady(waiting!); continue; }
            var picture = Win.Capture(hwnd, client);
            var after = Read(automation, process, hwnd, client, texts, out waiting);
            if (after is null) { steady.NotReady(waiting!); continue; }
            steady.Take(picture, before, after);
        }
        Console.WriteLine(steady.Summary(shot, clock.Elapsed));
        if (steady.Done) return steady;
        if (notTaken is not null && steady.Picture is { } last)
        {
            Directory.CreateDirectory(notTaken);
            Png.Save(Path.Combine(notTaken, shot + ".png"), last);
        }
        throw steady.NotTaken();
    }

    private static Look? Read(UIA3Automation automation, Process process, nint hwnd, bool client, bool texts, out string? waiting)
    {
        waiting = null;
        process.Refresh();
        if (process.HasExited) waiting = "its process has ended";
        else if (!Win.IsShown(hwnd)) waiting = "its window is not shown";
        if (waiting is not null) return null;
        var area = Win.Area(hwnd, client);
        if (area.Right - area.Left <= 0 || area.Bottom - area.Top <= 0) { waiting = "its window has no size"; return null; }
        string shape = $"{area.Left},{area.Top} {area.Right - area.Left}x{area.Bottom - area.Top}";
        if (!texts) return new Look(shape, null);
        try
        {
            return new Look(shape, Texts(automation, hwnd, area));
        }
        catch (Exception x) when (x is System.Runtime.InteropServices.COMException or TimeoutException or InvalidOperationException)
        {
            waiting = "its text could not be read through UI Automation";
            return null;
        }
    }

    /// <summary>The window's text, where UI Automation puts it, in the pixels of a picture of <paramref name="area"/>.</summary>
    private static List<ScreenText> Texts(UIA3Automation automation, nint hwnd, Win.Rect area)
    {
        var window = automation.FromHandle(hwnd);
        var found = new List<ScreenText>();
        foreach (var e in window.FindAllDescendants(cf => cf.ByControlType(ControlType.Text)))
        {
            try
            {
                var p = e.Properties;
                var r = e.BoundingRectangle;
                if (p.IsOffscreen.ValueOrDefault || r.IsEmpty || string.IsNullOrWhiteSpace(p.Name.ValueOrDefault) || InDisabled(e)) continue;
                found.Add(new ScreenText(p.Name.Value.Trim(), new Box(r.X - area.Left, r.Y - area.Top, r.Width, r.Height), KindOf(e)));
            }
            catch (Exception x) when (x is System.Runtime.InteropServices.COMException or FlaUI.Core.Exceptions.PropertyNotSupportedException) { }
        }
        return found;
    }

    /// <summary>Text of a control that is turned off (WCAG leaves inactive controls out of the contrast it asks for).</summary>
    private static bool InDisabled(AutomationElement e)
    {
        for (var up = e.Parent; up is not null; up = up.Parent)
            if (up.Properties.IsEnabled.TryGetValue(out bool enabled) && !enabled) return true;
        return false;
    }

    /// <summary>Large text by its font size and weight from the Text pattern; body text when the pattern does not say.</summary>
    private static TextKind KindOf(AutomationElement e)
    {
        try
        {
            if (e.Patterns.Text.PatternOrDefault?.DocumentRange is { } range
                && range.GetAttributeValue(e.Automation.TextAttributeLibrary.FontSize) is double points)
            {
                double px = points * 96 / 72;
                int weight = range.GetAttributeValue(e.Automation.TextAttributeLibrary.FontWeight) is int w ? w : 400;
                return ScreenText.KindOf(px, weight, null);
            }
        }
        catch (Exception x) when (x is System.Runtime.InteropServices.COMException or InvalidCastException) { }
        return TextKind.Normal;
    }
}

using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Play.Views;

/// <summary>
/// What Windows tells the music stand: whether a screen reader runs, whether a text field or the touch
/// keyboard is up (the layer never hides then), and keeping the screen on while the stand is open.
/// </summary>
internal static class StandPlatform
{
    private const uint SpiGetScreenReader = 0x0046;
    private const uint EsContinuous = 0x80000000, EsSystemRequired = 0x00000001, EsDisplayRequired = 0x00000002;

    [DllImport("user32.dll", EntryPoint = "SystemParametersInfoW", SetLastError = true)]
    private static extern bool SystemParametersInfo(uint action, uint param, out int value, uint winIni);

    [DllImport("kernel32.dll")]
    private static extern uint SetThreadExecutionState(uint flags);

    /// <summary>Narrator, NVDA or another screen reader (SPI_GETSCREENREADER), or any UIA client following focus.</summary>
    public static bool ScreenReaderRunning()
    {
        try
        {
            if (SystemParametersInfo(SpiGetScreenReader, 0, out int on, 0) && on != 0) return true;
            return AutomationPeer.ListenerExists(AutomationEvents.AutomationFocusChanged);
        }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException or COMException)
        {
            return false;
        }
    }

    /// <summary>A text field has focus, a flyout is open, or the touch keyboard shows.</summary>
    public static bool TextInputOrTouchKeyboard(XamlRoot? root)
    {
        if (root is null) return false;
        if (FocusManager.GetFocusedElement(root) is TextBox or NumberBox or PasswordBox or AutoSuggestBox) return true;
        if (VisualTreeHelper.GetOpenPopupsForXamlRoot(root).Count > 0) return true;
        return TouchKeyboardShown();
    }

    private static bool TouchKeyboardShown()
    {
        try
        {
            if (App.MainWindowInstance is not { } window) return false;
            var pane = Windows.UI.ViewManagement.InputPaneInterop.GetForWindow(WinRT.Interop.WindowNative.GetWindowHandle(window));
            return pane.Visible;
        }
        catch (Exception e) when (e is COMException or InvalidOperationException or ArgumentException)
        {
            return false;
        }
    }

    /// <summary>Keeps the display on while the stand is open (the Win32 counterpart of DisplayRequest; call on the UI thread).</summary>
    public static void KeepScreenOn(bool on)
    {
        try { SetThreadExecutionState(on ? EsContinuous | EsDisplayRequired | EsSystemRequired : EsContinuous); }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException) { }
    }
}

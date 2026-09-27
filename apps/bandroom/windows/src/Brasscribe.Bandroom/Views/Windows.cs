using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Platform;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;

namespace Brasscribe.Bandroom.Views;

internal static class WindowSizing
{
    public static IntPtr Hwnd(Window w) => WinRT.Interop.WindowNative.GetWindowHandle(w);

    public static double Scale(Window w)
    {
        uint dpi = Native.GetDpiForWindow(Hwnd(w));
        return (dpi == 0 ? 96 : dpi) / 96.0;
    }

    /// <summary>The work area (screen minus taskbar) of the monitor holding the point.</summary>
    public static Native.RECT WorkArea(int x, int y)
    {
        var mon = Native.MonitorFromPoint(new Native.POINT { X = x, Y = y }, 2 /* nearest */);
        var info = new Native.MONITORINFO { cbSize = System.Runtime.InteropServices.Marshal.SizeOf<Native.MONITORINFO>() };
        Native.GetMonitorInfo(mon, ref info);
        return info.rcWork;
    }

    public static void Theme(FrameworkElement root, string? theme)
    {
        if (theme is "light") root.RequestedTheme = ElementTheme.Light;
        else if (theme is "dark") root.RequestedTheme = ElementTheme.Dark;
    }
}

/// <summary>
/// The flyout above the notification area (§4): 360 epx wide, height to fit (scrolling past 80 % of the
/// screen), Mica, the Windows 11 flyout corners, light dismiss, Esc back to the icon.
/// </summary>
internal sealed class FlyoutWindow : Window
{
    private readonly BandroomPanel _panel;
    private readonly Func<Native.RECT?> _anchor;
    private readonly ScrollViewer _scroll;

    public FlyoutWindow(BandroomPanel panel, Func<Native.RECT?> anchor, string? theme)
    {
        _panel = panel;
        _anchor = anchor;
        _scroll = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollMode = ScrollMode.Disabled };
        var root = new Grid { Children = { _scroll } };
        WindowSizing.Theme(root, theme);
        root.PreviewKeyDown += OnKey;
        Content = root;
        Title = panel.Vm.Header;
        SystemBackdrop = new MicaBackdrop();
        var p = OverlappedPresenter.Create();
        p.IsResizable = false;
        p.IsMaximizable = false;
        p.IsMinimizable = false;
        p.IsAlwaysOnTop = true;
        p.SetBorderAndTitleBar(true, false);
        AppWindow.SetPresenter(p);
        AppWindow.IsShownInSwitchers = false;
        Activated += (_, e) =>
        {
            if (e.WindowActivationState == WindowActivationState.Deactivated && !Pinned && IsOpen) HideFlyout();
        };
        panel.SizeChangedByContent += () => { if (IsOpen) Place(); };
        panel.Vm.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(panel.Vm.Header)) Title = panel.Vm.Header; };
    }

    /// <summary>Screenshot and scan runs keep the flyout open when something else takes focus.</summary>
    public bool Pinned { get; set; }
    public bool IsOpen { get; private set; }
    public DateTime HiddenAt { get; private set; }

    public event Action? Opened;
    public event Action? Closed2;
    public event Action? EscapedToIcon;

    public void ShowFlyout()
    {
        IsOpen = true;
        Place();
        AppWindow.Show();
        Activate();
        Native.SetForegroundWindow(WindowSizing.Hwnd(this));
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { Place(); _panel.FocusPrimary(); });
        Opened?.Invoke();
    }

    public void HideFlyout()
    {
        if (!IsOpen) return;
        IsOpen = false;
        HiddenAt = DateTime.UtcNow;
        AppWindow.Hide();
        Closed2?.Invoke();
    }

    private void OnKey(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key != Windows.System.VirtualKey.Escape) return;
        e.Handled = true;
        if (_panel.Vm.Escape())
        {
            HideFlyout();
            EscapedToIcon?.Invoke();
        }
    }

    private void Place()
    {
        double scale = WindowSizing.Scale(this);
        int width = (int)Math.Round(360 * scale);
        _panel.Measure(new Windows.Foundation.Size(360, double.PositiveInfinity));
        double contentHeight = _panel.DesiredSize.Height;
        var anchor = _anchor();
        Native.POINT at;
        if (anchor is { } a) at = new Native.POINT { X = (a.Left + a.Right) / 2, Y = (a.Top + a.Bottom) / 2 };
        else Native.GetCursorPos(out at);
        var work = WindowSizing.WorkArea(at.X, at.Y);
        int margin = (int)Math.Round(12 * scale);
        int maxHeight = (int)((work.Bottom - work.Top) * 0.8);
        int height = Math.Min(maxHeight, (int)Math.Ceiling((contentHeight + 2) * scale));
        if (height < 100) height = maxHeight;
        int x = work.Right - width - margin;
        // Above the taskbar at the bottom; below it when the taskbar is at the top.
        bool taskbarTop = anchor is { } r && r.Top <= work.Top;
        int y = taskbarTop ? work.Top + margin : work.Bottom - height - margin;
        AppWindow.MoveAndResize(new RectInt32(x, y, width, height));
    }
}

/// <summary>"Brasscribe on this PC": the same content as a normal window, from the Start menu or past 150 % text size.</summary>
internal sealed class PanelWindow : Window
{
    public PanelWindow(BandroomPanel panel, string title, string? theme)
    {
        Panel = panel;
        var root = new Grid
        {
            Background = BandroomPanel.Res("BcBgBrush"),
            Children = { new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto } },
        };
        WindowSizing.Theme(root, theme);
        Content = root;
        Title = title;
        double scale = WindowSizing.Scale(this);
        AppWindow.Resize(new SizeInt32((int)(420 * scale), (int)(780 * scale)));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico"));
    }

    public BandroomPanel Panel { get; }
}

/// <summary>The Pair a phone window. The engine's pairing window is open exactly as long as this one.</summary>
internal sealed class PairWindow : Window
{
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _timer;

    public PairWindow(PairViewModel vm, string? theme)
    {
        Vm = vm;
        var panel = new PairPanel(vm);
        panel.DoneRequested += Close;
        var root = new Grid { Background = BandroomPanel.Res("BcBgBrush"), Children = { panel } };
        WindowSizing.Theme(root, theme);
        Content = root;
        Title = vm.Title;
        double scale = WindowSizing.Scale(this);
        AppWindow.Resize(new SizeInt32((int)(900 * scale), (int)(760 * scale)));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico"));
        _timer = DispatcherQueue.CreateTimer();
        _timer.Interval = TimeSpan.FromSeconds(2);
        _timer.Tick += async (_, _) => await vm.TickAsync();
        Activated += (_, e) => { if (e.WindowActivationState != WindowActivationState.Deactivated && !_timer.IsRunning) _timer.Start(); };
        Closed += async (_, _) =>
        {
            _timer.Stop();
            await vm.CloseAsync();
        };
        root.Loaded += (_, _) => panel.FocusDone();
    }

    public PairViewModel Vm { get; }
}

/// <summary>"Allow Kari's iPhone?" on its own, when a phone asks while the Pair window is closed.</summary>
internal sealed class AllowWindow : Window
{
    public AllowWindow(AllowRequestViewModel vm, string title, string? theme)
    {
        var card = new AllowCard(vm);
        var root = new Grid { Background = BandroomPanel.Res("BcBgBrush"), Padding = new Thickness(16), Children = { card } };
        WindowSizing.Theme(root, theme);
        Content = root;
        Title = title;
        double scale = WindowSizing.Scale(this);
        AppWindow.Resize(new SizeInt32((int)(380 * scale), (int)(470 * scale)));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico"));
        if (AppWindow.Presenter is OverlappedPresenter p)
        {
            p.IsAlwaysOnTop = true;
            p.IsMaximizable = false;
            p.IsMinimizable = false;
        }
        vm.Finished += () => DispatcherQueue.TryEnqueue(Close);
        root.Loaded += (_, _) => card.FocusAllow();
    }
}

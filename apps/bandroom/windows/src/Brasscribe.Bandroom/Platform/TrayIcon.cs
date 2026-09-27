using System.Runtime.InteropServices;
using Brasscribe.Bandroom.Core.State;
using Microsoft.Win32;

namespace Brasscribe.Bandroom.Platform;

/// <summary>
/// The notification-area icon (WinUI has no tray API): Shell_NotifyIcon on a message-only window, version 4,
/// so the keyboard works (Win+B, arrows, Enter opens the flyout, Shift+F10 or the Menu key opens the menu).
/// Identified by uID, not a GUID (a GUID is tied to the exe path). Re-added when Explorer restarts.
/// </summary>
internal sealed class TrayIcon : IDisposable
{
    private const int CallbackMessage = Native.WM_USER + 42;
    private const int IconId = 1;
    private readonly Native.WndProc _proc; // kept alive: the window calls it
    private readonly IntPtr _hwnd;
    private readonly uint _taskbarCreated;
    private IntPtr _icon;
    private string _tooltip = "Brasscribe";
    private (TrayBadge Badge, int Pie, bool Light)? _drawn;
    private bool _added;

    public TrayIcon()
    {
        _proc = WndProc;
        var wc = new Native.WNDCLASSEX
        {
            cbSize = (uint)Marshal.SizeOf<Native.WNDCLASSEX>(),
            lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_proc),
            hInstance = Native.GetModuleHandle(null),
            lpszClassName = "BrasscribeBandroomTray",
        };
        Native.RegisterClassEx(ref wc);
        _hwnd = Native.CreateWindowEx(0, wc.lpszClassName, "Brasscribe Bandroom", 0, 0, 0, 0, 0, Native.HWND_MESSAGE, IntPtr.Zero, wc.hInstance, IntPtr.Zero);
        _taskbarCreated = Native.RegisterWindowMessage("TaskbarCreated");
    }

    /// <summary>Click, Enter or Space on the icon.</summary>
    public event Action? Activated;
    /// <summary>Right-click, Shift+F10 or the Menu key: screen coordinates of where to show the menu.</summary>
    public event Action<int, int>? ContextMenuRequested;

    public IntPtr Handle => _hwnd;
    public bool IsShown => _added;
    public string? LastError { get; private set; }

    /// <summary>Shows the state: the badge shape and the accessible name / tooltip (§6.1).</summary>
    public void Update(TrayBadge badge, int pieEighths, string tooltip)
    {
        _tooltip = tooltip.Length > 127 ? tooltip[..127] : tooltip;
        bool light = TaskbarIsLight();
        if (_drawn != (badge, pieEighths, light))
        {
            var old = _icon;
            _icon = CreateIcon(badge, pieEighths, light);
            _drawn = (badge, pieEighths, light);
            if (old != IntPtr.Zero && _added) { Apply(Native.NIM_MODIFY); Native.DestroyIcon(old); return; }
            if (old != IntPtr.Zero) Native.DestroyIcon(old);
        }
        Apply(_added ? Native.NIM_MODIFY : Native.NIM_ADD);
    }

    private void Apply(int message)
    {
        var data = Data();
        data.uFlags = Native.NIF_MESSAGE | Native.NIF_ICON | Native.NIF_TIP | Native.NIF_SHOWTIP;
        if (!Native.Shell_NotifyIcon(message, ref data))
        {
            LastError = $"Shell_NotifyIcon({message}) failed: {Marshal.GetLastPInvokeError()}";
            if (message == Native.NIM_MODIFY) { _added = false; Apply(Native.NIM_ADD); }
            return;
        }
        if (message == Native.NIM_ADD)
        {
            _added = true;
            data.uVersion = Native.NOTIFYICON_VERSION_4;
            Native.Shell_NotifyIcon(Native.NIM_SETVERSION, ref data);
        }
    }

    private Native.NOTIFYICONDATA Data() => new()
    {
        cbSize = Marshal.SizeOf<Native.NOTIFYICONDATA>(),
        hWnd = _hwnd,
        uID = IconId,
        uCallbackMessage = CallbackMessage,
        hIcon = _icon,
        szTip = _tooltip,
        szInfo = "",
        szInfoTitle = "",
    };

    /// <summary>Esc in the flyout returns keyboard focus to the icon.</summary>
    public void Focus()
    {
        var data = Data();
        Native.Shell_NotifyIcon(Native.NIM_SETFOCUS, ref data);
    }

    /// <summary>The icon's rectangle on screen, to place the flyout above it.</summary>
    public Native.RECT? Bounds()
    {
        var id = new Native.NOTIFYICONIDENTIFIER { cbSize = Marshal.SizeOf<Native.NOTIFYICONIDENTIFIER>(), hWnd = _hwnd, uID = IconId };
        return Native.Shell_NotifyIconGetRect(ref id, out var r) == 0 ? r : null;
    }

    private IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == CallbackMessage)
        {
            // Version 4: LOWORD(lParam) is the event, wParam holds the anchor point.
            int ev = (int)(lParam.ToInt64() & 0xFFFF);
            int x = (short)(wParam.ToInt64() & 0xFFFF), y = (short)((wParam.ToInt64() >> 16) & 0xFFFF);
            switch (ev)
            {
                case Native.NIN_SELECT:
                case Native.NIN_KEYSELECT:
                    Activated?.Invoke();
                    break;
                case Native.WM_CONTEXTMENU:
                    ContextMenuRequested?.Invoke(x, y);
                    break;
            }
            return IntPtr.Zero;
        }
        if (msg == _taskbarCreated && _taskbarCreated != 0)
        {
            _added = false; // Explorer restarted: add the icon again
            Apply(Native.NIM_ADD);
            return IntPtr.Zero;
        }
        return Native.DefWindowProc(hWnd, msg, wParam, lParam);
    }

    /// <summary>A native popup menu at (x, y); returns the chosen id or 0.</summary>
    public int ShowMenu(int x, int y, IReadOnlyList<(int Id, string? Text, bool Enabled)> items)
    {
        var menu = Native.CreatePopupMenu();
        try
        {
            foreach (var (id, text, enabled) in items)
                Native.AppendMenu(menu, text is null ? Native.MF_SEPARATOR : Native.MF_STRING | (enabled ? 0 : Native.MF_GRAYED), id, text);
            Native.SetForegroundWindow(_hwnd); // so the menu closes when focus leaves it
            int chosen = Native.TrackPopupMenuEx(menu, Native.TPM_RETURNCMD | Native.TPM_RIGHTBUTTON | Native.TPM_BOTTOMALIGN, x, y, _hwnd, IntPtr.Zero);
            Native.PostMessage(_hwnd, Native.WM_NULL, IntPtr.Zero, IntPtr.Zero);
            return chosen;
        }
        finally { Native.DestroyMenu(menu); }
    }

    /// <summary>Light taskbar: dark ink; dark taskbar (the default): white.</summary>
    private static bool TaskbarIsLight()
    {
        using var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        return k?.GetValue("SystemUsesLightTheme") is int v && v == 1;
    }

    private static IntPtr CreateIcon(TrayBadge badge, int pie, bool lightTaskbar)
    {
        uint dpi = Native.GetDpiForSystem();
        int size = Math.Clamp(Native.GetSystemMetricsForDpi(Native.SM_CXSMICON, dpi), 16, 64);
        var ink = lightTaskbar ? ((byte)0x1B, (byte)0x1A, (byte)0x17) : ((byte)0xFF, (byte)0xFF, (byte)0xFF);
        var px = TrayIconRaster.Render(size, badge, pie, ink);
        var bmi = new Native.BITMAPINFOHEADER
        {
            biSize = Marshal.SizeOf<Native.BITMAPINFOHEADER>(),
            biWidth = size,
            biHeight = -size, // top-down
            biPlanes = 1,
            biBitCount = 32,
        };
        var color = Native.CreateDIBSection(IntPtr.Zero, ref bmi, 0, out var bits, IntPtr.Zero, 0);
        Marshal.Copy(px, 0, bits, px.Length);
        var mask = Native.CreateBitmap(size, size, 1, 1, new byte[((size + 15) / 16) * 2 * size]);
        var info = new Native.ICONINFO { fIcon = true, hbmColor = color, hbmMask = mask };
        var icon = Native.CreateIconIndirect(ref info);
        Native.DeleteObject(color);
        Native.DeleteObject(mask);
        return icon;
    }

    public void Dispose()
    {
        if (_added)
        {
            var data = Data();
            Native.Shell_NotifyIcon(Native.NIM_DELETE, ref data);
            _added = false;
        }
        if (_icon != IntPtr.Zero) Native.DestroyIcon(_icon);
        Native.DestroyWindow(_hwnd);
    }
}

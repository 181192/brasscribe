using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace Brasscribe.ScreenCheck;

/// <summary>The Win32 calls the tool needs: windows of a process, their pictures, the foreground.</summary>
internal static partial class Win
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left, Top, Right, Bottom; }

    private delegate bool EnumProc(nint hwnd, nint lParam);

    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc proc, nint lParam);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(nint hwnd, out Rect rect);
    [DllImport("user32.dll")] private static extern bool PrintWindow(nint hwnd, nint hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(nint hwnd);
    [DllImport("user32.dll")] public static extern nint GetForegroundWindow();

    /// <summary>The visible top-level windows of a process, at least 50 × 50 (the flyout is a tool window).</summary>
    public static List<nint> Visible(int pid)
    {
        var list = new List<nint>();
        EnumWindows((h, _) =>
        {
            GetWindowThreadProcessId(h, out uint p);
            if (p == pid && IsWindowVisible(h) && GetWindowRect(h, out var r) && r.Right - r.Left >= 50 && r.Bottom - r.Top >= 50) list.Add(h);
            return true;
        }, 0);
        return list;
    }

    [DllImport("user32.dll")] private static extern bool GetClientRect(nint hwnd, out Rect rect);

    /// <summary>The whole window as it is drawn, even where it is off screen or covered (PW_RENDERFULLCONTENT); with
    /// <paramref name="client"/>, its client area only (as Play's catalogue takes its screenshots).</summary>
    public static Picture Capture(nint hwnd, bool client = false)
    {
        Rect r;
        if (client) GetClientRect(hwnd, out r);
        else GetWindowRect(hwnd, out r);
        int w = r.Right - r.Left, h = r.Bottom - r.Top;
        using var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            nint hdc = g.GetHdc();
            try { PrintWindow(hwnd, hdc, client ? 3u : 2u); }
            finally { g.ReleaseHdc(hdc); }
        }
        var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            var bytes = new byte[w * h * 4];
            for (int y = 0; y < h; y++) Marshal.Copy(data.Scan0 + y * data.Stride, bytes, y * w * 4, w * 4);
            for (int i = 3; i < bytes.Length; i += 4) bytes[i] = 255; // a window is opaque
            return new Picture(w, h, bytes);
        }
        finally { bmp.UnlockBits(data); }
    }

    /// <summary>The window once it keeps still: pictures 250 ms apart until six in a row are the same, or 20 s pass.</summary>
    public static (Picture Picture, bool Steady) Steady(nint hwnd, bool client = false)
    {
        var start = System.Diagnostics.Stopwatch.StartNew();
        Picture? last = null;
        int same = 0;
        while (start.Elapsed < TimeSpan.FromSeconds(20))
        {
            Thread.Sleep(250);
            var now = Capture(hwnd, client);
            same = last is not null && now.SameAs(last) ? same + 1 : 0;
            last = now;
            if (same >= 5) return (now, true);
        }
        return (last!, false);
    }
}

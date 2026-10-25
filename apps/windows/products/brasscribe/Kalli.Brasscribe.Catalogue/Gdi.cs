using System.Runtime.InteropServices;
using Brasscribe.ScreenCheck;

namespace Brasscribe.Play.Catalogue;

/// <summary>
/// A window's client area as DWM composes it (PrintWindow with PW_CLIENTONLY | PW_RENDERFULLCONTENT), as BGRA, and
/// what says the window is the one to take: shown, not minimised, in front.
/// </summary>
internal static class Gdi
{
    [StructLayout(LayoutKind.Sequential)]
    private struct Rect { public int Left, Top, Right, Bottom; }

    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapInfoHeader
    {
        public int Size, Width, Height;
        public short Planes, BitCount;
        public int Compression, SizeImage, XPelsPerMeter, YPelsPerMeter, ClrUsed, ClrImportant;
    }

    [DllImport("user32.dll")] private static extern bool GetClientRect(nint hwnd, out Rect rect);
    [DllImport("user32.dll")] private static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll")] public static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(nint hwnd);
    [DllImport("user32.dll")] private static extern nint GetDC(nint hwnd);
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint hwnd, nint hdc);
    [DllImport("user32.dll")] private static extern bool PrintWindow(nint hwnd, nint hdc, uint flags);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleDC(nint hdc);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(nint hdc);
    [DllImport("gdi32.dll")] private static extern nint SelectObject(nint hdc, nint obj);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(nint obj);
    [DllImport("gdi32.dll")] private static extern nint CreateDIBSection(nint hdc, ref BitmapInfoHeader info, uint usage, out nint bits, nint section, uint offset);

    private const uint ClientOnly = 1, RenderFullContent = 2;

    /// <summary>The window is there, shown and not minimised.</summary>
    public static bool IsShown(nint hwnd) => IsWindow(hwnd) && IsWindowVisible(hwnd) && !IsIconic(hwnd);

    /// <summary>The client area's size in pixels; (0, 0) when the window is gone.</summary>
    public static (int Width, int Height) ClientSize(nint hwnd) =>
        GetClientRect(hwnd, out var r) ? (r.Right - r.Left, r.Bottom - r.Top) : (0, 0);

    public static Picture CaptureClient(nint hwnd)
    {
        if (!GetClientRect(hwnd, out var r)) throw new InvalidOperationException("the window has no client area");
        int w = r.Right - r.Left, h = r.Bottom - r.Top;
        if (w <= 0 || h <= 0) throw new InvalidOperationException("the window's client area is empty");
        nint screen = GetDC(0);
        nint dc = CreateCompatibleDC(screen);
        // A negative height: rows top to bottom, as Picture has them.
        var info = new BitmapInfoHeader { Size = Marshal.SizeOf<BitmapInfoHeader>(), Width = w, Height = -h, Planes = 1, BitCount = 32 };
        nint bitmap = CreateDIBSection(dc, ref info, 0, out nint bits, 0, 0);
        nint old = SelectObject(dc, bitmap);
        try
        {
            if (!PrintWindow(hwnd, dc, ClientOnly | RenderFullContent)) throw new InvalidOperationException("PrintWindow failed");
            var bytes = new byte[w * h * 4];
            Marshal.Copy(bits, bytes, 0, bytes.Length);
            for (int i = 3; i < bytes.Length; i += 4) bytes[i] = 255; // a window is opaque
            return new Picture(w, h, bytes);
        }
        finally
        {
            SelectObject(dc, old);
            DeleteObject(bitmap);
            DeleteDC(dc);
            ReleaseDC(0, screen);
        }
    }
}

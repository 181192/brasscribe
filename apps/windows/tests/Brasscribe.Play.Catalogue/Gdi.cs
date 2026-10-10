using System.Runtime.InteropServices;
using Brasscribe.ScreenCheck;

namespace Brasscribe.Play.Catalogue;

/// <summary>A window's client area as DWM composes it (PrintWindow with PW_CLIENTONLY | PW_RENDERFULLCONTENT), as BGRA.</summary>
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
    [DllImport("user32.dll")] private static extern nint GetDC(nint hwnd);
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint hwnd, nint hdc);
    [DllImport("user32.dll")] private static extern bool PrintWindow(nint hwnd, nint hdc, uint flags);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleDC(nint hdc);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(nint hdc);
    [DllImport("gdi32.dll")] private static extern nint SelectObject(nint hdc, nint obj);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(nint obj);
    [DllImport("gdi32.dll")] private static extern nint CreateDIBSection(nint hdc, ref BitmapInfoHeader info, uint usage, out nint bits, nint section, uint offset);

    private const uint ClientOnly = 1, RenderFullContent = 2;

    public static Picture CaptureClient(nint hwnd)
    {
        if (!GetClientRect(hwnd, out var r)) throw new InvalidOperationException("the window has no client area");
        int w = r.Right - r.Left, h = r.Bottom - r.Top;
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

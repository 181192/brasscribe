using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// Windows settings of this user that a catalogue run is taken in: a contrast theme (SPI_SETHIGHCONTRAST, the
/// same switch as Settings › Accessibility › Contrast themes) and the text size (Settings › Accessibility › Text size,
/// the TextScaleFactor value, read by apps when they start). Meant for a CI runner: on a PC of your own it changes
/// your settings until it is turned off again.
/// </summary>
internal static class SystemState
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct HighContrast
    {
        public int Size;
        public int Flags;
        public nint Scheme;
    }

    private const int GetHighContrast = 0x0042, SetHighContrast = 0x0043, On = 0x1;
    private const int UpdateIniFile = 0x1, SendChange = 0x2;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SystemParametersInfo(int action, int param, ref HighContrast value, int winIni);

    [DllImport("user32.dll")]
    private static extern uint GetSysColor(int index);

    public static int Run(Options o)
    {
        if (o.Get("contrast") is { } contrast) Contrast(contrast == "on");
        if (o.Get("text-scale") is { } scale)
        {
            string keep = o.Need("keep");
            if (scale == "restore")
            {
                string before = File.Exists(keep) ? File.ReadAllText(keep).Trim() : "none";
                TextScale(before == "none" ? null : int.Parse(before));
                File.Delete(keep);
            }
            else
            {
                using (var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Accessibility"))
                    File.WriteAllText(keep, key?.GetValue("TextScaleFactor") is int now ? now.ToString() : "none");
                TextScale(int.Parse(scale));
            }
        }
        Report();
        return 0;
    }

    private static void Contrast(bool on)
    {
        var hc = new HighContrast { Size = Marshal.SizeOf<HighContrast>(), Flags = on ? On : 0 };
        if (!SystemParametersInfo(SetHighContrast, hc.Size, ref hc, UpdateIniFile | SendChange))
            throw new InvalidOperationException($"SPI_SETHIGHCONTRAST failed: {Marshal.GetLastWin32Error()}");
        Thread.Sleep(3000); // apps and the theme service take the change in
        if (IsContrastOn() != on) throw new InvalidOperationException($"the contrast theme did not turn {(on ? "on" : "off")}");
    }

    private static bool IsContrastOn()
    {
        var hc = new HighContrast { Size = Marshal.SizeOf<HighContrast>() };
        return SystemParametersInfo(GetHighContrast, hc.Size, ref hc, 0) && (hc.Flags & On) != 0;
    }

    private static void TextScale(int? percent)
    {
        using var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Accessibility");
        if (percent is { } p)
        {
            if (p is < 100 or > 225) throw new UsageException("--text-scale is 100 to 225 (per cent) or off");
            key.SetValue("TextScaleFactor", p, RegistryValueKind.DWord);
        }
        else key.DeleteValue("TextScaleFactor", throwOnMissingValue: false);
    }

    private static void Report()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Accessibility");
        // COLOR_WINDOW 5, COLOR_WINDOWTEXT 8: a contrast theme's ground and text.
        static string Rgb(uint bgr) => $"#{bgr & 0xFF:X2}{bgr >> 8 & 0xFF:X2}{bgr >> 16 & 0xFF:X2}";
        Console.WriteLine($"contrast theme: {(IsContrastOn() ? "on" : "off")} (window {Rgb(GetSysColor(5))}, text {Rgb(GetSysColor(8))}); " +
                          $"TextScaleFactor: {key?.GetValue("TextScaleFactor") ?? "not set"}");
    }
}

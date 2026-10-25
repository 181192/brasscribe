using Kalli.Scribe;
using Kalli.Scribe.WinUI;

namespace Kalli.Brasscribe;

/// <summary>What makes this app Brasscribe Play among the apps on the shared core, and keeps it apart from them on one PC.</summary>
internal static class Product
{
    /// <summary>The app's name in its credential vault ("Brasscribe engine").</summary>
    public const string Name = "Brasscribe";

    /// <summary>It arranges for a band.</summary>
    public static Target Target => Target.Brass;

    /// <summary>Settings, the work folder, the crash log: %LOCALAPPDATA%\Brasscribe\Play.</summary>
    public static readonly AppFolder Folder = new(Path.Combine("Brasscribe", "Play"));

    /// <summary>Another launch with a pairing link is sent to the running app under this key.</summary>
    public const string InstanceKey = "BrasscribePlay";

    /// <summary>The hidden Pink palette, merged in while Pink is chosen.</summary>
    public const string PinkTheme = "ms-appx:///Themes/BrasscribePinkTheme.xaml";
}

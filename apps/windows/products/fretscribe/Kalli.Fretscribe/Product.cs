using Kalli.Scribe;
using Kalli.Scribe.WinUI;

namespace Kalli.Fretscribe;

/// <summary>What makes this app Fretscribe among the apps on the shared core, and keeps it apart from them on one PC.</summary>
internal static class Product
{
    /// <summary>The app's name in its credential vault ("Fretscribe engine").</summary>
    public const string Name = "Fretscribe";

    /// <summary>It writes tab for a fretted instrument.</summary>
    public static Target Target => Target.Fretted;

    /// <summary>Settings, the work folder, the practice recordings, the crash log: %LOCALAPPDATA%\Fretscribe.</summary>
    public static readonly AppFolder Folder = new("Fretscribe");

    /// <summary>Another launch with a pairing link is sent to the running app under this key.</summary>
    public const string InstanceKey = "Fretscribe";
}

namespace Kalli.Scribe.WinUI;

/// <summary>
/// Where an app keeps its own files: a folder under %LOCALAPPDATA% that no other app on the PC shares (the apps
/// run unpackaged). Settings, the work folder, the crash log and the credential fallback are in it.
/// </summary>
/// <param name="Name">The folder under %LOCALAPPDATA%, which may have more than one level ("Brasscribe\Play").</param>
public sealed record AppFolder(string Name)
{
    public string Root => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), Name);
    public string Work => Path.Combine(Root, "work");
    public string Settings => Path.Combine(Root, "settings.json");
    public string CrashLog => Path.Combine(Root, "crash.log");
    public string Credentials => Path.Combine(Root, "credentials.bin");
}

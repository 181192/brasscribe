namespace Brasscribe.Bandroom.Core;

/// <summary>The name phones see this PC by: the device name, or one set in Settings › Name shown to phones.</summary>
public static class ComputerName
{
    /// <summary>
    /// A name nobody chose: Windows' default ("DESKTOP-4F2K9QZ") or a serial-like hostname. Capital letters and
    /// digits (and hyphens), at least 8 characters, no spaces, with at least one digit.
    /// </summary>
    public static bool LooksMachineGenerated(string name)
    {
        string n = name.Trim();
        return n.Length >= 8 && n.All(c => c is (>= 'A' and <= 'Z') or (>= '0' and <= '9') or '-') && n.Any(char.IsAsciiDigit);
    }

    /// <summary>The name phones see: the one set in Settings, else the computer's own.</summary>
    public static string Shown(string system, string? custom) => custom?.Trim() is { Length: > 0 } c ? c : system;

    /// <summary>Settings offers its own field only when the computer's name looks machine-made, or one is already set.</summary>
    public static bool OffersCustomName(string system, string? custom) =>
        LooksMachineGenerated(system) || !string.IsNullOrWhiteSpace(custom);
}

/// <summary>Stores the name shown to phones on this PC only (a one-line file in Bandroom's state folder).</summary>
public sealed class ComputerNameStore(string filePath)
{
    public string FilePath { get; } = filePath;

    /// <summary>The name set in Settings, or null.</summary>
    public string? Load()
    {
        try { return File.Exists(FilePath) && File.ReadAllText(FilePath).Trim() is { Length: > 0 } n ? n : null; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }

    /// <summary>An empty name removes it, so phones see the computer's own name again.</summary>
    /// <returns>False when the file can't be written.</returns>
    public bool Save(string? name)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(name))
            {
                if (File.Exists(FilePath)) File.Delete(FilePath);
                return true;
            }
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            File.WriteAllText(FilePath, name.Trim());
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }
}

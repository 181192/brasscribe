using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;

namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// The engine's admin credential: 256 random bits, made on first run and kept in a file only this user
/// can read (an ACL with inheritance removed and one FullControl rule for the current user on Windows;
/// mode 0600 elsewhere). Bandroom passes it to the engine as BRASSCRIBE_ADMIN_TOKEN and sends it as the
/// bearer on owner calls. It is never written to engine.json, logs or diagnostics.
/// </summary>
public static class AdminCredential
{
    public static string LoadOrCreate(string path)
    {
        if (File.Exists(path))
        {
            var existing = File.ReadAllText(path).Trim();
            if (existing.Length >= 32)
            {
                Restrict(path);
                return existing;
            }
        }
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string token = Base64Url(RandomNumberGenerator.GetBytes(32));
        // Create empty, restrict, then write: the secret is never in a file others can read.
        using (File.Create(path)) { }
        Restrict(path);
        File.WriteAllText(path, token);
        return token;
    }

    private static string Base64Url(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public static void Restrict(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            var user = WindowsIdentity.GetCurrent().User ?? throw new InvalidOperationException("no user SID");
            var security = new FileSecurity();
            security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
            security.SetOwner(user);
            security.AddAccessRule(new FileSystemAccessRule(user, FileSystemRights.FullControl, AccessControlType.Allow));
            new FileInfo(path).SetAccessControl(security);
        }
        else
        {
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
    }

    /// <summary>Only the current user may read the file (for tests and the diagnostics check).</summary>
    public static bool IsRestricted(string path)
    {
        if (OperatingSystem.IsWindows()) return IsRestrictedWindows(path);
        var mode = File.GetUnixFileMode(path);
        return (mode & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.OtherRead | UnixFileMode.OtherWrite)) == 0;
    }

    [System.Runtime.Versioning.SupportedOSPlatform("windows")]
    private static bool IsRestrictedWindows(string path)
    {
        var user = WindowsIdentity.GetCurrent().User;
        var rules = new FileInfo(path).GetAccessControl().GetAccessRules(true, true, typeof(SecurityIdentifier));
        foreach (FileSystemAccessRule r in rules)
            if (!r.IdentityReference.Equals(user) && r.AccessControlType != AccessControlType.Deny) return false;
        return true;
    }
}

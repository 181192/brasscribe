using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Kalli.Scribe.Engine;
using Windows.Security.Credentials;

namespace Kalli.Scribe.WinUI;

/// <summary>
/// The engine credential in the Windows Credential Locker (PasswordVault): resource "&lt;app&gt; engine", user name =
/// server id. The locker is the user's, shared by every app: the app's name keeps each app's pairings its own.
/// </summary>
public sealed class CredentialLockerVault(string app) : ISecretVault
{
    private readonly PasswordVault _vault = new();

    private string Own(string resource) => $"{app} {resource}";

    public string? Get(string resource, string key)
    {
        try
        {
            var credential = _vault.Retrieve(Own(resource), key);
            credential.RetrievePassword();
            return credential.Password;
        }
        catch (COMException) { return null; } // not found
    }

    public void Set(string resource, string key, string secret)
    {
        Remove(resource, key); // Add does not replace an existing entry
        _vault.Add(new PasswordCredential(Own(resource), key, secret));
    }

    public void Remove(string resource, string key)
    {
        try { _vault.Remove(_vault.Retrieve(Own(resource), key)); }
        catch (COMException) { }
    }

    public IReadOnlyList<string> Keys(string resource)
    {
        try { return _vault.FindAllByResource(Own(resource)).Select(c => c.UserName).ToList(); }
        catch (COMException) { return []; } // none stored
    }

    /// <summary>The Credential Locker, or a DPAPI-protected file in the app's folder when the locker can't be used here.</summary>
    public static ISecretVault Create(string app, AppFolder folder)
    {
        try
        {
            var vault = new CredentialLockerVault(app);
            vault.Keys(EngineCredentials.Resource);
            return vault;
        }
        catch (Exception e) when (e is COMException or TypeLoadException or InvalidCastException or UnauthorizedAccessException)
        {
            return new DpapiFileVault(app, folder);
        }
    }
}

/// <summary>
/// Fallback: the secrets in the app's credentials.bin, encrypted for the current Windows user with DPAPI
/// (CryptProtectData), so the file is useless to anyone else or on another PC. Resources are stored as
/// "&lt;app&gt; &lt;resource&gt;", the names the Credential Locker has.
/// </summary>
public sealed class DpapiFileVault(string app, AppFolder folder) : ISecretVault
{
    private readonly string _path = folder.Credentials;
    private readonly string _description = $"{app} {EngineCredentials.Resource}";

    private string Own(string resource) => $"{app} {resource}";

    public string? Get(string resource, string key) => Load().GetValueOrDefault(Own(resource) + "\n" + key);

    public void Set(string resource, string key, string secret)
    {
        var all = Load();
        all[Own(resource) + "\n" + key] = secret;
        Save(all);
    }

    public void Remove(string resource, string key)
    {
        var all = Load();
        if (all.Remove(Own(resource) + "\n" + key)) Save(all);
    }

    public IReadOnlyList<string> Keys(string resource)
    {
        string prefix = Own(resource) + "\n";
        return Load().Keys.Where(k => k.StartsWith(prefix, StringComparison.Ordinal)).Select(k => k[prefix.Length..]).ToList();
    }

    private Dictionary<string, string> Load()
    {
        try
        {
            if (!File.Exists(_path)) return [];
            var plain = Unprotect(File.ReadAllBytes(_path));
            return JsonSerializer.Deserialize<Dictionary<string, string>>(Encoding.UTF8.GetString(plain)) ?? [];
        }
        catch (Exception e) when (e is IOException or JsonException or COMException or UnauthorizedAccessException) { return []; }
    }

    private void Save(Dictionary<string, string> all)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        File.WriteAllBytes(_path, Protect(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(all))));
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob
    {
        public int Size;
        public nint Data;
    }

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptProtectData(ref DataBlob input, string? description, nint entropy, nint reserved, nint prompt, int flags, out DataBlob output);

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptUnprotectData(ref DataBlob input, nint description, nint entropy, nint reserved, nint prompt, int flags, out DataBlob output);

    [DllImport("kernel32.dll")]
    private static extern nint LocalFree(nint memory);

    private const int UiForbidden = 0x1;

    private byte[] Protect(byte[] data) => Crypt(data, _description, protect: true);
    private static byte[] Unprotect(byte[] data) => Crypt(data, null, protect: false);

    private static byte[] Crypt(byte[] data, string? description, bool protect)
    {
        var handle = GCHandle.Alloc(data, GCHandleType.Pinned);
        try
        {
            var input = new DataBlob { Size = data.Length, Data = handle.AddrOfPinnedObject() };
            bool ok = protect
                ? CryptProtectData(ref input, description, 0, 0, 0, UiForbidden, out var output)
                : CryptUnprotectData(ref input, 0, 0, 0, 0, UiForbidden, out output);
            if (!ok) throw new COMException("DPAPI failed", Marshal.GetHRForLastWin32Error());
            try
            {
                var result = new byte[output.Size];
                Marshal.Copy(output.Data, result, 0, output.Size);
                return result;
            }
            finally { LocalFree(output.Data); }
        }
        finally { handle.Free(); }
    }
}

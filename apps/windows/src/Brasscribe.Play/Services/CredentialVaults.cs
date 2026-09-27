using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Brasscribe.Play.Core.Engine;
using Windows.Security.Credentials;

namespace Brasscribe.Play.Services;

/// <summary>The engine credential in the Windows Credential Locker (PasswordVault): resource "Brasscribe engine", user name = server id.</summary>
public sealed class CredentialLockerVault : ISecretVault
{
    private readonly PasswordVault _vault = new();

    public string? Get(string resource, string key)
    {
        try
        {
            var credential = _vault.Retrieve(resource, key);
            credential.RetrievePassword();
            return credential.Password;
        }
        catch (COMException) { return null; } // not found
    }

    public void Set(string resource, string key, string secret)
    {
        Remove(resource, key); // Add does not replace an existing entry
        _vault.Add(new PasswordCredential(resource, key, secret));
    }

    public void Remove(string resource, string key)
    {
        try { _vault.Remove(_vault.Retrieve(resource, key)); }
        catch (COMException) { }
    }

    public IReadOnlyList<string> Keys(string resource)
    {
        try { return _vault.FindAllByResource(resource).Select(c => c.UserName).ToList(); }
        catch (COMException) { return []; } // none stored
    }

    /// <summary>The Credential Locker, or a DPAPI-protected file when the locker can't be used here.</summary>
    public static ISecretVault Create()
    {
        try
        {
            var vault = new CredentialLockerVault();
            vault.Keys(EngineCredentials.Resource);
            return vault;
        }
        catch (Exception e) when (e is COMException or TypeLoadException or InvalidCastException or UnauthorizedAccessException)
        {
            return new DpapiFileVault();
        }
    }
}

/// <summary>
/// Fallback: the secrets in %LOCALAPPDATA%\Brasscribe\Play\credentials.bin, encrypted for the current
/// Windows user with DPAPI (CryptProtectData), so the file is useless to anyone else or on another PC.
/// </summary>
public sealed class DpapiFileVault : ISecretVault
{
    private readonly string _path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "Play", "credentials.bin");

    public string? Get(string resource, string key) => Load().GetValueOrDefault(resource + "\n" + key);

    public void Set(string resource, string key, string secret)
    {
        var all = Load();
        all[resource + "\n" + key] = secret;
        Save(all);
    }

    public void Remove(string resource, string key)
    {
        var all = Load();
        if (all.Remove(resource + "\n" + key)) Save(all);
    }

    public IReadOnlyList<string> Keys(string resource) =>
        Load().Keys.Where(k => k.StartsWith(resource + "\n", StringComparison.Ordinal)).Select(k => k[(resource.Length + 1)..]).ToList();

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

    private static byte[] Protect(byte[] data) => Crypt(data, protect: true);
    private static byte[] Unprotect(byte[] data) => Crypt(data, protect: false);

    private static byte[] Crypt(byte[] data, bool protect)
    {
        var handle = GCHandle.Alloc(data, GCHandleType.Pinned);
        try
        {
            var input = new DataBlob { Size = data.Length, Data = handle.AddrOfPinnedObject() };
            bool ok = protect
                ? CryptProtectData(ref input, "Brasscribe engine", 0, 0, 0, UiForbidden, out var output)
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

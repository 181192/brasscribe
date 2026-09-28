using System.Runtime.InteropServices;
using System.Text;

namespace Brasscribe.Bandroom.Platform;

/// <summary>
/// The user's own Hugging Face access key, which the band writer's download needs. HF_TOKEN in the environment
/// wins; otherwise the key saved in Settings, kept in Windows Credential Manager for this user only.
/// </summary>
internal static class HuggingFaceKey
{
    public const string Target = "Brasscribe/HuggingFace";

    /// <summary>HF_TOKEN, else the saved key; null when there is neither.</summary>
    public static string? Current() => FromEnvironment() ?? Read();

    public static string? FromEnvironment() =>
        Environment.GetEnvironmentVariable("HF_TOKEN") is { } t && !string.IsNullOrWhiteSpace(t) ? t.Trim() : null;

    public static string? Read()
    {
        if (!Native.CredRead(Target, Native.CRED_TYPE_GENERIC, 0, out var ptr)) return null;
        try
        {
            var cred = Marshal.PtrToStructure<Native.CREDENTIAL>(ptr);
            if (cred.CredentialBlob == IntPtr.Zero || cred.CredentialBlobSize == 0) return null;
            var bytes = new byte[cred.CredentialBlobSize];
            Marshal.Copy(cred.CredentialBlob, bytes, 0, bytes.Length);
            return Encoding.UTF8.GetString(bytes) is { Length: > 0 } key ? key : null;
        }
        finally { Native.CredFree(ptr); }
    }

    /// <summary>Saves the key (an empty one deletes it).</summary>
    /// <returns>False when Credential Manager refused.</returns>
    public static bool Save(string? key)
    {
        if (string.IsNullOrWhiteSpace(key))
            return Native.CredDelete(Target, Native.CRED_TYPE_GENERIC, 0) || Marshal.GetLastWin32Error() == Native.ERROR_NOT_FOUND;
        var bytes = Encoding.UTF8.GetBytes(key.Trim());
        var blob = Marshal.AllocHGlobal(bytes.Length);
        try
        {
            Marshal.Copy(bytes, 0, blob, bytes.Length);
            var cred = new Native.CREDENTIAL
            {
                Type = Native.CRED_TYPE_GENERIC,
                TargetName = Target,
                CredentialBlob = blob,
                CredentialBlobSize = (uint)bytes.Length,
                Persist = Native.CRED_PERSIST_LOCAL_MACHINE,
                UserName = "huggingface.co",
            };
            return Native.CredWrite(ref cred, 0);
        }
        finally
        {
            Marshal.FreeHGlobal(blob);
        }
    }
}

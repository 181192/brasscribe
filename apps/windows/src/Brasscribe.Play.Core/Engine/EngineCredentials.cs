using System.Text.Json;
using System.Text.Json.Serialization;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Engine;

/// <summary>
/// A small secret store: one secret per (resource, key). Windows keeps it in the Credential Locker
/// (PasswordVault); tests use <see cref="InMemorySecretVault"/>.
/// </summary>
public interface ISecretVault
{
    string? Get(string resource, string key);
    void Set(string resource, string key, string secret);
    void Remove(string resource, string key);
    IReadOnlyList<string> Keys(string resource);
}

public sealed class InMemorySecretVault : ISecretVault
{
    private readonly Dictionary<(string, string), string> _values = [];
    public string? Get(string resource, string key) => _values.GetValueOrDefault((resource, key));
    public void Set(string resource, string key, string secret) => _values[(resource, key)] = secret;
    public void Remove(string resource, string key) => _values.Remove((resource, key));
    public IReadOnlyList<string> Keys(string resource) => _values.Keys.Where(k => k.Item1 == resource).Select(k => k.Item2).ToList();
}

/// <summary>
/// What this device keeps per engine (docs/plan/pairing-and-remote-access.md §4.5). Only the token is
/// secret, but the whole record is small and lives in the vault so it moves with the device the same way.
/// </summary>
public sealed record EngineCredential(
    string ServerId,
    string Token,
    string? ServerName = null,
    string? DeviceId = null,
    string? LastAddress = null,
    DateTimeOffset? LastOk = null,
    DateTimeOffset? RotateAfter = null);

/// <summary>
/// The paired engines, one record per server id, plus which one is in use. A credential belongs to a
/// server id, never to an address: a new address never drops it, and only a 401 does.
/// </summary>
public sealed class EngineCredentials
{
    public const string Resource = "Brasscribe engine";

    /// <summary>Holds a token moved from the old settings.json until the engine tells us its server id.</summary>
    public const string LegacyKey = "legacy";

    private const string CurrentKey = "EngineServerId";
    private const string LegacyTokenKey = "EngineToken";
    private const string LegacyAddressKey = "EngineAddress";

    private readonly ISecretVault _vault;
    private readonly ISettingsStore _settings;

    public EngineCredentials(ISecretVault vault, ISettingsStore settings)
    {
        _vault = vault;
        _settings = settings;
        MigrateLegacy();
    }

    /// <summary>The server id of the engine in use; null before the first pairing.</summary>
    public string? CurrentServerId
    {
        get => _settings.Get<string?>(CurrentKey, null);
        set => _settings.Set(CurrentKey, value);
    }

    public EngineCredential? Current => CurrentServerId is { } id ? Get(id) : null;

    public EngineCredential? Get(string serverId)
    {
        var json = SafeGet(serverId);
        if (json is null) return null;
        try { return JsonSerializer.Deserialize(json, CredentialJsonContext.Default.EngineCredential); }
        catch (JsonException) { return null; }
    }

    public IReadOnlyList<EngineCredential> All() => SafeKeys().Select(Get).OfType<EngineCredential>().ToList();

    /// <summary>Stores a record (the new token is written here before it is used) and makes it the one in use.</summary>
    public void Save(EngineCredential credential, bool makeCurrent = true)
    {
        _vault.Set(Resource, credential.ServerId, JsonSerializer.Serialize(credential, CredentialJsonContext.Default.EngineCredential));
        if (makeCurrent) CurrentServerId = credential.ServerId;
    }

    public void Remove(string serverId)
    {
        try { _vault.Remove(Resource, serverId); }
        catch (Exception e) when (e is not OutOfMemoryException) { }
    }

    /// <summary>
    /// The first successful check of a moved token tells us its server id: the record moves to that key,
    /// unless a newer record already sits there.
    /// </summary>
    public EngineCredential Adopt(EngineCredential legacy, string serverId, string? serverName)
    {
        var record = Get(serverId) ?? legacy with { ServerId = serverId, ServerName = serverName ?? legacy.ServerName };
        Save(record);
        if (legacy.ServerId == LegacyKey) Remove(LegacyKey);
        return record;
    }

    /// <summary>
    /// Once: a token from the old plain settings.json moves into the vault (under <see cref="LegacyKey"/>,
    /// since the old store never knew the server id), and the plain copy is deleted. Running it again
    /// changes nothing, and it never overwrites a record already in the vault.
    /// </summary>
    private void MigrateLegacy()
    {
        var token = _settings.Get<string?>(LegacyTokenKey, null);
        if (string.IsNullOrEmpty(token)) return;
        if (SafeGet(LegacyKey) is null && CurrentServerId is null)
        {
            var address = _settings.Get<string?>(LegacyAddressKey, null);
            try { Save(new EngineCredential(LegacyKey, token, LastAddress: address)); }
            catch (Exception e) when (e is not OutOfMemoryException) { return; } // keep the plain copy rather than lose the pairing
        }
        _settings.Set<string?>(LegacyTokenKey, null);
    }

    private string? SafeGet(string key)
    {
        try { return _vault.Get(Resource, key); }
        catch (Exception e) when (e is not OutOfMemoryException) { return null; }
    }

    private IReadOnlyList<string> SafeKeys()
    {
        try { return _vault.Keys(Resource); }
        catch (Exception e) when (e is not OutOfMemoryException) { return []; }
    }
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(EngineCredential))]
internal sealed partial class CredentialJsonContext : JsonSerializerContext;

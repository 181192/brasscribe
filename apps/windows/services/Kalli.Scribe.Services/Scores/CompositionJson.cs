using System.Text.Json;
using System.Text.Json.Serialization;

namespace Brasscribe.Play.Core.Scores;

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
    DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    WriteIndented = false)]
[JsonSerializable(typeof(Composition))]
internal sealed partial class CompositionJsonContext : JsonSerializerContext;

/// <summary>Reads and writes Composition JSON with source-generated serialization.</summary>
public static class CompositionJson
{
    public static Composition Parse(string json) =>
        JsonSerializer.Deserialize(json, CompositionJsonContext.Default.Composition)
        ?? throw new JsonException("Composition JSON is null");

    public static async Task<Composition> ParseAsync(Stream utf8, CancellationToken ct = default) =>
        await JsonSerializer.DeserializeAsync(utf8, CompositionJsonContext.Default.Composition, ct).ConfigureAwait(false)
        ?? throw new JsonException("Composition JSON is null");

    public static string Serialize(Composition composition) =>
        JsonSerializer.Serialize(composition, CompositionJsonContext.Default.Composition);
}

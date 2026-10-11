namespace Brasscribe.Bandroom.Core.Engine;

/// <summary>The number Bandroom shares with the engine it starts.</summary>
public static class Wire
{
    /// <summary>
    /// The interface version this Bandroom is built for. The engine says its own in <c>GET /v1/health</c>; when the
    /// two differ Bandroom says which of them to update and asks that engine nothing else, but for closing the
    /// pairing code it opened when it started (<see cref="InterfaceMatch"/>).
    /// </summary>
    public const int InterfaceVersion = 1;
}

/// <summary>What gets the engine and Bandroom to the same interface version again.</summary>
public enum InterfaceFix
{
    /// <summary>The engine is older and this Bandroom bundles a newer one: the update, from this app.</summary>
    UpdateEngine,
    /// <summary>The engine is newer, or it is older and this Bandroom has no newer one to install: the latest Bandroom.</summary>
    LatestBandroom,
    /// <summary>The engine comes from a developer's folder: nothing this app can do. The words say so, with no button.</summary>
    None,
}

/// <summary>What the engine's interface version means for this Bandroom.</summary>
public enum InterfaceAnswer
{
    /// <summary>The same number: the two work together.</summary>
    Same,
    /// <summary>The engine's number is higher: this Bandroom is the older one.</summary>
    UpdateBandroom,
    /// <summary>The engine's number is lower, or it has none that can be read: the engine is the one to update.</summary>
    UpdateEngine,
}

public static class InterfaceMatch
{
    /// <summary>Compares the number in an engine's health answer with <see cref="Wire.InterfaceVersion"/>.</summary>
    public static InterfaceAnswer Of(int? engine) => engine switch
    {
        Wire.InterfaceVersion => InterfaceAnswer.Same,
        > Wire.InterfaceVersion => InterfaceAnswer.UpdateBandroom,
        _ => InterfaceAnswer.UpdateEngine,
    };

    /// <summary>
    /// The interface version in a health answer, or null when it has none that is a whole number in range: a float, a
    /// string, a bool or a number too large counts as none (the engine is the one to update), not as no answer.
    /// </summary>
    public static int? Read(System.Text.Json.JsonElement health) =>
        health.ValueKind == System.Text.Json.JsonValueKind.Object && health.TryGetProperty("interface_version", out var v)
        && v.ValueKind == System.Text.Json.JsonValueKind.Number && v.TryGetInt32(out int n) ? n : null;

    /// <summary>
    /// The fix that is offered. It is never one that would do nothing: the update from this app only while this app
    /// has another engine than the installed one (<paramref name="updatePending"/>: the workspace it bundles is not
    /// the one installed) and has not already tried (<paramref name="updateTried"/>: the update was run for this, and
    /// the engine that came up still does not match); an engine from a developer's folder
    /// (<paramref name="development"/>) is the developer's to update.
    /// </summary>
    public static InterfaceFix FixFor(InterfaceAnswer match, bool development, bool updatePending, bool updateTried) =>
        development ? InterfaceFix.None
        : match == InterfaceAnswer.UpdateEngine && updatePending && !updateTried ? InterfaceFix.UpdateEngine
        : InterfaceFix.LatestBandroom;
}

namespace Kalli.Scribe.Engine;

/// <summary>
/// The names and the number this app shares with the engine. The link and the network service carry the
/// family's name, not a product's: one engine serves every app.
/// </summary>
public static class Wire
{
    /// <summary>The scheme of the pairing link in the computer's QR code: <c>scribe://pair?…</c>.</summary>
    public const string PairScheme = "scribe";

    /// <summary>The DNS-SD service an engine on the local network advertises.</summary>
    public const string ServiceType = "_scribe._tcp";

    /// <summary>
    /// The interface version this app is built for. The engine says its own in <c>GET /v1/health</c> and, to a paired
    /// device, in <c>GET /v1/devices/me</c>; when the two differ the app says which of them to update and sends that
    /// engine nothing but those two (<see cref="InterfaceMatch"/>, <see cref="EngineClient"/>).
    /// </summary>
    public const int InterfaceVersion = 1;
}

/// <summary>What the engine's interface version means for this app.</summary>
public enum InterfaceAnswer
{
    /// <summary>The same number: the two work together.</summary>
    Same,
    /// <summary>The engine's number is higher: this app is the older one.</summary>
    UpdateApp,
    /// <summary>The engine's number is lower, or it has none that can be read: the computer's side is the one to update.</summary>
    UpdateBandroom,
}

public static class InterfaceMatch
{
    /// <summary>Compares the number in an engine's health answer with <see cref="Wire.InterfaceVersion"/>.</summary>
    public static InterfaceAnswer Of(int? engine) => engine switch
    {
        Wire.InterfaceVersion => InterfaceAnswer.Same,
        > Wire.InterfaceVersion => InterfaceAnswer.UpdateApp,
        _ => InterfaceAnswer.UpdateBandroom,
    };

    /// <summary>
    /// The interface version in an answer, or null when it has none that is a whole number in range: a float, a
    /// string, a bool or a number too large counts as none.
    /// </summary>
    public static int? Read(System.Text.Json.JsonElement answer) =>
        answer.ValueKind == System.Text.Json.JsonValueKind.Object && answer.TryGetProperty("interface_version", out var v)
        && v.ValueKind == System.Text.Json.JsonValueKind.Number && v.TryGetInt32(out int n) ? n : null;

    /// <summary>The two numbers in English, for technical details only: never the message.</summary>
    public static string Details(int? engineVersion) => string.Create(System.Globalization.CultureInfo.InvariantCulture,
        $"The engine's interface version is {(engineVersion is { } v ? v : "not given as a whole number")}; this app is built for {Wire.InterfaceVersion}.");
}

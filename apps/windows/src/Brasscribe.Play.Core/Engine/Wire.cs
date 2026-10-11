namespace Brasscribe.Play.Core.Engine;

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
    /// The interface version this app is built for. The engine says its own in <c>GET /v1/health</c>; when the
    /// two differ the app says which of them to update and sends that engine nothing else (<see cref="InterfaceMatch"/>).
    /// </summary>
    public const int InterfaceVersion = 1;
}

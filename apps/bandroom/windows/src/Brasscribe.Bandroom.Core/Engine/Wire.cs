namespace Brasscribe.Bandroom.Core.Engine;

/// <summary>The number Bandroom shares with the engine it starts.</summary>
public static class Wire
{
    /// <summary>
    /// The interface version this Bandroom is built for. The engine says its own in <c>GET /v1/health</c>; when the
    /// two differ Bandroom says which of them to update and asks that engine nothing else (<see cref="InterfaceMatch"/>).
    /// </summary>
    public const int InterfaceVersion = 1;
}

/// <summary>What the engine's interface version means for this Bandroom.</summary>
public enum InterfaceAnswer
{
    /// <summary>The same number: the two work together.</summary>
    Same,
    /// <summary>The engine's number is higher: this Bandroom is the older one.</summary>
    UpdateBandroom,
    /// <summary>The engine's number is lower, or it has none (an engine from before the number): the engine is the older one.</summary>
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
}

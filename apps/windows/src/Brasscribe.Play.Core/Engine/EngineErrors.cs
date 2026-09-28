using System.Net;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Engine;

/// <summary>
/// The player's words for what went wrong on the engine or in the core. The engine and the core
/// speak English (and seat ids); none of that reaches the screen, in either language.
/// </summary>
public static class EngineErrors
{
    /// <summary>The engine's machine codes on a refused job (the 422 body's <c>code</c>) → string key.</summary>
    private static readonly Dictionary<string, string> Codes = new()
    {
        ["quartet_needs_group"] = "Output_QuartetNeedsGroup",
        ["percussion_solo"] = "Error_PercussionSolo",
        ["seat_no_tune"] = "Error_SeatNoTune",
        ["reads_not_offered"] = "Error_ReadsNotOffered",
        ["invalid_options"] = "Error_Options",
    };

    /// <summary>The string key for an engine failure.</summary>
    public static string Key(EngineException e) => e switch
    {
        { Code: { } code } when Codes.TryGetValue(code, out var key) => key,
        { Code: EngineException.JobFailed } => "Transcribe_Failed",
        { Code: EngineException.Timeout } => "Error_Timeout",
        { Status: null } => "Error_Unreachable",
        { Status: HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden } => "Error_NeedsPairing",
        { Status: HttpStatusCode.NotFound } => "Error_NotFound",
        { Status: HttpStatusCode.UnprocessableEntity } => "Error_Options",
        { Status: HttpStatusCode.RequestEntityTooLarge } => "Error_TooLarge",
        _ => "Error_Engine",
    };

    public static string Message(EngineException e, IStrings s) => s[Key(e)];

    /// <summary>The string key for a core refusal (its English message; the core has no codes).</summary>
    public static string CoreKey(string message) => message switch
    {
        _ when message.Contains("percussion can't be written down", StringComparison.OrdinalIgnoreCase) => "Error_PercussionSolo",
        _ when message.Contains("does not carry the tune", StringComparison.OrdinalIgnoreCase)
            || message.Contains("keeps the tune", StringComparison.OrdinalIgnoreCase) => "Error_SeatNoTune",
        _ when message.Contains("whole group", StringComparison.OrdinalIgnoreCase) => "Output_QuartetNeedsGroup",
        _ when message.Contains("clef", StringComparison.OrdinalIgnoreCase) => "Error_ReadsNotOffered",
        _ => "Error_Arrange",
    };

    public static string CoreMessage(string message, IStrings s) => s[CoreKey(message)];
}

namespace Kalli.Scribe;

/// <summary>
/// What kind of output an app makes, as the core and the engine name it: the brass target arranges for a band, the
/// fretted one writes tab. Each app makes one; the engine's profiles and jobs each belong to one.
/// </summary>
/// <param name="Id">The target's id as the engine gives it for a profile and a job (<c>ProfileInfo.Target</c>, <c>Job.Target</c>).</param>
/// <param name="CoreId">The same target as the core's C interface takes it (<c>SC_TARGET_*</c>).</param>
public sealed record Target(string Id, int CoreId)
{
    public static readonly Target Brass = new("brass", 0);
    public static readonly Target Fretted = new("fretted", 1);

    /// <summary>A profile or job of this target: the engine said so. One without a target, or of another, is not.</summary>
    public bool Makes(string? target) => target == Id;
}
